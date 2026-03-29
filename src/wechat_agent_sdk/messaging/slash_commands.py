"""Slash commands handling (/echo, /toggle-debug, /clear)."""

from typing import Any, Dict, Optional

from wechat_agent_sdk.messaging.debug_mode import is_debug_mode, toggle_debug_mode
from wechat_agent_sdk.messaging.send import send_message_weixin
from wechat_agent_sdk.util.logger import logger


class SlashCommandResult:
    handled: bool = False


async def _send_reply(
    to: str,
    text: str,
    base_url: str,
    token: Optional[str],
    context_token: Optional[str],
) -> None:
    """Send a reply message."""
    await send_message_weixin(
        to=to,
        text=text,
        base_url=base_url,
        token=token,
        context_token=context_token,
    )


async def _handle_echo(
    to: str,
    args: str,
    received_at: int,
    event_timestamp: Optional[int],
    base_url: str,
    token: Optional[str],
    context_token: Optional[str],
) -> None:
    """Handle /echo command."""
    message = args.strip()
    if message:
        await _send_reply(to, message, base_url, token, context_token)

    event_ts = event_timestamp or 0
    platform_delay = f"{received_at - event_ts}ms" if event_ts > 0 else "N/A"
    timing = "\n".join([
        "⏱ 通道耗时",
        f"├ 事件时间: {event_ts if event_ts > 0 else 'N/A'}",
        f"├ 平台→插件: {platform_delay}",
        f"└ 插件处理: {__import__('time').time() * 1000 - received_at}ms",
    ])
    await _send_reply(to, timing, base_url, token, context_token)


async def handle_slash_command(
    content: str,
    to: str,
    context_token: Optional[str],
    base_url: str,
    token: Optional[str],
    account_id: str,
    log: callable,
    err_log: callable,
    received_at: int,
    event_timestamp: Optional[int],
    on_clear: Optional[callable] = None,
) -> SlashCommandResult:
    """Handle slash commands: /echo, /toggle-debug, /clear."""
    result = SlashCommandResult()

    trimmed = content.strip()
    if not trimmed.startswith("/"):
        return result

    space_idx = trimmed.find(" ")
    command = (trimmed[:space_idx] if space_idx != -1 else trimmed).lower()
    args = trimmed[space_idx + 1:] if space_idx != -1 else ""

    logger.info(f"[weixin] Slash command: {command}, args: {args[:50]}")

    try:
        if command == "/echo":
            await _handle_echo(
                to=to,
                args=args,
                received_at=received_at,
                event_timestamp=event_timestamp,
                base_url=base_url,
                token=token,
                context_token=context_token,
            )
            result.handled = True
        elif command == "/toggle-debug":
            enabled = toggle_debug_mode(account_id)
            await _send_reply(
                to,
                "Debug 模式已开启" if enabled else "Debug 模式已关闭",
                base_url,
                token,
                context_token,
            )
            result.handled = True
        elif command == "/clear":
            if on_clear:
                on_clear()
            await _send_reply(
                to,
                "✅ 会话已清除，重新开始对话",
                base_url,
                token,
                context_token,
            )
            result.handled = True
    except Exception as e:
        logger.error(f"[weixin] Slash command error: {e}")
        try:
            await _send_reply(
                to,
                f"❌ 指令执行失败: {str(e)[:200]}",
                base_url,
                token,
                context_token,
            )
        except Exception:
            pass
        result.handled = True

    return result
