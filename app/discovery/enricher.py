import logging
from typing import Dict, List, Optional

from app.core.url_utils import normalize_website
from app.discovery.social_discovery import SocialDiscovery
from app.discovery.types import EnrichedLead, ExtractedCompany
from app.discovery.website_enrichment import WebsiteEnrichmentAgent
from app.discovery.website_parser import WebsiteParser

logger = logging.getLogger(__name__)

INDIAN_CITIES = {
    "bangalore": ("Bangalore", "Karnataka"),
    "bengaluru": ("Bangalore", "Karnataka"),
    "mumbai": ("Mumbai", "Maharashtra"),
    "delhi": ("Delhi", "Delhi"),
    "hyderabad": ("Hyderabad", "Telangana"),
    "chennai": ("Chennai", "Tamil Nadu"),
    "pune": ("Pune", "Maharashtra"),
    "kolkata": ("Kolkata", "West Bengal"),
    "ahmedabad": ("Ahmedabad", "Gujarat"),
    "jaipur": ("Jaipur", "Rajasthan"),
    "kochi": ("Kochi", "Kerala"),
    "noida": ("Noida", "Uttar Pradesh"),
    "gurgaon": ("Gurgaon", "Haryana"),
    "gurugram": ("Gurgaon", "Haryana"),
}

STRATEGY_RELIABILITY = {
    "WEB_SEARCH": 55,
    "GOOGLE_SEARCH": 65,
    "STARTUP_INDIA": 80,
    "YOURSTORY": 75,
    "INC42": 75,
    "DIRECTORY": 60,
}


class LeadEnricher:
    """Enriches leads using website parser and social profile discovery."""

    def __init__(self):
        self.website_parser = WebsiteParser()
        self.website_enrichment = WebsiteEnrichmentAgent()
        self.social_discovery = SocialDiscovery()

    def enrich(self, company: ExtractedCompany) -> EnrichedLead:
        reliability = STRATEGY_RELIABILITY.get(company.strategy, 50)
        lead = EnrichedLead(
            name=company.name,
            website=company.website,
            description=company.description,
            article_context=company.article_context,
            founder=company.founder,
            industry=company.industry,
            country="India",
            funding_stage=company.funding,
            company_size=company.employee_size,
            categories=company.tags,
            sources=[
                {
                    "url": company.source_url or company.website or "",
                    "strategy": company.strategy,
                    "reliability_score": reliability,
                }
            ],
        )

        if company.website:
            self._apply_website_data(lead, company.website)

        self._apply_extracted_signals(lead, company)

        if company.social_links:
            for link in company.social_links:
                if not any(s["platform"] == link["platform"] for s in lead.social_links):
                    lead.social_links.append(link)

        lead.social_links = self.social_discovery.discover(
            company.name,
            website=lead.website,
            existing=lead.social_links,
        )

        self._infer_location(lead, company)
        return lead

    def _apply_extracted_signals(self, lead: EnrichedLead, company: ExtractedCompany) -> None:
        if company.email and not any(c["value"] == company.email for c in lead.contacts):
            lead.contacts.append({"type": "EMAIL", "value": company.email, "source": company.strategy, "is_verified": False})

        if company.phone and not any(c["value"] == company.phone for c in lead.contacts):
            lead.contacts.append({"type": "PHONE", "value": company.phone, "source": company.strategy, "is_verified": False})

        if company.founder and not any(p["name"] == company.founder for p in lead.profiles):
            lead.profiles.append({"name": company.founder, "title": "Founder", "profile_url": None})

        if company.location:
            location = company.location.strip()
            if location and not lead.city:
                lead.city = location

        if company.country and not lead.country:
            lead.country = company.country

        if company.funding and not lead.funding_stage:
            lead.funding_stage = company.funding

        if company.employee_size and not lead.company_size:
            lead.company_size = company.employee_size

        if company.industry and company.industry not in lead.categories:
            lead.categories.append(company.industry)

        if company.confidence and lead.confidence_score <= 0:
            lead.confidence_score = company.confidence

    def _apply_website_data(self, lead: EnrichedLead, website: str) -> None:
        parsed = self.website_enrichment.enrich(website)
        if not parsed:
            parsed = self.website_parser.parse(website)
        if not parsed:
            return

        if parsed.get("description") and not lead.description:
            lead.description = parsed["description"]
        if parsed.get("description") and not lead.website_intro:
            lead.website_intro = parsed["description"]

        for email in parsed.get("emails", []):
            if not any(c["value"] == email for c in lead.contacts):
                lead.contacts.append(
                    {"type": "EMAIL", "value": email, "source": "website", "is_verified": False}
                )

        for phone in parsed.get("phones", []):
            if not any(c["value"] == phone for c in lead.contacts):
                lead.contacts.append(
                    {"type": "PHONE", "value": phone, "source": "website", "is_verified": False}
                )

        for social in parsed.get("social_links", []):
            if not any(s["platform"] == social["platform"] for s in lead.social_links):
                lead.social_links.append(social)

        for founder in parsed.get("founders", []):
            if not any(p["name"] == founder["name"] for p in lead.profiles):
                lead.profiles.append(founder)

        for location in parsed.get("locations", []):
            if not lead.city and location:
                lead.city = location
                if not lead.state:
                    lead.state = None

    def _infer_location(self, lead: EnrichedLead, company: ExtractedCompany) -> None:
        combined = (
            f"{company.name} {company.description or ''} "
            f"{company.source_url or ''} {lead.description or ''} {company.location or ''}"
        ).lower()
        for key, (city, state) in INDIAN_CITIES.items():
            if key in combined:
                lead.city = city
                lead.state = state
                break
        if not lead.country and company.country:
            lead.country = company.country
