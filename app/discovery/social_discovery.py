import logging
import re
from difflib import SequenceMatcher
from typing import Dict, List, Optional
from urllib.parse import quote_plus

from app.core.url_utils import is_blocked_domain, is_safe_url, normalize_website
from app.discovery.http_client import fetch_url
from app.discovery.types import ExtractedCompany
from app.plugins.base import plugin_registry

logger = logging.getLogger(__name__)


class SocialDiscovery:
    """Discovers official social profiles when not found on the company website."""

    def discover(
        self,
        company_name: str,
        website: Optional[str] = None,
        existing: Optional[List[Dict[str, str]]] = None,
    ) -> List[Dict[str, str]]:
        existing = existing or []
        found_platforms = {link["platform"] for link in existing}
        results = list(existing)

        domain_hint = ""
        if website:
            from urllib.parse import urlparse
            domain_hint = urlparse(website).netloc.replace("www.", "").split(".")[0]

        searches = []
        if "LINKEDIN" not in found_platforms:
            searches.append(("LINKEDIN", f'site:linkedin.com/company "{company_name}"'))
        if "INSTAGRAM" not in found_platforms:
            query_name = domain_hint or company_name.split()[0]
            searches.append(("INSTAGRAM", f'site:instagram.com "{query_name}" startup'))
        if "TWITTER" not in found_platforms:
            searches.append(("TWITTER", f'site:twitter.com OR site:x.com "{company_name}"'))
        if "FACEBOOK" not in found_platforms:
            searches.append(("FACEBOOK", f'site:facebook.com "{company_name}"'))
        if "YOUTUBE" not in found_platforms:
            searches.append(("YOUTUBE", f'site:youtube.com "{company_name}"'))
        if "CRUNCHBASE" not in found_platforms:
            searches.append(("CRUNCHBASE", f'site:crunchbase.com/organization "{company_name}"'))
        if "WELLFOUNDED" not in found_platforms:
            searches.append(("WELLFOUNDED", f'site:wellfound.com "{company_name}" startup'))
        if "TRACXN" not in found_platforms:
            searches.append(("TRACXN", f'site:tracxn.com "{company_name}"'))
        if "STARTUPINDIA" not in found_platforms:
            searches.append(("STARTUPINDIA", f'site:startupindia.gov.in "{company_name}"'))

        for platform, query in searches:
            url = self._search_social(query, platform)
            if url and not any(r["platform"] == platform for r in results):
                results.append({"platform": platform, "url": url})

        return results

    def _search_social(self, query: str, platform: str) -> Optional[str]:
        try:
            search_results = plugin_registry.search(query, limit=5)
            for result in search_results:
                url = result.url
                if platform == "LINKEDIN" and "linkedin.com/company/" in url.lower() and self._similar(company_name, url):
                    return url.split("?")[0].rstrip("/")
                if platform == "INSTAGRAM" and "instagram.com/" in url.lower() and self._similar(company_name, url):
                    path = url.split("instagram.com/")[-1].split("/")[0]
                    if path and path not in ("p", "reel", "explore", "accounts"):
                        return f"https://instagram.com/{path}"
                if platform in ("TWITTER", "X") and ("twitter.com/" in url.lower() or "x.com/" in url.lower()):
                    for domain in ("twitter.com/", "x.com/"):
                        if domain in url.lower():
                            handle = url.lower().split(domain)[-1].split("/")[0].split("?")[0]
                            if handle and handle not in ("i", "intent", "share") and self._similar(company_name, handle):
                                return f"https://x.com/{handle}"
                if platform == "FACEBOOK" and "facebook.com/" in url.lower() and self._similar(company_name, url):
                    return url.split("?")[0].rstrip("/")
                if platform == "YOUTUBE" and "youtube.com/" in url.lower() and self._similar(company_name, url):
                    return url.split("?")[0].rstrip("/")
                if platform == "CRUNCHBASE" and "crunchbase.com/organization/" in url.lower() and self._similar(company_name, url):
                    return url.split("?")[0].rstrip("/")
                if platform in ("WELLFOUNDED", "TRACXN", "STARTUPINDIA") and self._similar(company_name, url):
                    return url.split("?")[0].rstrip("/")
        except Exception as exc:
            logger.debug("Social search failed for %s: %s", query, exc)
        return None

    def _similar(self, company_name: str, url_or_handle: str) -> bool:
        normalized_name = re.sub(r"[^a-z0-9]+", "", company_name.lower())
        normalized_target = re.sub(r"[^a-z0-9]+", "", url_or_handle.lower())
        if not normalized_name or not normalized_target:
            return False
        ratio = SequenceMatcher(None, normalized_name, normalized_target).ratio()
        return ratio >= 0.55 or normalized_name in normalized_target or normalized_target in normalized_name
