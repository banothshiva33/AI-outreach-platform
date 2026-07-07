from app.core.time import utc_now
from typing import Optional

from sqlalchemy.orm import Session
from uuid import UUID

from app.models.models import Job
from app.repositories.base import BaseRepository


class JobRepository(BaseRepository[Job]):
    def __init__(self):
        super().__init__(Job)

    def get_by_task_id(self, db: Session, task_id: str) -> Optional[Job]:
        return db.query(Job).filter(Job.task_id == task_id).first()

    def create_job(
        self,
        db: Session,
        *,
        task_id: str,
        name: str,
        run_id: Optional[UUID] = None,
    ) -> Job:
        return self.create(
            db,
            obj_in={
                "task_id": task_id,
                "name": name,
                "status": "PENDING",
                "run_id": run_id,
            },
        )

    def update_status(
        self,
        db: Session,
        *,
        job: Job,
        status: str,
        error: Optional[str] = None,
    ) -> Job:
        update_data = {"status": status, "updated_at": utc_now()}
        if error is not None:
            update_data["error"] = error
        return self.update(db, db_obj=job, obj_in=update_data)


job_repository = JobRepository()
