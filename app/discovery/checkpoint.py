import json
import logging
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.repositories import agent_run_repository

logger = logging.getLogger(__name__)


@dataclass
class CheckpointState:
    run_id: str
    keywords_processed: int = 0
    leads_found: int = 0
    duplicates_skipped: int = 0
    errors: int = 0
    last_keyword: Optional[str] = None
    batch_index: int = 0
    export_file: Optional[str] = None

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, data: str) -> "CheckpointState":
        return cls(**json.loads(data))


class CheckpointManager:
    """Persists and restores discovery engine checkpoint state."""

    def __init__(self, db: Session, run_id: UUID):
        self.db = db
        self.run_id = run_id
        self._state: Optional[CheckpointState] = None

    def load(self) -> CheckpointState:
        run = agent_run_repository.get(self.db, self.run_id)
        if run and run.last_checkpoint:
            try:
                self._state = CheckpointState.from_json(run.last_checkpoint)
                logger.info("Resumed checkpoint at keyword batch %d", self._state.batch_index)
                return self._state
            except (json.JSONDecodeError, TypeError):
                logger.warning("Invalid checkpoint data, starting fresh")

        self._state = CheckpointState(run_id=str(self.run_id))
        return self._state

    def save(self, state: CheckpointState, *, commit: bool = True) -> None:
        self._state = state
        run = agent_run_repository.get(self.db, self.run_id)
        if run:
            agent_run_repository.update_checkpoint(
                self.db, run=run, checkpoint=state.to_json(), commit=False
            )
            agent_run_repository.update_stats(
                self.db,
                run=run,
                stats={
                    "leads_found": state.leads_found,
                    "duplicates_skipped": state.duplicates_skipped,
                    "errors": state.errors,
                    "keywords_processed": state.keywords_processed,
                },
                commit=False,
            )
            if commit:
                self.db.commit()

    @property
    def state(self) -> CheckpointState:
        if self._state is None:
            return self.load()
        return self._state
