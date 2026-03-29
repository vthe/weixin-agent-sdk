"""Debug mode toggle, persisted to disk."""

import json
import os
from typing import Dict

from wechat_agent_sdk.storage.state_dir import resolve_state_dir
from wechat_agent_sdk.util.logger import logger


def _resolve_debug_mode_path() -> str:
    return os.path.join(resolve_state_dir(), "openclaw-weixin", "debug-mode.json")


class DebugModeState:
    accounts: Dict[str, bool] = {}


def _load_debug_state() -> DebugModeState:
    try:
        path = _resolve_debug_mode_path()
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                parsed = json.load(f)
            if parsed and isinstance(parsed.get("accounts"), dict):
                state = DebugModeState()
                state.accounts = parsed["accounts"]
                return state
    except Exception:
        pass
    return DebugModeState()


def _save_debug_state(state: DebugModeState) -> None:
    try:
        path = _resolve_debug_mode_path()
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"accounts": state.accounts}, f, indent=2)
    except Exception as e:
        logger.error(f"debug-mode: failed to persist state: {e}")


def toggle_debug_mode(account_id: str) -> bool:
    """Toggle debug mode for a bot account. Returns the new state."""
    state = _load_debug_state()
    next_state = not state.accounts.get(account_id, False)
    state.accounts[account_id] = next_state
    _save_debug_state(state)
    return next_state


def is_debug_mode(account_id: str) -> bool:
    """Check whether debug mode is active for a bot account."""
    return _load_debug_state().accounts.get(account_id, False)


def _reset_for_test() -> None:
    """Reset internal state — only for tests."""
    try:
        os.remove(_resolve_debug_mode_path())
    except Exception:
        pass
