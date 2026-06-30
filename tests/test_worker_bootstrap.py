from pathlib import Path

from mediaorchard.worker.bootstrap import (
    WorkerBootstrapConfig,
    build_bootstrap_command_argv,
    build_bootstrap_script,
    run_worker_bootstrap,
)


class FakeCompletedProcess:
    def __init__(self, *, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_build_bootstrap_script_sets_up_venv_shared_root_and_checks_tools():
    script = build_bootstrap_script(
        WorkerBootstrapConfig(
            target="local",
            install_root=Path("/Users/wangyan/.mediaorchard"),
            shared_root=Path("/Volumes/MediaOrchard"),
            python_executable="/opt/homebrew/bin/python3.13",
            package_spec="mediaorchard==0.1.0",
            whisper_package="mlx-whisper",
        )
    )

    assert "/opt/homebrew/bin/python3.13 -m venv /Users/wangyan/.mediaorchard/venv" in script
    assert "/Users/wangyan/.mediaorchard/venv/bin/python -m pip install mediaorchard==0.1.0 mlx-whisper" in script
    assert "mkdir -p /Volumes/MediaOrchard/inbox /Volumes/MediaOrchard/work /Volumes/MediaOrchard/output /Volumes/MediaOrchard/logs /Volumes/MediaOrchard/cache" in script
    assert "command -v ffmpeg >/dev/null" in script
    assert "command -v ffprobe >/dev/null" in script
    assert "import mlx_whisper" in script
    assert "/Users/wangyan/.mediaorchard/venv/bin/mediaorchard --help >/dev/null" in script


def test_build_bootstrap_command_argv_wraps_remote_with_ssh():
    argv = build_bootstrap_command_argv("wangyan@192.168.50.8")

    assert argv[:4] == ["ssh", "-o", "BatchMode=yes", "-o"]
    assert "ConnectTimeout=5" in argv
    assert "wangyan@192.168.50.8" in argv
    assert argv[-2:] == ["bash", "-s"]


def test_worker_bootstrap_dry_run_does_not_execute():
    calls = []

    result = run_worker_bootstrap(
        WorkerBootstrapConfig(target="local"),
        execute=False,
        command_runner=lambda argv, timeout, stdin: calls.append((argv, timeout, stdin)),
    )

    assert result.ok is True
    assert result.executed is False
    assert calls == []
    assert "python3" in result.script


def test_worker_bootstrap_execute_runs_command():
    calls = []

    def fake_runner(argv, timeout, stdin):
        calls.append((argv, timeout, stdin))
        return FakeCompletedProcess(stdout="ready\n")

    result = run_worker_bootstrap(
        WorkerBootstrapConfig(target="wangyan@192.168.50.9", timeout_seconds=30),
        execute=True,
        command_runner=fake_runner,
    )

    assert result.ok is True
    assert result.executed is True
    assert calls[0][0][0] == "ssh"
    assert calls[0][1] == 30
    assert "python3" in calls[0][2]
    assert result.stdout == "ready\n"
