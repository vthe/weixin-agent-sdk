"""Weixin API client for JSON over HTTP."""

import base64
import hashlib
import importlib.metadata
import json
import os
import random
import urllib.request
import urllib.error
from typing import Any, Dict, Optional

from wechat_agent_sdk.auth.accounts import load_config_route_tag
from wechat_agent_sdk.util.logger import logger


DEFAULT_LONG_POLL_TIMEOUT_MS = 35_000
DEFAULT_API_TIMEOUT_MS = 15_000
DEFAULT_CONFIG_TIMEOUT_MS = 10_000


def _read_channel_version() -> str:
    try:
        return importlib.metadata.version("wechat_agent_sdk")
    except Exception:
        return "unknown"


CHANNEL_VERSION = _read_channel_version()


def build_base_info() -> Dict[str, Any]:
    return {"channel_version": CHANNEL_VERSION}


def _ensure_trailing_slash(url: str) -> str:
    return url if url.endswith("/") else f"{url}/"


def _random_wechat_uin() -> str:
    uint32_val = random.getrandbits(32)
    return base64.b64encode(str(uint32_val).encode()).decode()


def _build_headers(token: Optional[str], body: str) -> Dict[str, str]:
    headers: Dict[str, str] = {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "Content-Length": str(len(body.encode())),
        "X-WECHAT-UIN": _random_wechat_uin(),
    }
    if token and token.strip():
        headers["Authorization"] = f"Bearer {token.strip()}"
    route_tag = load_config_route_tag()
    if route_tag:
        headers["SKRouteTag"] = route_tag
    logger.debug(f"requestHeaders: {json.dumps({**headers, 'Authorization': 'Bearer ***' if 'Authorization' in headers else None})}")
    return headers


def _api_fetch(
    base_url: str,
    endpoint: str,
    body: str,
    token: Optional[str] = None,
    timeout_ms: int = DEFAULT_API_TIMEOUT_MS,
    label: str = "",
    abort_signal: Optional[Any] = None,
) -> str:
    base = _ensure_trailing_slash(base_url)
    url = f"{base}{endpoint}"
    hdrs = _build_headers(token, body)
    logger.debug(f"POST {url} body={body[:200]}")

    timeout_sec = timeout_ms / 1000
    req = urllib.request.Request(
        url,
        data=body.encode(),
        headers=hdrs,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            raw_text = resp.read().decode("utf-8")
            logger.debug(f"{label} status={resp.status} raw={raw_text[:200]}")
            return raw_text
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8") if e.fp else "(unreadable)"
        logger.error(f"{label} HTTP error {e.code}: {body_text}")
        raise
    except Exception as e:
        logger.error(f"{label} request failed: {e}")
        raise


async def get_updates(
    base_url: str,
    token: Optional[str],
    get_updates_buf: Optional[str] = None,
    timeout_ms: Optional[int] = None,
    abort_signal: Optional[Any] = None,
) -> Dict[str, Any]:
    timeout = timeout_ms or DEFAULT_LONG_POLL_TIMEOUT_MS
    body = json.dumps({
        "get_updates_buf": get_updates_buf or "",
        "base_info": build_base_info(),
    })

    try:
        raw_text = _api_fetch(
            base_url=base_url,
            endpoint="ilink/bot/getupdates",
            body=body,
            token=token,
            timeout_ms=timeout,
            label="getUpdates",
            abort_signal=abort_signal,
        )
        return json.loads(raw_text)
    except Exception as err:
        if "timeout" in str(err).lower() or "timed out" in str(err).lower():
            logger.debug(f"getUpdates: client-side timeout after {timeout}ms, returning empty response")
            return {"ret": 0, "msgs": [], "get_updates_buf": get_updates_buf or ""}
        raise


async def get_upload_url(
    base_url: str,
    token: Optional[str],
    filekey: Optional[str] = None,
    media_type: Optional[int] = None,
    to_user_id: Optional[str] = None,
    rawsize: Optional[int] = None,
    rawfilemd5: Optional[str] = None,
    filesize: Optional[int] = None,
    thumb_rawsize: Optional[int] = None,
    thumb_rawfilemd5: Optional[str] = None,
    thumb_filesize: Optional[int] = None,
    no_need_thumb: Optional[bool] = None,
    aeskey: Optional[str] = None,
    timeout_ms: Optional[int] = None,
) -> Dict[str, Any]:
    body = json.dumps({
        "filekey": filekey,
        "media_type": media_type,
        "to_user_id": to_user_id,
        "rawsize": rawsize,
        "rawfilemd5": rawfilemd5,
        "filesize": filesize,
        "thumb_rawsize": thumb_rawsize,
        "thumb_rawfilemd5": thumb_rawfilemd5,
        "thumb_filesize": thumb_filesize,
        "no_need_thumb": no_need_thumb,
        "aeskey": aeskey,
        "base_info": build_base_info(),
    })

    raw_text = _api_fetch(
        base_url=base_url,
        endpoint="ilink/bot/getuploadurl",
        body=body,
        token=token,
        timeout_ms=timeout_ms or DEFAULT_API_TIMEOUT_MS,
        label="getUploadUrl",
    )
    return json.loads(raw_text)


async def send_message(
    base_url: str,
    token: Optional[str],
    msg: Dict[str, Any],
    timeout_ms: Optional[int] = None,
) -> None:
    body = json.dumps({**msg, "base_info": build_base_info()})
    _api_fetch(
        base_url=base_url,
        endpoint="ilink/bot/sendmessage",
        body=body,
        token=token,
        timeout_ms=timeout_ms or DEFAULT_API_TIMEOUT_MS,
        label="sendMessage",
    )


async def get_config(
    base_url: str,
    token: Optional[str],
    ilink_user_id: str,
    context_token: Optional[str] = None,
    timeout_ms: Optional[int] = None,
) -> Dict[str, Any]:
    body = json.dumps({
        "ilink_user_id": ilink_user_id,
        "context_token": context_token,
        "base_info": build_base_info(),
    })
    raw_text = _api_fetch(
        base_url=base_url,
        endpoint="ilink/bot/getconfig",
        body=body,
        token=token,
        timeout_ms=timeout_ms or DEFAULT_CONFIG_TIMEOUT_MS,
        label="getConfig",
    )
    return json.loads(raw_text)


async def send_typing(
    base_url: str,
    token: Optional[str],
    ilink_user_id: str,
    typing_ticket: str,
    status: int = 1,
    timeout_ms: Optional[int] = None,
) -> None:
    body = json.dumps({
        "ilink_user_id": ilink_user_id,
        "typing_ticket": typing_ticket,
        "status": status,
        "base_info": build_base_info(),
    })
    _api_fetch(
        base_url=base_url,
        endpoint="ilink/bot/sendtyping",
        body=body,
        token=token,
        timeout_ms=timeout_ms or DEFAULT_CONFIG_TIMEOUT_MS,
        label="sendTyping",
    )
