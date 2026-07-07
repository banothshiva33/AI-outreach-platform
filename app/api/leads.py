from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import verify_api_key
from app.repositories import lead_repository
from app.schemas import (
    LeadCreate,
    LeadResponse,
    ContactSchema,
    SocialLinkSchema,
    ProfileSchema,
    SourceSchema,
)

router = APIRouter(
    prefix="/api/leads",
    tags=["Leads"],
    dependencies=[Depends(verify_api_key)],
)


def _company_to_response(company) -> LeadResponse:
    return LeadResponse(
        id=company.id,
        name=company.name,
        website=company.website,
        description=company.description,
        country=company.country,
        state=company.state,
        city=company.city,
        company_size=company.company_size,
        funding_stage=company.funding_stage,
        lead_score=company.lead_score or 0,
        confidence_score=company.confidence_score or 0.0,
        created_at=company.created_at,
        updated_at=company.updated_at,
        categories=[c.name for c in company.categories],
        contacts=[ContactSchema.model_validate(c) for c in company.contacts],
        social_links=[SocialLinkSchema.model_validate(s) for s in company.social_links],
        profiles=[ProfileSchema.model_validate(p) for p in company.profiles],
        sources=[SourceSchema.model_validate(s) for s in company.sources],
    )


@router.get("", response_model=List[LeadResponse])
def search_leads(
    query: str | None = None,
    category: str | None = None,
    city: str | None = None,
    state: str | None = None,
    country: str | None = None,
    min_lead_score: int | None = None,
    only_verified: bool = False,
    only_with_email: bool = False,
    only_with_instagram: bool = False,
    only_with_linkedin: bool = False,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    companies = lead_repository.search_leads(
        db,
        query=query,
        category=category,
        city=city,
        state=state,
        country=country,
        min_lead_score=min_lead_score,
        only_verified=only_verified,
        only_with_email=only_with_email,
        only_with_instagram=only_with_instagram,
        only_with_linkedin=only_with_linkedin,
        skip=skip,
        limit=limit,
    )
    return [_company_to_response(c) for c in companies]


@router.get("/{lead_id}", response_model=LeadResponse)
def get_lead(lead_id: UUID, db: Session = Depends(get_db)):
    company = lead_repository.get(db, lead_id)
    if not company:
        raise HTTPException(status_code=404, detail="Lead not found")
    return _company_to_response(company)


@router.post("", response_model=LeadResponse, status_code=201)
def create_lead(payload: LeadCreate, db: Session = Depends(get_db)):
    company = lead_repository.create_or_update_lead(
        db,
        company_data=payload.model_dump(
            exclude={"categories", "contacts", "social_links", "profiles", "sources"}
        ),
        categories=payload.categories,
        contacts=[c.model_dump() for c in payload.contacts],
        social_links=[s.model_dump() for s in payload.social_links],
        profiles=[p.model_dump() for p in payload.profiles],
        sources=[s.model_dump() for s in payload.sources],
    )
    return _company_to_response(company)
