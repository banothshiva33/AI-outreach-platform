from typing import Any, Dict, List, Optional

from sqlalchemy import and_, or_, func
from sqlalchemy.orm import Session, joinedload

from app.core.url_utils import normalize_domain, normalize_website
from app.repositories.base import BaseRepository
from app.models.models import Company, Contact, SocialLink, Profile, Category, Source


class LeadRepository(BaseRepository[Company]):
    def __init__(self):
        super().__init__(Company)

    def get_by_website(self, db: Session, website: str) -> Optional[Company]:
        if not website:
            return None
        normalized = normalize_website(website)
        domain = normalize_domain(website)
        if not normalized:
            return None
        return (
            db.query(Company)
            .filter(
                or_(
                    Company.website == normalized,
                    Company.website == domain,
                    Company.website.ilike(f"%{domain}%"),
                )
            )
            .first()
        )

    def get_by_name(self, db: Session, name: str) -> Optional[Company]:
        return (
            db.query(Company)
            .filter(func.lower(Company.name) == name.strip().lower())
            .first()
        )

    def search_leads(
        self,
        db: Session,
        *,
        query: Optional[str] = None,
        category: Optional[str] = None,
        city: Optional[str] = None,
        state: Optional[str] = None,
        country: Optional[str] = None,
        min_lead_score: Optional[int] = None,
        only_verified: bool = False,
        only_with_email: bool = False,
        only_with_instagram: bool = False,
        only_with_linkedin: bool = False,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Company]:
        q = db.query(Company).options(
            joinedload(Company.profiles),
            joinedload(Company.social_links),
            joinedload(Company.contacts),
            joinedload(Company.categories),
            joinedload(Company.sources),
        )

        filters = []

        if query:
            filters.append(
                or_(
                    Company.name.ilike(f"%{query}%"),
                    Company.description.ilike(f"%{query}%"),
                    Company.website.ilike(f"%{query}%"),
                )
            )

        if category:
            q = q.join(Company.categories).filter(Category.name == category)

        if city:
            filters.append(Company.city.ilike(f"%{city.strip()}%"))

        if state:
            filters.append(Company.state.ilike(f"%{state.strip()}%"))

        if country:
            filters.append(Company.country.ilike(f"%{country.strip()}%"))

        if min_lead_score is not None:
            filters.append(Company.lead_score >= min_lead_score)

        if only_verified:
            q = q.outerjoin(Company.contacts).outerjoin(Company.social_links)
            filters.append(
                or_(Contact.is_verified.is_(True), SocialLink.is_verified.is_(True))
            )

        if only_with_email:
            q = q.join(Company.contacts).filter(Contact.type == "EMAIL")

        if only_with_instagram:
            q = q.join(Company.social_links).filter(SocialLink.platform == "INSTAGRAM")

        if only_with_linkedin:
            q = q.join(Company.social_links).filter(SocialLink.platform == "LINKEDIN")

        if filters:
            q = q.filter(and_(*filters))

        return (
            q.distinct()
            .order_by(Company.lead_score.desc(), Company.id.asc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def create_or_update_lead(
        self,
        db: Session,
        *,
        company_data: Dict[str, Any],
        categories: Optional[List[str]] = None,
        contacts: Optional[List[Dict[str, Any]]] = None,
        social_links: Optional[List[Dict[str, Any]]] = None,
        profiles: Optional[List[Dict[str, Any]]] = None,
        sources: Optional[List[Dict[str, Any]]] = None,
        commit: bool = True,
    ) -> Company:
        if company_data.get("website"):
            company_data = {**company_data, "website": normalize_website(company_data["website"])}

        if company_data.get("industry") and not company_data.get("categories"):
            company_data = {**company_data, "categories": [company_data["industry"]]}

        website = company_data.get("website")
        existing_company = self.get_by_website(db, website) if website else None
        if not existing_company:
            existing_company = self.get_by_name(db, company_data.get("name", ""))

        if existing_company:
            for field, val in company_data.items():
                if val is not None:
                    setattr(existing_company, field, val)
            db_company = existing_company
        else:
            db_company = Company(**company_data)
            db.add(db_company)
            db.flush()

        if categories:
            for cat_name in categories:
                cat_db = db.query(Category).filter(Category.name == cat_name).first()
                if not cat_db:
                    cat_db = Category(name=cat_name)
                    db.add(cat_db)
                    db.flush()
                if cat_db not in db_company.categories:
                    db_company.categories.append(cat_db)

        if contacts:
            for contact_data in contacts:
                val = contact_data.get("value")
                exists = (
                    db.query(Contact)
                    .filter(Contact.company_id == db_company.id, Contact.value == val)
                    .first()
                )
                if not exists:
                    db.add(Contact(company_id=db_company.id, **contact_data))
                elif contact_data.get("is_verified"):
                    exists.is_verified = True

        if social_links:
            for link_data in social_links:
                url = link_data.get("url")
                exists = (
                    db.query(SocialLink)
                    .filter(SocialLink.company_id == db_company.id, SocialLink.url == url)
                    .first()
                )
                if not exists:
                    db.add(SocialLink(company_id=db_company.id, **link_data))
                else:
                    for field in [
                        "followers_count",
                        "following_count",
                        "posts_count",
                        "is_verified",
                    ]:
                        if link_data.get(field) is not None:
                            setattr(exists, field, link_data[field])

        if profiles:
            for prof_data in profiles:
                prof_url = prof_data.get("profile_url")
                prof_name = prof_data.get("name")
                exists = None
                if prof_url:
                    exists = (
                        db.query(Profile)
                        .filter(
                            Profile.company_id == db_company.id,
                            Profile.profile_url == prof_url,
                        )
                        .first()
                    )
                elif prof_name:
                    exists = (
                        db.query(Profile)
                        .filter(
                            Profile.company_id == db_company.id,
                            Profile.name == prof_name,
                        )
                        .first()
                    )
                if not exists:
                    db.add(Profile(company_id=db_company.id, **prof_data))

        if sources:
            for src_data in sources:
                src_url = src_data.get("url")
                exists = (
                    db.query(Source)
                    .filter(Source.company_id == db_company.id, Source.url == src_url)
                    .first()
                )
                if not exists:
                    db.add(Source(company_id=db_company.id, **src_data))

        if commit:
            db.commit()
            db.refresh(db_company)
        else:
            db.flush()
        return db_company


lead_repository = LeadRepository()
