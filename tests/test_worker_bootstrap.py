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


def test_build_bootstrap_script_prepares_shared_root_before_installing_worker():
    script = build_bootstrap_script(
        WorkerBootstrapConfig(
            install_root=Path("/Users/wangyan/.mediaorchard"),
            shared_root=Path("/Volumes/MediaOrchard"),
            python_executable="/opt/homebrew/bin/python3.14",
            package_wheel=Path("/tmp/dist/mediaorchard-0.1.0-py3-none-any.whl"),
        )
    )

    shared_root_index = script.index(
        "mkdir -p /Volumes/MediaOrchard/inbox /Volumes/MediaOrchard/work "
        "/Volumes/MediaOrchard/output /Volumes/MediaOrchard/logs /Volumes/MediaOrchard/cache"
    )
    venv_index = script.index("/opt/homebrew/bin/python3.14 -m venv /Users/wangyan/.mediaorchard/venv")
    pip_upgrade_index = script.index("/Users/wangyan/.mediaorchard/venv/bin/python -m pip install -U pip")
    package_install_index = script.index(
        "/Users/wangyan/.mediaorchard/venv/bin/python -m pip install "
        "/Users/wangyan/.mediaorchard/packages/mediaorchard-0.1.0-py3-none-any.whl mlx-whisper"
    )

    assert shared_root_index < venv_index
    assert shared_root_index < pip_upgrade_index
    assert shared_root_index < package_install_index


def test_build_bootstrap_script_can_install_from_local_wheel():
    script = build_bootstrap_script(
        WorkerBootstrapConfig(
            target="wangyan@192.168.50.8",
            install_root=Path("/Users/wangyan/.mediaorchard"),
            package_wheel=Path("/tmp/dist/mediaorchard-0.1.0-py3-none-any.whl"),
            whisper_package="mlx-whisper",
        )
    )

    assert "mediaorchard==0.1.0" not in script
    assert "# Copy /tmp/dist/mediaorchard-0.1.0-py3-none-any.whl to /Users/wangyan/.mediaorchard/packages/mediaorchard-0.1.0-py3-none-any.whl before --execute." in script
    assert "/Users/wangyan/.mediaorchard/packages/mediaorchard-0.1.0-py3-none-any.whl" in script
    assert "test -f /Users/wangyan/.mediaorchard/packages/mediaorchard-0.1.0-py3-none-any.whl" in script
    assert "/Users/wangyan/.mediaorchard/venv/bin/python -m pip install /Users/wangyan/.mediaorchard/packages/mediaorchard-0.1.0-py3-none-any.whl mlx-whisper" in script


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


def test_worker_bootstrap_execute_copies_remote_wheel_before_script():
    calls = []

    def fake_runner(argv, timeout, stdin):
        calls.append((argv, timeout, stdin))
        return FakeCompletedProcess(stdout="ok\n")

    result = run_worker_bootstrap(
        WorkerBootstrapConfig(
            target="wangyan@192.168.50.8",
            install_root=Path("/Users/wangyan/.mediaorchard"),
            package_wheel=Path("/tmp/dist/mediaorchard-0.1.0-py3-none-any.whl"),
            copy_wheel=True,
            timeout_seconds=30,
        ),
        execute=True,
        command_runner=fake_runner,
    )

    assert result.ok is True
    assert calls[0] == (
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=5",
            "wangyan@192.168.50.8",
            "mkdir",
            "-p",
            "/Users/wangyan/.mediaorchard/packages",
        ],
        30,
        "",
    )
    assert calls[1] == (
        [
            "scp",
            "/tmp/dist/mediaorchard-0.1.0-py3-none-any.whl",
            "wangyan@192.168.50.8:/Users/wangyan/.mediaorchard/packages/mediaorchard-0.1.0-py3-none-any.whl",
        ],
        30,
        "",
    )
    assert calls[2][0] == build_bootstrap_command_argv("wangyan@192.168.50.8")
    assert "test -f /Users/wangyan/.mediaorchard/packages/mediaorchard-0.1.0-py3-none-any.whl" in calls[2][2]


def test_worker_bootstrap_remote_copy_quotes_target_package_path():
    calls = []

    def fake_runner(argv, timeout, stdin):
        calls.append((argv, timeout, stdin))
        return FakeCompletedProcess(stdout="ok\n")

    result = run_worker_bootstrap(
        WorkerBootstrapConfig(
            target="wangyan@192.168.50.8",
            install_root=Path("/Users/wang yan/.mediaorchard"),
            package_wheel=Path("/tmp/dist/mediaorchard-0.1.0-py3-none-any.whl"),
            copy_wheel=True,
        ),
        execute=True,
        command_runner=fake_runner,
    )

    assert result.ok is True
    assert calls[0][0][-1] == "'/Users/wang yan/.mediaorchard/packages'"
    assert calls[1][0][-1] == (
        "wangyan@192.168.50.8:'/Users/wang yan/.mediaorchard/packages/"
        "mediaorchard-0.1.0-py3-none-any.whl'"
    )


def test_worker_bootstrap_execute_copies_local_wheel_before_script():
    calls = []

    def fake_runner(argv, timeout, stdin):
        calls.append((argv, timeout, stdin))
        return FakeCompletedProcess(stdout="ok\n")

    result = run_worker_bootstrap(
        WorkerBootstrapConfig(
            target="local",
            install_root=Path("/tmp/mediaorchard-install"),
            package_wheel=Path("/tmp/dist/mediaorchard-0.1.0-py3-none-any.whl"),
            copy_wheel=True,
        ),
        execute=True,
        command_runner=fake_runner,
    )

    assert result.ok is True
    assert calls[0] == (["mkdir", "-p", "/tmp/mediaorchard-install/packages"], 300, "")
    assert calls[1] == (
        [
            "cp",
            "/tmp/dist/mediaorchard-0.1.0-py3-none-any.whl",
            "/tmp/mediaorchard-install/packages/mediaorchard-0.1.0-py3-none-any.whl",
        ],
        300,
        "",
    )
    assert calls[2][0] == build_bootstrap_command_argv("local")


def test_worker_bootstrap_copy_wheel_failure_stops_before_script():
    calls = []

    def fake_runner(argv, timeout, stdin):
        calls.append((argv, timeout, stdin))
        if argv[0] == "scp":
            return FakeCompletedProcess(returncode=1, stderr="copy failed\n")
        return FakeCompletedProcess(stdout="ok\n")

    result = run_worker_bootstrap(
        WorkerBootstrapConfig(
            target="wangyan@192.168.50.8",
            install_root=Path("/Users/wangyan/.mediaorchard"),
            package_wheel=Path("/tmp/dist/mediaorchard-0.1.0-py3-none-any.whl"),
            copy_wheel=True,
        ),
        execute=True,
        command_runner=fake_runner,
    )

    assert result.ok is False
    assert result.returncode == 1
    assert result.stderr == "copy failed\n"
    assert [call[0][0] for call in calls] == ["ssh", "scp"]
