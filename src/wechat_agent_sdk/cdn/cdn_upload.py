"""CDN upload with AES-128-ECB encryption."""

import base64
import urllib.request
import urllib.error
from typing import Optional

from wechat_agent_sdk.cdn.aes_ecb import encrypt_aes_ecb
from wechat_agent_sdk.cdn.cdn_url import build_cdn_upload_url
from wechat_agent_sdk.util.logger import logger


UPLOAD_MAX_RETRIES = 3


async def upload_buffer_to_cdn(
    buf: bytes,
    upload_param: str,
    filekey: str,
    cdn_base_url: str,
    aeskey: bytes,
    label: str = "",
) -> str:
    """Upload one buffer to the Weixin CDN with AES-128-ECB encryption."""
    ciphertext = encrypt_aes_ecb(buf, aeskey)
    cdn_url = build_cdn_upload_url(cdn_base_url, upload_param, filekey)
    logger.debug(
        f"{label}: CDN POST url={cdn_url} ciphertextSize={len(ciphertext)}"
    )

    download_param: Optional[str] = None
    last_error: Optional[Exception] = None

    for attempt in range(1, UPLOAD_MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(
                cdn_url,
                data=ciphertext,
                headers={"Content-Type": "application/octet-stream"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status >= 400 and resp.status < 500:
                    err_msg = resp.headers.get("x-error-message", "") or "(no message)"
                    logger.error(
                        f"{label}: CDN client error attempt={attempt} status={resp.status} errMsg={err_msg}"
                    )
                    raise Exception(f"CDN upload client error {resp.status}: {err_msg}")
                if resp.status != 200:
                    err_msg = resp.headers.get("x-error-message", f"status {resp.status}")
                    logger.error(
                        f"{label}: CDN server error attempt={attempt} status={resp.status} errMsg={err_msg}"
                    )
                    raise Exception(f"CDN upload server error: {err_msg}")
                download_param = resp.headers.get("x-encrypted-param")
                if not download_param:
                    logger.error(
                        f"{label}: CDN response missing x-encrypted-param header attempt={attempt}"
                    )
                    raise Exception("CDN upload response missing x-encrypted-param header")
                logger.debug(f"{label}: CDN upload success attempt={attempt}")
                break
        except Exception as e:
            last_error = e
            if "client error" in str(e):
                raise
            if attempt < UPLOAD_MAX_RETRIES:
                logger.error(f"{label}: attempt {attempt} failed, retrying... err={e}")
            else:
                logger.error(f"{label}: all {UPLOAD_MAX_RETRIES} attempts failed err={e}")

    if not download_param:
        raise last_error or Exception(f"CDN upload failed after {UPLOAD_MAX_RETRIES} attempts")

    return download_param
