"""Proxy configuration for HTTP/SOCKS5."""

import os
import logging
from typing import Dict, Any

logger = logging.getLogger('ClipGen')


def apply_proxy(config: Dict[str, Any]) -> None:
    """Apply proxy settings to environment variables.

    Args:
        config: Config dict with proxy_enabled, proxy_type, proxy_string keys
    """
    # Clear existing proxy settings
    for var in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]:
        os.environ.pop(var, None)

    enabled = config.get("proxy_enabled", False)
    if not enabled:
        logger.info("Proxy: Disabled (Direct connection)")
        return

    proxy_type = config.get("proxy_type", "HTTP")
    proxy_string = config.get("proxy_string", "").strip()

    if not proxy_string:
        return

    # Clean up protocol prefixes
    proxy_string = (proxy_string
                    .replace("http://", "")
                    .replace("https://", "")
                    .replace("socks5://", ""))

    # Build full proxy URL
    if proxy_type == "SOCKS5":
        full_proxy = f"socks5://{proxy_string}"
    else:
        full_proxy = f"http://{proxy_string}"

    # Set environment variables
    os.environ["HTTP_PROXY"] = full_proxy
    os.environ["HTTPS_PROXY"] = full_proxy
    os.environ["http_proxy"] = full_proxy
    os.environ["https_proxy"] = full_proxy

    # Log without credentials
    safe_log = proxy_string.split('@')[-1] if '@' in proxy_string else proxy_string
    logger.info(f"Proxy applied: {proxy_type} -> {safe_log}")
