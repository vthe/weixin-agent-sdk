"""Media file upload to Weixin CDN."""

import hashlib
import os
import urllib.request
from dataclasses import dataclass
from typing import Optional

from wechat_agent_sdk.api.api import get_upload_url
from wechat_agent_sdk.cdn.aes_ecb import aes_ecb_padded_size
from wechat_agent_sdk.cdn.cdn_upload import upload_buffer_to_cdn
from wechat_agent_sdk.media.mime import get_extension_from_content_type_or_url
from wechat_agent_sdk.util.logger import logger
from wechat_agent_sdk.util.random import temp_file_name
from wechat_agent_sdk.api.types import UploadMediaType


@dataclass
class UploadedFileInfo:
    filekey: str
    download_encrypted_query_param: str
    aeskey: str
    file_size: int
    file_size_ciphertext: int


async def download_remote_image_to_temp(url: str, dest_dir: str) -> str:
    """Download a remote media URL to a local temp file."""
    logger.debug(f"downloadRemoteImageToTemp: fetching url={url}")
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            if not resp.ok:
                msg = f"remote media download failed: {resp.status} {resp.reason} url={url}"
                logger.error(f"downloadRemoteImageToTemp: {msg}")
                raise Exception(msg)
            buf = resp.read()
            logger.debug(f"downloadRemoteImageToTemp: downloaded {len(buf)} bytes")
    except urllib.error.HTTPError as e:
        msg = f"remote media download failed: {e.code} {e.reason} url={url}"
        logger.error(f"downloadRemoteImageToTemp: {msg}")
        raise

    os.makedirs(dest_dir, exist_ok=True)
    content_type = resp.headers.get("content-type") if hasattr(resp, "headers") else None
    ext = get_extension_from_content_type_or_url(content_type, url)
    name = temp_file_name("weixin-remote", ext)
    file_path = os.path.join(dest_dir, name)
    with open(file_path, "wb") as f:
        f.write(buf)
    logger.debug(f"downloadRemoteImageToTemp: saved to {file_path} ext={ext}")
    return file_path


async def _upload_media_to_cdn(
    file_path: str,
    to_user_id: str,
    base_url: str,
    token: Optional[str],
    cdn_base_url: str,
    media_type: int,
    label: str,
) -> UploadedFileInfo:
    """Common upload pipeline: read file → hash → gen aeskey → getUploadUrl → uploadBufferToCdn."""
    with open(file_path, "rb") as f:
        plaintext = f.read()

    raw_size = len(plaintext)
    raw_file_md5 = hashlib.md5(plaintext).hexdigest()
    file_size = aes_ecb_padded_size(raw_size)
    filekey = os.urandom(16).hex()
    aeskey = os.urandom(16)

    logger.debug(
        f"{label}: file={file_path} rawsize={raw_size} filesize={file_size} md5={raw_file_md5} filekey={filekey}"
    )

    upload_resp = await get_upload_url(
        base_url=base_url,
        token=token,
        filekey=filekey,
        media_type=media_type,
        to_user_id=to_user_id,
        rawsize=raw_size,
        rawfilemd5=raw_file_md5,
        filesize=file_size,
        no_need_thumb=True,
        aeskey=aeskey.hex(),
    )

    upload_param = upload_resp.get("upload_param")
    if not upload_param:
        logger.error(
            f"{label}: getUploadUrl returned no upload_param, resp={upload_resp}"
        )
        raise Exception(f"{label}: getUploadUrl returned no upload_param")

    download_param = await upload_buffer_to_cdn(
        buf=plaintext,
        upload_param=upload_param,
        filekey=filekey,
        cdn_base_url=cdn_base_url,
        aeskey=aeskey,
        label=f"{label}[orig filekey={filekey}]",
    )

    return UploadedFileInfo(
        filekey=filekey,
        download_encrypted_query_param=download_param,
        aeskey=aeskey.hex(),
        file_size=raw_size,
        file_size_ciphertext=file_size,
    )


async def upload_file_to_weixin(
    file_path: str,
    to_user_id: str,
    base_url: str,
    token: Optional[str],
    cdn_base_url: str,
) -> UploadedFileInfo:
    """Upload a local image file to the Weixin CDN with AES-128-ECB encryption."""
    return await _upload_media_to_cdn(
        file_path=file_path,
        to_user_id=to_user_id,
        base_url=base_url,
        token=token,
        cdn_base_url=cdn_base_url,
        media_type=UploadMediaType["IMAGE"],
        label="uploadFileToWeixin",
    )


async def upload_video_to_weixin(
    file_path: str,
    to_user_id: str,
    base_url: str,
    token: Optional[str],
    cdn_base_url: str,
) -> UploadedFileInfo:
    """Upload a local video file to the Weixin CDN."""
    return await _upload_media_to_cdn(
        file_path=file_path,
        to_user_id=to_user_id,
        base_url=base_url,
        token=token,
        cdn_base_url=cdn_base_url,
        media_type=UploadMediaType["VIDEO"],
        label="uploadVideoToWeixin",
    )


async def upload_file_attachment_to_weixin(
    file_path: str,
    file_name: str,
    to_user_id: str,
    base_url: str,
    token: Optional[str],
    cdn_base_url: str,
) -> UploadedFileInfo:
    """Upload a local file attachment (non-image, non-video) to the Weixin CDN."""
    return await _upload_media_to_cdn(
        file_path=file_path,
        to_user_id=to_user_id,
        base_url=base_url,
        token=token,
        cdn_base_url=cdn_base_url,
        media_type=UploadMediaType["FILE"],
        label="uploadFileAttachmentToWeixin",
    )
