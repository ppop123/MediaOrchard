from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Column
from sqlalchemy.types import DateTime, JSON, TypeDecorator
from sqlmodel import Field, SQLModel

from mediaorchard.shared.enums import JobStatus, NodeStatus, StepStatus


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


def prefixed_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class Node(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    host: str | None = None
    status: NodeStatus = Field(default=NodeStatus.ONLINE)
    shared_root: str
    auth_key_id: str | None = None
    max_ffmpeg_jobs: int = 1
    max_whisper_jobs: int = 1
    active_jobs: int = 0
    active_ffmpeg_jobs: int = 0
    active_whisper_jobs: int = 0
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    free_disk_gb: float = 0.0
    thermal_state: str = "unknown"
    on_battery: bool = False
    last_heartbeat_at: datetime | None = Field(default=None, sa_column=Column(UTCDateTime(), nullable=True))
    created_at: datetime = Field(default_factory=utcnow, sa_column=Column(UTCDateTime(), nullable=False))
    updated_at: datetime = Field(default_factory=utcnow, sa_column=Column(UTCDateTime(), nullable=False))


class Job(SQLModel, table=True):
    id: str = Field(default_factory=lambda: prefixed_id("job"), primary_key=True)
    goal_type: str
    input_file: str
    output_dir: str
    status: JobStatus = Field(default=JobStatus.CREATED)
    priority: int = 5
    language: str | None = None
    quality: str = "standard"
    requested_outputs: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    user_request: str | None = None
    plan_id: str | None = None
    progress: float = 0.0
    error_message: str | None = None
    created_at: datetime = Field(default_factory=utcnow, sa_column=Column(UTCDateTime(), nullable=False))
    updated_at: datetime = Field(default_factory=utcnow, sa_column=Column(UTCDateTime(), nullable=False))
    completed_at: datetime | None = Field(default=None, sa_column=Column(UTCDateTime(), nullable=True))


class Plan(SQLModel, table=True):
    id: str = Field(default_factory=lambda: prefixed_id("plan"), primary_key=True)
    job_id: str
    status: str = "created"
    created_by: str = "rules"
    plan_schema_version: str = "1"
    plan_json: dict[str, Any] = Field(default_factory=lambda: {"version": "1"}, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow, sa_column=Column(UTCDateTime(), nullable=False))
    updated_at: datetime = Field(default_factory=utcnow, sa_column=Column(UTCDateTime(), nullable=False))


class Step(SQLModel, table=True):
    id: str = Field(default_factory=lambda: prefixed_id("step"), primary_key=True)
    job_id: str
    plan_id: str
    step_type: str
    tool_name: str
    status: StepStatus = Field(default=StepStatus.PENDING)
    depends_on: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    assigned_node_id: str | None = None
    assigned_at: datetime | None = Field(default=None, sa_column=Column(UTCDateTime(), nullable=True))
    claimed_at: datetime | None = Field(default=None, sa_column=Column(UTCDateTime(), nullable=True))
    assignment_epoch: int = 0
    input_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    output_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    retry_count: int = 0
    max_retries: int = 2
    started_at: datetime | None = Field(default=None, sa_column=Column(UTCDateTime(), nullable=True))
    completed_at: datetime | None = Field(default=None, sa_column=Column(UTCDateTime(), nullable=True))
    error_message: str | None = None


class ToolCall(SQLModel, table=True):
    id: str = Field(default_factory=lambda: prefixed_id("tool"), primary_key=True)
    job_id: str
    step_id: str
    node_id: str
    tool_name: str
    args_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    status: str = "created"
    stdout_path: str | None = None
    stderr_path: str | None = None
    exit_code: int | None = None
    started_at: datetime | None = Field(default=None, sa_column=Column(UTCDateTime(), nullable=True))
    completed_at: datetime | None = Field(default=None, sa_column=Column(UTCDateTime(), nullable=True))


class AgentDecision(SQLModel, table=True):
    id: str = Field(default_factory=lambda: prefixed_id("decision"), primary_key=True)
    job_id: str
    agent_name: str
    decision_type: str
    decision_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    reason: str
    confidence: float | None = None
    created_at: datetime = Field(default_factory=utcnow, sa_column=Column(UTCDateTime(), nullable=False))


class QualityReport(SQLModel, table=True):
    id: str = Field(default_factory=lambda: prefixed_id("quality"), primary_key=True)
    job_id: str
    status: str
    checks_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    warnings_json: list[Any] = Field(default_factory=list, sa_column=Column(JSON))
    recommendations_json: list[Any] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow, sa_column=Column(UTCDateTime(), nullable=False))
