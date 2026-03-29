"""Framework pairing/allowFrom integration."""

import json
import os
from typing import List, Optional

from wechat_agent_sdk.storage.state_dir import resolve_state_dir
from wechat_agent_sdk.util.logger import logger


def _resolve_credentials_dir() -> str:
    """Resolve the framework credentials directory."""
    override = os.environ.get("OPENCLAW_OAUTH_DIR", "").strip()
    if override:
        return override
    return os.path.join(resolve_state_dir(), "credentials")


def _safe_key(raw: str) -> str:
    """Sanitize a channel/account key for safe use in filenames."""
    trimmed = raw.strip().lower()
    if not trimmed:
        raise ValueError("invalid key for allowFrom path")
    safe = trimmed.replace("\\", "_").replace("/", "_").replace(":", "_").replace("*", "_")
    safe = safe.replace("?", "_").replace('"', "_").replace("<", "_").replace(">", "_").replace("|", "_")
    safe = safe.replace("..", "_")
    if not safe or safe == "_":
        raise ValueError("invalid key for allowFrom path")
    return safe


def resolve_framework_allow_from_path(account_id: str) -> str:
    """Resolve the framework allowFrom file path for a given account."""
    base = _safe_key("openclaw-weixin")
    safe_account = _safe_key(account_id)
    return os.path.join(_resolve_credentials_dir(), f"{base}-{safe_account}-allowFrom.json")


def read_framework_allow_from_list(account_id: str) -> List[str]:
    """Read the framework allowFrom list for an account."""
    file_path = resolve_framework_allow_from_path(account_id)
    try:
        if not os.path.exists(file_path):
            return []
        with open(file_path, "r", encoding="utf-8") as f:
            parsed = json.load(f)
        if isinstance(parsed, dict) and isinstance(parsed.get("allowFrom"), list):
            return [str(i) for i in parsed["allowFrom"] if isinstance(i, str) and i.strip()]
    except Exception:
        pass
    return []


def register_user_in_allow_from_store(
    account_id: str,
    user_id: str,
) -> bool:
    """Register a user ID in the channel allowFrom store."""
    trimmed_user_id = user_id.strip()
    if not trimmed_user_id:
        return False

    file_path = resolve_framework_allow_from_path(account_id)
    directory = os.path.dirname(file_path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    content = {"version": 1, "allowFrom": []}
    try:
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                parsed = json.load(f)
            if isinstance(parsed, dict) and isinstance(parsed.get("allowFrom"), list):
                content = parsed
    except Exception:
        pass

    if trimmed_user_id in content["allowFrom"]:
        return False

    content["allowFrom"].append(trimmed_user_id)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(content, f, indent=2)
    logger.info(
        f"registerUserInAllowFromStore: added userId={trimmed_user_id} accountId={account_id} path={file_path}"
    )
    return True
