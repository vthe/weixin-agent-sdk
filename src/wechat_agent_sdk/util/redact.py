"""Redaction utilities for safe logging."""

from typing import Optional
from urllib.parse import urlparse


DEFAULT_BODY_MAX_LEN = 200
DEFAULT_TOKEN_PREFIX_LEN = 6


def truncate(s: Optional[str], max_len: int) -> str:
    """Truncate a string, appending a length indicator when trimmed."""
    if not s:
        return ""
    if len(s) <= max_len:
        return s
    return f"{s[:max_len]}…(len={len(s)})"


def redact_token(token: Optional[str], prefix_len: int = DEFAULT_TOKEN_PREFIX_LEN) -> str:
    """Redact a token/secret: show only the first few chars + total length."""
    if not token:
        return "(none)"
    if len(token) <= prefix_len:
        return f"****(len={len(token)})"
    return f"{token[:prefix_len]}…(len={len(token)})"


def redact_body(body: Optional[str], max_len: int = DEFAULT_BODY_MAX_LEN) -> str:
    """Truncate a JSON body string to maxLen chars for safe logging."""
    if not body:
        return "(empty)"
    if len(body) <= max_len:
        return body
    return f"{body[:max_len]}…(truncated, totalLen={len(body)})"


def redact_url(raw_url: str) -> str:
    """Strip query string from a URL for safe logging."""
    try:
        u = urlparse(raw_url)
        base = f"{u.scheme}://{u.netloc}{u.path}"
        return f"{base}?<redacted>" if u.query else base
    except Exception:
        return truncate(raw_url, 80)
