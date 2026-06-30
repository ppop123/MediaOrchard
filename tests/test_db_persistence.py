from datetime import UTC, datetime

from sqlalchemy import inspect
from sqlmodel import Session

from mediaorchard.controller.db.models import (
    AgentDecision,
    Job,
    Node,
    Plan,
    QualityReport,
    Step,
    ToolCall,
)
from mediaorchard.controller.db.session import create_db_engine, init_db
from mediaorchard.shared.enums import JobStatus, NodeStatus, StepStatus


def make_engine(tmp_path):
    engine = create_db_engine(f"sqlite:///{tmp_path / 'test.db'}")
    init_db(engine)
    return engine


def test_init_db_creates_all_release_model_tables(tmp_path):
    engine = make_engine(tmp_path)

    tables = set(inspect(engine).get_table_names())

    assert {
        "node",
        "job",
        "plan",
        "step",
        "toolcall",
        "agentdecision",
        "qualityreport",
    }.issubset(tables)


def test_release_models_persist_across_sessions(tmp_path):
    engine = make_engine(tmp_path)
    now = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)

    with Session(engine) as session:
        session.add(
            Node(
                id="mac-studio",
                name="Mac Studio",
                host="192.168.50.2",
                status=NodeStatus.ONLINE,
                shared_root="/Volumes/MediaOrchard",
                auth_key_id="shared-key",
                max_ffmpeg_jobs=2,
                max_whisper_jobs=1,
                active_jobs=1,
                active_ffmpeg_jobs=1,
                active_whisper_jobs=0,
                cpu_percent=25.0,
                memory_percent=40.0,
                free_disk_gb=512.0,
                thermal_state="normal",
                on_battery=False,
                last_heartbeat_at=now,
            )
        )
        session.add(
            Job(
                id="job_1",
                goal_type="video_to_subtitle",
                input_file="/Volumes/MediaOrchard/inbox/demo.mp4",
                output_dir="/Volumes/MediaOrchard/output/job_1",
                status=JobStatus.RUNNING,
                priority=7,
                language="zh",
                quality="high",
                requested_outputs=["srt", "txt", "json"],
                user_request="make subtitles",
                plan_id="plan_1",
                progress=40.0,
            )
        )
        session.add(
            Plan(
                id="plan_1",
                job_id="job_1",
                status="created",
                created_by="rules",
                plan_schema_version="1",
                plan_json={
                    "version": "1",
                    "steps": ["probe_media", "extract_audio", "transcribe_audio"],
                },
            )
        )
        session.add(
            Step(
                id="step_1",
                job_id="job_1",
                plan_id="plan_1",
                step_type="extract_audio",
                tool_name="extract_audio",
                status=StepStatus.RUNNING,
                depends_on=["step_0"],
                assigned_node_id="mac-studio",
                assigned_at=now,
                claimed_at=now,
                assignment_epoch=2,
                input_json={"input_file": "/Volumes/MediaOrchard/inbox/demo.mp4"},
                output_json={"audio_file": "/Volumes/MediaOrchard/work/job_1/audio.wav"},
                retry_count=1,
                max_retries=3,
                started_at=now,
            )
        )
        session.add(
            ToolCall(
                id="tool_1",
                job_id="job_1",
                step_id="step_1",
                node_id="mac-studio",
                tool_name="extract_audio",
                args_json={"argv": ["ffmpeg", "-i", "demo.mp4"]},
                status="completed",
                stdout_path="/Volumes/MediaOrchard/logs/job_1/stdout.log",
                stderr_path="/Volumes/MediaOrchard/logs/job_1/stderr.log",
                exit_code=0,
                started_at=now,
                completed_at=now,
            )
        )
        session.add(
            AgentDecision(
                id="decision_1",
                job_id="job_1",
                agent_name="scheduler",
                decision_type="assign_step",
                decision_json={
                    "selected_node_id": "mac-studio",
                    "rejected_nodes": {},
                },
                reason="lowest eligible load",
                confidence=1.0,
            )
        )
        session.add(
            QualityReport(
                id="quality_1",
                job_id="job_1",
                status="passed",
                checks_json={"subtitle_srt_exists": True},
                warnings_json=[],
                recommendations_json=["review timestamps"],
            )
        )
        session.commit()

    with Session(engine) as session:
        node = session.get(Node, "mac-studio")
        job = session.get(Job, "job_1")
        plan = session.get(Plan, "plan_1")
        step = session.get(Step, "step_1")
        tool_call = session.get(ToolCall, "tool_1")
        decision = session.get(AgentDecision, "decision_1")
        quality = session.get(QualityReport, "quality_1")

        assert node is not None
        assert node.status == NodeStatus.ONLINE
        assert node.last_heartbeat_at == now
        assert job is not None
        assert job.requested_outputs == ["srt", "txt", "json"]
        assert job.status == JobStatus.RUNNING
        assert plan is not None
        assert plan.plan_schema_version == "1"
        assert plan.plan_json["steps"] == ["probe_media", "extract_audio", "transcribe_audio"]
        assert step is not None
        assert step.status == StepStatus.RUNNING
        assert step.depends_on == ["step_0"]
        assert step.output_json == {"audio_file": "/Volumes/MediaOrchard/work/job_1/audio.wav"}
        assert step.claimed_at == now
        assert tool_call is not None
        assert tool_call.args_json["argv"] == ["ffmpeg", "-i", "demo.mp4"]
        assert tool_call.exit_code == 0
        assert decision is not None
        assert decision.decision_json["selected_node_id"] == "mac-studio"
        assert decision.confidence == 1.0
        assert quality is not None
        assert quality.checks_json == {"subtitle_srt_exists": True}
        assert quality.recommendations_json == ["review timestamps"]
