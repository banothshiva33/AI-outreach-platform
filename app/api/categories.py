from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import verify_api_key
from app.repositories import category_repository
from app.schemas import CategoryResponse

router = APIRouter(
    prefix="/api/categories",
    tags=["Categories"],
    dependencies=[Depends(verify_api_key)],
)


@router.get("", response_model=List[CategoryResponse])
def list_categories(
    skip: int = 0,
    limit: int = 200,
    db: Session = Depends(get_db),
):
    categories = category_repository.get_multi(db, skip=skip, limit=limit)
    return [CategoryResponse.model_validate(c) for c in categories]
