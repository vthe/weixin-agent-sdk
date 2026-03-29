"""Weixin account management and credential storage."""

import json
import os
from typing import Any, Dict, List, Optional

from wechat_agent_sdk.storage.state_dir import resolve_state_dir
from wechat_agent_sdk.util.logger import logger


DEFAULT_BASE_URL = "https://ilinkai.weixin.qq.com"
CDN_BASE_URL = "https://novac2c.cdn.weixin.qq.com/c2c"


def normalize_account_id(raw: str) -> str:
    """Normalize an account ID to a filesystem-safe string."""
    return raw.strip().lower().replace("@", "-").replace(".", "-")


def derive_raw_account_id(normalized_id: str) -> Optional[str]:
    """Pattern-based reverse of normalizeAccountId for known weixin ID suffixes."""
    if normalized_id.endswith("-im-bot"):
        return f"{normalized_id[:-7]}@im.bot"
    if normalized_id.endswith("-im-wechat"):
        return f"{normalized_id[:-10]}@im.wechat"
    return None


def _resolve_weixin_state_dir() -> str:
    return os.path.join(resolve_state_dir(), "openclaw-weixin")


def _resolve_account_index_path() -> str:
    return os.path.join(_resolve_weixin_state_dir(), "accounts.json")


def list_indexed_weixin_account_ids() -> List[str]:
    """Returns all accountIds registered via QR login."""
    file_path = _resolve_account_index_path()
    try:
        if not os.path.exists(file_path):
            return []
        with open(file_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, list):
            return []
        return [str(i) for i in raw if isinstance(i, str) and i.strip()]
    except Exception:
        return []


def register_weixin_account_id(account_id: str) -> None:
    """Register accountId as the sole account in the persistent index."""
    directory = _resolve_weixin_state_dir()
    os.makedirs(directory, exist_ok=True)
    with open(_resolve_account_index_path(), "w", encoding="utf-8") as f:
        json.dump([account_id], f, indent=2)


def _resolve_accounts_dir() -> str:
    return os.path.join(_resolve_weixin_state_dir(), "accounts")


def _resolve_account_path(account_id: str) -> str:
    return os.path.join(_resolve_accounts_dir(), f"{account_id}.json")


WeixinAccountData = Dict[str, Any]


def _load_legacy_token() -> Optional[str]:
    """Load legacy single-file token."""
    legacy_path = os.path.join(
        resolve_state_dir(), "credentials", "openclaw-weixin", "credentials.json"
    )
    try:
        if not os.path.exists(legacy_path):
            return None
        with open(legacy_path, "r", encoding="utf-8") as f:
            parsed = json.load(f)
        return parsed.get("token") if isinstance(parsed, dict) else None
    except Exception:
        return None


def _read_account_file(file_path: str) -> Optional[WeixinAccountData]:
    try:
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return None


def load_weixin_account(account_id: str) -> Optional[WeixinAccountData]:
    """Load account data by ID, with compatibility fallbacks."""
    primary = _read_account_file(_resolve_account_path(account_id))
    if primary:
        return primary

    raw_id = derive_raw_account_id(account_id)
    if raw_id:
        compat = _read_account_file(_resolve_account_path(raw_id))
        if compat:
            return compat

    token = _load_legacy_token()
    if token:
        return {"token": token}

    return None


def save_weixin_account(
    account_id: str,
    update: Optional[Dict[str, str]] = None,
) -> None:
    """Persist account data after QR login (merges into existing file)."""
    if update is None:
        update = {}
    directory = _resolve_accounts_dir()
    os.makedirs(directory, exist_ok=True)

    existing = load_weixin_account(account_id) or {}

    token = update.get("token", "").strip() or existing.get("token", "")
    base_url = update.get("baseUrl", "").strip() or existing.get("baseUrl", "")
    user_id = update.get("userId")
    if user_id is not None:
        user_id = user_id.strip() or None

    data: WeixinAccountData = {}
    if token:
        data["token"] = token
        data["savedAt"] = __import__("datetime").datetime.now().isoformat()
    if base_url:
        data["baseUrl"] = base_url
    if user_id:
        data["userId"] = user_id

    file_path = _resolve_account_path(account_id)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    try:
        os.chmod(file_path, 0o600)
    except Exception:
        pass


def clear_weixin_account(account_id: str) -> None:
    """Remove account data file."""
    try:
        os.remove(_resolve_account_path(account_id))
    except Exception:
        pass


def clear_all_weixin_accounts() -> None:
    """Remove all account data files and clear the account index."""
    ids = list_indexed_weixin_account_ids()
    for id_ in ids:
        clear_weixin_account(id_)
    try:
        with open(_resolve_account_index_path(), "w", encoding="utf-8") as f:
            json.dump([], f)
    except Exception:
        pass


def _resolve_config_path() -> str:
    """Resolve the openclaw.json config file path."""
    env_path = os.environ.get("OPENCLAW_CONFIG", "").strip()
    if env_path:
        return env_path
    return os.path.join(resolve_state_dir(), "openclaw.json")


def load_config_route_tag(account_id: Optional[str] = None) -> Optional[str]:
    """Read routeTag from openclaw.json."""
    try:
        config_path = _resolve_config_path()
        if not os.path.exists(config_path):
            return None
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict):
            return None
        channels = cfg.get("channels")
        if not isinstance(channels, dict):
            return None
        section = channels.get("openclaw-weixin")
        if not isinstance(section, dict):
            return None
        if account_id:
            accounts = section.get("accounts")
            if isinstance(accounts, dict):
                account_tag = accounts.get(account_id, {}).get("routeTag")
                if isinstance(account_tag, (int, str)) and str(account_tag).strip():
                    return str(account_tag).strip()
        route_tag = section.get("routeTag")
        if isinstance(route_tag, (int, str)) and str(route_tag).strip():
            return str(route_tag).strip()
        return None
    except Exception:
        return None


class ResolvedWeixinAccount:
    def __init__(
        self,
        account_id: str,
        base_url: str,
        cdn_base_url: str,
        token: Optional[str] = None,
        enabled: bool = True,
        configured: bool = False,
    ):
        self.account_id = account_id
        self.base_url = base_url
        self.cdn_base_url = cdn_base_url
        self.token = token
        self.enabled = enabled
        self.configured = configured


def list_weixin_account_ids() -> List[str]:
    """List accountIds from the index file."""
    return list_indexed_weixin_account_ids()


def resolve_weixin_account(account_id: Optional[str] = None) -> ResolvedWeixinAccount:
    """Resolve a weixin account by ID, reading stored credentials."""
    if not account_id:
        raise ValueError("weixin: accountId is required (no default account)")

    raw = account_id.strip()
    if not raw:
        raise ValueError("weixin: accountId is required (no default account)")

    id_ = normalize_account_id(raw)
    account_data = load_weixin_account(id_) or {}
    token = account_data.get("token", "").strip() or None
    state_base_url = account_data.get("baseUrl", "").strip() or ""

    return ResolvedWeixinAccount(
        account_id=id_,
        base_url=state_base_url or DEFAULT_BASE_URL,
        cdn_base_url=CDN_BASE_URL,
        token=token,
        enabled=True,
        configured=bool(token),
    )
