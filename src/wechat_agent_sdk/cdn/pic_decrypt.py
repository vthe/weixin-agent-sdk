"""CDN download with AES-128-ECB decryption."""

import base64
import urllib.request
import urllib.error
from typing import Optional

from wechat_agent_sdk.cdn.aes_ecb import decrypt_aes_ecb
from wechat_agent_sdk.cdn.cdn_url import build_cdn_download_url
from wechat_agent_sdk.util.logger import logger


async def _fetch_cdn_bytes(url: str, label: str) -> bytes:
    """Download raw bytes from the CDN (no decryption)."""
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            logger.debug(f"{label}: response status={resp.status} ok={resp.ok}")
            if not resp.ok:
                body = resp.read().decode("utf-8", errors="replace")
                msg = f"{label}: CDN download {resp.status} {resp.reason} body={body}"
                logger.error(msg)
                raise Exception(msg)
            return resp.read()
    except urllib.error.URLError as e:
        logger.error(f"{label}: fetch network error url={url} err={e}")
        raise


def _parse_aes_key(aes_key_base64: str, label: str) -> bytes:
    """Parse CDNMedia.aes_key into a raw 16-byte AES key."""
    decoded = base64.b64decode(aes_key_base64)
    if len(decoded) == 16:
        return decoded
    if len(decoded) == 32 and decoded.hex().isalnum():
        return bytes.fromhex(decoded.hex())
    msg = f"{label}: aes_key must decode to 16 raw bytes or 32-char hex string, got {len(decoded)} bytes"
    logger.error(msg)
    raise ValueError(msg)


async def download_and_decrypt_buffer(
    encrypted_query_param: str,
    aes_key_base64: str,
    cdn_base_url: str,
    label: str = "",
) -> bytes:
    """Download and AES-128-ECB decrypt a CDN media file. Returns plaintext bytes."""
    key = _parse_aes_key(aes_key_base64, label)
    url = build_cdn_download_url(encrypted_query_param, cdn_base_url)
    logger.debug(f"{label}: fetching url={url}")
    encrypted = await _fetch_cdn_bytes(url, label)
    logger.debug(f"{label}: downloaded {len(encrypted)} bytes, decrypting")
    decrypted = decrypt_aes_ecb(encrypted, key)
    logger.debug(f"{label}: decrypted {len(decrypted)} bytes")
    return decrypted


async def download_plain_cdn_buffer(
    encrypted_query_param: str,
    cdn_base_url: str,
    label: str = "",
) -> bytes:
    """Download plain (unencrypted) bytes from the CDN."""
    url = build_cdn_download_url(encrypted_query_param, cdn_base_url)
    logger.debug(f"{label}: fetching url={url}")
    return await _fetch_cdn_bytes(url, label)
