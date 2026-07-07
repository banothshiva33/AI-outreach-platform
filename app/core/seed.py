import logging

from sqlalchemy.orm import Session

from app.models.models import Category
from app.repositories import category_repository

logger = logging.getLogger("app.core.seed")

TARGET_CATEGORIES = [
    "Startup",
    "Startup India",
    "Entrepreneur",
    "Founder",
    "Co-founder",
    "CEO",
    "Business Coach",
    "Business Mentor",
    "Business News",
    "Startup News",
    "Accelerator",
    "Incubator",
    "Angel Investor",
    "VC",
    "AI Startup",
    "SaaS",
    "FinTech",
    "EdTech",
    "HealthTech",
    "AgriTech",
    "PropTech",
    "DeepTech",
    "Blockchain",
    "Cybersecurity",
    "Marketing Agency",
    "Product Company",
    "Tech Company",
    "Recruitment Company",
    "HR Company",
    "D2C",
    "E-commerce",
    "Manufacturing Startup",
    "Innovation Lab",
]


def seed_categories(db: Session) -> None:
    logger.info("Starting database seeding for categories...")
    existing = {
        name
        for (name,) in db.query(Category.name).filter(Category.name.in_(TARGET_CATEGORIES)).all()
    }
    to_create = [Category(name=name) for name in TARGET_CATEGORIES if name not in existing]
    if to_create:
        db.bulk_save_objects(to_create)
        db.commit()
    logger.info("Seeding completed. Added %s new categories.", len(to_create))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from app.core.database import SessionLocal

    session = SessionLocal()
    try:
        seed_categories(session)
    finally:
        session.close()
