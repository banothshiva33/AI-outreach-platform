import logging
from typing import Optional
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.repositories import (
    exclude_memory_repository,
    lead_repository,
    search_history_repository,
)

logger = logging.getLogger(__name__)


class AgentMemory:
    """
    Remembers processed entities to never repeat work.
    Tracks companies, websites, keywords, dead URLs, duplicates, and social profiles.
    """

    def __init__(self, db: Session):
        self.db = db

    def is_keyword_processed(self, keyword: str) -> bool:
        return search_history_repository.is_processed(self.db, keyword)

    def mark_keyword_done(
        self, keyword: str, *, status: str = "COMPLETED", error: Optional[str] = None, commit: bool = True
    ) -> None:
        search_history_repository.mark_searched(
            self.db, keyword=keyword, status=status, error_message=error, commit=commit
        )

    def is_url_excluded(self, url: str) -> bool:
        return exclude_memory_repository.is_excluded(self.db, "URL", url)

    def is_domain_excluded(self, domain: str) -> bool:
        return exclude_memory_repository.is_excluded(self.db, "DOMAIN", domain)

    def is_social_excluded(self, profile_url: str) -> bool:
        return exclude_memory_repository.is_excluded(self.db, "SOCIAL_PROFILE", profile_url)

    def mark_dead_url(self, url: str, reason: str = "DEAD_URL") -> None:
        exclude_memory_repository.add_exclusion(
            self.db, entity_type="URL", entity_value=url, reason=reason
        )

    def mark_duplicate_company(self, identifier: str) -> None:
        exclude_memory_repository.add_exclusion(
            self.db,
            entity_type="DOMAIN",
            entity_value=identifier,
            reason="DUPLICATE_COMPANY",
        )

    def is_company_duplicate(self, *, website: Optional[str], name: str) -> bool:
        if website:
            domain = urlparse(website).netloc.lower().replace("www.", "")
            if domain and self.is_domain_excluded(domain):
                return True
            existing = lead_repository.get_by_website(self.db, website)
            if existing:
                return True

        existing_by_name = lead_repository.get_by_name(self.db, name)
        return existing_by_name is not None

    def remember_company(
        self,
        *,
        name: str,
        website: Optional[str] = None,
        linkedin: Optional[str] = None,
        instagram: Optional[str] = None,
        email: Optional[str] = None,
        domain: Optional[str] = None,
        source: Optional[str] = None,
        status: str = "DISCOVERED",
        commit: bool = True,
    ) -> None:
        values = [
            ("COMPANY", name),
            ("WEBSITE", website),
            ("LINKEDIN", linkedin),
            ("INSTAGRAM", instagram),
            ("EMAIL", email),
            ("DOMAIN", domain),
        ]
        for entity_type, value in values:
            if value:
                exclude_memory_repository.add_exclusion(
                    self.db,
                    entity_type=entity_type,
                    entity_value=value,
                    reason=status,
                    commit=False,
                )

        if commit:
            self.db.commit()

    def seen_company(self, *, name: str, website: Optional[str] = None) -> bool:
        if self.is_company_duplicate(website=website, name=name):
            return True
        if website:
            normalized_domain = urlparse(website).netloc.lower().replace("www.", "")
            return self.is_domain_excluded(normalized_domain)
        return False

    def mark_exported(self, company_id: str) -> None:
        exclude_memory_repository.add_exclusion(
            self.db,
            entity_type="DOMAIN",
            entity_value=f"exported:{company_id}",
            reason="EXPORTED",
        )
