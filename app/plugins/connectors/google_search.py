import logging
from typing import List
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup

from app.discovery.types import SearchResult
from app.plugins.base import BaseSearchPlugin, register_search_plugin

logger = logging.getLogger(__name__)


@register_search_plugin
class GoogleSearchConnector(BaseSearchPlugin):
    """
    Google Search connector.
    Uses Google Custom Search API when configured, otherwise SerpAPI Google engine.
    """

    name = "google_search"
    priority = 1

    def is_available(self) -> bool:
        from app.core.config import settings
        return bool(
            (settings.GOOGLE_CSE_ID and settings.GOOGLE_API_KEY)
            or settings.SERPAPI_API_KEY
        )

    def search(self, keyword: str, *, limit: int = 10) -> List[SearchResult]:
        from app.core.config import settings

        if settings.GOOGLE_CSE_ID and settings.GOOGLE_API_KEY:
            return self._search_cse(keyword, limit=limit)
        if settings.SERPAPI_API_KEY:
            return self._search_serpapi(keyword, limit=limit)
        return []

    def _search_cse(self, keyword: str, *, limit: int) -> List[SearchResult]:
        from app.core.config import settings

        results: List[SearchResult] = []
        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.get(
                    "https://www.googleapis.com/customsearch/v1",
                    params={
                        "key": settings.GOOGLE_API_KEY,
                        "cx": settings.GOOGLE_CSE_ID,
                        "q": keyword,
                        "num": min(limit, 10),
                        "gl": "in",
                        "cr": "countryIN",
                    },
                )
                response.raise_for_status()
                for item in response.json().get("items", []):
                    results.append(
                        SearchResult(
                            title=item.get("title", ""),
                            url=item.get("link", ""),
                            snippet=item.get("snippet", ""),
                            source=self.name,
                        )
                    )
        except Exception as exc:
            logger.warning("Google CSE search failed for '%s': %s", keyword, exc)
        return results

    def _search_serpapi(self, keyword: str, *, limit: int) -> List[SearchResult]:
        from app.core.config import settings

        results: List[SearchResult] = []
        try:
            with httpx.Client(timeout=20.0) as client:
                response = client.get(
                    "https://serpapi.com/search",
                    params={
                        "api_key": settings.SERPAPI_API_KEY,
                        "q": keyword,
                        "num": min(limit, 10),
                        "engine": "google",
                        "google_domain": "google.co.in",
                        "gl": "in",
                    },
                )
                response.raise_for_status()
                for item in response.json().get("organic_results", []):
                    results.append(
                        SearchResult(
                            title=item.get("title", ""),
                            url=item.get("link", ""),
                            snippet=item.get("snippet", ""),
                            source=self.name,
                        )
                    )
        except Exception as exc:
            logger.warning("SerpAPI Google search failed for '%s': %s", keyword, exc)
        return results
