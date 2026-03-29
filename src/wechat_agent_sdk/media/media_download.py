"""Media download from Weixin CDN."""

import base64
import os
from typing import Any, Dict, Optional

from wechat_agent_sdk.cdn.pic_decrypt import download_and_decrypt_buffer, download_plain_cdn_buffer
from wechat_agent_sdk.media.mime import get_mime_from_filename
from wechat_agent_sdk.media.silk_transcode import silk_to_wav
from wechat_agent_sdk.util.logger import logger
from wechat_agent_sdk.api.types import MessageItemType


WEIXIN_MEDIA_MAX_BYTES = 100 * 1024 * 1024

MEDIA_TEMP_DIR = "/tmp/weixin-agent/media"


async def _save_media_buffer(
    buffer: bytes,
    content_type: Optional[str] = None,
    subdir: Optional[str] = None,
    max_bytes: int = WEIXIN_MEDIA_MAX_BYTES,
    original_filename: Optional[str] = None,
) -> Dict[str, str]:
    """Save a buffer to a temporary file."""
    directory = os.path.join(MEDIA_TEMP_DIR, subdir or "")
    os.makedirs(directory, exist_ok=True)

    if original_filename:
        _, ext = os.path.splitext(original_filename)
        ext = ext if ext else ".bin"
    elif content_type:
        from wechat_agent_sdk.media.mime import get_extension_from_mime
        ext = get_extension_from_mime(content_type)
    else:
        ext = ".bin"

    name = f"{int(__import__('time').time() * 1000)}-{os.urandom(4).hex()}{ext}"
    file_path = os.path.join(directory, name)
    with open(file_path, "wb") as f:
        f.write(buffer)

    return {"path": file_path}


class WeixinInboundMediaOpts:
    decrypted_pic_path: Optional[str] = None
    decrypted_voice_path: Optional[str] = None
    voice_media_type: Optional[str] = None
    decrypted_file_path: Optional[str] = None
    file_media_type: Optional[str] = None
    decrypted_video_path: Optional[str] = None


async def download_media_from_item(
    item: Dict[str, Any],
    cdn_base_url: str,
    label: str = "",
) -> WeixinInboundMediaOpts:
    """Download and decrypt media from a single MessageItem."""
    result = WeixinInboundMediaOpts()

    item_type = item.get("type")

    if item_type == MessageItemType["IMAGE"]:
        img = item.get("image_item", {})
        media = img.get("media", {}) or {}
        encrypt_query = media.get("encrypt_query_param")
        if not encrypt_query:
            return result

        aes_key_base64 = img.get("aeskey")
        if aes_key_base64:
            aes_key_base64 = base64.b64encode(bytes.fromhex(aes_key_base64)).decode()
        else:
            aes_key_base64 = media.get("aes_key")

        logger.debug(
            f"{label} image: encrypt_query_param={encrypt_query[:40]}... "
            f"hasAesKey={bool(aes_key_base64)}"
        )

        try:
            buf = None
            if aes_key_base64:
                buf = await download_and_decrypt_buffer(
                    encrypt_query, aes_key_base64, cdn_base_url, f"{label} image"
                )
            else:
                buf = await download_plain_cdn_buffer(encrypt_query, cdn_base_url, f"{label} image-plain")

            saved = await _save_media_buffer(buf, None, "inbound", WEIXIN_MEDIA_MAX_BYTES)
            result.decrypted_pic_path = saved["path"]
            logger.debug(f"{label} image saved: {saved['path']}")
        except Exception as e:
            logger.error(f"{label} image download/decrypt failed: {e}")

    elif item_type == MessageItemType["VOICE"]:
        voice = item.get("voice_item", {})
        media = voice.get("media", {}) or {}
        encrypt_query = media.get("encrypt_query_param")
        aes_key = media.get("aes_key")
        if not encrypt_query or not aes_key:
            return result

        try:
            silk_buf = await download_and_decrypt_buffer(
                encrypt_query, aes_key, cdn_base_url, f"{label} voice"
            )
            logger.debug(f"{label} voice: decrypted {len(silk_buf)} bytes, attempting silk transcode")

            wav_buf = await silk_to_wav(silk_buf)
            if wav_buf:
                saved = await _save_media_buffer(wav_buf, "audio/wav", "inbound", WEIXIN_MEDIA_MAX_BYTES)
                result.decrypted_voice_path = saved["path"]
                result.voice_media_type = "audio/wav"
                logger.debug(f"{label} voice: saved WAV to {saved['path']}")
            else:
                saved = await _save_media_buffer(silk_buf, "audio/silk", "inbound", WEIXIN_MEDIA_MAX_BYTES)
                result.decrypted_voice_path = saved["path"]
                result.voice_media_type = "audio/silk"
                logger.debug(f"{label} voice: silk transcode unavailable, saved raw SILK to {saved['path']}")
        except Exception as e:
            logger.error(f"{label} voice download/transcode failed: {e}")

    elif item_type == MessageItemType["FILE"]:
        file_item = item.get("file_item", {})
        media = file_item.get("media", {}) or {}
        encrypt_query = media.get("encrypt_query_param")
        aes_key = media.get("aes_key")
        if not encrypt_query or not aes_key:
            return result

        try:
            buf = await download_and_decrypt_buffer(
                encrypt_query, aes_key, cdn_base_url, f"{label} file"
            )
            file_name = file_item.get("file_name", "file.bin")
            mime = get_mime_from_filename(file_name)
            saved = await _save_media_buffer(
                buf, mime, "inbound", WEIXIN_MEDIA_MAX_BYTES, file_name
            )
            result.decrypted_file_path = saved["path"]
            result.file_media_type = mime
            logger.debug(f"{label} file: saved to {saved['path']} mime={mime}")
        except Exception as e:
            logger.error(f"{label} file download failed: {e}")

    elif item_type == MessageItemType["VIDEO"]:
        video_item = item.get("video_item", {})
        media = video_item.get("media", {}) or {}
        encrypt_query = media.get("encrypt_query_param")
        aes_key = media.get("aes_key")
        if not encrypt_query or not aes_key:
            return result

        try:
            buf = await download_and_decrypt_buffer(
                encrypt_query, aes_key, cdn_base_url, f"{label} video"
            )
            saved = await _save_media_buffer(buf, "video/mp4", "inbound", WEIXIN_MEDIA_MAX_BYTES)
            result.decrypted_video_path = saved["path"]
            logger.debug(f"{label} video: saved to {saved['path']}")
        except Exception as e:
            logger.error(f"{label} video download failed: {e}")

    return result
