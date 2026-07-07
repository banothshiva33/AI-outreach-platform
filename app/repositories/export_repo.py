from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.models import Export
from app.repositories.base import BaseRepository


class ExportRepository(BaseRepository[Export]):
    def __init__(self):
        super().__init__(Export)

    def create_export(
        self,
        db: Session,
        *,
        file_name: str,
        file_path: str,
        format: str,
        records_count: int = 0,
        filters: Optional[Dict[str, Any]] = None,
        user_id: Optional[UUID] = None,
    ) -> Export:
        return self.create(
            db,
            obj_in={
                "file_name": file_name,
                "file_path": file_path,
                "format": format,
                "records_count": records_count,
                "filters": filters,
                "user_id": user_id,
            },
        )

    def get_recent(self, db: Session, *, limit: int = 20) -> List[Export]:
        return (
            db.query(Export)
            .order_by(Export.created_at.desc())
            .limit(limit)
            .all()
        )


export_repository = ExportRepository()
