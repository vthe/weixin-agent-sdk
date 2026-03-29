"""Long-poll monitor: getUpdates → process message → call agent → send reply."""

import time
from typing import Any, Dict, List, Optional

from wechat_agent_sdk.agent.interface import Agent
from wechat_agent_sdk.api.api import get_updates
from wechat_agent_sdk.api.config_cache import WeixinConfigManager
from wechat_agent_sdk.api.session_guard import SESSION_EXPIRED_ERRCODE, get_remaining_pause_ms, is_session_paused, pause_session
from wechat_agent_sdk.messaging.process_message import process_one_message
from wechat_agent_sdk.storage.sync_buf import get_sync_buf_file_path, load_get_updates_buf, save_get_updates_buf
from wechat_agent_sdk.util.logger import logger


DEFAULT_LONG_POLL_TIMEOUT_MS = 35_000
MAX_CONSECUTIVE_FAILURES = 3
BACKOFF_DELAY_MS = 30_000
RETRY_DELAY_MS = 2_000


class MonitorWeixinOpts:
    base_url: str
    cdn_base_url: str
    token: Optional[str]
    account_id: str
    agent: Agent
    abort_signal: Optional[Any] = None
    long_poll_timeout_ms: Optional[int] = None
    log: Optional[callable] = None


async def monitor_weixin_provider(
    base_url: str,
    cdn_base_url: str,
    token: Optional[str],
    account_id: str,
    agent: Agent,
    abort_signal: Optional[Any] = None,
    long_poll_timeout_ms: Optional[int] = None,
    log: Optional[callable] = None,
) -> None:
    log_fn = log or (lambda msg: print(msg))
    err_log = lambda msg: (log_fn(msg), logger.error(msg))
    a_log = logger.with_account(account_id)

    log_fn(f"[weixin] monitor started ({base_url}, account={account_id})")
    a_log.info(f"Monitor started: baseUrl={base_url}")

    sync_file_path = get_sync_buf_file_path(account_id)
    previous_buf = load_get_updates_buf(sync_file_path)
    get_updates_buf = previous_buf or ""

    if previous_buf:
        log_fn(f"[weixin] resuming from previous sync buf ({len(get_updates_buf)} bytes)")
    else:
        log_fn("[weixin] no previous sync buf, starting fresh")

    config_manager = WeixinConfigManager(base_url, token, log_fn)

    next_timeout_ms = long_poll_timeout_ms or DEFAULT_LONG_POLL_TIMEOUT_MS
    consecutive_failures = 0

    while not (abort_signal and abort_signal.aborted if hasattr(abort_signal, "aborted") else False):
        try:
            resp = await get_updates(
                base_url=base_url,
                token=token,
                get_updates_buf=get_updates_buf,
                timeout_ms=next_timeout_ms,
                abort_signal=abort_signal,
            )

            if resp.get("longpolling_timeout_ms") and resp["longpolling_timeout_ms"] > 0:
                next_timeout_ms = resp["longpolling_timeout_ms"]

            ret = resp.get("ret")
            errcode = resp.get("errcode")
            is_api_error = (ret is not None and ret != 0) or (errcode is not None and errcode != 0)

            if is_api_error:
                is_session_expired = errcode == SESSION_EXPIRED_ERRCODE or ret == SESSION_EXPIRED_ERRCODE

                if is_session_expired:
                    pause_session(account_id)
                    pause_ms = get_remaining_pause_ms(account_id)
                    err_log(
                        f"[weixin] session expired (errcode {SESSION_EXPIRED_ERRCODE}), "
                        f"pausing for { (pause_ms + 59_999) // 60_000 } min"
                    )
                    consecutive_failures = 0
                    await _sleep(pause_ms / 1000, abort_signal)
                    continue

                consecutive_failures += 1
                err_log(
                    f"[weixin] getUpdates failed: ret={ret} errcode={errcode} "
                    f"errmsg={resp.get('errmsg', '')} ({consecutive_failures}/{MAX_CONSECUTIVE_FAILURES})"
                )
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    err_log(f"[weixin] {MAX_CONSECUTIVE_FAILURES} consecutive failures, backing off 30s")
                    consecutive_failures = 0
                    await _sleep(BACKOFF_DELAY_MS / 1000, abort_signal)
                else:
                    await _sleep(RETRY_DELAY_MS / 1000, abort_signal)
                continue

            consecutive_failures = 0

            if resp.get("get_updates_buf") and resp["get_updates_buf"] != "":
                save_get_updates_buf(sync_file_path, resp["get_updates_buf"])
                get_updates_buf = resp["get_updates_buf"]

            msgs: List[Dict[str, Any]] = resp.get("msgs") or []
            for full in msgs:
                a_log.info(
                    f"inbound: from={full.get('from_user_id')} "
                    f"types={[i.get('type') for i in full.get('item_list') or []]}"
                )

                from_user_id = full.get("from_user_id", "")
                cached_config = await config_manager.get_for_user(from_user_id, full.get("context_token"))

                deps_account_id = account_id
                deps_agent = agent
                deps_base_url = base_url
                deps_cdn_base_url = cdn_base_url
                deps_token = token
                deps_typing_ticket = cached_config.typing_ticket
                deps_err_log = err_log

                class Deps:
                    account_id: str = deps_account_id
                    agent: Agent = deps_agent
                    base_url: str = deps_base_url
                    cdn_base_url: str = deps_cdn_base_url
                    token: Optional[str] = deps_token
                    typing_ticket: Optional[str] = deps_typing_ticket
                    log: callable = log_fn
                    err_log: callable = deps_err_log

                await process_one_message(full, Deps())

        except Exception as e:
            if abort_signal and hasattr(abort_signal, "aborted") and abort_signal.aborted:
                a_log.info("Monitor stopped (aborted)")
                return
            consecutive_failures += 1
            err_log(f"[weixin] getUpdates error ({consecutive_failures}/{MAX_CONSECUTIVE_FAILURES}): {e}")
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                consecutive_failures = 0
                await _sleep(BACKOFF_DELAY_MS / 1000, abort_signal)
            else:
                await _sleep(RETRY_DELAY_MS / 1000, abort_signal)

    a_log.info("Monitor ended")


async def _sleep(seconds: float, abort_signal: Optional[Any] = None) -> None:
    if abort_signal and hasattr(abort_signal, "aborted") and abort_signal.aborted:
        raise Exception("aborted")
    time.sleep(seconds)
