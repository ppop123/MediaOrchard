from pathlib import Path

from starlette.testclient import TestClient

from mediaorchard.controller.db.models import Step
from mediaorchard.controller.main import create_app
from mediaorchard.shared.enums import StepStatus
from mediaorchard.shared.security import hash_api_key
from mediaorchard.worker.agent import WorkerAgent


class FakeTransport:
    def __init__(self):
        self.calls = []
        self.claim_response = None

    def post(self, path, json=None):
        self.calls.append(("POST", path, json))
        if path == "/steps/claim-next":
            return self.claim_response
        return {"ok": True}


class ControllerTestTransport:
    def __init__(self, client: TestClient, node_id: str):
        self.client = client
        self.headers = {
            "Authorization": "Bearer secret",
            "X-MediaOrchard-Node-Id": node_id,
        }

    def post(self, path, json=None):
        response = self.client.post(path, headers=self.headers, json=json)
        if response.status_code == 204:
            return None
        response.raise_for_status()
        return response.json()


def make_client(tmp_path: Path) -> tuple[TestClient, Path]:
    shared_root = tmp_path / "MediaOrchard"
    shared_root.mkdir()
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        api_key_hash=hash_api_key("secret"),
        shared_root=shared_root,
    )
    return TestClient(app), shared_root


def test_worker_agent_registers_and_sends_heartbeat(tmp_path):
    shared_root = tmp_path / "MediaOrchard"
    shared_root.mkdir()
    transport = FakeTransport()
    worker = WorkerAgent(
        node_id="mac-studio",
        node_name="Mac Studio",
        shared_root=shared_root,
        transport=transport,
    )

    worker.register()
    worker.heartbeat(
        cpu_percent=10,
        memory_percent=20,
        free_disk_gb=100,
        active_jobs=0,
        active_ffmpeg_jobs=0,
        active_whisper_jobs=0,
        thermal_state="normal",
        on_battery=False,
    )

    assert transport.calls[0] == (
        "POST",
        "/nodes/register",
        {
            "node_id": "mac-studio",
            "name": "Mac Studio",
            "shared_root": str(shared_root.resolve()),
            "max_ffmpeg_jobs": 1,
            "max_whisper_jobs": 1,
        },
    )
    assert transport.calls[1][1] == "/nodes/mac-studio/heartbeat"


def test_worker_agent_claims_assigned_step():
    transport = FakeTransport()
    transport.claim_response = {"id": "step_1", "assignment_epoch": 3}
    worker = WorkerAgent(
        node_id="mac-studio",
        node_name="Mac Studio",
        shared_root=Path("/tmp"),
        transport=transport,
    )

    claimed = worker.claim_next()

    assert claimed == {"id": "step_1", "assignment_epoch": 3}
    assert transport.calls == [("POST", "/steps/claim-next", {"node_id": "mac-studio"})]


def test_worker_agent_claims_step_against_real_controller_contract(tmp_path):
    client, shared_root = make_client(tmp_path)
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
    worker = WorkerAgent(
        node_id="mac-studio",
        node_name="Mac Studio",
        shared_root=shared_root,
        transport=ControllerTestTransport(client, "mac-studio"),
    )

    claimed = worker.claim_next()
    duplicate = worker.claim_next()

    assert claimed is not None
    assert claimed["id"] == "step_1"
    assert claimed["claimed_at"] is not None
    assert duplicate is None


def test_worker_agent_reports_shutdown_interruption_for_active_step():
    transport = FakeTransport()
    worker = WorkerAgent(
        node_id="mac-studio",
        node_name="Mac Studio",
        shared_root=Path("/tmp"),
        transport=transport,
    )

    worker.report_interrupted(step_id="step_1", assignment_epoch=7)

    assert transport.calls == [
        (
            "POST",
            "/steps/step_1/fail",
            {
                "assignment_epoch": 7,
                "error_message": "interrupted_by_worker_shutdown",
            },
        )
    ]
