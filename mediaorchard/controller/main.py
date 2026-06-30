from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
import os
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlmodel import Session, select

from mediaorchard.controller.db.models import Job, Node, Plan, Step, utcnow
from mediaorchard.controller.db.session import create_db_engine, init_db
from mediaorchard.controller.runtime.state_machine import (
    TransitionError,
    transition_step,
    validate_assignment_epoch,
)
from mediaorchard.controller.scheduler.loop import SchedulerError, assign_best_node
from mediaorchard.controller.scheduler.policies import SchedulerConfig
from mediaorchard.shared.enums import JobStatus, NodeStatus, StepStatus
from mediaorchard.shared.paths import (
    PathSecurityError,
    build_job_output_dir,
    resolve_allowlisted_path,
    validate_shared_root,
)
from mediaorchard.shared.security import verify_api_key


class NodeRegisterRequest(BaseModel):
    node_id: str
    name: str
    shared_root: str
    max_ffmpeg_jobs: int = 1
    max_whisper_jobs: int = 1


class NodeHeartbeatRequest(BaseModel):
    cpu_percent: float = Field(ge=0)
    memory_percent: float = Field(ge=0)
    free_disk_gb: float = Field(ge=0)
    active_jobs: int = Field(ge=0)
    active_ffmpeg_jobs: int = Field(ge=0)
    active_whisper_jobs: int = Field(ge=0)
    thermal_state: str
    on_battery: bool


class JobCreateRequest(BaseModel):
    goal_type: str
    input_file: str
    outputs: list[str]
    language: str | None = None
    quality: str = "standard"
    priority: int = 5
    user_request: str | None = None


class StepEpochRequest(BaseModel):
    assignment_epoch: int


class StepClaimNextRequest(BaseModel):
    node_id: str


class StepProgressRequest(StepEpochRequest):
    percent: float | None = Field(default=None, ge=0, le=100)
    message: str | None = None


class StepCompleteRequest(StepEpochRequest):
    output_json: dict = Field(default_factory=dict)


class StepFailRequest(StepEpochRequest):
    error_message: str


def create_app(
    *,
    database_url: str = "sqlite:///mediaorchard.db",
    api_key_hash: str = "",
    shared_root: str | Path = "/Volumes/MediaOrchard",
) -> FastAPI:
    app = FastAPI(title="MediaOrchard Controller")
    engine = create_db_engine(database_url)
    init_db(engine)
    app.state.engine = engine
    app.state.session_factory = lambda: Session(engine)
    app.state.api_key_hash = api_key_hash
    app.state.shared_root = Path(shared_root).expanduser().resolve(strict=False)

    def get_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    def require_worker_auth(
        request: Request,
        authorization: str | None = Header(default=None),
        x_mediaorchard_key: str | None = Header(default=None),
    ) -> None:
        raw_key = x_mediaorchard_key
        if authorization and authorization.lower().startswith("bearer "):
            raw_key = authorization.split(" ", 1)[1]

        if not verify_api_key(raw_key or "", request.app.state.api_key_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid worker api key")

    def require_worker_node_id(
        x_mediaorchard_node_id: str | None = Header(default=None),
    ) -> str:
        if not x_mediaorchard_node_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="missing worker node id")
        return x_mediaorchard_node_id

    def schedule_queued_steps(session: Session, now: datetime) -> None:
        # Caller owns the surrounding transaction so heartbeat metrics and assignments commit together.
        queued_steps = list(
            session.exec(
                select(Step)
                .where(Step.status == StepStatus.QUEUED)
                .order_by(Step.id)
            ).all()
        )
        if not queued_steps:
            return

        nodes = list(session.exec(select(Node)).all())
        scheduler_config = SchedulerConfig(shared_root=str(app.state.shared_root))
        for step in queued_steps:
            try:
                decision = assign_best_node(step, nodes, scheduler_config, now=now)
            except SchedulerError:
                continue
            if decision.selected_node is not None:
                session.add(step)
                session.add(decision.selected_node)

    def mark_job_running(session: Session, job_id: str) -> None:
        job = session.get(Job, job_id)
        if job is None:
            return
        if job.status in {JobStatus.CREATED, JobStatus.QUEUED}:
            job.status = JobStatus.RUNNING
            job.progress = max(job.progress, 1.0)
            job.updated_at = utcnow()
            session.add(job)
            session.commit()

    def mark_job_after_step_completion(session: Session, job_id: str) -> None:
        job = session.get(Job, job_id)
        if job is None:
            return
        steps = list(session.exec(select(Step).where(Step.job_id == job_id)).all())
        if not steps:
            job.status = JobStatus.FAILED
            job.error_message = "job has no steps"
            job.completed_at = utcnow()
            job.updated_at = utcnow()
            session.add(job)
            session.commit()
            return

        completed_count = sum(1 for step in steps if step.status == StepStatus.COMPLETED)
        job.progress = round((completed_count / len(steps)) * 100, 2)
        if completed_count == len(steps):
            job.status = JobStatus.COMPLETED
            job.completed_at = utcnow()
        else:
            job.status = JobStatus.RUNNING
        job.updated_at = utcnow()
        session.add(job)
        session.commit()

    def mark_job_failed(session: Session, job_id: str, error_message: str) -> None:
        job = session.get(Job, job_id)
        if job is None:
            return
        job.status = JobStatus.FAILED
        job.error_message = error_message
        job.completed_at = utcnow()
        job.updated_at = utcnow()
        session.add(job)
        session.commit()

    @app.get("/nodes")
    def list_nodes(
        _: None = Depends(require_worker_auth),
        session: Session = Depends(get_session),
        limit: int = 100,
        offset: int = 0,
    ) -> list[Node]:
        return list(session.exec(select(Node).offset(offset).limit(limit)).all())

    @app.get("/nodes/{node_id}")
    def get_node(
        node_id: str,
        _: None = Depends(require_worker_auth),
        session: Session = Depends(get_session),
    ) -> Node:
        node = session.get(Node, node_id)
        if node is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="node not found")
        return node

    @app.post("/nodes/register", status_code=status.HTTP_201_CREATED)
    def register_node(
        body: NodeRegisterRequest,
        request: Request,
        _: None = Depends(require_worker_auth),
        session: Session = Depends(get_session),
    ) -> Node:
        shared_check = validate_shared_root(body.shared_root, request.app.state.shared_root)
        if not shared_check.ok:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=shared_check.reason)

        node = session.get(Node, body.node_id) or Node(
            id=body.node_id,
            name=body.name,
            shared_root=str(shared_check.worker_root),
        )
        node.name = body.name
        node.host = request.client.host if request.client else None
        node.status = NodeStatus.ONLINE
        node.shared_root = str(shared_check.worker_root)
        node.max_ffmpeg_jobs = body.max_ffmpeg_jobs
        node.max_whisper_jobs = body.max_whisper_jobs
        node.updated_at = utcnow()
        session.add(node)
        session.commit()
        session.refresh(node)
        return node

    @app.post("/nodes/{node_id}/heartbeat")
    def heartbeat_node(
        node_id: str,
        body: NodeHeartbeatRequest,
        _: None = Depends(require_worker_auth),
        session: Session = Depends(get_session),
    ) -> Node:
        node = session.get(Node, node_id)
        if node is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="node not found")

        node.cpu_percent = body.cpu_percent
        node.memory_percent = body.memory_percent
        node.free_disk_gb = body.free_disk_gb
        node.active_jobs = body.active_jobs
        node.active_ffmpeg_jobs = body.active_ffmpeg_jobs
        node.active_whisper_jobs = body.active_whisper_jobs
        node.thermal_state = body.thermal_state
        node.on_battery = body.on_battery
        now = datetime.now(UTC)
        node.last_heartbeat_at = now
        node.updated_at = utcnow()
        session.add(node)
        schedule_queued_steps(session, now)
        session.commit()
        session.refresh(node)
        return node

    @app.post("/jobs", status_code=status.HTTP_201_CREATED)
    def create_job(
        body: JobCreateRequest,
        request: Request,
        _: None = Depends(require_worker_auth),
        session: Session = Depends(get_session),
    ) -> Job:
        if body.goal_type != "video_to_subtitle":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="unsupported goal_type for MVP",
            )
        try:
            input_file = resolve_allowlisted_path(body.input_file, [request.app.state.shared_root])
        except PathSecurityError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

        job = Job(
            goal_type=body.goal_type,
            input_file=str(input_file),
            output_dir="",
            status=JobStatus.QUEUED,
            priority=body.priority,
            language=body.language,
            quality=body.quality,
            requested_outputs=body.outputs,
            user_request=body.user_request,
        )
        job.output_dir = str(build_job_output_dir(request.app.state.shared_root / "output", job.id))
        plan = Plan(
            job_id=job.id,
            status="queued",
            plan_json={
                "version": "1",
                "goal_type": body.goal_type,
                "steps": ["video_to_subtitle_pipeline"],
            },
        )
        job.plan_id = plan.id
        step = Step(
            job_id=job.id,
            plan_id=plan.id,
            step_type="video_to_subtitle",
            tool_name="video_to_subtitle_pipeline",
            status=StepStatus.QUEUED,
            input_json={
                "input_file": str(input_file),
                "output_dir": job.output_dir,
                "work_dir": str(request.app.state.shared_root / "work" / job.id),
                "requested_outputs": body.outputs,
                "language": body.language,
                "quality": body.quality,
            },
        )
        session.add(job)
        session.add(plan)
        session.add(step)
        session.commit()
        session.refresh(job)
        return job

    @app.get("/jobs")
    def list_jobs(
        _: None = Depends(require_worker_auth),
        session: Session = Depends(get_session),
        limit: int = 100,
        offset: int = 0,
    ) -> list[Job]:
        return list(session.exec(select(Job).offset(offset).limit(limit)).all())

    @app.get("/jobs/{job_id}")
    def get_job(
        job_id: str,
        _: None = Depends(require_worker_auth),
        session: Session = Depends(get_session),
    ) -> Job:
        job = session.get(Job, job_id)
        if job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
        return job

    def get_step_or_404(step_id: str, session: Session) -> Step:
        step = session.get(Step, step_id)
        if step is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="step not found")
        return step

    def validate_epoch_or_409(step: Step, assignment_epoch: int) -> None:
        try:
            validate_assignment_epoch(step, assignment_epoch)
        except TransitionError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    def transition_or_409(step: Step, target: StepStatus) -> StepStatus:
        try:
            return transition_step(step.status, target)
        except TransitionError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    def validate_worker_ownership(step: Step, worker_node_id: str) -> None:
        if step.assigned_node_id != worker_node_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="worker does not own assigned step")

    def persist_step_update_or_409(
        session: Session,
        step: Step,
        *,
        worker_node_id: str,
        from_statuses: set[StepStatus],
        values: dict,
        require_unclaimed: bool = False,
    ) -> Step:
        statement = (
            update(Step)
            .where(Step.id == step.id)
            .where(Step.assignment_epoch == step.assignment_epoch)
            .where(Step.assigned_node_id == worker_node_id)
            .where(Step.status.in_(from_statuses))
        )
        if require_unclaimed:
            statement = statement.where(Step.claimed_at.is_(None))

        result = session.exec(statement.values(**values))
        if result.rowcount != 1:
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="step changed before lifecycle update",
            )
        session.commit()
        refreshed = session.get(Step, step.id)
        if refreshed is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="step not found")
        return refreshed

    @app.post("/steps/claim-next", response_model=None)
    def claim_next(
        body: StepClaimNextRequest,
        _: None = Depends(require_worker_auth),
        worker_node_id: str = Depends(require_worker_node_id),
        session: Session = Depends(get_session),
    ) -> Step | Response:
        if body.node_id != worker_node_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="worker node id mismatch")

        step = session.exec(
            select(Step)
            .where(Step.status == StepStatus.ASSIGNED)
            .where(Step.assigned_node_id == worker_node_id)
            .where(Step.claimed_at.is_(None))
            .order_by(Step.assigned_at)
            .limit(1)
        ).first()
        if step is None:
            return Response(status_code=status.HTTP_204_NO_CONTENT)

        now = datetime.now(UTC)
        result = session.exec(
            update(Step)
            .where(Step.id == step.id)
            .where(Step.status == StepStatus.ASSIGNED)
            .where(Step.assigned_node_id == worker_node_id)
            .where(Step.claimed_at.is_(None))
            .values(claimed_at=now)
        )
        if result.rowcount != 1:
            session.rollback()
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        session.commit()
        step = session.get(Step, step.id)
        if step is None:
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        return step

    @app.post("/steps/{step_id}/start")
    def start_step(
        step_id: str,
        body: StepEpochRequest,
        _: None = Depends(require_worker_auth),
        worker_node_id: str = Depends(require_worker_node_id),
        session: Session = Depends(get_session),
    ) -> Step:
        step = get_step_or_404(step_id, session)
        validate_worker_ownership(step, worker_node_id)
        validate_epoch_or_409(step, body.assignment_epoch)
        next_status = transition_or_409(step, StepStatus.RUNNING)
        updated = persist_step_update_or_409(
            session,
            step,
            worker_node_id=worker_node_id,
            from_statuses={StepStatus.ASSIGNED},
            values={"status": next_status, "started_at": datetime.now(UTC)},
        )
        mark_job_running(session, updated.job_id)
        return updated

    @app.post("/steps/{step_id}/progress")
    def progress_step(
        step_id: str,
        body: StepProgressRequest,
        _: None = Depends(require_worker_auth),
        worker_node_id: str = Depends(require_worker_node_id),
        session: Session = Depends(get_session),
    ) -> Step:
        step = get_step_or_404(step_id, session)
        validate_worker_ownership(step, worker_node_id)
        validate_epoch_or_409(step, body.assignment_epoch)
        progress_payload = {"percent": body.percent, "message": body.message}
        output_json = {**(step.output_json or {}), "progress": progress_payload}
        return persist_step_update_or_409(
            session,
            step,
            worker_node_id=worker_node_id,
            from_statuses={StepStatus.RUNNING},
            values={"output_json": output_json},
        )

    @app.post("/steps/{step_id}/complete")
    def complete_step(
        step_id: str,
        body: StepCompleteRequest,
        _: None = Depends(require_worker_auth),
        worker_node_id: str = Depends(require_worker_node_id),
        session: Session = Depends(get_session),
    ) -> Step:
        step = get_step_or_404(step_id, session)
        validate_worker_ownership(step, worker_node_id)
        validate_epoch_or_409(step, body.assignment_epoch)
        next_status = transition_or_409(step, StepStatus.COMPLETED)
        updated = persist_step_update_or_409(
            session,
            step,
            worker_node_id=worker_node_id,
            from_statuses={StepStatus.RUNNING},
            values={
                "status": next_status,
                "output_json": body.output_json,
                "completed_at": datetime.now(UTC),
            },
        )
        mark_job_after_step_completion(session, updated.job_id)
        return updated

    @app.post("/steps/{step_id}/fail")
    def fail_step(
        step_id: str,
        body: StepFailRequest,
        _: None = Depends(require_worker_auth),
        worker_node_id: str = Depends(require_worker_node_id),
        session: Session = Depends(get_session),
    ) -> Step:
        step = get_step_or_404(step_id, session)
        validate_worker_ownership(step, worker_node_id)
        validate_epoch_or_409(step, body.assignment_epoch)
        next_status = transition_or_409(step, StepStatus.FAILED)
        updated = persist_step_update_or_409(
            session,
            step,
            worker_node_id=worker_node_id,
            from_statuses={StepStatus.ASSIGNED, StepStatus.RUNNING},
            values={
                "status": next_status,
                "error_message": body.error_message,
                "completed_at": datetime.now(UTC),
            },
        )
        mark_job_failed(session, updated.job_id, body.error_message)
        return updated

    @app.post("/steps/{step_id}/claim")
    def claim_step(
        step_id: str,
        body: StepEpochRequest,
        _: None = Depends(require_worker_auth),
        worker_node_id: str = Depends(require_worker_node_id),
        session: Session = Depends(get_session),
    ) -> Step:
        step = get_step_or_404(step_id, session)
        validate_worker_ownership(step, worker_node_id)
        validate_epoch_or_409(step, body.assignment_epoch)
        if step.status != StepStatus.ASSIGNED:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="step is not assigned")
        return persist_step_update_or_409(
            session,
            step,
            worker_node_id=worker_node_id,
            from_statuses={StepStatus.ASSIGNED},
            values={"claimed_at": datetime.now(UTC)},
            require_unclaimed=True,
        )

    return app


app = create_app(
    database_url=os.getenv("MEDIAORCHARD_DATABASE_URL", "sqlite:///mediaorchard.db"),
    api_key_hash=os.getenv("MEDIAORCHARD_API_KEY_HASH", "__unset__"),
    shared_root=os.getenv("MEDIAORCHARD_SHARED_ROOT", "/Volumes/MediaOrchard"),
)
