"""Random ID and temp file name generation."""

import hashlib
import os
import time


def generate_id(prefix: str) -> str:
    """Generate a prefixed unique ID using timestamp + random bytes."""
    random_bytes = os.urandom(4).hex()
    return f"{prefix}:{int(time.time() * 1000)}-{random_bytes}"


def temp_file_name(prefix: str, ext: str) -> str:
    """Generate a temporary file name with random suffix."""
    random_bytes = os.urandom(4).hex()
    return f"{prefix}-{int(time.time() * 1000)}-{random_bytes}{ext}"
