import logging
import re
from typing import List
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup

from app.core.url_utils import normalize_website
from app.discovery.http_client import fetch_url
from app.discovery.types import ExtractedCompany
from app.plugins.base import BaseDirectoryConnector, register_directory_connector

logger = logging.getLogger(__name__)

BASE_URL = "https://www.startupindia.gov.in"


@register_directory_connector
class StartupIndiaConnector(BaseDirectoryConnector):
    name = "startup_india"
    priority = 10

    def is_available(self) -> bool:
        return True

    def discover(self, keyword: str, *, limit: int = 10) -> List[ExtractedCompany]:
        companies: List[ExtractedCompany] = []
        search_url = (
            f"{BASE_URL}/content/sih/en/search.html"
            f"?searchTerm={quote_plus(keyword)}"
        )
        html = fetch_url(search_url)
        if not html:
            html = fetch_url(f"{BASE_URL}/content/sih/en/startup-scheme.html")
        if not html:
            return companies

        soup = BeautifulSoup(html, "html.parser")
        for card in soup.select(
            "div.startup-card, div.search-result, article, div.card, li.search-item"
        ):
            company = self._parse_card(card, keyword)
            if company:
                companies.append(company)
            if len(companies) >= limit:
                break

        if not companies:
            companies = self._parse_links(soup, keyword, limit=limit)

        return companies[:limit]

    def _parse_card(self, card, keyword: str) -> ExtractedCompany | None:
        title_el = card.select_one("h2, h3, h4, .title, .startup-name, a")
        if not title_el:
            return None
        name = title_el.get_text(strip=True)
        if len(name) < 3:
            return None

        website = None
        link = card.select_one("a[href*='http']")
        if link:
            href = link.get("href", "")
            if "startupindia.gov.in" not in href:
                website = normalize_website(href)

        desc_el = card.select_one("p, .description, .summary")
        description = desc_el.get_text(strip=True) if desc_el else None

        return ExtractedCompany(
            name=name,
            website=website,
            description=description,
            source_url=BASE_URL,
            strategy="STARTUP_INDIA",
            tags=self._tags(keyword),
        )

    def _parse_links(self, soup: BeautifulSoup, keyword: str, *, limit: int) -> List[ExtractedCompany]:
        companies = []
        pattern = re.compile(r"(?:startup|founder|company)", re.I)
        for anchor in soup.find_all("a", href=True):
            text = anchor.get_text(strip=True)
            if len(text) < 4 or len(text) > 80:
                continue
            if not pattern.search(text) and keyword.lower() not in text.lower():
                continue
            href = anchor["href"]
            if href.startswith("/"):
                href = urljoin(BASE_URL, href)
            companies.append(
                ExtractedCompany(
                    name=text,
                    website=normalize_website(href) if "startupindia" not in href else None,
                    source_url=href,
                    strategy="STARTUP_INDIA",
                    tags=self._tags(keyword),
                )
            )
            if len(companies) >= limit:
                break
        return companies

    def _tags(self, keyword: str) -> List[str]:
        tags = ["Startup India", "Startup"]
        if "ai" in keyword.lower():
            tags.append("AI Startup")
        return tags
