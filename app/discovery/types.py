from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str = ""


@dataclass
class ExtractedCompany:
    name: str
    website: Optional[str] = None
    description: Optional[str] = None
    article_context: Optional[str] = None
    occurrence_count: int = 0
    entity_type: Optional[str] = None
    founder: Optional[str] = None
    industry: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    country: Optional[str] = None
    funding: Optional[str] = None
    employee_size: Optional[str] = None
    confidence: float = 0.0
    source_url: Optional[str] = None
    source_urls: List[str] = field(default_factory=list)
    strategy: str = "WEB_SEARCH"
    tags: List[str] = field(default_factory=list)
    social_links: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class EnrichedLead:
    name: str
    website: Optional[str] = None
    description: Optional[str] = None
    article_context: Optional[str] = None
    website_intro: Optional[str] = None
    llm_confidence: float = 0.0
    founder: Optional[str] = None
    industry: Optional[str] = None
    country: Optional[str] = None
    state: Optional[str] = None
    city: Optional[str] = None
    funding_stage: Optional[str] = None
    company_size: Optional[str] = None
    categories: List[str] = field(default_factory=list)
    contacts: List[Dict[str, Any]] = field(default_factory=list)
    social_links: List[Dict[str, Any]] = field(default_factory=list)
    profiles: List[Dict[str, Any]] = field(default_factory=list)
    sources: List[Dict[str, Any]] = field(default_factory=list)
    lead_score: int = 0
    confidence_score: float = 0.0


@dataclass
class StartupMention:
    company_name: str
    article_context: Optional[str] = None
    occurrence_count: int = 0
    entity_type: Optional[str] = None
    founder: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin: Optional[str] = None
    instagram: Optional[str] = None
    twitter: Optional[str] = None
    location: Optional[str] = None
    country: Optional[str] = None
    industry: Optional[str] = None
    website_if_present: Optional[str] = None
    description: Optional[str] = None
    funding: Optional[str] = None
    employee_size: Optional[str] = None
    confidence: float = 0.0
    source_url: Optional[str] = None
