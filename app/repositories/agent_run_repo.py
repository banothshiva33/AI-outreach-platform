from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models.models import AgentRun, Log
from app.repositories.base import BaseRepository


class ActiveRunError(Exception):
    pass


class AgentRunRepository(BaseRepository[AgentRun]):
    def __init__(self):
        super().__init__(AgentRun)

    def get_active_run(self, db: Session) -> Optional[AgentRun]:
        return (
            db.query(AgentRun)
            .filter(AgentRun.status == "RUNNING")
            .order_by(AgentRun.started_at.desc())
            .first()
        )

    def create_run(
        self,
        db: Session,
        *,
        trigger_type: str = "MANUAL",
        config: Optional[Dict[str, Any]] = None,
    ) -> AgentRun:
        active = (
            db.query(AgentRun)
            .filter(AgentRun.status == "RUNNING")
            .with_for_update()
            .first()
        )
        if active:
            raise ActiveRunError(str(active.id))

        run = AgentRun(
            status="RUNNING",
            trigger_type=trigger_type,
            config=config or {},
            stats={"leads_found": 0, "duplicates_skipped": 0, "errors": 0},
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    def update_checkpoint(
        self, db: Session, *, run: AgentRun, checkpoint: str, commit: bool = True
    ) -> AgentRun:
        return self.update(
            db, db_obj=run, obj_in={"last_checkpoint": checkpoint}, commit=commit
        )

    def update_stats(
        self,
        db: Session,
        *,
        run: AgentRun,
        stats: Dict[str, Any],
        commit: bool = True,
    ) -> AgentRun:
        merged = {**(run.stats or {}), **stats}
        return self.update(db, db_obj=run, obj_in={"stats": merged}, commit=commit)

    def complete_run(
        self,
        db: Session,
        *,
        run: AgentRun,
        status: str = "COMPLETED",
        commit: bool = True,
    ) -> AgentRun:
        return self.update(
            db,
            db_obj=run,
            obj_in={"status": status, "ended_at": utc_now()},
            commit=commit,
        )

    def add_log(
        self,
        db: Session,
        *,
        run_id: UUID,
        level: str,
        module: str,
        message: str,
        extra: Optional[Dict[str, Any]] = None,
        commit: bool = False,
    ) -> Log:
        log = Log(
            run_id=run_id,
            level=level,
            module=module,
            message=message,
            extra=extra,
        )
        db.add(log)
        if commit:
            db.commit()
            db.refresh(log)
        else:
            db.flush()
        return log

    def get_logs(
        self, db: Session, *, run_id: UUID, skip: int = 0, limit: int = 100
    ) -> List[Log]:
        return (
            db.query(Log)
            .filter(Log.run_id == run_id)
            .order_by(Log.timestamp.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )


agent_run_repository = AgentRunRepository()
