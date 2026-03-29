"""Send media files to Weixin via CDN upload."""

import os
from typing import Optional

from wechat_agent_sdk.cdn.upload import (
    upload_file_to_weixin,
    upload_video_to_weixin,
    upload_file_attachment_to_weixin,
)
from wechat_agent_sdk.media.mime import get_mime_from_filename
from wechat_agent_sdk.messaging.send import (
    send_image_message_weixin,
    send_video_message_weixin,
    send_file_message_weixin,
)
from wechat_agent_sdk.util.logger import logger


async def send_weixin_media_file(
    file_path: str,
    to: str,
    text: str,
    base_url: str,
    token: Optional[str],
    context_token: Optional[str],
    cdn_base_url: str,
) -> str:
    """Upload a local file and send it as a weixin message."""
    mime = get_mime_from_filename(file_path)
    file_name = os.path.basename(file_path)

    if mime.startswith("video/"):
        logger.info(f"[weixin] sendWeixinMediaFile: uploading video filePath={file_path} to={to}")
        uploaded = await upload_video_to_weixin(
            file_path=file_path,
            to_user_id=to,
            base_url=base_url,
            token=token,
            cdn_base_url=cdn_base_url,
        )
        logger.info(
            f"[weixin] sendWeixinMediaFile: video upload done filekey={uploaded.filekey} size={uploaded.file_size}"
        )
        return await send_video_message_weixin(
            to=to,
            text=text,
            uploaded={
                "downloadEncryptedQueryParam": uploaded.download_encrypted_query_param,
                "aeskey": uploaded.aeskey,
                "fileSize": uploaded.file_size,
                "fileSizeCiphertext": uploaded.file_size_ciphertext,
            },
            base_url=base_url,
            token=token,
            context_token=context_token,
        )

    if mime.startswith("image/"):
        logger.info(f"[weixin] sendWeixinMediaFile: uploading image filePath={file_path} to={to}")
        uploaded = await upload_file_to_weixin(
            file_path=file_path,
            to_user_id=to,
            base_url=base_url,
            token=token,
            cdn_base_url=cdn_base_url,
        )
        logger.info(
            f"[weixin] sendWeixinMediaFile: image upload done filekey={uploaded.filekey} size={uploaded.file_size}"
        )
        return await send_image_message_weixin(
            to=to,
            text=text,
            uploaded={
                "downloadEncryptedQueryParam": uploaded.download_encrypted_query_param,
                "aeskey": uploaded.aeskey,
                "fileSize": uploaded.file_size,
                "fileSizeCiphertext": uploaded.file_size_ciphertext,
            },
            base_url=base_url,
            token=token,
            context_token=context_token,
        )

    logger.info(
        f"[weixin] sendWeixinMediaFile: uploading file attachment filePath={file_path} name={file_name} to={to}"
    )
    uploaded = await upload_file_attachment_to_weixin(
        file_path=file_path,
        file_name=file_name,
        to_user_id=to,
        base_url=base_url,
        token=token,
        cdn_base_url=cdn_base_url,
    )
    logger.info(
        f"[weixin] sendWeixinMediaFile: file upload done filekey={uploaded.filekey} size={uploaded.file_size}"
    )
    return await send_file_message_weixin(
        to=to,
        text=text,
        file_name=file_name,
        uploaded={
            "downloadEncryptedQueryParam": uploaded.download_encrypted_query_param,
            "aeskey": uploaded.aeskey,
            "fileSize": uploaded.file_size,
            "fileSizeCiphertext": uploaded.file_size_ciphertext,
        },
        base_url=base_url,
        token=token,
        context_token=context_token,
    )
