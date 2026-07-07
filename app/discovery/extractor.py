import json
import logging
import re
from typing import List, Optional
from urllib.parse import urlparse

from app.core.url_utils import is_blocked_domain, normalize_website

from app.discovery.types import ExtractedCompany, SearchResult

logger = logging.getLogger(__name__)

COMPANY_SUFFIXES = re.compile(
    r"\b(Pvt\.?\s*Ltd\.?|Private Limited|LLP|Inc\.?|Corp\.?|Technologies|Solutions|Labs|Ventures|Innovations)\b",
    re.IGNORECASE,
)

SKIP_DOMAINS = {
    "linkedin.com", "facebook.com", "twitter.com", "x.com", "instagram.com",
    "youtube.com", "wikipedia.org", "medium.com", "crunchbase.com",
    "yourstory.com", "inc42.com", "entrepreneur.com", "economictimes.com",
    "livemint.com", "techcrunch.com", "forbes.com",
}


class CompanyExtractor:
    """Extracts company candidates from search results."""

    def extract_from_results(
        self, results: List[SearchResult], *, keyword: str
    ) -> List[ExtractedCompany]:
        companies: List[ExtractedCompany] = []
        seen_names = set()

        for result in results:
            company = self._extract_from_result(result, keyword=keyword)
            if company and company.name.lower() not in seen_names:
                seen_names.add(company.name.lower())
                companies.append(company)

        return companies

    def _extract_from_result(
        self, result: SearchResult, *, keyword: str
    ) -> Optional[ExtractedCompany]:
        from urllib.parse import urlparse

        domain = urlparse(result.url).netloc.lower().replace("www.", "")
        strategy = self._strategy_for_domain(domain, result.source)

        if any(skip in domain for skip in SKIP_DOMAINS):
            return self._extract_from_directory(result, keyword, strategy=strategy)

        name = self._clean_company_name(result.title)
        if not name or len(name) < 2:
            return None

        website = normalize_website(result.url)
        if website and is_blocked_domain(website):
            return self._extract_from_directory(result, keyword, strategy=strategy)

        return ExtractedCompany(
            name=name,
            website=website,
            description=result.snippet,
            source_url=result.url,
            strategy=strategy,
            tags=self._infer_tags(keyword),
        )

    def _strategy_for_domain(self, domain: str, source: str) -> str:
        if "startupindia.gov.in" in domain:
            return "STARTUP_INDIA"
        if "yourstory.com" in domain:
            return "YOURSTORY"
        if "inc42.com" in domain:
            return "INC42"
        if source in ("google_search", "google_cse", "serpapi"):
            return "GOOGLE_SEARCH"
        return "WEB_SEARCH"

    def _extract_from_directory(
        self, result: SearchResult, keyword: str, *, strategy: str = "DIRECTORY"
    ) -> Optional[ExtractedCompany]:
        return self._extract_from_snippet(result, keyword, strategy=strategy)

    def _extract_from_snippet(
        self, result: SearchResult, keyword: str, *, strategy: str = "DIRECTORY"
    ) -> Optional[ExtractedCompany]:
        """Try to extract company name from directory/listing pages."""
        patterns = [
            r"([A-Z][A-Za-z0-9&\s]{2,40}(?:Pvt\.?\s*Ltd\.?|Private Limited|LLP|Inc\.?|Technologies|Solutions|Labs|Ventures)?)",
        ]
        for pattern in patterns:
            match = re.search(pattern, result.snippet + " " + result.title)
            if match:
                name = self._clean_company_name(match.group(1))
                if name and len(name) >= 3:
                    return ExtractedCompany(
                        name=name,
                        description=result.snippet,
                        source_url=result.url,
                        strategy=strategy,
                        tags=self._infer_tags(keyword),
                    )
        return None

    def _clean_company_name(self, title: str) -> str:
        name = re.split(r"[-|–—:]", title)[0].strip()
        name = re.sub(r"\s*[-|]\s*.*$", "", name)
        name = re.sub(r"\s+", " ", name).strip()
        if len(name) > 80:
            name = name[:80].rsplit(" ", 1)[0]
        return name

    def _normalize_website(self, url: str) -> Optional[str]:
        if is_blocked_domain(url):
            return None
        return normalize_website(url)

    def _infer_tags(self, keyword: str) -> List[str]:
        tags = []
        kw_lower = keyword.lower()
        for tag in [
            "Startup", "AI Startup", "FinTech", "EdTech", "HealthTech", "SaaS",
            "DeepTech", "Founder", "Women Founder", "Tech Founder",
        ]:
            if tag.lower() in kw_lower:
                tags.append(tag)
        if "startup" in kw_lower and "Startup" not in tags:
            tags.append("Startup")
        return tags[:5]
