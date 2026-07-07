import json
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from app.core.url_utils import is_safe_url
from app.discovery.content_fetcher import fetch_page_html
from app.discovery.http_client import fetch_url

logger = logging.getLogger(__name__)

EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
)
PHONE_PATTERN = re.compile(
    r"(?:\+91[\s-]?)?[6-9]\d{9}"
)

SOCIAL_PLATFORMS = {
    "LINKEDIN": re.compile(
        r"https?://(?:www\.)?linkedin\.com/(?:company|school)/[\w\-./%]+", re.I
    ),
    "INSTAGRAM": re.compile(
        r"https?://(?:www\.)?instagram\.com/(?!p/|reel/|stories/)[\w.]+/?", re.I
    ),
    "TWITTER": re.compile(
        r"https?://(?:www\.)?(?:twitter|x)\.com/(?!i/|intent/)[\w]+/?", re.I
    ),
}

JUNK_EMAIL_FRAGMENTS = (
    "example", "sentry", "wix", "schema", "wordpress", "png", "jpg",
    "domain.com", "email.com", "u003e", "noreply", "no-reply",
)

INSTAGRAM_SKIP_USERNAMES = {
    "instagram", "explore", "about", "legal", "accounts", "p", "reel",
}


class WebsiteParser:
    """Parses a company website for contacts, social profiles, and metadata."""

    def parse(self, website: str) -> Dict[str, Any]:
        if not is_safe_url(website):
            return {}

        html = fetch_url(website)
        if not html:
            html = fetch_page_html(website)
        if not html:
            return {}

        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(" ", strip=True)

        result: Dict[str, Any] = {
            "description": self._extract_description(soup),
            "emails": self._extract_emails(soup, text, website),
            "phones": self._extract_phones(soup, text),
            "social_links": self._extract_social_links(soup, html),
            "founders": self._extract_founders(soup, text),
        }
        return result

    def _extract_description(self, soup: BeautifulSoup) -> Optional[str]:
        for attrs in [
            {"property": "og:description"},
            {"name": "description"},
            {"name": "twitter:description"},
        ]:
            tag = soup.find("meta", attrs=attrs)
            if tag and tag.get("content"):
                return tag["content"][:500]

        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if item.get("@type") in ("Organization", "Corporation", "LocalBusiness"):
                        desc = item.get("description")
                        if desc:
                            return str(desc)[:500]
            except (json.JSONDecodeError, TypeError):
                continue
        return None

    def _extract_emails(
        self, soup: BeautifulSoup, text: str, base_url: str
    ) -> List[str]:
        emails: List[str] = []
        seen = set()

        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            if href.startswith("mailto:"):
                email = href.replace("mailto:", "").split("?")[0].strip().lower()
                if self._is_valid_email(email, base_url) and email not in seen:
                    seen.add(email)
                    emails.append(email)

        for match in EMAIL_PATTERN.findall(text):
            email = match.lower()
            if self._is_valid_email(email, base_url) and email not in seen:
                seen.add(email)
                emails.append(email)

        return emails[:3]

    def _is_valid_email(self, email: str, base_url: str) -> bool:
        if any(fragment in email for fragment in JUNK_EMAIL_FRAGMENTS):
            return False
        domain = urlparse(base_url).netloc.replace("www.", "")
        email_domain = email.split("@")[-1]
        if domain and (domain in email_domain or email_domain in domain):
            return True
        public_domains = ("gmail.com", "yahoo.com", "outlook.com", "hotmail.com")
        if any(email.endswith(f"@{d}") for d in public_domains):
            return True
        return "." in email_domain and len(email_domain) > 3

    def _extract_phones(self, soup: BeautifulSoup, text: str) -> List[str]:
        phones: List[str] = []
        seen: set[str] = set()

        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            if href.startswith("tel:"):
                phone = re.sub(r"[\s\-()]", "", href.replace("tel:", "").split("?")[0])
                if len(phone) >= 10 and phone not in seen:
                    seen.add(phone)
                    phones.append(phone)

        for match in PHONE_PATTERN.findall(text):
            cleaned = re.sub(r"[\s\-()]", "", match)
            if len(cleaned) >= 10 and cleaned not in seen:
                seen.add(cleaned)
                phones.append(cleaned)
        return phones[:2]

    def _extract_social_links(self, soup: BeautifulSoup, html: str) -> List[Dict[str, str]]:
        links: List[Dict[str, str]] = []
        seen_platforms = set()

        candidates = set()
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"].strip()
            if href.startswith("//"):
                href = "https:" + href
            candidates.add(href)

        for match in re.findall(r'https?://[^\s"\'<>]+', html):
            candidates.add(match.rstrip(".,;)"))

        for url in candidates:
            for platform, pattern in SOCIAL_PLATFORMS.items():
                if platform in seen_platforms:
                    continue
                match = pattern.search(url)
                if match:
                    normalized = self._normalize_social_url(platform, match.group(0))
                    if normalized:
                        links.append({"platform": platform, "url": normalized})
                        seen_platforms.add(platform)
        return links

    def _normalize_social_url(self, platform: str, url: str) -> Optional[str]:
        url = url.rstrip("/").split("?")[0]
        if platform == "INSTAGRAM":
            username = urlparse(url).path.strip("/").split("/")[0].lower()
            if username in INSTAGRAM_SKIP_USERNAMES or len(username) < 2:
                return None
        if platform == "LINKEDIN" and "/in/" in url.lower():
            return None
        return url

    def _extract_founders(self, soup: BeautifulSoup, text: str) -> List[Dict[str, Optional[str]]]:
        founders = []
        patterns = [
            r"(?:Founder|CEO|Co-founder|Co-Founder|Managing Director)[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})",
            r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}),?\s+(?:Founder|CEO|Co-founder)",
        ]
        seen_names = set()
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                name = match.group(1).strip()
                if name in seen_names or len(name) < 4:
                    continue
                profile_url = None
                first_name = name.split()[0].lower()
                for anchor in soup.find_all("a", href=True):
                    href = anchor["href"]
                    if "linkedin.com/in/" in href and first_name in href.lower():
                        profile_url = href.split("?")[0]
                        break
                founders.append({"name": name, "title": "Founder", "profile_url": profile_url})
                seen_names.add(name)
                if len(founders) >= 2:
                    return founders
        return founders
