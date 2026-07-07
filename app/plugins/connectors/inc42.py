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

BASE_URL = "https://inc42.com"


@register_directory_connector
class Inc42Connector(BaseDirectoryConnector):
    name = "inc42"
    priority = 15

    def is_available(self) -> bool:
        return True

    def discover(self, keyword: str, *, limit: int = 10) -> List[ExtractedCompany]:
        companies: List[ExtractedCompany] = []
        search_url = f"{BASE_URL}/?s={quote_plus(keyword)}"
        html = fetch_url(search_url)
        if not html:
            html = fetch_url(f"{BASE_URL}/buzz/")
        if not html:
            return companies

        soup = BeautifulSoup(html, "html.parser")
        articles = soup.select(
            "article, div.post, div.card, li.post-item, div.buzz-item"
        )

        for article in articles:
            company = self._parse_article(article, keyword)
            if company:
                companies.append(company)
            if len(companies) >= limit:
                break

        if not companies:
            for anchor in soup.select("a[href*='inc42.com/buzz/'], a[href*='/20']"):
                title = anchor.get_text(strip=True)
                name = self._extract_company_name(title)
                if name and keyword.lower().split()[0] in title.lower():
                    companies.append(
                        ExtractedCompany(
                            name=name,
                            description=title,
                            source_url=urljoin(BASE_URL, anchor.get("href", "")),
                            strategy="INC42",
                            tags=self._tags(keyword),
                        )
                    )
                if len(companies) >= limit:
                    break

        return companies[:limit]

    def _parse_article(self, article, keyword: str) -> ExtractedCompany | None:
        title_el = article.select_one("h1, h2, h3, h4, .entry-title, a")
        if not title_el:
            return None
        title = title_el.get_text(strip=True)
        name = self._extract_company_name(title)
        if not name:
            return None

        desc_el = article.select_one("p, .excerpt, .summary")
        description = desc_el.get_text(strip=True) if desc_el else title

        link = article.select_one("a[href]")
        source_url = urljoin(BASE_URL, link["href"]) if link else BASE_URL

        website = None
        for anchor in article.select("a[href*='http']"):
            href = anchor.get("href", "")
            if "inc42.com" not in href:
                website = normalize_website(href)
                break

        return ExtractedCompany(
            name=name,
            website=website,
            description=description,
            source_url=source_url,
            strategy="INC42",
            tags=self._tags(keyword),
        )

    def _extract_company_name(self, title: str) -> str | None:
        patterns = [
            r"^([A-Z][A-Za-z0-9&\s]{2,40}?)(?:\s+(?:raises|bags|secures|launches|acquires|gets))",
            r"^([A-Z][A-Za-z0-9&\s]{2,40}?)(?:\s*[-–—|])",
        ]
        for pattern in patterns:
            match = re.match(pattern, title, re.I)
            if match:
                return match.group(1).strip()
        if 3 <= len(title) <= 60 and title[0].isupper():
            return title.split(" - ")[0].strip()
        return None

    def _tags(self, keyword: str) -> List[str]:
        tags = ["Startup", "Startup News"]
        for tag in ("FinTech", "AI", "SaaS", "D2C", "B2B"):
            if tag.lower() in keyword.lower():
                tags.append(tag)
        return tags
