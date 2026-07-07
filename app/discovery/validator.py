import re
from typing import Optional

from app.discovery.types import ExtractedCompany, EnrichedLead

GENERIC_NAMES = {
    "home", "about", "contact", "login", "signup", "search", "results",
    "untitled", "welcome", "company", "startup", "business", "india",
    "read more", "learn more", "click here",
}

FORBIDDEN_PREFIXES = (
    "meet ",
    "startup india team",
    "internal trade",
    "about startup india",
    "contact us",
    "home",
    "privacy policy",
    "terms",
    "careers",
    "investors",
    "blog",
    "news",
    "resources",
)

TITLE_REJECTION_RE = re.compile(
    r"\b(top|best|guide|how to|news|report|analysis|review|market|ranking|list|blog|magazine|conference|startup investors)\b",
    re.I,
)

TITLE_PUNCTUATION_RE = re.compile(r"[|]{1,}|[:]{2,}|\s-\s|\s\|\s")
NAVIGATION_RE = re.compile(r"\b(home|about|contact|team|careers|investors|resources|blog|news|privacy policy|terms)\b", re.I)
ENTITY_TYPE_RE = re.compile(r"\b(team|department|initiative|program)\b", re.I)
COMPANY_INDICATORS = re.compile(
    r"\b(Pvt\.?\s*Ltd\.?|Private Limited|LLP|Inc\.?|Corp\.?|Technologies|Solutions|Labs|Ventures|Studio|Systems|AI|Health|Fintech|SaaS)\b",
    re.I,
)


class CompanyValidator:
    """Validates company candidates before enrichment and persistence."""

    def validate_extracted(self, company: ExtractedCompany) -> bool:
        return not self.explain_extracted(company)

    def validate_enriched(self, lead: EnrichedLead) -> bool:
        return not self.explain_enriched(lead)

    def explain_extracted(self, company: ExtractedCompany) -> list[str]:
        reasons: list[str] = []
        if not self._valid_name(company.name):
            reasons.append("invalid_name")
        if self._looks_like_article_title(company.name, company.description):
            reasons.append("looks_like_article_title")
        if self._looks_like_heading_or_nav(company.name):
            reasons.append("looks_like_heading_or_nav")
        if self._looks_like_forbidden_prefix(company.name):
            reasons.append("forbidden_prefix")
        if self._is_forbidden_entity_type(company.entity_type, company.name, company.description):
            reasons.append("forbidden_entity_type")
        if self._is_article_derived(company) and company.occurrence_count and company.occurrence_count < 2:
            reasons.append("single_article_mention")
        if self._looks_like_website_or_evidence_missing(company):
            reasons.append("missing_evidence")
        if not self._has_company_signal(company):
            reasons.append("missing_company_signal")
        if company.website and not self._valid_website(company.website):
            reasons.append("invalid_website")
        return reasons

    def explain_enriched(self, lead: EnrichedLead) -> list[str]:
        reasons: list[str] = []
        if not self._valid_name(lead.name):
            reasons.append("invalid_name")
        if self._looks_like_article_title(lead.name, lead.description):
            reasons.append("looks_like_article_title")
        if self._looks_like_heading_or_nav(lead.name):
            reasons.append("looks_like_heading_or_nav")
        if self._looks_like_forbidden_prefix(lead.name):
            reasons.append("forbidden_prefix")
        if self._is_forbidden_entity_type(None, lead.name, lead.description):
            reasons.append("forbidden_entity_type")
        if self._description_matches_intro(lead.description, lead.website_intro):
            reasons.append("description_matches_website_intro")
        if not self._has_enriched_signal(lead):
            reasons.append("missing_enrichment_signal")
        if lead.website and not self._valid_website(lead.website):
            reasons.append("invalid_website")
        return reasons

    def _valid_name(self, name: Optional[str]) -> bool:
        if not name or len(name.strip()) < 3:
            return False
        cleaned = name.strip().lower()
        if cleaned in GENERIC_NAMES:
            return False
        if re.fullmatch(r"[\W\d_]+", cleaned):
            return False
        if len(name) > 120:
            return False
        return True

    def _looks_like_article_title(self, name: str, description: Optional[str] = None) -> bool:
        combined = f"{name} {description or ''}".strip().lower()
        if TITLE_REJECTION_RE.search(combined):
            return True
        if len(name.split()) > 8:
            return True
        if TITLE_PUNCTUATION_RE.search(name):
            return True
        if name.endswith("?") or name.endswith("!"):
            return True
        if re.search(r"\b(meet|introducing|announces|launches|raises|investors|startups|startup investors)\b", combined):
            return True
        return False

    def _looks_like_heading_or_nav(self, name: str) -> bool:
        lowered = name.strip().lower()
        if lowered in GENERIC_NAMES:
            return True
        if any(lowered.startswith(prefix) for prefix in FORBIDDEN_PREFIXES):
            return True
        return bool(NAVIGATION_RE.search(lowered))

    def _looks_like_forbidden_prefix(self, name: str) -> bool:
        lowered = name.strip().lower()
        return any(lowered.startswith(prefix) for prefix in FORBIDDEN_PREFIXES)

    def _is_forbidden_entity_type(self, entity_type: Optional[str], name: str, description: Optional[str]) -> bool:
        combined = f"{entity_type or ''} {name} {description or ''}".lower()
        if entity_type and ENTITY_TYPE_RE.search(entity_type):
            return True
        return bool(ENTITY_TYPE_RE.search(combined))

    def _looks_like_website_or_evidence_missing(self, company: ExtractedCompany) -> bool:
        if company.website or company.social_links or company.founder or company.industry or company.tags:
            return False
        if company.description and len(company.description.strip()) > 40:
            return False
        return True

    def _is_article_derived(self, company: ExtractedCompany) -> bool:
        strategy = (company.strategy or "").upper()
        if strategy in {"ARTICLE_AI", "ARTICLE", "WEB_ARTICLE"}:
            return True
        return bool(company.article_context)

    def _description_matches_intro(self, description: Optional[str], website_intro: Optional[str]) -> bool:
        if not description or not website_intro:
            return False
        left = re.sub(r"\s+", " ", description).strip().lower()
        right = re.sub(r"\s+", " ", website_intro).strip().lower()
        if not left or not right:
            return False
        return left == right or left[:160] == right[:160]

    def _has_company_signal(self, company: ExtractedCompany) -> bool:
        if COMPANY_INDICATORS.search(company.name):
            return True
        if company.website:
            return True
        if company.social_links:
            return True
        if company.founder or company.industry:
            return True
        if company.tags:
            return True
        return False

    def _has_enriched_signal(self, lead: EnrichedLead) -> bool:
        has_contact = bool(lead.contacts)
        has_social = bool(lead.social_links)
        has_profile = bool(lead.profiles)
        has_website = bool(lead.website)
        has_location = bool(lead.city or lead.state or lead.country)
        return has_website or has_social or has_contact or has_profile or has_location

    def _valid_website(self, website: str) -> bool:
        if not website.startswith("http"):
            return False
        from urllib.parse import urlparse
        domain = urlparse(website).netloc.lower().replace("www.", "")
        blocked_domains = ("example.com", "example.org", "localhost", "127.0.0.1")
        return domain not in blocked_domains
