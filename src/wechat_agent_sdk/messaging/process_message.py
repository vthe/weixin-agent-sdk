"""Process inbound Weixin messages: slash commands, media download, agent call, reply send."""

import os
import time
from typing import Any, Dict, List, Optional

from wechat_agent_sdk.agent.interface import Agent, ChatRequest
from wechat_agent_sdk.api.api import send_typing
from wechat_agent_sdk.api.types import MessageItemType, TypingStatus
from wechat_agent_sdk.cdn.upload import download_remote_image_to_temp
from wechat_agent_sdk.media.media_download import download_media_from_item
from wechat_agent_sdk.messaging.inbound import set_context_token, weixin_message_to_msg_context
from wechat_agent_sdk.messaging.error_notice import send_weixin_error_notice
from wechat_agent_sdk.messaging.send_media import send_weixin_media_file
from wechat_agent_sdk.messaging.send import markdown_to_plain_text, send_message_weixin
from wechat_agent_sdk.messaging.slash_commands import handle_slash_command
from wechat_agent_sdk.util.logger import logger


MEDIA_TEMP_DIR = "/tmp/weixin-agent/media"


def _extract_text_body(item_list: Optional[List[Dict[str, Any]]]) -> str:
    """Extract raw text from item_list."""
    if not item_list:
        return ""
    for item in item_list:
        if item.get("type") == MessageItemType["TEXT"]:
            text_item = item.get("text_item") or {}
            text = text_item.get("text")
            if text is not None:
                return str(text)
    return ""


def _find_media_item(item_list: Optional[List[Dict[str, Any]]]) -> Optional[Dict[str, Any]]:
    """Find the first downloadable media item from a message."""
    if not item_list:
        return None

    direct = None
    for item in item_list:
        if item.get("type") == MessageItemType["IMAGE"] and item.get("image_item", {}).get("media", {}).get("encrypt_query_param"):
            direct = item
            break
    if direct:
        return direct

    for item in item_list:
        if item.get("type") == MessageItemType["VIDEO"] and item.get("video_item", {}).get("media", {}).get("encrypt_query_param"):
            direct = item
            break
    if direct:
        return direct

    for item in item_list:
        if item.get("type") == MessageItemType["FILE"] and item.get("file_item", {}).get("media", {}).get("encrypt_query_param"):
            direct = item
            break
    if direct:
        return direct

    for item in item_list:
        if (item.get("type") == MessageItemType["VOICE"] and
            item.get("voice_item", {}).get("media", {}).get("encrypt_query_param") and
            not item.get("voice_item", {}).get("text")):
            direct = item
            break
    if direct:
        return direct

    for item in item_list:
        if (item.get("type") == MessageItemType["TEXT"] and
            item.get("ref_msg", {}).get("message_item")):
            ref_item = item["ref_msg"]["message_item"]
            ref_type = ref_item.get("type")
            if ref_type in (MessageItemType["IMAGE"], MessageItemType["VIDEO"],
                           MessageItemType["FILE"], MessageItemType["VOICE"]):
                return item["ref_msg"]

    return None


class ProcessMessageDeps:
    account_id: str
    agent: Agent
    base_url: str
    cdn_base_url: str
    token: Optional[str]
    typing_ticket: Optional[str]
    log: callable
    err_log: callable


async def _save_media_buffer(
    buffer: bytes,
    content_type: Optional[str] = None,
    subdir: Optional[str] = None,
    max_bytes: int = 100 * 1024 * 1024,
    original_filename: Optional[str] = None,
) -> Dict[str, str]:
    """Save a buffer to a temporary file."""
    directory = os.path.join(MEDIA_TEMP_DIR, subdir or "")
    os.makedirs(directory, exist_ok=True)

    if original_filename:
        _, ext = os.path.splitext(original_filename)
        ext = ext if ext else ".bin"
    elif content_type:
        from wechat_agent_sdk.media.mime import get_extension_from_mime
        ext = get_extension_from_mime(content_type)
    else:
        ext = ".bin"

    name = f"{int(time.time() * 1000)}-{os.urandom(4).hex()}{ext}"
    file_path = os.path.join(directory, name)
    with open(file_path, "wb") as f:
        f.write(buffer)

    return {"path": file_path}


async def process_one_message(
    full: Dict[str, Any],
    deps: ProcessMessageDeps,
) -> None:
    """Process a single inbound message."""
    received_at = int(time.time() * 1000)
    text_body = _extract_text_body(full.get("item_list"))
    conversation_id = full.get("from_user_id", "")

    if text_body.startswith("/"):
        slash_result = await handle_slash_command(
            content=text_body,
            to=conversation_id,
            context_token=full.get("context_token"),
            base_url=deps.base_url,
            token=deps.token,
            account_id=deps.account_id,
            log=deps.log,
            err_log=deps.err_log,
            received_at=received_at,
            event_timestamp=full.get("create_time_ms"),
            on_clear=lambda: deps.agent.clear_session(conversation_id) if hasattr(deps.agent, "clear_session") and callable(deps.agent.clear_session) else None,
        )
        if slash_result.handled:
            return

    context_token = full.get("context_token")
    if context_token:
        set_context_token(deps.account_id, full.get("from_user_id", ""), context_token)

    media: Optional[ChatRequest] = None
    media_item = _find_media_item(full.get("item_list"))
    if media_item:
        try:
            downloaded = await download_media_from_item(
                media_item,
                deps.cdn_base_url,
                label="inbound",
            )
            if downloaded.decrypted_pic_path:
                media = ChatRequest(
                    conversation_id=conversation_id,
                    text="",
                    media=deps.agent.__class__.__annotations__.get("media") if hasattr(deps.agent, "__class__") else None,
                )
                media.type = "image"
                media.filePath = downloaded.decrypted_pic_path
                media.mimeType = "image/*"
            elif downloaded.decrypted_video_path:
                media = ChatRequest(
                    conversation_id=conversation_id,
                    text="",
                    media=deps.agent.__class__.__annotations__.get("media") if hasattr(deps.agent, "__class__") else None,
                )
                media.type = "video"
                media.filePath = downloaded.decrypted_video_path
                media.mimeType = "video/mp4"
            elif downloaded.decrypted_file_path:
                media = ChatRequest(
                    conversation_id=conversation_id,
                    text="",
                )
                media.media.type = "file"
                media.media.filePath = downloaded.decrypted_file_path
                media.media.mimeType = downloaded.file_media_type or "application/octet-stream"
            elif downloaded.decrypted_voice_path:
                media = ChatRequest(
                    conversation_id=conversation_id,
                    text="",
                )
                media.media.type = "audio"
                media.media.filePath = downloaded.decrypted_voice_path
                media.media.mimeType = downloaded.voice_media_type or "audio/wav"
        except Exception as e:
            logger.error(f"media download failed: {e}")

    from wechat_agent_sdk.messaging.inbound import _body_from_item_list
    body_text = _body_from_item_list(full.get("item_list"))

    request = ChatRequest(
        conversationId=conversation_id,
        text=body_text,
    )

    to = full.get("from_user_id", "")

    typing_timer: Optional[object] = None

    async def start_typing() -> None:
        if deps.typing_ticket:
            try:
                await send_typing(
                    base_url=deps.base_url,
                    token=deps.token,
                    ilink_user_id=to,
                    typing_ticket=deps.typing_ticket,
                    status=TypingStatus["TYPING"],
                )
            except Exception:
                pass

    if deps.typing_ticket:
        await start_typing()

    try:
        response = await deps.agent.chat(request)

        if response.media:
            media_url = response.media.url
            file_path: str

            if media_url.startswith("http://") or media_url.startswith("https://"):
                file_path = await download_remote_image_to_temp(
                    media_url,
                    os.path.join(MEDIA_TEMP_DIR, "outbound"),
                )
            else:
                file_path = media_url if os.path.isabs(media_url) else os.path.abspath(media_url)

            await send_weixin_media_file(
                file_path=file_path,
                to=to,
                text=markdown_to_plain_text(response.text) if response.text else "",
                base_url=deps.base_url,
                token=deps.token,
                context_token=context_token,
                cdn_base_url=deps.cdn_base_url,
            )
        elif response.text:
            await send_message_weixin(
                to=to,
                text=markdown_to_plain_text(response.text),
                base_url=deps.base_url,
                token=deps.token,
                context_token=context_token,
            )
    except Exception as e:
        logger.error(f"processOneMessage: agent or send failed: {e}")
        await send_weixin_error_notice(
            to=to,
            message=f"⚠️ 处理消息失败：{e}",
            base_url=deps.base_url,
            token=deps.token,
            context_token=context_token,
            err_log=deps.err_log,
        )
    finally:
        if deps.typing_ticket:
            try:
                await send_typing(
                    base_url=deps.base_url,
                    token=deps.token,
                    ilink_user_id=to,
                    typing_ticket=deps.typing_ticket,
                    status=TypingStatus["CANCEL"],
                )
            except Exception:
                pass
