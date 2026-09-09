from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_BASE_URL = "https://ilinkai.weixin.qq.com"
CDN_BASE_URL = "https://novac2c.cdn.weixin.qq.com/c2c"
CHANNEL_KEY = "openclaw-weixin"


@dataclass(slots=True)
class WeixinAccountData:
    token: str | None = None
    saved_at: str | None = None
    base_url: str | None = None
    user_id: str | None = None


@dataclass(slots=True)
class ResolvedWeixinAccount:
    account_id: str
    base_url: str
    cdn_base_url: str
    token: str | None
    enabled: bool
    configured: bool


def resolve_state_dir() -> Path:
    state_dir = (
        os.getenv("OPENCLAW_STATE_DIR", "").strip()
        or os.getenv(
            "CLAWDBOT_STATE_DIR",
            "",
        ).strip()
    )
    return Path(state_dir) if state_dir else Path.home() / ".openclaw"


def resolve_weixin_state_dir() -> Path:
    return resolve_state_dir() / CHANNEL_KEY


def normalize_account_id(raw: str) -> str:
    return raw.strip().lower().replace("@", "-").replace(".", "-")


def derive_raw_account_id(normalized_id: str) -> str | None:
    if normalized_id.endswith("-im-bot"):
        return f"{normalized_id[:-7]}@im.bot"
    if normalized_id.endswith("-im-wechat"):
        return f"{normalized_id[:-10]}@im.wechat"
    return None


def list_account_ids() -> list[str]:
    index_path = resolve_weixin_state_dir() / "accounts.json"
    try:
        data = json.loads(index_path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, str) and item.strip()]


def register_account_id(account_id: str) -> None:
    account_ids = list_account_ids()
    if account_id in account_ids:
        return
    state_dir = resolve_weixin_state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)
    account_ids.append(account_id)
    (state_dir / "accounts.json").write_text(json.dumps(account_ids, indent=2))


def list_account_tokens(limit: int = 10) -> list[str]:
    account_ids = list_account_ids()
    tokens: list[str] = []
    for account_id in reversed(account_ids):
        if len(tokens) >= limit:
            break
        data = load_account(account_id)
        token = (data.token or "").strip() if data else ""
        if token:
            tokens.append(token)
    return tokens


def resolve_accounts_dir() -> Path:
    return resolve_weixin_state_dir() / "accounts"


def resolve_account_path(account_id: str) -> Path:
    return resolve_accounts_dir() / f"{account_id}.json"


def load_account(account_id: str) -> WeixinAccountData | None:
    candidates = [resolve_account_path(account_id)]
    raw_id = derive_raw_account_id(account_id)
    if raw_id:
        candidates.append(resolve_account_path(raw_id))

    for path in candidates:
        try:
            data = json.loads(path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        return WeixinAccountData(
            token=data.get("token"),
            saved_at=data.get("savedAt"),
            base_url=data.get("baseUrl"),
            user_id=data.get("userId"),
        )
    return None


def save_account(account_id: str, update: WeixinAccountData) -> None:
    existing = load_account(account_id) or WeixinAccountData()
    merged = WeixinAccountData(
        token=(update.token or existing.token or "").strip() or None,
        saved_at=update.saved_at or existing.saved_at,
        base_url=(update.base_url or existing.base_url or "").strip() or None,
        user_id=(update.user_id or existing.user_id or "").strip() or None,
    )

    accounts_dir = resolve_accounts_dir()
    accounts_dir.mkdir(parents=True, exist_ok=True)
    payload = {}
    if merged.token:
        payload["token"] = merged.token
        payload["savedAt"] = merged.saved_at
    if merged.base_url:
        payload["baseUrl"] = merged.base_url
    if merged.user_id:
        payload["userId"] = merged.user_id

    account_path = resolve_account_path(account_id)
    account_path.write_text(json.dumps(payload, indent=2))
    account_path.chmod(0o600)


def resolve_config_path() -> Path:
    config_path = os.getenv("OPENCLAW_CONFIG", "").strip()
    return Path(config_path) if config_path else resolve_state_dir() / "openclaw.json"


def load_config_route_tag(account_id: str | None = None) -> str | None:
    try:
        config = json.loads(resolve_config_path().read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None

    if not isinstance(config, dict):
        return None
    channels = config.get("channels")
    if not isinstance(channels, dict):
        return None
    section = channels.get(CHANNEL_KEY)
    if not isinstance(section, dict):
        return None

    if account_id:
        accounts = section.get("accounts")
        if isinstance(accounts, dict):
            account_section = accounts.get(account_id)
            if isinstance(account_section, dict):
                route_tag = account_section.get("routeTag")
                if isinstance(route_tag, (str, int)) and str(route_tag).strip():
                    return str(route_tag).strip()

    route_tag = section.get("routeTag")
    if isinstance(route_tag, (str, int)) and str(route_tag).strip():
        return str(route_tag).strip()
    return None


def load_config_bot_agent() -> str | None:
    try:
        config = json.loads(resolve_config_path().read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None

    if not isinstance(config, dict):
        return None
    channels = config.get("channels")
    if not isinstance(channels, dict):
        return None
    section = channels.get(CHANNEL_KEY)
    if not isinstance(section, dict):
        return None

    bot_agent = section.get("botAgent")
    if isinstance(bot_agent, str) and bot_agent.strip():
        return bot_agent.strip()
    return None


def get_sync_buf_path(account_id: str) -> Path:
    return resolve_accounts_dir() / f"{account_id}.sync.json"


def load_get_updates_buf(account_id: str) -> str | None:
    primary = _read_sync_buf(get_sync_buf_path(account_id))
    if primary is not None:
        return primary

    raw_id = derive_raw_account_id(account_id)
    if raw_id:
        compat = _read_sync_buf(get_sync_buf_path(raw_id))
        if compat is not None:
            return compat

    legacy = (
        resolve_state_dir()
        / "agents"
        / "default"
        / "sessions"
        / ".openclaw-weixin-sync"
        / "default.json"
    )
    return _read_sync_buf(legacy)


def _read_sync_buf(path: Path) -> str | None:
    try:
        payload = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    value = payload.get("get_updates_buf")
    return value if isinstance(value, str) else None


def save_get_updates_buf(account_id: str, get_updates_buf: str) -> None:
    sync_path = get_sync_buf_path(account_id)
    sync_path.parent.mkdir(parents=True, exist_ok=True)
    sync_path.write_text(json.dumps({"get_updates_buf": get_updates_buf}))


def resolve_account(account_id: str | None) -> ResolvedWeixinAccount:
    if not account_id or not account_id.strip():
        raise ValueError("account_id is required")
    normalized_id = normalize_account_id(account_id)
    account_data = load_account(normalized_id)
    token = None
    base_url = DEFAULT_BASE_URL
    if account_data:
        token = (account_data.token or "").strip() or None
        base_url = (account_data.base_url or "").strip() or DEFAULT_BASE_URL
    return ResolvedWeixinAccount(
        account_id=normalized_id,
        base_url=base_url,
        cdn_base_url=CDN_BASE_URL,
        token=token,
        enabled=True,
        configured=bool(token),
    )
