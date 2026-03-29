"""Send error notices to Weixin."""

from wechat_agent_sdk.util.logger import logger
from wechat_agent_sdk.messaging.send import send_message_weixin


async def send_weixin_error_notice(
    to: str,
    message: str,
    base_url: str,
    token: str | None,
    context_token: str | None,
    err_log: callable,
) -> None:
    """Send a plain-text error notice back to the user."""
    if not context_token:
        logger.warn(f"sendWeixinErrorNotice: no contextToken for to={to}, cannot notify user")
        return

    try:
        await send_message_weixin(
            to=to,
            text=message,
            base_url=base_url,
            token=token,
            context_token=context_token,
        )
        logger.debug(f"sendWeixinErrorNotice: sent to={to}")
    except Exception as e:
        err_log(f"[weixin] sendWeixinErrorNotice failed to={to}: {e}")
