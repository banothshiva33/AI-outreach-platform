import logging
from typing import List
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup

from app.core.url_utils import normalize_website
from app.discovery.http_client import fetch_url
from app.discovery.types import ExtractedCompany
from app.plugins.base import BaseDirectoryConnector, register_directory_connector

logger = logging.getLogger(__name__)

BASE_URL = "https://yourstory.com"


@register_directory_connector
class YourStoryConnector(BaseDirectoryConnector):
    name = "yourstory"
    priority = 20

    def is_available(self) -> bool:
        return True

    def discover(self, keyword: str, *, limit: int = 10) -> List[ExtractedCompany]:
        companies: List[ExtractedCompany] = []
        search_url = f"{BASE_URL}/search?q={quote_plus(keyword)}"
        html = fetch_url(search_url)
        if not html:
            html = fetch_url(f"{BASE_URL}/search?category=startup")
        if not html:
            return companies

        soup = BeautifulSoup(html, "html.parser")
        articles = soup.select(
            "article, div.story-card, div.card, li.search-result, div.post-item"
        )

        for article in articles:
            company = self._parse_article(article, keyword)
            if company:
                companies.append(company)
            if len(companies) >= limit:
                break

        if not companies:
            for anchor in soup.select("a[href*='/20']"):
                title = anchor.get_text(strip=True)
                if len(title) < 10 or keyword.lower().split()[0] not in title.lower():
                    continue
                name = self._extract_company_from_title(title)
                if name:
                    companies.append(
                        ExtractedCompany(
                            name=name,
                            description=title,
                            source_url=urljoin(BASE_URL, anchor.get("href", "")),
                            strategy="YOURSTORY",
                            tags=self._tags(keyword),
                        )
                    )
                if len(companies) >= limit:
                    break

        return companies[:limit]

    def _parse_article(self, article, keyword: str) -> ExtractedCompany | None:
        title_el = article.select_one("h1, h2, h3, h4, .title, a")
        if not title_el:
            return None
        title = title_el.get_text(strip=True)
        name = self._extract_company_from_title(title)
        if not name:
            return None

        desc_el = article.select_one("p, .excerpt, .summary")
        description = desc_el.get_text(strip=True) if desc_el else title

        link = article.select_one("a[href]")
        source_url = urljoin(BASE_URL, link["href"]) if link else BASE_URL

        website = None
        ext_link = article.select_one("a[href*='http']:not([href*='yourstory'])")
        if ext_link:
            website = normalize_website(ext_link["href"])

        return ExtractedCompany(
            name=name,
            website=website,
            description=description,
            source_url=source_url,
            strategy="YOURSTORY",
            tags=self._tags(keyword),
        )

    def _extract_company_from_title(self, title: str) -> str | None:
        separators = [" - ", " | ", ": ", " raises ", " launches ", " bags ", " secures "]
        name = title
        for sep in separators:
            if sep in title.lower():
                idx = title.lower().index(sep)
                name = title[:idx].strip()
                break
        if 3 <= len(name) <= 80:
            return name
        return None

    def _tags(self, keyword: str) -> List[str]:
        tags = ["Startup", "Startup News"]
        for tag in ("FinTech", "AI", "SaaS", "EdTech", "HealthTech"):
            if tag.lower() in keyword.lower():
                tags.append(tag)
        return tags
