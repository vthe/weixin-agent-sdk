"""Sync buffer persistence for get_updates_buf."""

import json
import os
from typing import Optional

from wechat_agent_sdk.auth.accounts import derive_raw_account_id
from wechat_agent_sdk.storage.state_dir import resolve_state_dir


def _resolve_accounts_dir() -> str:
    return os.path.join(resolve_state_dir(), "openclaw-weixin", "accounts")


def get_sync_buf_file_path(account_id: str) -> str:
    """Path to the persistent get_updates_buf file for an account."""
    return os.path.join(_resolve_accounts_dir(), f"{account_id}.sync.json")


def _get_legacy_sync_buf_default_json_path() -> str:
    return os.path.join(
        resolve_state_dir(),
        "agents",
        "default",
        "sessions",
        ".openclaw-weixin-sync",
        "default.json",
    )


def _read_sync_buf_file(file_path: str) -> Optional[str]:
    try:
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and isinstance(data.get("get_updates_buf"), str):
                    return data["get_updates_buf"]
    except Exception:
        pass
    return None


def load_get_updates_buf(file_path: str) -> Optional[str]:
    """Load persisted get_updates_buf with legacy fallback."""
    value = _read_sync_buf_file(file_path)
    if value is not None:
        return value

    account_id = os.path.basename(file_path).replace(".sync.json", "")
    raw_id = derive_raw_account_id(account_id)
    if raw_id:
        compat_path = os.path.join(_resolve_accounts_dir(), f"{raw_id}.sync.json")
        compat_value = _read_sync_buf_file(compat_path)
        if compat_value is not None:
            return compat_value

    return _read_sync_buf_file(_get_legacy_sync_buf_default_json_path())


def save_get_updates_buf(file_path: str, get_updates_buf: str) -> None:
    """Persist get_updates_buf. Creates parent dir if needed."""
    directory = os.path.dirname(file_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump({"get_updates_buf": get_updates_buf}, f)
