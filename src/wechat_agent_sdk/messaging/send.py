"""Send text messages to Weixin."""

import re
from typing import Any, Dict, Optional

from wechat_agent_sdk.api.api import send_message as api_send_message
from wechat_agent_sdk.util.logger import logger
from wechat_agent_sdk.util.random import generate_id
from wechat_agent_sdk.api.types import MessageItemType, MessageState, MessageType


def generate_client_id() -> str:
    return generate_id("openclaw-weixin")


def markdown_to_plain_text(text: str) -> str:
    """Convert markdown-formatted model reply to plain text for Weixin delivery."""
    result = text

    result = re.sub(r"```[^\n]*\n?([\s\S]*?)```", lambda m: m.group(1).strip(), result)

    result = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", result)

    result = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", result)

    result = re.sub(r"^\|[\s:|-]+\|$", "", result, flags=re.MULTILINE)
    result = re.sub(r"^\|(.+)\|$", lambda m: "  ".join(c.strip() for c in m.group(1).split("|")), result, flags=re.MULTILINE)

    result = re.sub(r"\*\*(.+?)\*\*", r"\1", result)
    result = re.sub(r"\*(.+?)\*", r"\1", result)
    result = re.sub(r"__(.+?)__", r"\1", result)
    result = re.sub(r"_(.+?)_", r"\1", result)
    result = re.sub(r"~~(.+?)~~", r"\1", result)
    result = re.sub(r"`(.+?)`", r"\1", result)

    return result


def _build_text_message_req(
    to: str,
    text: str,
    context_token: Optional[str],
    client_id: str,
) -> Dict[str, Any]:
    """Build a SendMessageReq containing a single text message."""
    item_list = [{"type": MessageItemType["TEXT"], "text_item": {"text": text}}] if text else []
    return {
        "msg": {
            "from_user_id": "",
            "to_user_id": to,
            "client_id": client_id,
            "message_type": MessageType["BOT"],
            "message_state": MessageState["FINISH"],
            "item_list": item_list if item_list else None,
            "context_token": context_token,
        }
    }


async def send_message_weixin(
    to: str,
    text: str,
    base_url: str,
    token: Optional[str],
    context_token: Optional[str],
) -> str:
    """Send a plain text message downstream."""
    if not context_token:
        logger.error(f"sendMessageWeixin: contextToken missing, refusing to send to={to}")
        raise ValueError("sendMessageWeixin: contextToken is required")

    client_id = generate_client_id()
    req = _build_text_message_req(to, text, context_token, client_id)

    try:
        await api_send_message(base_url, token, req)
    except Exception as e:
        logger.error(f"sendMessageWeixin: failed to={to} clientId={client_id} err={e}")
        raise

    return client_id


async def _send_media_items(
    to: str,
    text: str,
    media_item: Dict[str, Any],
    base_url: str,
    token: Optional[str],
    context_token: Optional[str],
    label: str,
) -> str:
    """Send one or more MessageItems downstream."""
    items = []
    if text:
        items.append({"type": MessageItemType["TEXT"], "text_item": {"text": text}})
    items.append(media_item)

    last_client_id = ""
    for item in items:
        last_client_id = generate_client_id()
        req = {
            "msg": {
                "from_user_id": "",
                "to_user_id": to,
                "client_id": last_client_id,
                "message_type": MessageType["BOT"],
                "message_state": MessageState["FINISH"],
                "item_list": [item],
                "context_token": context_token,
            }
        }
        try:
            await api_send_message(base_url, token, req)
        except Exception as e:
            logger.error(f"{label}: failed to={to} clientId={last_client_id} err={e}")
            raise

    logger.debug(f"{label}: success to={to} clientId={last_client_id}")
    return last_client_id


async def send_image_message_weixin(
    to: str,
    text: str,
    uploaded: Dict[str, Any],
    base_url: str,
    token: Optional[str],
    context_token: Optional[str],
) -> str:
    """Send an image message downstream."""
    if not context_token:
        logger.error(f"sendImageMessageWeixin: contextToken missing, refusing to send to={to}")
        raise ValueError("sendImageMessageWeixin: contextToken is required")

    import base64
    image_item = {
        "type": MessageItemType["IMAGE"],
        "image_item": {
            "media": {
                "encrypt_query_param": uploaded.get("downloadEncryptedQueryParam"),
                "aes_key": base64.b64encode(bytes.fromhex(uploaded.get("aeskey", ""))).decode(),
                "encrypt_type": 1,
            },
            "mid_size": uploaded.get("fileSizeCiphertext"),
        },
    }

    return await _send_media_items(
        to, text, image_item, base_url, token, context_token, "sendImageMessageWeixin"
    )


async def send_video_message_weixin(
    to: str,
    text: str,
    uploaded: Dict[str, Any],
    base_url: str,
    token: Optional[str],
    context_token: Optional[str],
) -> str:
    """Send a video message downstream."""
    if not context_token:
        logger.error(f"sendVideoMessageWeixin: contextToken missing, refusing to send to={to}")
        raise ValueError("sendVideoMessageWeixin: contextToken is required")

    import base64
    video_item = {
        "type": MessageItemType["VIDEO"],
        "video_item": {
            "media": {
                "encrypt_query_param": uploaded.get("downloadEncryptedQueryParam"),
                "aes_key": base64.b64encode(bytes.fromhex(uploaded.get("aeskey", ""))).decode(),
                "encrypt_type": 1,
            },
            "video_size": uploaded.get("fileSizeCiphertext"),
        },
    }

    return await _send_media_items(
        to, text, video_item, base_url, token, context_token, "sendVideoMessageWeixin"
    )


async def send_file_message_weixin(
    to: str,
    text: str,
    file_name: str,
    uploaded: Dict[str, Any],
    base_url: str,
    token: Optional[str],
    context_token: Optional[str],
) -> str:
    """Send a file attachment downstream."""
    if not context_token:
        logger.error(f"sendFileMessageWeixin: contextToken missing, refusing to send to={to}")
        raise ValueError("sendFileMessageWeixin: contextToken is required")

    import base64
    file_item = {
        "type": MessageItemType["FILE"],
        "file_item": {
            "media": {
                "encrypt_query_param": uploaded.get("downloadEncryptedQueryParam"),
                "aes_key": base64.b64encode(bytes.fromhex(uploaded.get("aeskey", ""))).decode(),
                "encrypt_type": 1,
            },
            "file_name": file_name,
            "len": str(uploaded.get("fileSize")),
        },
    }

    return await _send_media_items(
        to, text, file_item, base_url, token, context_token, "sendFileMessageWeixin"
    )
