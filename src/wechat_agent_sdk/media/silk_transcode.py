"""SILK audio transcoding to WAV."""

import io
import struct
import wave
from typing import Optional

from wechat_agent_sdk.util.logger import logger


SILK_SAMPLE_RATE = 24000


def _pcm_bytes_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    """Wrap raw pcm_s16le bytes in a WAV container."""
    pcm_bytes = len(pcm)
    total_size = 44 + pcm_bytes
    buf = bytearray(total_size)
    offset = 0

    buf[offset:offset + 4] = b"RIFF"
    offset += 4
    struct.pack_into("<I", buf, offset, total_size - 8)
    offset += 4
    buf[offset:offset + 4] = b"WAVE"
    offset += 4

    buf[offset:offset + 4] = b"fmt "
    offset += 4
    struct.pack_into("<I", buf, offset, 16)
    offset += 4
    struct.pack_into("<H", buf, offset, 1)
    offset += 2
    struct.pack_into("<H", buf, offset, 1)
    offset += 2
    struct.pack_into("<I", buf, offset, sample_rate)
    offset += 4
    struct.pack_into("<I", buf, offset, sample_rate * 2)
    offset += 4
    struct.pack_into("<H", buf, offset, 2)
    offset += 2
    struct.pack_into("<H", buf, offset, 16)
    offset += 2

    buf[offset:offset + 4] = b"data"
    offset += 4
    struct.pack_into("<I", buf, offset, pcm_bytes)
    offset += 4

    buf[offset:offset + pcm_bytes] = pcm

    return bytes(buf)


async def silk_to_wav(silk_buf: bytes) -> Optional[bytes]:
    """Try to transcode a SILK audio buffer to WAV.

    Returns a WAV bytes on success, or None if silk-wasm is unavailable or decoding fails.
    Note: Python version uses basic SILK detection; full transcoding requires silk-python SDK.
    """
    try:
        logger.debug(f"silkToWav: attempting to decode {len(silk_buf)} bytes of SILK")

        try:
            import silk
            pcm_data = silk.decode(silk_buf, SILK_SAMPLE_RATE)
            wav = _pcm_bytes_to_wav(pcm_data, SILK_SAMPLE_RATE)
            logger.debug(f"silkToWav: WAV size={len(wav)}")
            return wav
        except ImportError:
            logger.warn("silk-python not installed, skipping SILK transcoding")
            return None
    except Exception as e:
        logger.warn(f"silkToWav: transcode failed, will use raw silk err={e}")
        return None
