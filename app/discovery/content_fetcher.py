import logging
import re
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_page_html(url: str, *, timeout: float = 20.0) -> Optional[str]:
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
            html = response.text
            if _needs_browser_render(html):
                rendered = _render_with_playwright(url, timeout=timeout)
                return rendered or html
            return html
    except Exception as exc:
        logger.debug("Fetch failed for %s: %s", url, exc)
        rendered = _render_with_playwright(url, timeout=timeout)
        return rendered


def _needs_browser_render(html: str) -> bool:
    if not html:
        return True
    lowered = html.lower()
    if "javascript" in lowered and len(html) < 5000:
        return True
    if "__next_data__" in lowered or "data-reactroot" in lowered:
        return True
    text = re.sub(r"<[^>]+>", " ", html)
    return len(text.split()) < 150 and len(html) > 1000


def _render_with_playwright(url: str, *, timeout: float = 20.0) -> Optional[str]:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        logger.debug("Playwright unavailable for %s: %s", url, exc)
        return None

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1800})
            page.goto(url, wait_until="networkidle", timeout=int(timeout * 1000))
            page.wait_for_load_state("domcontentloaded", timeout=int(timeout * 1000))
            html = page.content()
            browser.close()
            return html
    except PlaywrightTimeoutError:
        logger.debug("Playwright timed out for %s", url)
    except Exception as exc:
        logger.debug("Playwright render failed for %s: %s", url, exc)
    return None
