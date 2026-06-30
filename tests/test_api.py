from pathlib import Path

from starlette.testclient import TestClient

from mediaorchard.controller.main import create_app
from mediaorchard.shared.security import hash_api_key


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
    assert fetched.json()["status"] == "created"


def test_job_list_requires_auth(tmp_path):
    client, _ = make_client(tmp_path)

    response = client.get("/jobs")

    assert response.status_code == 401


def test_claim_next_returns_204_when_no_step_assigned(tmp_path):
    client, _ = make_client(tmp_path)

    response = client.post("/steps/claim-next", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 204
