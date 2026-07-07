from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.models import Category
from app.repositories.base import BaseRepository


class CategoryRepository(BaseRepository[Category]):
    def __init__(self):
        super().__init__(Category)

    def get_by_name(self, db: Session, name: str) -> Optional[Category]:
        return db.query(Category).filter(Category.name == name).first()

    def get_or_create(self, db: Session, name: str) -> Category:
        existing = self.get_by_name(db, name)
        if existing:
            return existing
        return self.create(db, obj_in={"name": name})

    def search_by_prefix(self, db: Session, prefix: str, limit: int = 50) -> List[Category]:
        return (
            db.query(Category)
            .filter(Category.name.ilike(f"{prefix}%"))
            .order_by(Category.name)
            .limit(limit)
            .all()
        )


category_repository = CategoryRepository()
