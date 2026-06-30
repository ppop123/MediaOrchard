from __future__ import annotations

import shlex
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkerBootstrapConfig:
    target: str = "local"
    install_root: Path = Path("~/.mediaorchard")
    shared_root: Path = Path("/Volumes/MediaOrchard")
    python_executable: str = "python3"
    package_spec: str = "mediaorchard==0.1.0"
    whisper_package: str = "mlx-whisper"
    timeout_seconds: int = 300


@dataclass(frozen=True)
class WorkerBootstrapResult:
    target: str
    executed: bool
    script: str
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0


CompletedProcessRunner = Callable[[list[str], int, str], subprocess.CompletedProcess[str]]

SHARED_ROOT_DIRS = ("inbox", "work", "output", "logs", "cache")


def build_bootstrap_script(config: WorkerBootstrapConfig) -> str:
    install_root = config.install_root.expanduser()
    shared_root = config.shared_root.expanduser()
    venv_dir = install_root / "venv"
    python = shlex.quote(config.python_executable)
    venv_python = shlex.quote(str(venv_dir / "bin" / "python"))
    venv_mediaorchard = shlex.quote(str(venv_dir / "bin" / "mediaorchard"))
    package_args = " ".join(
        shlex.quote(package)
        for package in [config.package_spec, config.whisper_package]
        if package
    )
    shared_dirs = " ".join(shlex.quote(str(shared_root / name)) for name in SHARED_ROOT_DIRS)
    return "\n".join(
        [
            "set -euo pipefail",
            f"{python} - <<'PY_VERSION'",
            "import sys",
            "raise SystemExit(0 if sys.version_info >= (3, 11) else 1)",
            "PY_VERSION",
            f"mkdir -p {shlex.quote(str(install_root))}",
            f"{python} -m venv {shlex.quote(str(venv_dir))}",
            f"{venv_python} -m pip install -U pip",
            f"{venv_python} -m pip install {package_args}",
            f"mkdir -p {shared_dirs}",
            "command -v ffmpeg >/dev/null",
            "command -v ffprobe >/dev/null",
            f"{venv_python} - <<'PY_WHISPER'",
            "import mlx_whisper",
            "print(getattr(mlx_whisper, '__version__', 'present'))",
            "PY_WHISPER",
            f"{venv_mediaorchard} --help >/dev/null",
        ]
    )


def build_bootstrap_command_argv(target: str) -> list[str]:
    if target in {"", "local", "localhost", "127.0.0.1"}:
        return ["bash", "-s"]
    return [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=5",
        target,
        "bash",
        "-s",
    ]


def run_worker_bootstrap(
    config: WorkerBootstrapConfig,
    *,
    execute: bool = False,
    command_runner: CompletedProcessRunner | None = None,
) -> WorkerBootstrapResult:
    script = build_bootstrap_script(config)
    if not execute:
        return WorkerBootstrapResult(target=config.target, executed=False, script=script)

    runner = command_runner or run_command
    completed = runner(build_bootstrap_command_argv(config.target), config.timeout_seconds, script)
    return WorkerBootstrapResult(
        target=config.target,
        executed=True,
        script=script,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def run_command(argv: list[str], timeout_seconds: int, stdin: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv,
            shell=False,
            capture_output=True,
            text=True,
            check=False,
            input=stdin,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            argv,
            1,
            "",
            f"timeout after {timeout_seconds}s",
        )
