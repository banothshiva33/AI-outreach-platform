from typing import List, Optional, Set

from sqlalchemy import nullsfirst
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models.models import ExcludeMemory, SearchHistory
from app.repositories.base import BaseRepository


class SearchHistoryRepository(BaseRepository[SearchHistory]):
    def __init__(self):
        super().__init__(SearchHistory)

    def get_by_keyword(self, db: Session, keyword: str) -> Optional[SearchHistory]:
        normalized = keyword.strip().lower()
        return (
            db.query(SearchHistory)
            .filter(SearchHistory.keyword == normalized)
            .first()
        )

    def get_processed_keywords(self, db: Session, keywords: List[str]) -> Set[str]:
        normalized = [keyword.strip().lower() for keyword in keywords if keyword.strip()]
        if not normalized:
            return set()
        rows = (
            db.query(SearchHistory.keyword)
            .filter(
                SearchHistory.keyword.in_(normalized),
                SearchHistory.status == "COMPLETED",
            )
            .all()
        )
        return {row[0] for row in rows}

    def mark_searched(
        self,
        db: Session,
        *,
        keyword: str,
        status: str = "COMPLETED",
        error_message: Optional[str] = None,
        commit: bool = True,
    ) -> SearchHistory:
        normalized = keyword.strip().lower()
        existing = self.get_by_keyword(db, normalized)
        if existing:
            existing.status = status
            existing.search_count = (existing.search_count or 0) + 1
            existing.last_searched = utc_now()
            existing.error_message = error_message
            if commit:
                db.commit()
                db.refresh(existing)
            else:
                db.flush()
            return existing

        record = SearchHistory(
            keyword=normalized,
            status=status,
            search_count=1,
            last_searched=utc_now(),
            error_message=error_message,
        )
        db.add(record)
        if commit:
            db.commit()
            db.refresh(record)
        else:
            db.flush()
        return record

    def get_pending_keywords(
        self, db: Session, *, limit: int = 100, after_keyword: Optional[str] = None
    ) -> List[SearchHistory]:
        query = db.query(SearchHistory).filter(SearchHistory.status == "PENDING")
        if after_keyword:
            query = query.filter(SearchHistory.keyword > after_keyword.strip().lower())
        return (
            query.order_by(nullsfirst(SearchHistory.last_searched.asc()), SearchHistory.keyword.asc())
            .limit(limit)
            .all()
        )

    def is_processed(self, db: Session, keyword: str) -> bool:
        record = self.get_by_keyword(db, keyword)
        return record is not None and record.status == "COMPLETED"


class ExcludeMemoryRepository(BaseRepository[ExcludeMemory]):
    def __init__(self):
        super().__init__(ExcludeMemory)

    def is_excluded(self, db: Session, entity_type: str, entity_value: str) -> bool:
        normalized = entity_value.strip().lower()
        return (
            db.query(ExcludeMemory)
            .filter(
                ExcludeMemory.entity_type == entity_type,
                ExcludeMemory.entity_value == normalized,
            )
            .first()
            is not None
        )

    def add_exclusion(
        self,
        db: Session,
        *,
        entity_type: str,
        entity_value: str,
        reason: Optional[str] = None,
        commit: bool = True,
    ) -> ExcludeMemory:
        normalized = entity_value.strip().lower()
        existing = (
            db.query(ExcludeMemory)
            .filter(
                ExcludeMemory.entity_type == entity_type,
                ExcludeMemory.entity_value == normalized,
            )
            .first()
        )
        if existing:
            return existing

        record = ExcludeMemory(
            entity_type=entity_type,
            entity_value=normalized,
            reason=reason,
        )
        db.add(record)
        if commit:
            db.commit()
            db.refresh(record)
        else:
            db.flush()
        return record

    def get_by_type(
        self, db: Session, entity_type: str, *, skip: int = 0, limit: int = 500
    ) -> List[ExcludeMemory]:
        return (
            db.query(ExcludeMemory)
            .filter(ExcludeMemory.entity_type == entity_type)
            .offset(skip)
            .limit(limit)
            .all()
        )


search_history_repository = SearchHistoryRepository()
exclude_memory_repository = ExcludeMemoryRepository()
