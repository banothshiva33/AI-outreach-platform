from celery import Celery
from app.core.config import settings

# Initialize Celery app instance
celery_app = Celery(
    "outreach_agent_workers",
    broker=settings.redis_url,
    backend=settings.redis_url
)

# Celery Task Queue Settings
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Worker concurrency and tasks management
    worker_prefetch_multiplier=1, # Fetch one task at a time for fair distribution
    task_acks_late=True,          # Acknowledge task completion only after successful execution
    task_reject_on_worker_lost=True, # Reschedule tasks if worker container dies unexpectedly
)

# Auto-discover Celery tasks registered under the workers module
celery_app.autodiscover_tasks(["app.workers"])
