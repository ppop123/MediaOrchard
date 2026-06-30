import subprocess

from mediaorchard.worker.preflight import (
    PreflightCheck,
    WorkerPreflightConfig,
    build_command_argv,
    resolve_marker_path,
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


def test_worker_preflight_reports_shared_root_marker_mismatch(tmp_path):
    expected_token = "mediaorchard-release-root"

    def fake_runner(argv, _timeout):
        script = argv[-1]
        if "sys.version_info" in script:
            return FakeCompletedProcess(stdout="3.14.3\n")
        if "command -v ffmpeg" in script:
            return FakeCompletedProcess(stdout="/opt/homebrew/bin/ffmpeg\n")
        if "command -v ffprobe" in script:
            return FakeCompletedProcess(stdout="/opt/homebrew/bin/ffprobe\n")
        if "import mlx_whisper" in script:
            return FakeCompletedProcess(stdout="0.4.3\n")
        if "test -d" in script:
            return FakeCompletedProcess(stdout=f"{tmp_path}\n")
        if "cat" in script:
            return FakeCompletedProcess(stdout="other-root\n")
        raise AssertionError(f"unexpected script: {script}")

    result = run_worker_preflight(
        WorkerPreflightConfig(
            target="local",
            shared_root=tmp_path,
            shared_root_marker=".mediaorchard-shared-root-id",
            shared_root_marker_value=expected_token,
        ),
        command_runner=fake_runner,
    )

    assert result.ok is False
    marker = result.checks[-1]
    assert marker.name == "shared_root_marker"
    assert marker.ok is False
    assert expected_token in marker.detail
    assert "other-root" in marker.detail


def test_worker_preflight_passes_when_shared_root_marker_matches(tmp_path):
    def fake_runner(argv, _timeout):
        script = argv[-1]
        if "sys.version_info" in script:
            return FakeCompletedProcess(stdout="3.14.3\n")
        if "command -v ffmpeg" in script:
            return FakeCompletedProcess(stdout="/opt/homebrew/bin/ffmpeg\n")
        if "command -v ffprobe" in script:
            return FakeCompletedProcess(stdout="/opt/homebrew/bin/ffprobe\n")
        if "import mlx_whisper" in script:
            return FakeCompletedProcess(stdout="0.4.3\n")
        if "test -d" in script:
            return FakeCompletedProcess(stdout=f"{tmp_path}\n")
        if "cat" in script:
            return FakeCompletedProcess(stdout="release-root-token\n")
        raise AssertionError(f"unexpected script: {script}")

    result = run_worker_preflight(
        WorkerPreflightConfig(
            shared_root=tmp_path,
            shared_root_marker=".mediaorchard-shared-root-id",
            shared_root_marker_value="release-root-token",
        ),
        command_runner=fake_runner,
    )

    assert result.ok is True
    assert result.checks[-1] == PreflightCheck(
        "shared_root_marker",
        True,
        "release-root-token",
    )


def test_worker_preflight_reports_missing_shared_root_marker_file(tmp_path):
    def fake_runner(argv, _timeout):
        script = argv[-1]
        if "sys.version_info" in script:
            return FakeCompletedProcess(stdout="3.14.3\n")
        if "command -v ffmpeg" in script:
            return FakeCompletedProcess(stdout="/opt/homebrew/bin/ffmpeg\n")
        if "command -v ffprobe" in script:
            return FakeCompletedProcess(stdout="/opt/homebrew/bin/ffprobe\n")
        if "import mlx_whisper" in script:
            return FakeCompletedProcess(stdout="0.4.3\n")
        if "test -d" in script:
            return FakeCompletedProcess(stdout=f"{tmp_path}\n")
        if "cat" in script:
            return FakeCompletedProcess(returncode=1, stderr="No such file\n")
        raise AssertionError(f"unexpected script: {script}")

    result = run_worker_preflight(
        WorkerPreflightConfig(
            shared_root=tmp_path,
            shared_root_marker=".mediaorchard-shared-root-id",
            shared_root_marker_value="release-root-token",
        ),
        command_runner=fake_runner,
    )

    assert result.ok is False
    assert result.checks[-1] == PreflightCheck(
        "shared_root_marker",
        False,
        "No such file",
    )


def test_resolve_marker_path_keeps_absolute_marker_path(tmp_path):
    marker = tmp_path / "marker-id"

    assert resolve_marker_path(tmp_path / "root", marker) == marker


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
