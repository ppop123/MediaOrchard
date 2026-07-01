import json
from pathlib import Path
from types import SimpleNamespace

from starlette.testclient import TestClient

from mediaorchard.cli import runtime as cli_runtime
from mediaorchard.cli.runtime import HttpWorkerTransport
from mediaorchard.controller.db.models import Step
from mediaorchard.controller.main import create_app
from mediaorchard.shared.enums import StepStatus
from mediaorchard.shared.security import hash_api_key
from mediaorchard.cli.runtime import (
    ControllerRuntimeConfig,
    WorkerRuntimeConfig,
    list_nodes,
    run_controller,
    run_worker,
    submit_job,
)


class FakeHttpResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return json.dumps(self.payload).encode()


def test_run_controller_invokes_uvicorn_with_configured_app_and_network_options(tmp_path):
    calls = []

    def fake_uvicorn_run(app_path, **kwargs):
        calls.append((app_path, kwargs))

    config = ControllerRuntimeConfig(
        host="127.0.0.1",
        port=9876,
        database_url=f"sqlite:///{tmp_path / 'controller.db'}",
        api_key_hash="sha256:test",
        shared_root=tmp_path,
    )

    run_controller(config, uvicorn_run=fake_uvicorn_run)

    assert calls == [
        (
            "mediaorchard.controller.main:app",
            {
                "host": "127.0.0.1",
                "port": 9876,
                "log_level": "info",
                "env_file": None,
            },
        )
    ]


def test_run_controller_exports_controller_environment(tmp_path, monkeypatch):
    monkeypatch.delenv("MEDIAORCHARD_DATABASE_URL", raising=False)
    monkeypatch.delenv("MEDIAORCHARD_API_KEY_HASH", raising=False)
    monkeypatch.delenv("MEDIAORCHARD_SHARED_ROOT", raising=False)
    monkeypatch.delenv("MEDIAORCHARD_NODE_PRIORITIES", raising=False)

    config = ControllerRuntimeConfig(
        host="127.0.0.1",
        port=9876,
        database_url=f"sqlite:///{tmp_path / 'controller.db'}",
        api_key_hash="sha256:test",
        shared_root=tmp_path,
        node_priorities={"192.168.50.8": 100, "192.168.50.9": 100},
    )

    run_controller(config, uvicorn_run=lambda *_args, **_kwargs: None)

    assert __import__("os").environ["MEDIAORCHARD_DATABASE_URL"] == config.database_url
    assert __import__("os").environ["MEDIAORCHARD_API_KEY_HASH"] == "sha256:test"
    assert __import__("os").environ["MEDIAORCHARD_SHARED_ROOT"] == str(tmp_path.resolve())
    assert __import__("os").environ["MEDIAORCHARD_NODE_PRIORITIES"] == "192.168.50.8=100,192.168.50.9=100"


def test_controller_api_helpers_send_auth_header_and_decode_lists(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        return FakeHttpResponse([{"id": "mac-studio", "status": "online"}])

    monkeypatch.setattr(cli_runtime, "urlopen", fake_urlopen)

    nodes = list_nodes("http://controller.local/", "secret")

    assert nodes == [{"id": "mac-studio", "status": "online"}]
    assert calls[0][0].full_url == "http://controller.local/nodes"
    assert calls[0][0].get_method() == "GET"
    assert calls[0][0].get_header("Authorization") == "Bearer secret"
    assert calls[0][1] == 10.0


def test_submit_job_posts_json_payload(monkeypatch):
    calls = []
    payload = {
        "goal_type": "video_to_subtitle",
        "input_file": "/Volumes/MediaOrchard/input/demo.mp4",
        "outputs": ["srt"],
    }

    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        return FakeHttpResponse({"id": "job_1", "status": "created"})

    monkeypatch.setattr(cli_runtime, "urlopen", fake_urlopen)

    job = submit_job("http://controller.local", "secret", payload)

    assert job == {"id": "job_1", "status": "created"}
    request = calls[0][0]
    assert request.full_url == "http://controller.local/jobs"
    assert request.get_method() == "POST"
    assert request.get_header("Authorization") == "Bearer secret"
    assert request.get_header("Content-type") == "application/json"
    assert json.loads(request.data.decode()) == payload


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, path, json=None):
        self.calls.append((path, json))
        if path == "/steps/claim-next" and self.responses:
            return self.responses.pop(0)
        return {"ok": True}


def test_run_worker_registers_heartbeats_and_claims_with_bounded_polling(tmp_path):
    transport = FakeTransport([{"id": "step_1", "assignment_epoch": 1}, None])
    metrics = [
        {
            "cpu_percent": 10,
            "memory_percent": 20,
            "free_disk_gb": 100,
            "active_jobs": 0,
            "active_ffmpeg_jobs": 0,
            "active_whisper_jobs": 0,
            "thermal_state": "normal",
            "on_battery": False,
        }
    ]
    sleeps = []
    config = WorkerRuntimeConfig(
        node_id="mac-studio",
        node_name="Mac Studio",
        shared_root=tmp_path,
        controller_url="http://127.0.0.1:18765",
        api_key="secret",
        poll_once=False,
        max_polls=2,
        claim_interval_seconds=0.25,
        execute_claimed_steps=False,
    )

    claimed = run_worker(
        config,
        transport=transport,
        metrics_provider=lambda: dict(metrics[0]),
        sleep=sleeps.append,
    )

    assert [step["id"] for step in claimed] == ["step_1"]
    assert transport.calls[0][0] == "/nodes/register"
    assert transport.calls[1][0] == "/nodes/mac-studio/heartbeat"
    assert transport.calls[2] == ("/steps/claim-next", {"node_id": "mac-studio"})
    assert transport.calls[3][0] == "/nodes/mac-studio/heartbeat"
    assert transport.calls[4] == ("/steps/claim-next", {"node_id": "mac-studio"})
    assert sleeps == [0.25]


def test_run_worker_poll_once_does_not_sleep_after_claim(tmp_path):
    transport = FakeTransport([None])
    config = WorkerRuntimeConfig(
        node_id="mac-studio",
        node_name="Mac Studio",
        shared_root=tmp_path,
        controller_url="http://127.0.0.1:18765",
        api_key="secret",
        poll_once=True,
        max_polls=None,
        claim_interval_seconds=10,
        execute_claimed_steps=False,
    )

    claimed = run_worker(
        config,
        transport=transport,
        metrics_provider=lambda: {
            "cpu_percent": 0,
            "memory_percent": 0,
            "free_disk_gb": 1,
            "active_jobs": 0,
            "active_ffmpeg_jobs": 0,
            "active_whisper_jobs": 0,
            "thermal_state": "normal",
            "on_battery": False,
        },
        sleep=lambda _seconds: (_ for _ in ()).throw(AssertionError("should not sleep")),
    )

    assert claimed == []


class ControllerApiTransport(HttpWorkerTransport):
    def __init__(self, client: TestClient, **kwargs):
        super().__init__(**kwargs)
        self.client = client

    def post(self, path, json=None):
        response = self.client.post(
            path,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "X-MediaOrchard-Node-Id": self.node_id,
            },
            json=json,
        )
        if response.status_code == 204:
            return None
        response.raise_for_status()
        return response.json()


def test_run_worker_integrates_with_controller_api(tmp_path):
    shared_root = tmp_path / "MediaOrchard"
    shared_root.mkdir()
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'controller.db'}",
        api_key_hash=hash_api_key("secret"),
        shared_root=shared_root,
    )
    client = TestClient(app)
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
                assignment_epoch=1,
            )
        )
        session.commit()
    transport = ControllerApiTransport(
        client,
        controller_url="http://testserver",
        api_key="secret",
        node_id="mac-studio",
    )

    claimed = run_worker(
        WorkerRuntimeConfig(
            node_id="mac-studio",
            node_name="Mac Studio",
            shared_root=shared_root,
            controller_url="http://testserver",
            api_key="secret",
            poll_once=True,
            execute_claimed_steps=False,
        ),
        transport=transport,
        metrics_provider=lambda: {
            "cpu_percent": 1,
            "memory_percent": 2,
            "free_disk_gb": 3,
            "active_jobs": 0,
            "active_ffmpeg_jobs": 0,
            "active_whisper_jobs": 0,
            "thermal_state": "normal",
            "on_battery": False,
        },
    )

    assert [step["id"] for step in claimed] == ["step_1"]
    nodes = client.get("/nodes", headers={"Authorization": "Bearer secret"})
    assert nodes.json()[0]["id"] == "mac-studio"


def test_run_worker_executes_submitted_pipeline_job_with_controller_api(tmp_path):
    shared_root = tmp_path / "MediaOrchard"
    shared_root.mkdir()
    input_file = shared_root / "inbox" / "demo.mp4"
    input_file.parent.mkdir()
    input_file.write_text("placeholder")
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'controller.db'}",
        api_key_hash=hash_api_key("secret"),
        shared_root=shared_root,
    )
    client = TestClient(app)
    created = client.post(
        "/jobs",
        headers={"Authorization": "Bearer secret"},
        json={
            "goal_type": "video_to_subtitle",
            "input_file": str(input_file),
            "outputs": ["srt", "txt", "json"],
            "language": "zh",
            "quality": "standard",
            "priority": 5,
        },
    )
    transport = ControllerApiTransport(
        client,
        controller_url="http://testserver",
        api_key="secret",
        node_id="mac-studio",
    )

    claimed = run_worker(
        WorkerRuntimeConfig(
            node_id="mac-studio",
            node_name="Mac Studio",
            shared_root=shared_root,
            controller_url="http://testserver",
            api_key="secret",
            poll_once=True,
        ),
        transport=transport,
        metrics_provider=lambda: {
            "cpu_percent": 1,
            "memory_percent": 2,
            "free_disk_gb": 100,
            "active_jobs": 0,
            "active_ffmpeg_jobs": 0,
            "active_whisper_jobs": 0,
            "thermal_state": "normal",
            "on_battery": False,
        },
    )

    job_id = created.json()["id"]
    assert [step["job_id"] for step in claimed] == [job_id]
    job = client.get(f"/jobs/{job_id}", headers={"Authorization": "Bearer secret"}).json()
    assert job["status"] == "completed"
    output_dir = Path(job["output_dir"])
    assert (output_dir / "subtitle.srt").is_file()
    assert (output_dir / "transcript.txt").is_file()
    assert (output_dir / "quality_report.json").is_file()


def test_run_claimed_pipeline_step_uses_real_media_pipeline(monkeypatch, tmp_path):
    calls = []

    def fake_real_pipeline(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            status="completed",
            steps=["custom-real-step"],
            error_message=None,
            output_dir=Path(kwargs["output_dir"]),
            work_dir=Path(kwargs["work_dir"]),
            transcript_text="hello media orchard",
            quality_report={"status": "passed"},
        )

    monkeypatch.setattr(cli_runtime, "run_real_video_to_subtitle_pipeline", fake_real_pipeline)
    step = {
        "id": "step_1",
        "job_id": "job_1",
        "tool_name": "video_to_subtitle_pipeline",
        "input_json": {
            "input_file": str(tmp_path / "inbox" / "demo.mp4"),
            "output_dir": str(tmp_path / "output" / "job_1"),
            "work_dir": str(tmp_path / "work" / "job_1"),
            "requested_outputs": ["srt", "txt", "json"],
            "language": "zh",
        },
    }
    config = WorkerRuntimeConfig(
        node_id="mac-studio",
        node_name="Mac Studio",
        shared_root=tmp_path,
        controller_url="http://testserver",
        api_key="secret",
        execution_mode="real",
        python_executable="python3.11",
        whisper_model="mlx-community/whisper-small",
        tool_timeout_seconds=77,
    )

    output = cli_runtime.run_claimed_pipeline_step(step, config)

    assert output["status"] == "completed"
    assert output["quality_report"] == {"status": "passed"}
    assert output["pipeline_steps"] == ["custom-real-step"]
    assert calls == [
        {
            "input_file": str(tmp_path / "inbox" / "demo.mp4"),
            "output_dir": str(tmp_path / "output" / "job_1"),
            "work_dir": str(tmp_path / "work" / "job_1"),
            "requested_outputs": ["srt", "txt", "json"],
            "language": "zh",
            "job_id": "job_1",
            "python_executable": "python3.11",
            "whisper_model": "mlx-community/whisper-small",
            "timeout_seconds": 77,
        }
    ]
