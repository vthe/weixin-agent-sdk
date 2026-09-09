from __future__ import annotations

import base64
import json
import random
from importlib.metadata import PackageNotFoundError, version
from typing import Any

import httpx

from weixin_agent.storage import (
    load_config_bot_agent,
    load_config_route_tag,
    list_account_tokens,
)

DEFAULT_LONG_POLL_TIMEOUT_S = 35.0
DEFAULT_API_TIMEOUT_S = 15.0
DEFAULT_CONFIG_TIMEOUT_S = 10.0
DEFAULT_ILINK_BOT_TYPE = "3"
SESSION_EXPIRED_ERRCODE = -14
DEFAULT_BOT_AGENT = "OpenClaw"

try:
    PACKAGE_VERSION = version("weixin-agent-sdk")
except PackageNotFoundError:
    PACKAGE_VERSION = "0.1.0"


def build_client_version(version_string: str) -> int:
    parts = version_string.split(".")
    values = [0, 0, 0]
    for i, part in enumerate(parts[:3]):
        try:
            values[i] = int(part)
        except ValueError:
            pass
    return ((values[0] & 0xFF) << 16) | ((values[1] & 0xFF) << 8) | (values[2] & 0xFF)


# iLink-App-Id / iLink-App-ClientVersion: mirrors package.json ilink_appid + version.
ILINK_APP_ID = "bot"
ILINK_APP_CLIENT_VERSION = str(build_client_version(PACKAGE_VERSION))


def build_base_info() -> dict[str, str]:
    return {
        "channel_version": PACKAGE_VERSION,
        "bot_agent": load_config_bot_agent() or DEFAULT_BOT_AGENT,
    }


def build_common_headers() -> dict[str, str]:
    return {
        "iLink-App-Id": ILINK_APP_ID,
        "iLink-App-ClientVersion": ILINK_APP_CLIENT_VERSION,
    }


def random_wechat_uin() -> str:
    raw = str(random.randint(0, 2**32 - 1)).encode()
    return base64.b64encode(raw).decode()


class WeixinApiClient:
    def __init__(self, base_url: str, token: str | None = None) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.token = token.strip() if token else None
        self._client = httpx.AsyncClient(base_url=self.base_url, follow_redirects=True)

    async def aclose(self) -> None:
        await self._client.aclose()

    def _build_headers(self, body: str, account_id: str | None = None) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "AuthorizationType": "ilink_bot_token",
            "Content-Length": str(len(body.encode())),
            "X-WECHAT-UIN": random_wechat_uin(),
            **build_common_headers(),
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        route_tag = load_config_route_tag(account_id)
        if route_tag:
            headers["SKRouteTag"] = route_tag
        return headers

    async def _post_json(
        self,
        endpoint: str,
        payload: dict[str, Any],
        *,
        timeout: float,
        account_id: str | None = None,
    ) -> dict[str, Any]:
        body = json.dumps(payload)
        response = await self._client.post(
            endpoint,
            content=body,
            headers=self._build_headers(body, account_id=account_id),
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()

    async def _get_json(
        self,
        endpoint: str,
        *,
        params: dict[str, Any],
        timeout: float,
        headers: dict[str, str] | None = None,
        account_id: str | None = None,
        base_url: str | None = None,
    ) -> dict[str, Any]:
        merged_headers = build_common_headers()
        if headers:
            merged_headers.update(headers)
        route_tag = load_config_route_tag(account_id)
        if route_tag:
            merged_headers["SKRouteTag"] = route_tag

        client = self._client
        if base_url and base_url.rstrip("/") != self.base_url.rstrip("/"):
            client = httpx.AsyncClient(base_url=base_url.rstrip("/") + "/", follow_redirects=True)
        try:
            response = await client.get(
                endpoint,
                params=params,
                headers=merged_headers or None,
                timeout=timeout,
            )
            response.raise_for_status()
            return response.json()
        finally:
            if client is not self._client:
                await client.aclose()

    async def get_updates(
        self,
        *,
        get_updates_buf: str,
        timeout: float = DEFAULT_LONG_POLL_TIMEOUT_S,
        account_id: str | None = None,
    ) -> dict[str, Any]:
        try:
            return await self._post_json(
                "ilink/bot/getupdates",
                {
                    "get_updates_buf": get_updates_buf,
                    "base_info": build_base_info(),
                },
                timeout=timeout,
                account_id=account_id,
            )
        except httpx.TimeoutException:
            return {"ret": 0, "msgs": [], "get_updates_buf": get_updates_buf}

    async def get_upload_url(
        self,
        payload: dict[str, Any],
        *,
        account_id: str | None = None,
    ) -> dict[str, Any]:
        return await self._post_json(
            "ilink/bot/getuploadurl",
            {**payload, "base_info": build_base_info()},
            timeout=DEFAULT_API_TIMEOUT_S,
            account_id=account_id,
        )

    async def send_message(self, payload: dict[str, Any], *, account_id: str | None = None) -> None:
        await self._post_json(
            "ilink/bot/sendmessage",
            {**payload, "base_info": build_base_info()},
            timeout=DEFAULT_API_TIMEOUT_S,
            account_id=account_id,
        )

    async def get_config(
        self,
        *,
        ilink_user_id: str,
        context_token: str | None,
        account_id: str | None = None,
    ) -> dict[str, Any]:
        return await self._post_json(
            "ilink/bot/getconfig",
            {
                "ilink_user_id": ilink_user_id,
                "context_token": context_token,
                "base_info": build_base_info(),
            },
            timeout=DEFAULT_CONFIG_TIMEOUT_S,
            account_id=account_id,
        )

    async def send_typing(self, payload: dict[str, Any], *, account_id: str | None = None) -> None:
        await self._post_json(
            "ilink/bot/sendtyping",
            {**payload, "base_info": build_base_info()},
            timeout=DEFAULT_CONFIG_TIMEOUT_S,
            account_id=account_id,
        )

    async def fetch_qr_code(
        self,
        *,
        bot_type: str = DEFAULT_ILINK_BOT_TYPE,
        account_id: str | None = None,
    ) -> dict[str, Any]:
        return await self._post_json(
            f"ilink/bot/get_bot_qrcode?bot_type={bot_type}",
            {"local_token_list": list_account_tokens()},
            timeout=DEFAULT_API_TIMEOUT_S,
            account_id=account_id,
        )

    async def poll_qr_status(
        self,
        *,
        qrcode: str,
        verify_code: str | None = None,
        base_url: str | None = None,
        account_id: str | None = None,
    ) -> dict[str, Any]:
        try:
            params: dict[str, Any] = {"qrcode": qrcode}
            if verify_code:
                params["verify_code"] = verify_code
            return await self._get_json(
                "ilink/bot/get_qrcode_status",
                params=params,
                timeout=DEFAULT_LONG_POLL_TIMEOUT_S,
                account_id=account_id,
                base_url=base_url,
            )
        except httpx.TimeoutException:
            return {"status": "wait"}
