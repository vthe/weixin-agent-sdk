from __future__ import annotations

import base64
import hashlib
import mimetypes
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from weixin_agent.api import WeixinApiClient

UPLOAD_MEDIA_IMAGE = 1
UPLOAD_MEDIA_VIDEO = 2
UPLOAD_MEDIA_FILE = 3
UPLOAD_MEDIA_VOICE = 4

MESSAGE_ITEM_IMAGE = 2
MESSAGE_ITEM_VOICE = 3
MESSAGE_ITEM_FILE = 4
MESSAGE_ITEM_VIDEO = 5

WEIXIN_MEDIA_TEMP_DIR = Path(tempfile.gettempdir()) / "weixin-agent" / "media"


@dataclass(slots=True)
class UploadedFileInfo:
    filekey: str
    download_encrypted_query_param: str
    aes_key_hex: str
    file_size: int
    file_size_ciphertext: int


def encrypt_aes_ecb(plaintext: bytes, key: bytes) -> bytes:
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    cipher = Cipher(algorithms.AES(key), modes.ECB())
    encryptor = cipher.encryptor()
    return encryptor.update(padded) + encryptor.finalize()


def decrypt_aes_ecb(ciphertext: bytes, key: bytes) -> bytes:
    cipher = Cipher(algorithms.AES(key), modes.ECB())
    decryptor = cipher.decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


def aes_ecb_padded_size(plaintext_size: int) -> int:
    return ((plaintext_size // 16) + 1) * 16


def get_mime_from_filename(filename: str) -> str:
    mime, _ = mimetypes.guess_type(filename)
    return mime or "application/octet-stream"


def get_extension_from_mime(mime_type: str | None, fallback_name: str = "") -> str:
    if fallback_name:
        suffix = Path(fallback_name).suffix
        if suffix:
            return suffix
    if mime_type:
        suffix = mimetypes.guess_extension(mime_type.split(";")[0].strip())
        if suffix:
            return suffix
    return ".bin"


def build_cdn_download_url(encrypted_query_param: str, cdn_base_url: str) -> str:
    encoded = quote(encrypted_query_param, safe="")
    return f"{cdn_base_url.rstrip('/')}/download?encrypted_query_param={encoded}"


def build_cdn_upload_url(cdn_base_url: str, upload_param: str, filekey: str) -> str:
    base = cdn_base_url.rstrip("/")
    params = httpx.QueryParams(
        {"encrypted_query_param": upload_param, "filekey": filekey},
    )
    return f"{base}/upload?{params}"


def parse_aes_key(aes_key_base64: str) -> bytes:
    decoded = base64.b64decode(aes_key_base64)
    if len(decoded) == 16:
        return decoded
    if len(decoded) == 32 and all(chr(ch) in "0123456789abcdefABCDEF" for ch in decoded):
        return bytes.fromhex(decoded.decode("ascii"))
    raise ValueError("aes_key must decode to 16 raw bytes or 32-char hex string")


async def fetch_cdn_bytes(url: str) -> bytes:
    async with httpx.AsyncClient(follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.content


def resolve_media_ref(media: object) -> tuple[str | None, str | None]:
    """Return (full_url, encrypt_query_param) from a media dict, or (None, None)."""
    if not isinstance(media, dict):
        return None, None
    full_url = media.get("full_url")
    full_url = full_url if isinstance(full_url, str) and full_url else None
    encrypt_query_param = media.get("encrypt_query_param")
    encrypt_query_param = encrypt_query_param if isinstance(encrypt_query_param, str) and encrypt_query_param else None
    return full_url, encrypt_query_param


async def download_and_decrypt_buffer(
    encrypted_query_param: str,
    aes_key_base64: str,
    cdn_base_url: str,
    full_url: str | None = None,
) -> bytes:
    url = full_url or build_cdn_download_url(encrypted_query_param, cdn_base_url)
    encrypted = await fetch_cdn_bytes(url)
    return decrypt_aes_ecb(encrypted, parse_aes_key(aes_key_base64))


async def download_plain_cdn_buffer(
    encrypted_query_param: str,
    cdn_base_url: str,
    full_url: str | None = None,
) -> bytes:
    url = full_url or build_cdn_download_url(encrypted_query_param, cdn_base_url)
    return await fetch_cdn_bytes(url)


async def save_media_buffer(
    buffer: bytes,
    *,
    content_type: str | None = None,
    subdir: str,
    original_filename: str | None = None,
) -> Path:
    directory = WEIXIN_MEDIA_TEMP_DIR / subdir
    directory.mkdir(parents=True, exist_ok=True)
    extension = get_extension_from_mime(content_type, original_filename or "")
    filename = f"{os.urandom(6).hex()}{extension}"
    path = directory / filename
    path.write_bytes(buffer)
    return path


async def download_remote_media_to_temp(url: str, subdir: str) -> Path:
    async with httpx.AsyncClient(follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        content_type = response.headers.get("content-type")
        parsed = urlparse(url)
        path = await save_media_buffer(
            response.content,
            content_type=content_type,
            subdir=subdir,
            original_filename=Path(parsed.path).name,
        )
        return path


async def download_media_from_item(
    item: dict[str, object],
    cdn_base_url: str,
) -> tuple[Path, str, str | None] | None:
    item_type = item.get("type")

    if item_type == MESSAGE_ITEM_IMAGE:
        image_item = item.get("image_item")
        if not isinstance(image_item, dict):
            return None
        media = image_item.get("media")
        full_url, encrypted_query_param = resolve_media_ref(media)
        if not full_url and not encrypted_query_param:
            return None
        aes_key = None
        raw_hex_key = image_item.get("aeskey")
        if isinstance(raw_hex_key, str) and raw_hex_key:
            aes_key = base64.b64encode(bytes.fromhex(raw_hex_key)).decode()
        else:
            candidate = media.get("aes_key") if isinstance(media, dict) else None
            if isinstance(candidate, str) and candidate:
                aes_key = candidate
        buffer = (
            await download_and_decrypt_buffer(
                encrypted_query_param or "", aes_key, cdn_base_url, full_url=full_url
            )
            if aes_key
            else await download_plain_cdn_buffer(
                encrypted_query_param or "", cdn_base_url, full_url=full_url
            )
        )
        path = await save_media_buffer(buffer, subdir="inbound")
        return path, "image/*", None

    if item_type == MESSAGE_ITEM_VOICE:
        voice_item = item.get("voice_item")
        if not isinstance(voice_item, dict):
            return None
        media = voice_item.get("media")
        full_url, encrypted_query_param = resolve_media_ref(media)
        aes_key = media.get("aes_key") if isinstance(media, dict) else None
        if (not full_url and not encrypted_query_param) or not isinstance(aes_key, str) or not aes_key:
            return None
        buffer = await download_and_decrypt_buffer(
            encrypted_query_param or "", aes_key, cdn_base_url, full_url=full_url
        )
        path = await save_media_buffer(
            buffer,
            content_type="audio/silk",
            subdir="inbound",
            original_filename="voice.silk",
        )
        return path, "audio/silk", None

    if item_type == MESSAGE_ITEM_FILE:
        file_item = item.get("file_item")
        if not isinstance(file_item, dict):
            return None
        media = file_item.get("media")
        full_url, encrypted_query_param = resolve_media_ref(media)
        aes_key = media.get("aes_key") if isinstance(media, dict) else None
        file_name = file_item.get("file_name")
        if (not full_url and not encrypted_query_param) or not isinstance(aes_key, str) or not aes_key:
            return None
        buffer = await download_and_decrypt_buffer(
            encrypted_query_param or "", aes_key, cdn_base_url, full_url=full_url
        )
        mime_type = (
            get_mime_from_filename(file_name)
            if isinstance(file_name, str)
            else "application/octet-stream"
        )
        path = await save_media_buffer(
            buffer,
            content_type=mime_type,
            subdir="inbound",
            original_filename=file_name if isinstance(file_name, str) else None,
        )
        return path, mime_type, file_name if isinstance(file_name, str) else None

    if item_type == MESSAGE_ITEM_VIDEO:
        video_item = item.get("video_item")
        if not isinstance(video_item, dict):
            return None
        media = video_item.get("media")
        full_url, encrypted_query_param = resolve_media_ref(media)
        aes_key = media.get("aes_key") if isinstance(media, dict) else None
        if (not full_url and not encrypted_query_param) or not isinstance(aes_key, str) or not aes_key:
            return None
        buffer = await download_and_decrypt_buffer(
            encrypted_query_param or "", aes_key, cdn_base_url, full_url=full_url
        )
        path = await save_media_buffer(
            buffer,
            content_type="video/mp4",
            subdir="inbound",
            original_filename="video.mp4",
        )
        return path, "video/mp4", None

    return None


async def upload_buffer_to_cdn(
    *,
    buffer: bytes,
    upload_param: str | None,
    filekey: str,
    cdn_base_url: str,
    aes_key: bytes,
    upload_full_url: str | None = None,
) -> str:
    ciphertext = encrypt_aes_ecb(buffer, aes_key)
    url = upload_full_url or build_cdn_upload_url(cdn_base_url, upload_param or "", filekey)
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for attempt in range(3):
            response = await client.post(
                url,
                content=ciphertext,
                headers={"Content-Type": "application/octet-stream"},
            )
            if response.status_code == 200:
                encrypted_param = response.headers.get("x-encrypted-param")
                if not encrypted_param:
                    raise ValueError("CDN upload response missing x-encrypted-param header")
                return encrypted_param
            if 400 <= response.status_code < 500:
                response.raise_for_status()
            if attempt == 2:
                response.raise_for_status()
    raise RuntimeError("unreachable")


async def upload_media_to_weixin(
    *,
    file_path: Path,
    to_user_id: str,
    api_client: WeixinApiClient,
    cdn_base_url: str,
    media_type: int,
    account_id: str | None = None,
) -> UploadedFileInfo:
    plaintext = file_path.read_bytes()
    rawsize = len(plaintext)
    rawfilemd5 = hashlib.md5(plaintext, usedforsecurity=False).hexdigest()
    filesize = aes_ecb_padded_size(rawsize)
    filekey = os.urandom(16).hex()
    aes_key = os.urandom(16)

    upload_url = await api_client.get_upload_url(
        {
            "filekey": filekey,
            "media_type": media_type,
            "to_user_id": to_user_id,
            "rawsize": rawsize,
            "rawfilemd5": rawfilemd5,
            "filesize": filesize,
            "no_need_thumb": True,
            "aeskey": aes_key.hex(),
        },
        account_id=account_id,
    )
    upload_param = upload_url.get("upload_param")
    upload_full_url = upload_url.get("upload_full_url")
    upload_param = upload_param if isinstance(upload_param, str) and upload_param else None
    upload_full_url = upload_full_url if isinstance(upload_full_url, str) and upload_full_url else None
    if not upload_param and not upload_full_url:
        raise ValueError("getUploadUrl returned no upload URL (need upload_full_url or upload_param)")

    download_param = await upload_buffer_to_cdn(
        buffer=plaintext,
        upload_param=upload_param,
        filekey=filekey,
        cdn_base_url=cdn_base_url,
        aes_key=aes_key,
        upload_full_url=upload_full_url,
    )
    return UploadedFileInfo(
        filekey=filekey,
        download_encrypted_query_param=download_param,
        aes_key_hex=aes_key.hex(),
        file_size=rawsize,
        file_size_ciphertext=filesize,
    )
