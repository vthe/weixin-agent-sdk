"""Unified CDN URL construction for Weixin CDN upload/download."""


def build_cdn_download_url(encrypted_query_param: str, cdn_base_url: str) -> str:
    """Build a CDN download URL from encrypt_query_param."""
    return f"{cdn_base_url}/download?encrypted_query_param={encrypted_query_param}"


def build_cdn_upload_url(cdn_base_url: str, upload_param: str, filekey: str) -> str:
    """Build a CDN upload URL from upload_param and filekey."""
    return f"{cdn_base_url}/upload?encrypted_query_param={upload_param}&filekey={filekey}"
