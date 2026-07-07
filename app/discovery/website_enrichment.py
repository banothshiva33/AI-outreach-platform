import logging
import json
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from app.core.url_utils import is_safe_url, normalize_website
from app.discovery.content_fetcher import fetch_page_html
from app.discovery.website_parser import WebsiteParser

logger = logging.getLogger(__name__)


class WebsiteEnrichmentAgent:
    """Visits a company site and common supporting pages to collect every useful signal."""

    COMMON_PATHS = [
        "/",
        "/about",
        "/about-us",
        "/company",
        "/team",
        "/leadership",
        "/founders",
        "/careers",
        "/contact",
        "/privacy",
        "/footer",
        "/header",
    ]

    def __init__(self):
        self.website_parser = WebsiteParser()

    def enrich(self, website: str) -> Dict[str, Any]:
        normalized = normalize_website(website)
        if not normalized or not is_safe_url(normalized):
            return {}

        merged: Dict[str, Any] = {
            "description": None,
            "emails": [],
            "phones": [],
            "social_links": [],
            "founders": [],
            "locations": [],
            "pages_visited": [],
        }

        for path in self.COMMON_PATHS:
            page_url = urljoin(normalized + "/", path.lstrip("/"))
            html = fetch_page_html(page_url)
            if not html:
                continue

            data = self.website_parser.parse(page_url)
            if not data:
                continue

            merged["pages_visited"].append(page_url)
            self._merge_text_field(merged, data.get("description"))
            self._merge_unique(merged["emails"], data.get("emails", []))
            self._merge_unique(merged["phones"], data.get("phones", []))
            self._merge_socials(merged["social_links"], data.get("social_links", []))
            self._merge_founders(merged["founders"], data.get("founders", []))

            location = self._extract_location(data, html)
            if location and location not in merged["locations"]:
                merged["locations"].append(location)

        logger.info(
            json.dumps(
                {
                    "stage": "website_enrichment",
                    "event": "website_enriched",
                    "website": normalized,
                    "pages_visited": merged["pages_visited"],
                    "emails": merged["emails"],
                    "phones": merged["phones"],
                    "social_links": merged["social_links"],
                    "founders": merged["founders"],
                    "locations": merged["locations"],
                }
            ),
        )

        return merged

    def _merge_text_field(self, merged: Dict[str, Any], text: Optional[str]) -> None:
        if text and not merged.get("description"):
            merged["description"] = text

    def _merge_unique(self, target: List[str], values: List[str]) -> None:
        for value in values:
            if value not in target:
                target.append(value)

    def _merge_socials(self, target: List[Dict[str, str]], values: List[Dict[str, str]]) -> None:
        seen = {(item["platform"], item["url"]) for item in target}
        for value in values:
            key = (value.get("platform"), value.get("url"))
            if key not in seen and value.get("platform") and value.get("url"):
                target.append(value)
                seen.add(key)

    def _merge_founders(self, target: List[Dict[str, Optional[str]]], values: List[Dict[str, Optional[str]]]) -> None:
        seen = {item.get("name") for item in target}
        for value in values:
            name = value.get("name")
            if name and name not in seen:
                target.append(value)
                seen.add(name)

    def _extract_location(self, data: Dict[str, Any], html: str) -> Optional[str]:
        soup = BeautifulSoup(html, "html.parser")
        candidates = []
        text = soup.get_text(" ", strip=True)
        for pattern in [
            r"\b(Bangalore|Bengaluru|Mumbai|Delhi|Hyderabad|Chennai|Pune|Kolkata|Ahmedabad|Jaipur|Kochi|Noida|Gurugram|Gurgaon)\b",
            r"\b(India|UAE|Singapore|United States)\b",
        ]:
            match = re.search(pattern, text, flags=re.I)
            if match:
                candidates.append(match.group(1))
        return candidates[0] if candidates else None
