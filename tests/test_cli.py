from typer.testing import CliRunner

from mediaorchard.cli import main as cli_main
from mediaorchard.cli.main import app


def test_cli_help_loads():
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "MediaOrchard" in result.output
    assert "controller" in result.output
    assert "worker" in result.output


def test_controller_start_invokes_runtime(monkeypatch, tmp_path):
    calls = []

    def fake_run_controller(config):
        calls.append(config)

    monkeypatch.setattr(cli_main, "run_controller", fake_run_controller)
    result = CliRunner().invoke(
        app,
        [
            "controller",
            "start",
            "--host",
            "127.0.0.1",
            "--port",
            "9876",
            "--database-url",
            f"sqlite:///{tmp_path / 'controller.db'}",
            "--api-key-hash",
            "sha256:test",
            "--shared-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert "Starting Controller" in result.output
    assert "not implemented" not in result.output
    assert calls[0].host == "127.0.0.1"
    assert calls[0].port == 9876
    assert calls[0].api_key_hash == "sha256:test"


def test_controller_start_requires_api_key_hash(tmp_path):
    result = CliRunner().invoke(
        app,
        [
            "controller",
            "start",
            "--database-url",
            f"sqlite:///{tmp_path / 'controller.db'}",
            "--shared-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code != 0
    assert "Controller API key hash is required" in result.output


def test_worker_start_invokes_runtime_once(monkeypatch, tmp_path):
    calls = []

    def fake_run_worker(config):
        calls.append(config)
        return []

    monkeypatch.setattr(cli_main, "run_worker", fake_run_worker)
    result = CliRunner().invoke(
        app,
        [
            "worker",
            "start",
            "--node-id",
            "mac-studio",
            "--node-name",
            "Mac Studio",
            "--controller-url",
            "http://127.0.0.1:8765",
            "--api-key",
            "secret",
            "--shared-root",
            str(tmp_path),
            "--execution-mode",
            "real",
            "--python",
            "python3.11",
            "--whisper-model",
            "mlx-community/whisper-small",
            "--tool-timeout-seconds",
            "77",
            "--once",
        ],
    )

    assert result.exit_code == 0
    assert "Starting Worker mac-studio" in result.output
    assert "not implemented" not in result.output
    assert calls[0].node_id == "mac-studio"
    assert calls[0].node_name == "Mac Studio"
    assert calls[0].poll_once is True
    assert calls[0].execution_mode == "real"
    assert calls[0].python_executable == "python3.11"
    assert calls[0].whisper_model == "mlx-community/whisper-small"
    assert calls[0].tool_timeout_seconds == 77


def test_nodes_lists_controller_nodes(monkeypatch):
    monkeypatch.setattr(
        cli_main,
        "list_nodes",
        lambda controller_url, api_key: [
            {"id": "mac-studio", "status": "online", "cpu_percent": 12.5}
        ],
    )

    result = CliRunner().invoke(
        app,
        [
            "nodes",
            "--controller-url",
            "http://127.0.0.1:8765",
            "--api-key",
            "secret",
        ],
    )

    assert result.exit_code == 0
    assert "mac-studio" in result.output
    assert "online" in result.output


def test_jobs_lists_controller_jobs(monkeypatch):
    monkeypatch.setattr(
        cli_main,
        "list_jobs",
        lambda controller_url, api_key: [
            {"id": "job_1", "status": "created", "goal_type": "video_to_subtitle"}
        ],
    )

    result = CliRunner().invoke(
        app,
        [
            "jobs",
            "--controller-url",
            "http://127.0.0.1:8765",
            "--api-key",
            "secret",
        ],
    )

    assert result.exit_code == 0
    assert "job_1" in result.output
    assert "video_to_subtitle" in result.output


def test_submit_posts_job_to_controller(monkeypatch, tmp_path):
    input_file = tmp_path / "demo.mp4"
    input_file.write_text("placeholder")
    calls = []

    def fake_submit_job(controller_url, api_key, payload):
        calls.append((controller_url, api_key, payload))
        return {"id": "job_1", "status": "created"}

    monkeypatch.setattr(cli_main, "submit_job", fake_submit_job)
    result = CliRunner().invoke(
        app,
        [
            "submit",
            str(input_file),
            "--controller-url",
            "http://127.0.0.1:8765",
            "--api-key",
            "secret",
            "--goal",
            "video_to_subtitle",
            "--language",
            "zh",
            "--output",
            "srt",
            "--output",
            "txt",
            "--quality",
            "high",
            "--priority",
            "7",
        ],
    )

    assert result.exit_code == 0
    assert "job_1" in result.output
    assert calls[0][2] == {
        "goal_type": "video_to_subtitle",
        "input_file": str(input_file),
        "outputs": ["srt", "txt"],
        "language": "zh",
        "quality": "high",
        "priority": 7,
        "user_request": None,
    }


def test_submit_rejects_missing_input_file(monkeypatch, tmp_path):
    monkeypatch.setattr(cli_main, "submit_job", lambda *_args, **_kwargs: {"id": "unused"})

    result = CliRunner().invoke(
        app,
        [
            "submit",
            str(tmp_path / "missing.mp4"),
            "--controller-url",
            "http://127.0.0.1:8765",
            "--api-key",
            "secret",
        ],
    )

    assert result.exit_code != 0
    assert "input_file does not exist" in result.output
