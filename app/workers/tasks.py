import logging
from uuid import UUID

from celery.exceptions import MaxRetriesExceededError

from app.core.database import SessionLocal
from app.discovery.engine import DiscoveryEngine
from app.repositories import agent_run_repository, job_repository
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.tasks.test_ping")
def test_ping(message: str) -> str:
    logger.info("Ping task received with message: %s", message)
    return f"Pong! Received: {message}"


@celery_app.task(
    name="app.workers.tasks.run_discovery",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def run_discovery_task(self, run_id: str) -> dict:
    db = SessionLocal()
    job = job_repository.get_by_task_id(db, self.request.id)
    try:
        if not job:
            job = job_repository.create_job(
                db,
                task_id=self.request.id,
                name="run_discovery",
                run_id=UUID(run_id),
            )
        job_repository.update_status(db, job=job, status="RUNNING")

        run = agent_run_repository.get(db, UUID(run_id))
        if not run:
            raise ValueError(f"Agent run {run_id} not found")

        config = run.config or {}
        engine = DiscoveryEngine(db, UUID(run_id))
        state = engine.run(
            max_keywords=config.get("max_keywords", 50),
            results_per_keyword=config.get("results_per_keyword", 10),
            resume=config.get("resume", True),
        )

        job_repository.update_status(db, job=job, status="SUCCESS")
        return {
            "run_id": run_id,
            "leads_found": state.leads_found,
            "keywords_processed": state.keywords_processed,
            "duplicates_skipped": state.duplicates_skipped,
            "errors": state.errors,
        }
    except Exception as exc:
        logger.exception("Discovery task failed for run %s", run_id)
        if job:
            job_repository.update_status(db, job=job, status="RETRY", error=str(exc))

        try:
            raise self.retry(exc=exc)
        except MaxRetriesExceededError:
            run = agent_run_repository.get(db, UUID(run_id))
            if run:
                agent_run_repository.complete_run(db, run=run, status="FAILED")
            if job:
                job_repository.update_status(db, job=job, status="FAILURE", error=str(exc))
            raise
    finally:
        db.close()
