"""在内存中记录每个用户的 context_token，供主动推送消息使用。"""

from __future__ import annotations

_context_tokens: dict[str, str] = {}


def remember_context_token(user_id: str, context_token: str) -> None:
    """记录某用户最近一次消息的 context_token。"""
    _context_tokens[user_id] = context_token


def get_context_token(user_id: str) -> str | None:
    """获取某用户最近一次消息的 context_token，不存在时返回 None。"""
    return _context_tokens.get(user_id)