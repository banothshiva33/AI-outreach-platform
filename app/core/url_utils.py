import ipaddress
import socket
from typing import Optional
from urllib.parse import urlparse

BLOCKED_DOMAINS = {
    "facebook.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "wikipedia.org",
    "linkedin.com",
    "instagram.com",
    "reddit.com",
}


def normalize_website(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    raw = url.strip().lower().rstrip("/")
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    domain = parsed.netloc.lower().replace("www.", "")
    if not domain:
        return None
    return f"https://{domain}"


def normalize_domain(url: Optional[str]) -> Optional[str]:
    normalized = normalize_website(url)
    if not normalized:
        return None
    return urlparse(normalized).netloc


def is_blocked_domain(url: str) -> bool:
    domain = urlparse(url).netloc.lower().replace("www.", "")
    return any(blocked in domain for blocked in BLOCKED_DOMAINS)


def is_safe_url(url: str) -> bool:
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        return False
    hostname = parsed.hostname
    if not hostname:
        return False
    if hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
        return False
    try:
        for info in socket.getaddrinfo(hostname, None):
            ip = ipaddress.ip_address(info[4][0])
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
            ):
                return False
    except (socket.gaierror, ValueError):
        return False
    return True
