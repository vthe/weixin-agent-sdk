"""WeChat protocol types (mirrors proto: GetUpdatesReq/Resp, WeixinMessage, SendMessageReq)."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


UploadMediaType = {
    "IMAGE": 1,
    "VIDEO": 2,
    "FILE": 3,
    "VOICE": 4,
}


MessageType = {
    "NONE": 0,
    "USER": 1,
    "BOT": 2,
}


MessageItemType = {
    "NONE": 0,
    "TEXT": 1,
    "IMAGE": 2,
    "VOICE": 3,
    "FILE": 4,
    "VIDEO": 5,
}


MessageState = {
    "NEW": 0,
    "GENERATING": 1,
    "FINISH": 2,
}


TypingStatus = {
    "TYPING": 1,
    "CANCEL": 2,
}


@dataclass
class BaseInfo:
    channel_version: Optional[str] = None


@dataclass
class CDNMedia:
    encrypt_query_param: Optional[str] = None
    aes_key: Optional[str] = None
    encrypt_type: Optional[int] = None


@dataclass
class TextItem:
    text: Optional[str] = None


@dataclass
class ImageItem:
    media: Optional[CDNMedia] = None
    thumb_media: Optional[CDNMedia] = None
    aeskey: Optional[str] = None
    url: Optional[str] = None
    mid_size: Optional[int] = None
    thumb_size: Optional[int] = None
    thumb_height: Optional[int] = None
    thumb_width: Optional[int] = None
    hd_size: Optional[int] = None


@dataclass
class VoiceItem:
    media: Optional[CDNMedia] = None
    encode_type: Optional[int] = None
    bits_per_sample: Optional[int] = None
    sample_rate: Optional[int] = None
    playtime: Optional[int] = None
    text: Optional[str] = None


@dataclass
class FileItem:
    media: Optional[CDNMedia] = None
    file_name: Optional[str] = None
    md5: Optional[str] = None
    len: Optional[str] = None


@dataclass
class VideoItem:
    media: Optional[CDNMedia] = None
    video_size: Optional[int] = None
    play_length: Optional[int] = None
    video_md5: Optional[str] = None
    thumb_media: Optional[CDNMedia] = None
    thumb_size: Optional[int] = None
    thumb_height: Optional[int] = None
    thumb_width: Optional[int] = None


@dataclass
class RefMessage:
    message_item: Optional["MessageItem"] = None
    title: Optional[str] = None


@dataclass
class MessageItem:
    type: Optional[int] = None
    create_time_ms: Optional[int] = None
    update_time_ms: Optional[int] = None
    is_completed: Optional[bool] = None
    msg_id: Optional[str] = None
    ref_msg: Optional[RefMessage] = None
    text_item: Optional[TextItem] = None
    image_item: Optional[ImageItem] = None
    voice_item: Optional[VoiceItem] = None
    file_item: Optional[FileItem] = None
    video_item: Optional[VideoItem] = None


@dataclass
class WeixinMessage:
    seq: Optional[int] = None
    message_id: Optional[int] = None
    from_user_id: Optional[str] = None
    to_user_id: Optional[str] = None
    client_id: Optional[str] = None
    create_time_ms: Optional[int] = None
    update_time_ms: Optional[int] = None
    delete_time_ms: Optional[int] = None
    session_id: Optional[str] = None
    group_id: Optional[str] = None
    message_type: Optional[int] = None
    message_state: Optional[int] = None
    item_list: Optional[List[MessageItem]] = None
    context_token: Optional[str] = None


@dataclass
class GetUpdatesReq:
    sync_buf: Optional[str] = None
    get_updates_buf: Optional[str] = None


@dataclass
class GetUpdatesResp:
    ret: Optional[int] = None
    errcode: Optional[int] = None
    errmsg: Optional[str] = None
    msgs: Optional[List[WeixinMessage]] = None
    sync_buf: Optional[str] = None
    get_updates_buf: Optional[str] = None
    longpolling_timeout_ms: Optional[int] = None


@dataclass
class SendMessageReq:
    msg: Optional[WeixinMessage] = None


@dataclass
class SendMessageResp:
    pass


@dataclass
class SendTypingReq:
    ilink_user_id: Optional[str] = None
    typing_ticket: Optional[str] = None
    status: Optional[int] = None


@dataclass
class SendTypingResp:
    ret: Optional[int] = None
    errmsg: Optional[str] = None


@dataclass
class GetConfigResp:
    ret: Optional[int] = None
    errmsg: Optional[str] = None
    typing_ticket: Optional[str] = None


@dataclass
class GetUploadUrlReq:
    filekey: Optional[str] = None
    media_type: Optional[int] = None
    to_user_id: Optional[str] = None
    rawsize: Optional[int] = None
    rawfilemd5: Optional[str] = None
    filesize: Optional[int] = None
    thumb_rawsize: Optional[int] = None
    thumb_rawfilemd5: Optional[str] = None
    thumb_filesize: Optional[int] = None
    no_need_thumb: Optional[bool] = None
    aeskey: Optional[str] = None


@dataclass
class GetUploadUrlResp:
    upload_param: Optional[str] = None
    thumb_upload_param: Optional[str] = None
