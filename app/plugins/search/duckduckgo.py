import logging
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

from app.core.url_utils import is_blocked_domain
from app.discovery.types import SearchResult
from app.plugins.base import BaseSearchPlugin, register_search_plugin

logger = logging.getLogger(__name__)


@register_search_plugin
class DuckDuckGoSearchPlugin(BaseSearchPlugin):
    """Free HTML-based DuckDuckGo search — fallback when Google API is unavailable."""

    name = "duckduckgo"
    priority = 30

    def is_available(self) -> bool:
        return True

    def search(self, keyword: str, *, limit: int = 10) -> list[SearchResult]:
        results: list[SearchResult] = []
        try:
            with httpx.Client(timeout=15.0, follow_redirects=True) as client:
                response = client.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": keyword},
                    headers={"User-Agent": "Mozilla/5.0 OutreachBot/1.0"},
                )
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")

                for result_div in soup.select(".result"):
                    title_el = result_div.select_one(".result__a")
                    snippet_el = result_div.select_one(".result__snippet")
                    if not title_el:
                        continue

                    href = title_el.get("href", "")
                    url = self._resolve_url(href)
                    if not url or is_blocked_domain(url):
                        continue

                    results.append(
                        SearchResult(
                            title=title_el.get_text(strip=True),
                            url=url,
                            snippet=snippet_el.get_text(strip=True) if snippet_el else "",
                            source=self.name,
                        )
                    )
                    if len(results) >= limit:
                        break
        except Exception as exc:
            logger.warning("DuckDuckGo search failed for '%s': %s", keyword, exc)

        return results

    def _resolve_url(self, href: str) -> str:
        if href.startswith("//duckduckgo.com/l/"):
            parsed = urlparse("https:" + href)
            params = parse_qs(parsed.query)
            uddg = params.get("uddg", [""])[0]
            return unquote(uddg)
        if href.startswith("http"):
            return href
        return ""
