from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
import os
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from mediaorchard.controller.db.models import Job, Node, utcnow
from mediaorchard.controller.db.session import create_db_engine, init_db
from mediaorchard.shared.enums import NodeStatus
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
        node.last_heartbeat_at = datetime.now(UTC)
        node.updated_at = utcnow()
        session.add(node)
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
        try:
            input_file = resolve_allowlisted_path(body.input_file, [request.app.state.shared_root])
        except PathSecurityError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

        job = Job(
            goal_type=body.goal_type,
            input_file=str(input_file),
            output_dir="",
            priority=body.priority,
            language=body.language,
            quality=body.quality,
            requested_outputs=body.outputs,
            user_request=body.user_request,
        )
        job.output_dir = str(build_job_output_dir(request.app.state.shared_root / "output", job.id))
        session.add(job)
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

    @app.post("/steps/claim-next", status_code=status.HTTP_204_NO_CONTENT)
    def claim_next(_: None = Depends(require_worker_auth)) -> Response:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return app


app = create_app(
    database_url=os.getenv("MEDIAORCHARD_DATABASE_URL", "sqlite:///mediaorchard.db"),
    api_key_hash=os.getenv("MEDIAORCHARD_API_KEY_HASH", "__unset__"),
    shared_root=os.getenv("MEDIAORCHARD_SHARED_ROOT", "/Volumes/MediaOrchard"),
)
