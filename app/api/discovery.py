import logging
import json
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import verify_api_key
from app.repositories import agent_run_repository
from app.repositories.agent_run_repo import ActiveRunError
from app.schemas import AgentRunResponse, DiscoveryStartRequest, DiscoveryStatusResponse
from app.workers.tasks import run_discovery_task

router = APIRouter(
    prefix="/api/discovery",
    tags=["Discovery"],
    dependencies=[Depends(verify_api_key)],
)

logger = logging.getLogger(__name__)


@router.post("/start")
def start_discovery(
    payload: DiscoveryStartRequest,
    db: Session = Depends(get_db),
):
    max_keywords = min(payload.max_keywords, settings.DISCOVERY_MAX_KEYWORDS)
    results_per_keyword = min(
        payload.results_per_keyword, settings.DISCOVERY_MAX_RESULTS_PER_KEYWORD
    )

    try:
        run = agent_run_repository.create_run(
            db,
            trigger_type="MANUAL",
            config={
                "max_keywords": max_keywords,
                "results_per_keyword": results_per_keyword,
                "resume": payload.resume,
            },
        )
    except ActiveRunError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Discovery already running (run_id={exc})",
        ) from exc

    logger.info(
        json.dumps(
            {
                "stage": "api_start",
                "event": "post_api_discovery_start",
                "run_id": str(run.id),
                "max_keywords": max_keywords,
                "results_per_keyword": results_per_keyword,
                "resume": payload.resume,
            }
        ),
    )

    task = run_discovery_task.delay(str(run.id))
    return {
        "message": "Discovery engine started",
        "run_id": str(run.id),
        "task_id": task.id,
    }


@router.get("/status", response_model=DiscoveryStatusResponse)
def discovery_status(db: Session = Depends(get_db)):
    active = agent_run_repository.get_active_run(db)
    return DiscoveryStatusResponse(
        is_running=active is not None,
        active_run=AgentRunResponse.model_validate(active) if active else None,
        message="Discovery running" if active else "Discovery idle",
    )


@router.post("/pause/{run_id}")
def pause_discovery(run_id: UUID, db: Session = Depends(get_db)):
    run = agent_run_repository.get(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    agent_run_repository.update(db, db_obj=run, obj_in={"status": "PAUSED"})
    return {"message": "Discovery paused", "run_id": str(run_id)}


@router.post("/resume/{run_id}")
def resume_discovery(run_id: UUID, db: Session = Depends(get_db)):
    run = agent_run_repository.get(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status != "PAUSED":
        raise HTTPException(status_code=400, detail="Run is not paused")

    active = agent_run_repository.get_active_run(db)
    if active:
        raise HTTPException(status_code=409, detail="Another discovery run is active")

    agent_run_repository.update(db, db_obj=run, obj_in={"status": "RUNNING"})
    task = run_discovery_task.delay(str(run.id))
    return {"message": "Discovery resumed", "run_id": str(run_id), "task_id": task.id}


@router.get("/runs/{run_id}", response_model=AgentRunResponse)
def get_run(run_id: UUID, db: Session = Depends(get_db)):
    run = agent_run_repository.get(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return AgentRunResponse.model_validate(run)


@router.get("/runs/{run_id}/logs")
def get_run_logs(
    run_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    run = agent_run_repository.get(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    logs = agent_run_repository.get_logs(db, run_id=run_id, skip=skip, limit=limit)
    return [
        {
            "level": log.level,
            "module": log.module,
            "message": log.message,
            "extra": log.extra,
            "timestamp": log.timestamp.isoformat(),
        }
        for log in logs
    ]
