import subprocess

from mediaorchard.worker.preflight import (
    WorkerPreflightConfig,
    build_command_argv,
    run_command,
    run_worker_preflight,
)


class FakeCompletedProcess:
    def __init__(self, *, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_worker_preflight_passes_when_requirements_are_available(tmp_path):
    calls = []

    def fake_runner(argv, timeout):
        calls.append((argv, timeout))
        script = argv[-1]
        if "sys.version_info" in script:
            return FakeCompletedProcess(stdout="3.11.6\n")
        if "command -v ffmpeg" in script:
            return FakeCompletedProcess(stdout="/opt/homebrew/bin/ffmpeg\n")
        if "command -v ffprobe" in script:
            return FakeCompletedProcess(stdout="/opt/homebrew/bin/ffprobe\n")
        if "import mlx_whisper" in script:
            return FakeCompletedProcess(stdout="present\n")
        if "test -d" in script:
            return FakeCompletedProcess(stdout=f"{tmp_path}\n")
        raise AssertionError(f"unexpected script: {script}")

    result = run_worker_preflight(
        WorkerPreflightConfig(
            target="local",
            shared_root=tmp_path,
            runtime_python_executable="python3.11",
            whisper_python_executable="python3",
        ),
        command_runner=fake_runner,
    )

    assert result.ok is True
    assert [(check.name, check.ok) for check in result.checks] == [
        ("python>=3.11", True),
        ("ffmpeg", True),
        ("ffprobe", True),
        ("mlx_whisper", True),
        ("shared_root", True),
    ]
    assert all(timeout == 10 for _argv, timeout in calls)


def test_worker_preflight_reports_missing_requirements(tmp_path):
    def fake_runner(argv, _timeout):
        script = argv[-1]
        if "sys.version_info" in script:
            return FakeCompletedProcess(stdout="3.9.6\n")
        return FakeCompletedProcess(returncode=1, stdout="", stderr="missing\n")

    result = run_worker_preflight(
        WorkerPreflightConfig(
            target="wangyan@192.168.50.8",
            shared_root=tmp_path,
            runtime_python_executable="python3",
            whisper_python_executable="python3",
        ),
        command_runner=fake_runner,
    )

    assert result.ok is False
    assert result.target == "wangyan@192.168.50.8"
    assert result.checks[0].name == "python>=3.11"
    assert result.checks[0].ok is False
    assert "3.9.6" in result.checks[0].detail
    assert [check.name for check in result.checks if not check.ok] == [
        "python>=3.11",
        "ffmpeg",
        "ffprobe",
        "mlx_whisper",
        "shared_root",
    ]


def test_build_command_argv_wraps_remote_checks_with_ssh():
    argv = build_command_argv("wangyan@192.168.50.8", "command -v ffmpeg")

    assert argv[:4] == ["ssh", "-o", "BatchMode=yes", "-o"]
    assert "ConnectTimeout=5" in argv
    assert "wangyan@192.168.50.8" in argv
    assert argv[-3:] == ["sh", "-lc", "'command -v ffmpeg'"]


def test_run_command_returns_failed_process_on_timeout(monkeypatch):
    def timeout_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd=["ssh", "host"], timeout=10)

    monkeypatch.setattr(subprocess, "run", timeout_run)

    completed = run_command(["ssh", "host"], 10)

    assert completed.returncode == 1
    assert completed.stdout == ""
    assert completed.stderr == "timeout after 10s"
