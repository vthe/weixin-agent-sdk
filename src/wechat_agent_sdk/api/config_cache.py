"""Config cache with periodic refresh and exponential-backoff retry."""

import time
from typing import Any, Dict, Optional

from wechat_agent_sdk.api.api import get_config
from wechat_agent_sdk.util.logger import logger


CONFIG_CACHE_TTL_MS = 24 * 60 * 60 * 1000
CONFIG_CACHE_INITIAL_RETRY_MS = 2_000
CONFIG_CACHE_MAX_RETRY_MS = 60 * 60 * 1000


class CachedConfig:
    typing_ticket: str = ""


class ConfigCacheEntry:
    config: CachedConfig
    ever_succeeded: bool
    next_fetch_at: int
    retry_delay_ms: int

    def __init__(self, config: CachedConfig, ever_succeeded: bool, next_fetch_at: int, retry_delay_ms: int):
        self.config = config
        self.ever_succeeded = ever_succeeded
        self.next_fetch_at = next_fetch_at
        self.retry_delay_ms = retry_delay_ms


class WeixinConfigManager:
    def __init__(self, base_url: str, token: Optional[str], log: callable):
        self._base_url = base_url
        self._token = token
        self._log = log
        self._cache: Dict[str, ConfigCacheEntry] = {}

    async def get_for_user(self, user_id: str, context_token: Optional[str] = None) -> CachedConfig:
        now = int(time.time() * 1000)
        entry = self._cache.get(user_id)
        should_fetch = entry is None or now >= entry.next_fetch_at

        if should_fetch:
            fetch_ok = False
            try:
                resp = await get_config(
                    base_url=self._base_url,
                    token=self._token,
                    ilink_user_id=user_id,
                    context_token=context_token,
                )
                if resp.get("ret") == 0:
                    config = CachedConfig()
                    config.typing_ticket = resp.get("typing_ticket", "")
                    self._cache[user_id] = ConfigCacheEntry(
                        config=config,
                        ever_succeeded=True,
                        next_fetch_at=now + int(CONFIG_CACHE_TTL_MS * (0.5 + 0.5 * __import__('random').random())),
                        retry_delay_ms=CONFIG_CACHE_INITIAL_RETRY_MS,
                    )
                    self._log(f"[weixin] config {'refreshed' if entry and entry.ever_succeeded else 'cached'} for {user_id}")
                    fetch_ok = True
            except Exception as e:
                self._log(f"[weixin] getConfig failed for {user_id} (ignored): {e}")

            if not fetch_ok:
                prev_delay = entry.retry_delay_ms if entry else CONFIG_CACHE_INITIAL_RETRY_MS
                next_delay = min(prev_delay * 2, CONFIG_CACHE_MAX_RETRY_MS)
                if entry:
                    entry.next_fetch_at = now + next_delay
                    entry.retry_delay_ms = next_delay
                else:
                    self._cache[user_id] = ConfigCacheEntry(
                        config=CachedConfig(),
                        ever_succeeded=False,
                        next_fetch_at=now + CONFIG_CACHE_INITIAL_RETRY_MS,
                        retry_delay_ms=CONFIG_CACHE_INITIAL_RETRY_MS,
                    )

        cached = self._cache.get(user_id)
        return cached.config if cached else CachedConfig()
