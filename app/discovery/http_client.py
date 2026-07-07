import logging
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_url(url: str, *, timeout: float = 15.0) -> Optional[str]:
    try:
        with httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers=DEFAULT_HEADERS,
        ) as client:
            response = client.get(url)
            if response.status_code >= 400:
                logger.debug("HTTP %s for %s", response.status_code, url)
                return None
            return response.text
    except Exception as exc:
        logger.debug("Fetch failed for %s: %s", url, exc)
        return None
