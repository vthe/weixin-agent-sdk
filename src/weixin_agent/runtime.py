from __future__ import annotations

import asyncio
import base64
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

from weixin_agent.api import SESSION_EXPIRED_ERRCODE, WeixinApiClient
from weixin_agent.media import (
    UPLOAD_MEDIA_FILE,
    UPLOAD_MEDIA_IMAGE,
    UPLOAD_MEDIA_VIDEO,
    download_media_from_item,
    download_remote_media_to_temp,
    get_mime_from_filename,
    upload_media_to_weixin,
)
from weixin_agent.models import Agent, ChatRequest, ChatResponse, IncomingMedia
from weixin_agent.session import remember_context_token
from weixin_agent.storage import (
    ResolvedWeixinAccount,
    load_get_updates_buf,
    save_get_updates_buf,
)

MESSAGE_ITEM_TEXT = 1
MESSAGE_ITEM_IMAGE = 2
MESSAGE_ITEM_VOICE = 3
MESSAGE_ITEM_FILE = 4
MESSAGE_ITEM_VIDEO = 5
MESSAGE_TYPE_BOT = 2
MESSAGE_STATE_FINISH = 2
TYPING_STATUS_TYPING = 1
TYPING_STATUS_CANCEL = 2

_DEBUG_ACCOUNTS: set[str] = set()


def generate_client_id() -> str:
    return f"weixin-agent-{uuid4().hex}"


def markdown_to_plain_text(text: str) -> str:
    result = re.sub(r"```[^\n]*\n?([\s\S]*?)```", lambda m: m.group(1).strip(), text)
    result = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", result)
    result = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", result)
    result = re.sub(r"^\|[\s:|-]+\|$", "", result, flags=re.MULTILINE)
    result = re.sub(
        r"^\|(.+)\|$",
        lambda m: "  ".join(part.strip() for part in m.group(1).split("|")),
        result,
        flags=re.MULTILINE,
    )
    for pattern in (
        r"\*\*(.+?)\*\*",
        r"\*(.+?)\*",
        r"__(.+?)__",
        r"_(.+?)_",
        r"~~(.+?)~~",
        r"`(.+?)`",
    ):
        result = re.sub(pattern, r"\1", result)
    return result


def is_media_item(item: dict[str, Any]) -> bool:
    return item.get("type") in {
        MESSAGE_ITEM_IMAGE,
        MESSAGE_ITEM_VOICE,
        MESSAGE_ITEM_FILE,
        MESSAGE_ITEM_VIDEO,
    }


def body_from_item_list(item_list: list[dict[str, Any]] | None) -> str:
    if not item_list:
        return ""
    for item in item_list:
        item_type = item.get("type")
        if item_type == MESSAGE_ITEM_TEXT:
            text_item = item.get("text_item")
            if not isinstance(text_item, dict):
                continue
            text = text_item.get("text")
            if not isinstance(text, str):
                continue
            ref = item.get("ref_msg")
            if not isinstance(ref, dict):
                return text
            ref_message_item = ref.get("message_item")
            if isinstance(ref_message_item, dict) and is_media_item(ref_message_item):
                return text
            parts: list[str] = []
            title = ref.get("title")
            if isinstance(title, str) and title:
                parts.append(title)
            if isinstance(ref_message_item, dict):
                quoted = body_from_item_list([ref_message_item])
                if quoted:
                    parts.append(quoted)
            return f"[Quoted: {' | '.join(parts)}]\n{text}" if parts else text
        if item_type == MESSAGE_ITEM_VOICE:
            voice_item = item.get("voice_item")
            if isinstance(voice_item, dict):
                text = voice_item.get("text")
                if isinstance(text, str) and text:
                    return text
    return ""


def extract_text_body(item_list: list[dict[str, Any]] | None) -> str:
    if not item_list:
        return ""
    for item in item_list:
        if item.get("type") != MESSAGE_ITEM_TEXT:
            continue
        text_item = item.get("text_item")
        if isinstance(text_item, dict):
            text = text_item.get("text")
            if isinstance(text, str):
                return text
    return ""


def find_media_item(item_list: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    if not item_list:
        return None
    for desired_type in (MESSAGE_ITEM_IMAGE, MESSAGE_ITEM_VIDEO, MESSAGE_ITEM_FILE):
        for item in item_list:
            if item.get("type") == desired_type:
                return item
    for item in item_list:
        if item.get("type") == MESSAGE_ITEM_VOICE:
            voice_item = item.get("voice_item")
            if isinstance(voice_item, dict) and not voice_item.get("text"):
                return item
    for item in item_list:
        if item.get("type") != MESSAGE_ITEM_TEXT:
            continue
        ref = item.get("ref_msg")
        if not isinstance(ref, dict):
            continue
        ref_message_item = ref.get("message_item")
        if isinstance(ref_message_item, dict) and is_media_item(ref_message_item):
            return ref_message_item
    return None


async def send_text_message(
    api_client: WeixinApiClient,
    *,
    to_user_id: str,
    context_token: str,
    text: str,
    account_id: str,
) -> str:
    client_id = generate_client_id()
    await api_client.send_message(
        {
            "msg": {
                "from_user_id": "",
                "to_user_id": to_user_id,
                "client_id": client_id,
                "message_type": MESSAGE_TYPE_BOT,
                "message_state": MESSAGE_STATE_FINISH,
                "item_list": [{"type": MESSAGE_ITEM_TEXT, "text_item": {"text": text}}],
                "context_token": context_token,
            },
        },
        account_id=account_id,
    )
    return client_id


async def send_media_message(
    api_client: WeixinApiClient,
    *,
    to_user_id: str,
    context_token: str,
    text: str,
    media_url: str,
    media_file_name: str | None,
    cdn_base_url: str,
    account_id: str,
) -> str:
    if media_url.startswith(("http://", "https://")):
        file_path = await download_remote_media_to_temp(media_url, "outbound")
    else:
        file_path = Path(media_url).expanduser()
        if not file_path.is_absolute():
            file_path = Path.cwd() / file_path

    mime_type = get_mime_from_filename(file_path.name)
    if mime_type.startswith("video/"):
        uploaded = await upload_media_to_weixin(
            file_path=file_path,
            to_user_id=to_user_id,
            api_client=api_client,
            cdn_base_url=cdn_base_url,
            media_type=UPLOAD_MEDIA_VIDEO,
            account_id=account_id,
        )
        media_item = {
            "type": MESSAGE_ITEM_VIDEO,
            "video_item": {
                "media": {
                    "encrypt_query_param": uploaded.download_encrypted_query_param,
                    "aes_key": base64.b64encode(uploaded.aes_key_hex.encode()).decode(),
                    "encrypt_type": 1,
                },
                "video_size": uploaded.file_size_ciphertext,
            },
        }
    elif mime_type.startswith("image/"):
        uploaded = await upload_media_to_weixin(
            file_path=file_path,
            to_user_id=to_user_id,
            api_client=api_client,
            cdn_base_url=cdn_base_url,
            media_type=UPLOAD_MEDIA_IMAGE,
            account_id=account_id,
        )
        media_item = {
            "type": MESSAGE_ITEM_IMAGE,
            "image_item": {
                "media": {
                    "encrypt_query_param": uploaded.download_encrypted_query_param,
                    "aes_key": base64.b64encode(uploaded.aes_key_hex.encode()).decode(),
                    "encrypt_type": 1,
                },
                "mid_size": uploaded.file_size_ciphertext,
            },
        }
    else:
        uploaded = await upload_media_to_weixin(
            file_path=file_path,
            to_user_id=to_user_id,
            api_client=api_client,
            cdn_base_url=cdn_base_url,
            media_type=UPLOAD_MEDIA_FILE,
            account_id=account_id,
        )
        media_item = {
            "type": MESSAGE_ITEM_FILE,
            "file_item": {
                "media": {
                    "encrypt_query_param": uploaded.download_encrypted_query_param,
                    "aes_key": base64.b64encode(uploaded.aes_key_hex.encode()).decode(),
                    "encrypt_type": 1,
                },
                "file_name": media_file_name or file_path.name,
                "len": str(uploaded.file_size),
            },
        }

    last_client_id = ""
    items: list[dict[str, Any]] = []
    if text:
        items.append({"type": MESSAGE_ITEM_TEXT, "text_item": {"text": text}})
    items.append(media_item)
    for item in items:
        last_client_id = generate_client_id()
        await api_client.send_message(
            {
                "msg": {
                    "from_user_id": "",
                    "to_user_id": to_user_id,
                    "client_id": last_client_id,
                    "message_type": MESSAGE_TYPE_BOT,
                    "message_state": MESSAGE_STATE_FINISH,
                    "item_list": [item],
                    "context_token": context_token,
                },
            },
            account_id=account_id,
        )
    return last_client_id


async def handle_slash_command(
    api_client: WeixinApiClient,
    *,
    account: ResolvedWeixinAccount,
    text_body: str,
    to_user_id: str,
    context_token: str,
    received_at_ms: int,
) -> bool:
    if text_body.startswith("/echo "):
        reply_text = text_body.removeprefix("/echo ").strip()
        elapsed_ms = int(asyncio.get_running_loop().time() * 1000) - received_at_ms
        await send_text_message(
            api_client,
            to_user_id=to_user_id,
            context_token=context_token,
            text=f"{reply_text}\n[channel latency: {max(elapsed_ms, 0)}ms]",
            account_id=account.account_id,
        )
        return True

    if text_body == "/toggle-debug":
        if account.account_id in _DEBUG_ACCOUNTS:
            _DEBUG_ACCOUNTS.remove(account.account_id)
            enabled = False
        else:
            _DEBUG_ACCOUNTS.add(account.account_id)
            enabled = True
        await send_text_message(
            api_client,
            to_user_id=to_user_id,
            context_token=context_token,
            text=f"debug mode {'enabled' if enabled else 'disabled'}",
            account_id=account.account_id,
        )
        return True

    return False


async def maybe_send_typing(
    api_client: WeixinApiClient,
    *,
    account: ResolvedWeixinAccount,
    to_user_id: str,
    context_token: str | None,
    status: int,
) -> None:
    if not context_token:
        return
    try:
        config = await api_client.get_config(
            ilink_user_id=to_user_id,
            context_token=context_token,
            account_id=account.account_id,
        )
        typing_ticket = config.get("typing_ticket")
        if not isinstance(typing_ticket, str) or not typing_ticket:
            return
        await api_client.send_typing(
            {
                "ilink_user_id": to_user_id,
                "typing_ticket": typing_ticket,
                "status": status,
            },
            account_id=account.account_id,
        )
    except Exception:
        return


async def process_message(
    api_client: WeixinApiClient,
    *,
    account: ResolvedWeixinAccount,
    agent: Agent,
    full_message: dict[str, Any],
    log: Callable[[str], None],
) -> None:
    received_at_ms = int(asyncio.get_running_loop().time() * 1000)
    item_list = full_message.get("item_list")
    items = item_list if isinstance(item_list, list) else []
    to_user_id = full_message.get("from_user_id")
    context_token = full_message.get("context_token")
    if not isinstance(to_user_id, str) or not to_user_id:
        return
    if not isinstance(context_token, str) or not context_token:
        return

    remember_context_token(to_user_id, context_token)

    text_body = extract_text_body(items)
    if text_body.startswith("/"):
        handled = await handle_slash_command(
            api_client,
            account=account,
            text_body=text_body,
            to_user_id=to_user_id,
            context_token=context_token,
            received_at_ms=received_at_ms,
        )
        if handled:
            return

    media = None
    media_item = find_media_item(items)
    if media_item:
        downloaded = await download_media_from_item(media_item, account.cdn_base_url)
        if downloaded:
            file_path, mime_type, file_name = downloaded
            media_type = "file"
            if mime_type.startswith("image/"):
                media_type = "image"
            elif mime_type.startswith("audio/"):
                media_type = "audio"
            elif mime_type.startswith("video/"):
                media_type = "video"
            media = IncomingMedia(
                type=media_type,
                file_path=str(file_path),
                mime_type=mime_type,
                file_name=file_name,
            )

    request = ChatRequest(
        conversation_id=to_user_id,
        text=body_from_item_list(items),
        media=media,
    )

    await maybe_send_typing(
        api_client,
        account=account,
        to_user_id=to_user_id,
        context_token=context_token,
        status=TYPING_STATUS_TYPING,
    )

    try:
        response = await agent.chat(request)
        await send_response(
            api_client,
            account=account,
            to_user_id=to_user_id,
            context_token=context_token,
            response=response,
            received_at_ms=received_at_ms,
        )
    except Exception as exc:
        await send_text_message(
            api_client,
            to_user_id=to_user_id,
            context_token=context_token,
            text=f"Processing failed: {exc}",
            account_id=account.account_id,
        )
        log(f"[weixin] processing failed: {exc}")
    finally:
        await maybe_send_typing(
            api_client,
            account=account,
            to_user_id=to_user_id,
            context_token=context_token,
            status=TYPING_STATUS_CANCEL,
        )


async def send_response(
    api_client: WeixinApiClient,
    *,
    account: ResolvedWeixinAccount,
    to_user_id: str,
    context_token: str,
    response: ChatResponse,
    received_at_ms: int,
) -> None:
    debug_suffix = ""
    if account.account_id in _DEBUG_ACCOUNTS:
        elapsed_ms = int(asyncio.get_running_loop().time() * 1000) - received_at_ms
        debug_suffix = f"\n[debug latency: {max(elapsed_ms, 0)}ms]"

    text = markdown_to_plain_text(response.text or "")
    if debug_suffix:
        text = f"{text}{debug_suffix}".strip()

    if response.media:
        await send_media_message(
            api_client,
            to_user_id=to_user_id,
            context_token=context_token,
            text=text,
            media_url=response.media.url,
            media_file_name=response.media.file_name,
            cdn_base_url=account.cdn_base_url,
            account_id=account.account_id,
        )
        return

    if text:
        await send_text_message(
            api_client,
            to_user_id=to_user_id,
            context_token=context_token,
            text=text,
            account_id=account.account_id,
        )


async def monitor_weixin(
    *,
    api_client: WeixinApiClient,
    account: ResolvedWeixinAccount,
    agent: Agent,
    log: Callable[[str], None],
) -> None:
    get_updates_buf = load_get_updates_buf(account.account_id) or ""
    consecutive_failures = 0
    next_timeout = 35.0

    while True:
        try:
            response = await api_client.get_updates(
                get_updates_buf=get_updates_buf,
                timeout=next_timeout,
                account_id=account.account_id,
            )
            if (
                isinstance(response.get("longpolling_timeout_ms"), int)
                and response["longpolling_timeout_ms"] > 0
            ):
                next_timeout = response["longpolling_timeout_ms"] / 1000

            ret = response.get("ret", 0)
            errcode = response.get("errcode", 0)
            if ret or errcode:
                if ret == SESSION_EXPIRED_ERRCODE or errcode == SESSION_EXPIRED_ERRCODE:
                    log("[weixin] session expired, sleeping for 1 hour")
                    await asyncio.sleep(3600)
                    continue
                consecutive_failures += 1
                log(
                    "[weixin] getUpdates failed: "
                    f"ret={ret} errcode={errcode} errmsg={response.get('errmsg', '')}"
                )
                await asyncio.sleep(30 if consecutive_failures >= 3 else 2)
                if consecutive_failures >= 3:
                    consecutive_failures = 0
                continue

            consecutive_failures = 0
            new_buf = response.get("get_updates_buf")
            if isinstance(new_buf, str) and new_buf:
                get_updates_buf = new_buf
                save_get_updates_buf(account.account_id, new_buf)

            messages = response.get("msgs")
            if not isinstance(messages, list):
                continue
            for message in messages:
                if isinstance(message, dict):
                    await process_message(
                        api_client,
                        account=account,
                        agent=agent,
                        full_message=message,
                        log=log,
                    )
        except Exception as exc:
            consecutive_failures += 1
            log(f"[weixin] monitor error ({consecutive_failures}/3): {exc}")
            await asyncio.sleep(30 if consecutive_failures >= 3 else 2)
            if consecutive_failures >= 3:
                consecutive_failures = 0
