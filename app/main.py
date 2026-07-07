import logging
import os
from contextlib import asynccontextmanager
from typing import Callable, Optional

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api import categories_router, discovery_router, exports_router, leads_router
from app.core.config import settings
from app.core.database import SessionLocal, engine, get_db
from app.core.logging import setup_logging
from app.core.seed import seed_categories

logger = logging.getLogger("app.main")


def create_app(
    *,
    seed_on_startup: bool = True,
    require_db: Optional[bool] = None,
) -> FastAPI:
    db_required = settings.REQUIRE_DB_ON_STARTUP if require_db is None else require_db

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        setup_logging(settings.LOG_LEVEL)
        logger.info("Starting Startup Outreach Lead Collection Platform...")

        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            logger.info("Successfully connected to the database.")

            if seed_on_startup:
                db = SessionLocal()
                try:
                    seed_categories(db)
                finally:
                    db.close()
        except Exception as exc:
            logger.critical("Database connection failed during startup: %s", exc)
            if db_required:
                raise

        yield
        logger.info("Shutting down Startup Outreach Lead Collection Platform...")

    app = FastAPI(
        title="Startup Outreach Lead Collection Platform",
        description="Autonomous lead collection and analytics platform using modular AI agents.",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
    os.makedirs(static_dir, exist_ok=True)
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    app.include_router(leads_router)
    app.include_router(categories_router)
    app.include_router(discovery_router)
    app.include_router(exports_router)

    @app.get("/health", response_class=JSONResponse, tags=["Health"])
    def health_check(db: Session = Depends(get_db)):
        db_ok = False
        try:
            db.execute(text("SELECT 1"))
            db_ok = True
        except Exception as exc:
            logger.error("Health check database query failure: %s", exc)

        return {
            "status": "healthy" if db_ok else "unhealthy",
            "api": "ok",
            "database": "connected" if db_ok else "disconnected",
        }

    @app.get("/", tags=["Dashboard"])
    def root():
        return {
            "message": "Startup Outreach Lead Collection Platform API",
            "docs": "/docs",
            "health": "/health",
        }

    return app


app = create_app()
