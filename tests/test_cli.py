from typer.testing import CliRunner

from mediaorchard.cli import main as cli_main
from mediaorchard.cli.main import app
from mediaorchard.worker.bootstrap import WorkerBootstrapResult
from mediaorchard.worker.preflight import PreflightCheck, WorkerPreflightResult


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


def test_doctor_worker_reports_preflight_failures(monkeypatch, tmp_path):
    def fake_preflight(config):
        assert config.runtime_python_executable == ".venv/bin/python"
        assert config.whisper_python_executable == "python3"
        return WorkerPreflightResult(
            target=config.target,
            checks=[
                PreflightCheck("python>=3.11", False, "found 3.9.6"),
                PreflightCheck("ffmpeg", False, "missing"),
                PreflightCheck("shared_root", True, str(config.shared_root)),
            ],
        )

    monkeypatch.setattr(cli_main, "run_worker_preflight", fake_preflight)
    result = CliRunner().invoke(
        app,
        [
            "doctor",
            "worker",
            "--target",
            "wangyan@192.168.50.8",
            "--shared-root",
            str(tmp_path),
            "--runtime-python",
            ".venv/bin/python",
            "--whisper-python",
            "python3",
        ],
    )

    assert result.exit_code == 1
    assert "wangyan@192.168.50.8 FAIL" in result.output
    assert "FAIL python>=3.11: found 3.9.6" in result.output
    assert "PASS shared_root" in result.output


def test_doctor_worker_passes_shared_root_marker_to_preflight(monkeypatch, tmp_path):
    def fake_preflight(config):
        assert str(config.shared_root_marker) == ".mediaorchard-shared-root-id"
        assert config.shared_root_marker_value == "release-root-token"
        return WorkerPreflightResult(
            target=config.target,
            checks=[
                PreflightCheck("python>=3.11", True, "3.14.3"),
                PreflightCheck("shared_root", True, str(config.shared_root)),
                PreflightCheck("shared_root_marker", True, "release-root-token"),
            ],
        )

    monkeypatch.setattr(cli_main, "run_worker_preflight", fake_preflight)
    result = CliRunner().invoke(
        app,
        [
            "doctor",
            "worker",
            "--target",
            "local",
            "--shared-root",
            str(tmp_path),
            "--shared-root-marker",
            ".mediaorchard-shared-root-id",
            "--shared-root-marker-value",
            "release-root-token",
        ],
    )

    assert result.exit_code == 0
    assert "PASS shared_root_marker" in result.output


def test_doctor_worker_rejects_marker_value_without_marker():
    result = CliRunner().invoke(
        app,
        [
            "doctor",
            "worker",
            "--shared-root-marker-value",
            "release-root-token",
        ],
    )

    assert result.exit_code != 0
    assert "--shared-root-marker-value requires --shared-root-marker" in result.output


def test_doctor_worker_bootstrap_defaults_to_dry_run():
    result = CliRunner().invoke(
        app,
        [
            "doctor",
            "worker-bootstrap",
            "--target",
            "wangyan@192.168.50.8",
            "--install-root",
            "/Users/wangyan/.mediaorchard",
            "--shared-root",
            "/Volumes/MediaOrchard",
            "--python",
            "/opt/homebrew/bin/python3.13",
            "--package-spec",
            "mediaorchard==0.1.0",
        ],
    )

    assert result.exit_code == 0
    assert "wangyan@192.168.50.8 DRY-RUN" in result.output
    assert "/opt/homebrew/bin/python3.13 -m venv /Users/wangyan/.mediaorchard/venv" in result.output
    assert "mediaorchard==0.1.0" in result.output


def test_doctor_worker_bootstrap_accepts_local_wheel(tmp_path):
    wheel = tmp_path / "mediaorchard-0.1.0-py3-none-any.whl"
    wheel.write_text("placeholder")

    result = CliRunner().invoke(
        app,
        [
            "doctor",
            "worker-bootstrap",
            "--target",
            "wangyan@192.168.50.8",
            "--install-root",
            "/Users/wangyan/.mediaorchard",
            "--wheel",
            str(wheel),
        ],
    )

    assert result.exit_code == 0
    assert "wangyan@192.168.50.8 DRY-RUN" in result.output
    assert "mediaorchard==0.1.0" not in result.output
    assert f"# Copy {wheel} to /Users/wangyan/.mediaorchard/packages/mediaorchard-0.1.0-py3-none-any.whl before --execute." in result.output
    assert "/Users/wangyan/.mediaorchard/packages/mediaorchard-0.1.0-py3-none-any.whl" in result.output


def test_doctor_worker_bootstrap_rejects_missing_local_wheel(tmp_path):
    result = CliRunner().invoke(
        app,
        [
            "doctor",
            "worker-bootstrap",
            "--wheel",
            str(tmp_path / "missing.whl"),
        ],
    )

    assert result.exit_code != 0
    assert "wheel does not exist" in result.output


def test_doctor_worker_bootstrap_rejects_wheel_with_custom_package_spec(tmp_path):
    wheel = tmp_path / "mediaorchard-0.1.0-py3-none-any.whl"
    wheel.write_text("placeholder")

    result = CliRunner().invoke(
        app,
        [
            "doctor",
            "worker-bootstrap",
            "--wheel",
            str(wheel),
            "--package-spec",
            "mediaorchard @ git+https://example.invalid/repo.git",
        ],
    )

    assert result.exit_code != 0
    assert "--package-spec cannot be combined with --wheel" in result.output


def test_doctor_worker_bootstrap_execute_can_copy_local_wheel(monkeypatch, tmp_path):
    wheel = tmp_path / "mediaorchard-0.1.0-py3-none-any.whl"
    wheel.write_text("placeholder")
    calls = []

    def fake_bootstrap(config, *, execute):
        calls.append((config, execute))
        return WorkerBootstrapResult(target=config.target, executed=execute, script="script", stdout="ready\n")

    monkeypatch.setattr(cli_main, "run_worker_bootstrap", fake_bootstrap)
    result = CliRunner().invoke(
        app,
        [
            "doctor",
            "worker-bootstrap",
            "--target",
            "wangyan@192.168.50.8",
            "--wheel",
            str(wheel),
            "--copy-wheel",
            "--execute",
        ],
    )

    assert result.exit_code == 0
    assert "wangyan@192.168.50.8 PASS" in result.output
    assert calls[0][0].package_wheel == wheel
    assert calls[0][0].copy_wheel is True
    assert calls[0][1] is True


def test_doctor_worker_bootstrap_rejects_copy_wheel_without_wheel():
    result = CliRunner().invoke(
        app,
        [
            "doctor",
            "worker-bootstrap",
            "--copy-wheel",
        ],
    )

    assert result.exit_code != 0
    assert "--copy-wheel requires --wheel" in result.output
