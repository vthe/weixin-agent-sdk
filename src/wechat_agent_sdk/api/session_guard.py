"""Session guard: pause/resume on errcode -14."""

from wechat_agent_sdk.util.logger import logger


SESSION_PAUSE_DURATION_MS = 60 * 60 * 1000
SESSION_EXPIRED_ERRCODE = -14

_pause_until_map: dict = {}


def pause_session(account_id: str) -> None:
    """Pause all inbound/outbound API calls for accountId for one hour."""
    until = _get_current_time_ms() + SESSION_PAUSE_DURATION_MS
    _pause_until_map[account_id] = until
    logger.info(
        f"session-guard: paused accountId={account_id} until="
        f"{__import__('datetime').datetime.fromtimestamp(until / 1000).isoformat()} "
        f"({SESSION_PAUSE_DURATION_MS / 1000}s)"
    )


def _get_current_time_ms() -> int:
    return int(__import__('time').time() * 1000)


def is_session_paused(account_id: str) -> bool:
    """Returns True when the bot is still within its one-hour cooldown window."""
    until = _pause_until_map.get(account_id)
    if until is None:
        return False
    if _get_current_time_ms() >= until:
        del _pause_until_map[account_id]
        return False
    return True


def get_remaining_pause_ms(account_id: str) -> int:
    """Milliseconds remaining until the pause expires (0 when not paused)."""
    until = _pause_until_map.get(account_id)
    if until is None:
        return 0
    remaining = until - _get_current_time_ms()
    if remaining <= 0:
        del _pause_until_map[account_id]
        return 0
    return remaining


def assert_session_active(account_id: str) -> None:
    """Throw if the session is currently paused."""
    if is_session_paused(account_id):
        remaining_min = (get_remaining_pause_ms(account_id) + 59_999) // 60_000
        raise Exception(
            f"session paused for accountId={account_id}, {remaining_min} min remaining "
            f"(errcode {SESSION_EXPIRED_ERRCODE})"
        )


def _reset_for_test() -> None:
    """Reset internal state — only for tests."""
    _pause_until_map.clear()
