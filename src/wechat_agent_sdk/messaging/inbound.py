"""Inbound message handling: context token store and message parsing."""

from typing import Any, Dict, List, Optional

from wechat_agent_sdk.util.logger import logger
from wechat_agent_sdk.util.random import generate_id
from wechat_agent_sdk.api.types import MessageItemType


_context_token_store: Dict[str, str] = {}


def _context_token_key(account_id: str, user_id: str) -> str:
    return f"{account_id}:{user_id}"


def set_context_token(account_id: str, user_id: str, token: str) -> None:
    """Store a context token for a given account+user pair."""
    key = _context_token_key(account_id, user_id)
    logger.debug(f"setContextToken: key={key}")
    _context_token_store[key] = token


def get_context_token(account_id: str, user_id: str) -> Optional[str]:
    """Retrieve the cached context token for a given account+user pair."""
    key = _context_token_key(account_id, user_id)
    val = _context_token_store.get(key)
    logger.debug(f"getContextToken: key={key} found={val is not None} storeSize={len(_context_token_store)}")
    return val


def _generate_message_sid() -> str:
    return generate_id("openclaw-weixin")


class WeixinMsgContext:
    Body: str = ""
    From: str = ""
    To: str = ""
    AccountId: str = ""
    OriginatingChannel: str = "openclaw-weixin"
    OriginatingTo: str = ""
    MessageSid: str = ""
    Timestamp: Optional[int] = None
    Provider: str = "openclaw-weixin"
    ChatType: str = "direct"
    SessionKey: Optional[str] = None
    context_token: Optional[str] = None
    MediaUrl: Optional[str] = None
    MediaPath: Optional[str] = None
    MediaType: Optional[str] = None
    CommandBody: Optional[str] = None
    CommandAuthorized: Optional[bool] = None


def _is_media_item(item: Dict[str, Any]) -> bool:
    item_type = item.get("type")
    return item_type in (
        MessageItemType["IMAGE"],
        MessageItemType["VIDEO"],
        MessageItemType["FILE"],
        MessageItemType["VOICE"],
    )


def _body_from_item_list(item_list: Optional[List[Dict[str, Any]]]) -> str:
    """Extract text body from item_list."""
    if not item_list:
        return ""

    for item in item_list:
        if item.get("type") == MessageItemType["TEXT"]:
            text_item = item.get("text_item", {}) or {}
            text = text_item.get("text")
            if text is not None:
                text = str(text)
                ref = item.get("ref_msg")
                if not ref:
                    return text
                ref_item = ref.get("message_item")
                if ref_item and _is_media_item(ref_item):
                    return text
                parts = []
                if ref.get("title"):
                    parts.append(ref["title"])
                if ref_item:
                    ref_body = _body_from_item_list([ref_item])
                    if ref_body:
                        parts.append(ref_body)
                if not parts:
                    return text
                return f"[引用: {' | '.join(parts)}]\n{text}"

        if item.get("type") == MessageItemType["VOICE"]:
            voice_item = item.get("voice_item", {}) or {}
            if voice_item.get("text"):
                return str(voice_item["text"])

    return ""


class WeixinInboundMediaOpts:
    decrypted_pic_path: Optional[str] = None
    decrypted_voice_path: Optional[str] = None
    voice_media_type: Optional[str] = None
    decrypted_file_path: Optional[str] = None
    file_media_type: Optional[str] = None
    decrypted_video_path: Optional[str] = None


def weixin_message_to_msg_context(
    msg: Dict[str, Any],
    account_id: str,
    opts: Optional[WeixinInboundMediaOpts] = None,
) -> WeixinMsgContext:
    """Convert a WeixinMessage from getUpdates to the inbound MsgContext."""
    ctx = WeixinMsgContext()
    from_user_id = msg.get("from_user_id", "")

    ctx.From = from_user_id
    ctx.To = from_user_id
    ctx.AccountId = account_id
    ctx.OriginatingChannel = "openclaw-weixin"
    ctx.OriginatingTo = from_user_id
    ctx.MessageSid = _generate_message_sid()
    ctx.Timestamp = msg.get("create_time_ms")
    ctx.Provider = "openclaw-weixin"
    ctx.ChatType = "direct"
    ctx.Body = _body_from_item_list(msg.get("item_list"))

    if msg.get("context_token"):
        ctx.context_token = msg["context_token"]

    if opts:
        if opts.decrypted_pic_path:
            ctx.MediaPath = opts.decrypted_pic_path
            ctx.MediaType = "image/*"
        elif opts.decrypted_video_path:
            ctx.MediaPath = opts.decrypted_video_path
            ctx.MediaType = "video/mp4"
        elif opts.decrypted_file_path:
            ctx.MediaPath = opts.decrypted_file_path
            ctx.MediaType = opts.file_media_type or "application/octet-stream"
        elif opts.decrypted_voice_path:
            ctx.MediaPath = opts.decrypted_voice_path
            ctx.MediaType = opts.voice_media_type or "audio/wav"

    return ctx


def get_context_token_from_msg_context(ctx: WeixinMsgContext) -> Optional[str]:
    """Extract the context_token from an inbound WeixinMsgContext."""
    return ctx.context_token
