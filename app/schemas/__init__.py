from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ContactSchema(BaseModel):
    type: str
    value: str
    is_verified: bool = False
    source: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class SocialLinkSchema(BaseModel):
    platform: str
    url: str
    username: Optional[str] = None
    followers_count: Optional[int] = None
    following_count: Optional[int] = None
    posts_count: Optional[int] = None
    is_verified: bool = False

    model_config = ConfigDict(from_attributes=True)


class ProfileSchema(BaseModel):
    name: str
    title: Optional[str] = None
    profile_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class SourceSchema(BaseModel):
    url: str
    strategy: str
    reliability_score: int = 50

    model_config = ConfigDict(from_attributes=True)


class LeadCreate(BaseModel):
    name: str
    website: Optional[str] = None
    description: Optional[str] = None
    country: Optional[str] = None
    state: Optional[str] = None
    city: Optional[str] = None
    company_size: Optional[str] = None
    funding_stage: Optional[str] = None
    lead_score: int = 0
    confidence_score: float = 0.0
    categories: List[str] = Field(default_factory=list)
    contacts: List[ContactSchema] = Field(default_factory=list)
    social_links: List[SocialLinkSchema] = Field(default_factory=list)
    profiles: List[ProfileSchema] = Field(default_factory=list)
    sources: List[SourceSchema] = Field(default_factory=list)


class LeadResponse(BaseModel):
    id: UUID
    name: str
    website: Optional[str] = None
    description: Optional[str] = None
    country: Optional[str] = None
    state: Optional[str] = None
    city: Optional[str] = None
    company_size: Optional[str] = None
    funding_stage: Optional[str] = None
    lead_score: int
    confidence_score: float
    created_at: datetime
    updated_at: datetime
    categories: List[str] = Field(default_factory=list)
    contacts: List[ContactSchema] = Field(default_factory=list)
    social_links: List[SocialLinkSchema] = Field(default_factory=list)
    profiles: List[ProfileSchema] = Field(default_factory=list)
    sources: List[SourceSchema] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class LeadSearchParams(BaseModel):
    query: Optional[str] = None
    category: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    min_lead_score: Optional[int] = None
    only_verified: bool = False
    only_with_email: bool = False
    only_with_instagram: bool = False
    only_with_linkedin: bool = False
    skip: int = 0
    limit: int = 100


class CategoryResponse(BaseModel):
    id: UUID
    name: str

    model_config = ConfigDict(from_attributes=True)


class AgentRunCreate(BaseModel):
    trigger_type: str = "MANUAL"
    config: Dict[str, Any] = Field(default_factory=dict)


class AgentRunResponse(BaseModel):
    id: UUID
    status: str
    trigger_type: str
    config: Optional[Dict[str, Any]] = None
    stats: Optional[Dict[str, Any]] = None
    last_checkpoint: Optional[str] = None
    started_at: datetime
    ended_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class DiscoveryStartRequest(BaseModel):
    max_keywords: int = 50
    results_per_keyword: int = 10
    resume: bool = True


class DiscoveryStatusResponse(BaseModel):
    active_run: Optional[AgentRunResponse] = None
    is_running: bool
    message: str


class ExportRequest(BaseModel):
    format: str = "CSV"
    query: Optional[str] = None
    category: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    min_lead_score: Optional[int] = None
    resume_export_id: Optional[UUID] = None


class ExportResponse(BaseModel):
    id: UUID
    file_name: str
    format: str
    records_count: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
