import os
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import verify_api_key
from app.repositories import export_repository, lead_repository
from app.schemas import ExportRequest, ExportResponse
from app.core.config import settings
from app.services.export_service import ExportService

router = APIRouter(
    prefix="/api/exports",
    tags=["Exports"],
    dependencies=[Depends(verify_api_key)],
)

export_service = ExportService(export_dir=settings.EXPORT_DIR)


def _safe_export_path(file_path: str) -> str:
    export_root = os.path.realpath(settings.EXPORT_DIR)
    resolved = os.path.realpath(file_path)
    if not resolved.startswith(export_root):
        raise HTTPException(status_code=400, detail="Invalid export path")
    return resolved


@router.post("", response_model=ExportResponse, status_code=201)
def create_export(payload: ExportRequest, db: Session = Depends(get_db)):
    skip = 0
    if payload.resume_export_id:
        prior = export_repository.get(db, payload.resume_export_id)
        if prior:
            skip = prior.records_count

    companies = lead_repository.search_leads(
        db,
        query=payload.query,
        category=payload.category,
        city=payload.city,
        state=payload.state,
        country=payload.country,
        min_lead_score=payload.min_lead_score,
        skip=skip,
        limit=10000,
    )

    file_name, file_path, count = export_service.export_leads(
        companies,
        format=payload.format,
    )

    record = export_repository.create_export(
        db,
        file_name=file_name,
        file_path=file_path,
        format=payload.format.upper(),
        records_count=skip + count,
        filters=payload.model_dump(exclude={"resume_export_id"}),
    )
    return ExportResponse.model_validate(record)


@router.get("", response_model=list[ExportResponse])
def list_exports(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    exports = export_repository.get_recent(db, limit=limit)
    return [ExportResponse.model_validate(item) for item in exports]


@router.get("/{export_id}/download")
def download_export(export_id: UUID, db: Session = Depends(get_db)):
    record = export_repository.get(db, export_id)
    if not record:
        raise HTTPException(status_code=404, detail="Export not found")

    safe_path = _safe_export_path(record.file_path)
    if not os.path.exists(safe_path):
        raise HTTPException(status_code=404, detail="Export file missing on disk")

    return FileResponse(
        safe_path,
        filename=record.file_name,
        media_type="application/octet-stream",
    )
