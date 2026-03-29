"""Weixin QR code login flow."""

import json
import time
import urllib.request
import urllib.error
import uuid
from typing import Any, Dict, Optional

from wechat_agent_sdk.auth.accounts import load_config_route_tag
from wechat_agent_sdk.util.logger import logger
from wechat_agent_sdk.util.redact import redact_token


DEFAULT_ILINK_BOT_TYPE = "3"
ACTIVE_LOGIN_TTL_MS = 5 * 60 * 1000
QR_LONG_POLL_TIMEOUT_MS = 35_000

_active_logins: Dict[str, Dict[str, Any]] = {}


def _is_login_fresh(login: Dict[str, Any]) -> bool:
    return (time.time() * 1000) - login["startedAt"] < ACTIVE_LOGIN_TTL_MS


def _purge_expired_logins() -> None:
    now = time.time() * 1000
    expired = [k for k, v in _active_logins.items() if now - v["startedAt"] >= ACTIVE_LOGIN_TTL_MS]
    for k in expired:
        del _active_logins[k]


async def _fetch_qr_code(api_base_url: str, bot_type: str) -> Dict[str, Any]:
    base = api_base_url if api_base_url.endswith("/") else f"{api_base_url}/"
    url = f"{base}ilink/bot/get_bot_qrcode?bot_type={urllib.parse.quote(bot_type)}"
    logger.info(f"Fetching QR code from: {url}")

    headers = {}
    route_tag = load_config_route_tag()
    if route_tag:
        headers["SKRouteTag"] = route_tag

    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status < 200 or resp.status >= 300:
                body = resp.read().decode("utf-8", errors="replace")
                logger.error(f"QR code fetch failed: {resp.status} {resp.reason} body={body}")
                raise Exception(f"Failed to fetch QR code: {resp.status} {resp.reason}")
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        logger.error(f"QR code fetch failed: {e.code} {e.reason} body={body}")
        raise


async def _poll_qr_status(api_base_url: str, qrcode: str) -> Dict[str, Any]:
    base = api_base_url if api_base_url.endswith("/") else f"{api_base_url}/"
    url = f"{base}ilink/bot/get_qrcode_status?qrcode={urllib.parse.quote(qrcode)}"
    logger.debug(f"Long-poll QR status from: {url}")

    headers = {
        "iLink-App-ClientVersion": "1",
    }
    route_tag = load_config_route_tag()
    if route_tag:
        headers["SKRouteTag"] = route_tag

    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=QR_LONG_POLL_TIMEOUT_MS / 1000) as resp:
            logger.debug(f"pollQRStatus: HTTP {resp.status}, reading body...")
            raw_text = resp.read().decode("utf-8")
            logger.debug(f"pollQRStatus: body={raw_text[:200]}")
            if resp.status < 200 or resp.status >= 300:
                logger.error(f"QR status poll failed: {resp.status} {resp.reason} body={raw_text}")
                raise Exception(f"Failed to poll QR status: {resp.status} {resp.reason}")
            return json.loads(raw_text)
    except Exception as e:
        if "timed out" in str(e).lower():
            logger.debug(f"pollQRStatus: client-side timeout after {QR_LONG_POLL_TIMEOUT_MS}ms, returning wait")
            return {"status": "wait"}
        raise


class WeixinQrStartResult:
    def __init__(
        self,
        qrcode_url: Optional[str] = None,
        message: str = "",
        session_key: str = "",
    ):
        self.qrcodeUrl = qrcode_url
        self.message = message
        self.sessionKey = session_key


class WeixinQrWaitResult:
    def __init__(
        self,
        connected: bool = False,
        bot_token: Optional[str] = None,
        account_id: Optional[str] = None,
        base_url: Optional[str] = None,
        user_id: Optional[str] = None,
        message: str = "",
    ):
        self.connected = connected
        self.botToken = bot_token
        self.accountId = account_id
        self.baseUrl = base_url
        self.userId = user_id
        self.message = message


async def start_weixin_login_with_qr(
    api_base_url: str,
    bot_type: Optional[str] = None,
    timeout_ms: Optional[int] = None,
    force: bool = False,
    account_id: Optional[str] = None,
) -> WeixinQrStartResult:
    session_key = account_id or str(uuid.uuid4())
    _purge_expired_logins()

    existing = _active_logins.get(session_key)
    if not force and existing and _is_login_fresh(existing) and existing.get("qrcodeUrl"):
        return WeixinQrStartResult(
            qrcode_url=existing["qrcodeUrl"],
            message="二维码已就绪，请使用微信扫描。",
            session_key=session_key,
        )

    try:
        bot_type = bot_type or DEFAULT_ILINK_BOT_TYPE
        logger.info(f"Starting Weixin login with bot_type={bot_type}")

        if not api_base_url:
            return WeixinQrStartResult(
                message="No baseUrl configured. Add channels.openclaw-weixin.baseUrl to your config before logging in.",
                session_key=session_key,
            )

        qr_response = await _fetch_qr_code(api_base_url, bot_type)
        logger.info(
            f"QR code received, qrcode={redact_token(qr_response.get('qrcode'))} "
            f"imgContentLen={len(qr_response.get('qrcode_img_content') or '')}"
        )
        logger.info(f"二维码链接: {qr_response.get('qrcode_img_content')}")

        login_entry: Dict[str, Any] = {
            "sessionKey": session_key,
            "id": str(uuid.uuid4()),
            "qrcode": qr_response.get("qrcode", ""),
            "qrcodeUrl": qr_response.get("qrcode_img_content", ""),
            "startedAt": time.time() * 1000,
        }

        _active_logins[session_key] = login_entry

        return WeixinQrStartResult(
            qrcode_url=qr_response.get("qrcode_img_content"),
            message="使用微信扫描以下二维码，以完成连接。",
            session_key=session_key,
        )
    except Exception as e:
        logger.error(f"Failed to start Weixin login: {e}")
        return WeixinQrStartResult(
            message=f"Failed to start login: {e}",
            session_key=session_key,
        )


MAX_QR_REFRESH_COUNT = 3


async def wait_for_weixin_login(
    session_key: str,
    api_base_url: str,
    timeout_ms: Optional[int] = None,
    verbose: bool = False,
    bot_type: Optional[str] = None,
) -> WeixinQrWaitResult:
    global _active_logins

    active_login = _active_logins.get(session_key)

    if not active_login:
        logger.warn(f"waitForWeixinLogin: no active login sessionKey={session_key}")
        return WeixinQrWaitResult(connected=False, message="当前没有进行中的登录，请先发起登录。")

    if not _is_login_fresh(active_login):
        logger.warn(f"waitForWeixinLogin: login QR expired sessionKey={session_key}")
        if session_key in _active_logins:
            del _active_logins[session_key]
        return WeixinQrWaitResult(connected=False, message="二维码已过期，请重新生成。")

    timeout_ms = max(timeout_ms or 480000, 1000)
    deadline = time.time() * 1000 + timeout_ms
    scanned_printed = False
    qr_refresh_count = 1

    logger.info("Starting to poll QR code status...")

    while time.time() * 1000 < deadline:
        try:
            status_response = await _poll_qr_status(api_base_url, active_login["qrcode"])
            logger.debug(
                f"pollQRStatus: status={status_response.get('status')} "
                f"hasBotToken={bool(status_response.get('bot_token'))} "
                f"hasBotId={bool(status_response.get('ilink_bot_id'))}"
            )
            active_login["status"] = status_response.get("status")

            status = status_response.get("status")

            if status == "wait":
                if verbose:
                    print(".", end="", flush=True)
            elif status == "scaned":
                if not scanned_printed:
                    print("\n👀 已扫码，在微信继续操作...")
                    scanned_printed = True
            elif status == "expired":
                qr_refresh_count += 1
                if qr_refresh_count > MAX_QR_REFRESH_COUNT:
                    logger.warn(
                        f"waitForWeixinLogin: QR expired {MAX_QR_REFRESH_COUNT} times, giving up sessionKey={session_key}"
                    )
                    if session_key in _active_logins:
                        del _active_logins[session_key]
                    return WeixinQrWaitResult(
                        connected=False,
                        message="登录超时：二维码多次过期，请重新开始登录流程。",
                    )

                print(f"\n⏳ 二维码已过期，正在刷新...({qr_refresh_count}/{MAX_QR_REFRESH_COUNT})")
                logger.info(
                    f"waitForWeixinLogin: QR expired, refreshing ({qr_refresh_count}/{MAX_QR_REFRESH_COUNT})"
                )

                try:
                    bot_type = bot_type or DEFAULT_ILINK_BOT_TYPE
                    qr_response = await _fetch_qr_code(api_base_url, bot_type)
                    active_login["qrcode"] = qr_response.get("qrcode", "")
                    active_login["qrcodeUrl"] = qr_response.get("qrcode_img_content", "")
                    active_login["startedAt"] = time.time() * 1000
                    scanned_printed = False
                    logger.info(
                        f"waitForWeixinLogin: new QR code obtained qrcode={redact_token(qr_response.get('qrcode'))}"
                    )
                    print("🔄 新二维码已生成，请重新扫描\n")
                    try:
                        import qrcode
                        img = qrcode.make(qr_response.get("qrcode_img_content", ""))
                        img.show()
                    except Exception:
                        print(f"如果二维码未能成功展示，请用浏览器打开以下链接扫码：")
                        print(qr_response.get("qrcode_img_content", ""))
                except Exception as refresh_err:
                    logger.error(f"waitForWeixinLogin: failed to refresh QR code: {refresh_err}")
                    if session_key in _active_logins:
                        del _active_logins[session_key]
                    return WeixinQrWaitResult(
                        connected=False,
                        message=f"刷新二维码失败: {refresh_err}",
                    )
            elif status == "confirmed":
                if not status_response.get("ilink_bot_id"):
                    if session_key in _active_logins:
                        del _active_logins[session_key]
                    logger.error("Login confirmed but ilink_bot_id missing from response")
                    return WeixinQrWaitResult(
                        connected=False,
                        message="登录失败：服务器未返回 ilink_bot_id。",
                    )

                active_login["botToken"] = status_response.get("bot_token")
                if session_key in _active_logins:
                    del _active_logins[session_key]

                logger.info(
                    f"✅ Login confirmed! ilink_bot_id={status_response.get('ilink_bot_id')} "
                    f"ilink_user_id={redact_token(status_response.get('ilink_user_id'))}"
                )

                return WeixinQrWaitResult(
                    connected=True,
                    bot_token=status_response.get("bot_token"),
                    account_id=status_response.get("ilink_bot_id"),
                    base_url=status_response.get("baseurl"),
                    user_id=status_response.get("ilink_user_id"),
                    message="✅ 与微信连接成功！",
                )

        except Exception as e:
            logger.error(f"Error polling QR status: {e}")
            if session_key in _active_logins:
                del _active_logins[session_key]
            return WeixinQrWaitResult(connected=False, message=f"Login failed: {e}")

        await _sleep(1)

    logger.warn(
        f"waitForWeixinLogin: timed out waiting for QR scan sessionKey={session_key} timeoutMs={timeout_ms}"
    )
    if session_key in _active_logins:
        del _active_logins[session_key]
    return WeixinQrWaitResult(connected=False, message="登录超时，请重试。")


async def _sleep(seconds: float) -> None:
    import asyncio
    await asyncio.sleep(seconds)
