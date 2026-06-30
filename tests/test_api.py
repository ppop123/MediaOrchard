from pathlib import Path

from starlette.testclient import TestClient

from mediaorchard.controller.main import create_app
from sqlmodel import select

from mediaorchard.controller.db.models import Plan, Step
from mediaorchard.shared.security import hash_api_key
from mediaorchard.shared.enums import JobStatus, StepStatus


def worker_headers(node_id: str = "mac-studio") -> dict[str, str]:
    return {
        "Authorization": "Bearer secret",
        "X-MediaOrchard-Node-Id": node_id,
    }


def make_client(tmp_path: Path) -> tuple[TestClient, Path]:
    shared_root = tmp_path / "MediaOrchard"
    shared_root.mkdir()
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        api_key_hash=hash_api_key("secret"),
        shared_root=shared_root,
    )
    return TestClient(app), shared_root


def test_worker_registration_requires_auth(tmp_path):
    client, shared_root = make_client(tmp_path)

    response = client.post(
        "/nodes/register",
        json={
            "node_id": "mac-studio",
            "name": "Mac Studio",
            "shared_root": str(shared_root),
            "max_ffmpeg_jobs": 2,
            "max_whisper_jobs": 1,
        },
    )

    assert response.status_code == 401


def test_node_list_requires_auth(tmp_path):
    client, _ = make_client(tmp_path)

    response = client.get("/nodes")

    assert response.status_code == 401


def test_worker_can_register_and_heartbeat_with_valid_auth(tmp_path):
    client, shared_root = make_client(tmp_path)
    headers = {"Authorization": "Bearer secret"}

    register = client.post(
        "/nodes/register",
        headers=headers,
        json={
            "node_id": "mac-studio",
            "name": "Mac Studio",
            "shared_root": str(shared_root),
            "max_ffmpeg_jobs": 2,
            "max_whisper_jobs": 1,
        },
    )
    heartbeat = client.post(
        "/nodes/mac-studio/heartbeat",
        headers=headers,
        json={
            "cpu_percent": 12.5,
            "memory_percent": 40.0,
            "free_disk_gb": 512.0,
            "active_jobs": 0,
            "active_ffmpeg_jobs": 0,
            "active_whisper_jobs": 0,
            "thermal_state": "normal",
            "on_battery": False,
        },
    )
    nodes = client.get("/nodes", headers=headers)

    assert register.status_code == 201
    assert heartbeat.status_code == 200
    assert nodes.status_code == 200
    assert nodes.json()[0]["id"] == "mac-studio"
    assert nodes.json()[0]["cpu_percent"] == 12.5


def test_create_job_requires_auth(tmp_path):
    client, shared_root = make_client(tmp_path)
    input_file = shared_root / "inbox" / "demo.mp4"
    input_file.parent.mkdir()
    input_file.write_text("placeholder")

    response = client.post(
        "/jobs",
        json={
            "goal_type": "video_to_subtitle",
            "input_file": str(input_file),
            "outputs": ["srt", "txt", "json"],
            "language": "zh",
            "quality": "high",
            "priority": 5,
        },
    )

    assert response.status_code == 401


def test_create_and_get_job_with_auth(tmp_path):
    client, shared_root = make_client(tmp_path)
    input_file = shared_root / "inbox" / "demo.mp4"
    input_file.parent.mkdir()
    input_file.write_text("placeholder")
    headers = {"Authorization": "Bearer secret"}

    created = client.post(
        "/jobs",
        headers=headers,
        json={
            "goal_type": "video_to_subtitle",
            "input_file": str(input_file),
            "outputs": ["srt", "txt", "json"],
            "language": "zh",
            "quality": "high",
            "priority": 5,
        },
    )
    job_id = created.json()["id"]
    fetched = client.get(f"/jobs/{job_id}", headers=headers)

    assert created.status_code == 201
    assert fetched.status_code == 200
    assert fetched.json()["goal_type"] == "video_to_subtitle"
    assert fetched.json()["status"] == "queued"


def test_create_job_builds_initial_plan_and_pipeline_step(tmp_path):
    client, shared_root = make_client(tmp_path)
    input_file = shared_root / "inbox" / "demo.mp4"
    input_file.parent.mkdir()
    input_file.write_text("placeholder")
    headers = {"Authorization": "Bearer secret"}

    created = client.post(
        "/jobs",
        headers=headers,
        json={
            "goal_type": "video_to_subtitle",
            "input_file": str(input_file),
            "outputs": ["srt", "txt", "json"],
            "language": "zh",
            "quality": "high",
            "priority": 5,
        },
    )

    assert created.status_code == 201
    app = client.app
    with app.state.session_factory() as session:
        job_id = created.json()["id"]
        plans = list(session.exec(select(Plan).where(Plan.job_id == job_id)).all())
        steps = list(session.exec(select(Step).where(Step.job_id == job_id)).all())

    assert len(plans) == 1
    assert len(steps) == 1
    assert created.json()["plan_id"] == plans[0].id
    assert steps[0].status == StepStatus.QUEUED
    assert steps[0].tool_name == "video_to_subtitle_pipeline"
    assert steps[0].input_json["input_file"] == str(input_file.resolve())
    assert steps[0].input_json["requested_outputs"] == ["srt", "txt", "json"]


def test_worker_heartbeat_assigns_queued_pipeline_step(tmp_path):
    client, shared_root = make_client(tmp_path)
    input_file = shared_root / "inbox" / "demo.mp4"
    input_file.parent.mkdir()
    input_file.write_text("placeholder")
    headers = {"Authorization": "Bearer secret"}
    client.post(
        "/jobs",
        headers=headers,
        json={
            "goal_type": "video_to_subtitle",
            "input_file": str(input_file),
            "outputs": ["srt"],
            "language": "zh",
            "quality": "standard",
            "priority": 5,
        },
    )
    client.post(
        "/nodes/register",
        headers=headers,
        json={
            "node_id": "mac-studio",
            "name": "Mac Studio",
            "shared_root": str(shared_root),
            "max_ffmpeg_jobs": 2,
            "max_whisper_jobs": 1,
        },
    )

    heartbeat = client.post(
        "/nodes/mac-studio/heartbeat",
        headers=headers,
        json={
            "cpu_percent": 12.5,
            "memory_percent": 40.0,
            "free_disk_gb": 512.0,
            "active_jobs": 0,
            "active_ffmpeg_jobs": 0,
            "active_whisper_jobs": 0,
            "thermal_state": "normal",
            "on_battery": False,
        },
    )
    claimed = client.post("/steps/claim-next", headers=worker_headers(), json={"node_id": "mac-studio"})

    assert heartbeat.status_code == 200
    assert claimed.status_code == 200
    assert claimed.json()["status"] == "assigned"
    app = client.app
    with app.state.session_factory() as session:
        step = session.get(Step, claimed.json()["id"])
        assert step is not None
        assert step.assigned_node_id == "mac-studio"
        assert step.assignment_epoch == 1


def test_job_list_requires_auth(tmp_path):
    client, _ = make_client(tmp_path)

    response = client.get("/jobs")

    assert response.status_code == 401


def test_claim_next_returns_204_when_no_step_assigned(tmp_path):
    client, _ = make_client(tmp_path)

    response = client.post(
        "/steps/claim-next",
        headers=worker_headers(),
        json={"node_id": "mac-studio"},
    )

    assert response.status_code == 204


def test_claim_next_returns_assigned_step_for_authenticated_node(tmp_path):
    client, shared_root = make_client(tmp_path)
    headers = worker_headers()
    app = client.app
    step_id = "step_1"
    with app.state.session_factory() as session:
        session.add(
            Step(
                id=step_id,
                job_id="job_1",
                plan_id="plan_1",
                step_type="probe_media",
                tool_name="probe_media",
                status=StepStatus.ASSIGNED,
                assigned_node_id="mac-studio",
                assignment_epoch=3,
                input_json={"path": str(shared_root / "inbox" / "demo.mp4")},
            )
        )
        session.commit()

    response = client.post("/steps/claim-next", headers=headers, json={"node_id": "mac-studio"})

    assert response.status_code == 200
    assert response.json()["id"] == step_id
    assert response.json()["assignment_epoch"] == 3
    assert response.json()["claimed_at"] is not None


def test_claim_next_does_not_return_same_step_twice(tmp_path):
    client, _ = make_client(tmp_path)
    headers = worker_headers()
    app = client.app
    with app.state.session_factory() as session:
        session.add(
            Step(
                id="step_1",
                job_id="job_1",
                plan_id="plan_1",
                step_type="probe_media",
                tool_name="probe_media",
                status=StepStatus.ASSIGNED,
                assigned_node_id="mac-studio",
                assignment_epoch=3,
            )
        )
        session.commit()

    first = client.post("/steps/claim-next", headers=headers, json={"node_id": "mac-studio"})
    second = client.post("/steps/claim-next", headers=headers, json={"node_id": "mac-studio"})

    assert first.status_code == 200
    assert second.status_code == 204


def test_claim_next_rejects_node_header_mismatch(tmp_path):
    client, _ = make_client(tmp_path)

    response = client.post(
        "/steps/claim-next",
        headers=worker_headers("mac-mini"),
        json={"node_id": "mac-studio"},
    )

    assert response.status_code == 403


def test_lifecycle_rejects_wrong_assigned_node(tmp_path):
    client, _ = make_client(tmp_path)
    app = client.app
    with app.state.session_factory() as session:
        session.add(
            Step(
                id="step_1",
                job_id="job_1",
                plan_id="plan_1",
                step_type="probe_media",
                tool_name="probe_media",
                status=StepStatus.ASSIGNED,
                assigned_node_id="mac-studio",
                assignment_epoch=5,
            )
        )
        session.commit()

    response = client.post(
        "/steps/step_1/start",
        headers=worker_headers("mac-mini"),
        json={"assignment_epoch": 5},
    )

    assert response.status_code == 403


def test_explicit_step_claim_sets_lease_once(tmp_path):
    client, _ = make_client(tmp_path)
    headers = worker_headers()
    app = client.app
    with app.state.session_factory() as session:
        session.add(
            Step(
                id="step_1",
                job_id="job_1",
                plan_id="plan_1",
                step_type="probe_media",
                tool_name="probe_media",
                status=StepStatus.ASSIGNED,
                assigned_node_id="mac-studio",
                assignment_epoch=5,
            )
        )
        session.commit()

    first = client.post("/steps/step_1/claim", headers=headers, json={"assignment_epoch": 5})
    second = client.post("/steps/step_1/claim", headers=headers, json={"assignment_epoch": 5})

    assert first.status_code == 200
    assert first.json()["claimed_at"] is not None
    assert second.status_code == 409


def test_step_lifecycle_rejects_stale_epoch_and_accepts_current_epoch(tmp_path):
    client, _ = make_client(tmp_path)
    headers = worker_headers()
    app = client.app
    with app.state.session_factory() as session:
        session.add(
            Step(
                id="step_1",
                job_id="job_1",
                plan_id="plan_1",
                step_type="probe_media",
                tool_name="probe_media",
                status=StepStatus.ASSIGNED,
                assigned_node_id="mac-studio",
                assignment_epoch=5,
            )
        )
        session.commit()

    stale = client.post("/steps/step_1/start", headers=headers, json={"assignment_epoch": 4})
    current = client.post("/steps/step_1/start", headers=headers, json={"assignment_epoch": 5})
    progress = client.post(
        "/steps/step_1/progress",
        headers=headers,
        json={"assignment_epoch": 5, "percent": 50.0, "message": "halfway"},
    )
    complete = client.post(
        "/steps/step_1/complete",
        headers=headers,
        json={"assignment_epoch": 5, "output_json": {"ok": True}},
    )

    assert stale.status_code == 409
    assert current.status_code == 200
    assert progress.status_code == 200
    assert complete.status_code == 200
    assert complete.json()["status"] == "completed"
    assert complete.json()["output_json"] == {"ok": True}


def test_step_complete_rejects_stale_epoch(tmp_path):
    client, _ = make_client(tmp_path)
    headers = worker_headers()
    app = client.app
    with app.state.session_factory() as session:
        session.add(
            Step(
                id="step_1",
                job_id="job_1",
                plan_id="plan_1",
                step_type="probe_media",
                tool_name="probe_media",
                status=StepStatus.RUNNING,
                assigned_node_id="mac-studio",
                assignment_epoch=9,
            )
        )
        session.commit()

    response = client.post(
        "/steps/step_1/complete",
        headers=headers,
        json={"assignment_epoch": 8, "output_json": {"late": True}},
    )

    assert response.status_code == 409


def test_step_fail_records_error_message(tmp_path):
    client, _ = make_client(tmp_path)
    headers = worker_headers()
    app = client.app
    with app.state.session_factory() as session:
        session.add(
            Step(
                id="step_1",
                job_id="job_1",
                plan_id="plan_1",
                step_type="probe_media",
                tool_name="probe_media",
                status=StepStatus.RUNNING,
                assigned_node_id="mac-studio",
                assignment_epoch=2,
            )
        )
        session.commit()

    response = client.post(
        "/steps/step_1/fail",
        headers=headers,
        json={"assignment_epoch": 2, "error_message": "ffprobe failed"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["error_message"] == "ffprobe failed"
