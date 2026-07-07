import logging
from typing import Optional
from urllib.parse import urlparse

from app.core.url_utils import is_blocked_domain, normalize_website
from app.discovery.types import ExtractedCompany
from app.plugins.base import plugin_registry

logger = logging.getLogger(__name__)

DIRECTORY_DOMAINS = {
    "yourstory.com", "inc42.com", "startupindia.gov.in", "linkedin.com",
    "crunchbase.com", "medium.com", "facebook.com", "twitter.com", "x.com",
    "instagram.com", "wikipedia.org",
}


class WebsiteFinder:
    """Finds the official company website when only a directory listing is available."""

    def find_website(self, company: ExtractedCompany) -> Optional[str]:
        if company.website and not is_blocked_domain(company.website):
            return normalize_website(company.website)

        query = f'"{company.name}" official website India'
        try:
            results = plugin_registry.search(query, limit=8)
            for result in results:
                domain = urlparse(result.url).netloc.lower().replace("www.", "")
                if any(skip in domain for skip in DIRECTORY_DOMAINS):
                    continue
                website = normalize_website(result.url)
                if website:
                    return website
        except Exception as exc:
            logger.debug("Website discovery failed for %s: %s", company.name, exc)
        return None
