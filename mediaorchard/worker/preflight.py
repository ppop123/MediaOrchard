from __future__ import annotations

import shlex
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PreflightCheck:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class WorkerPreflightConfig:
    target: str = "local"
    shared_root: Path = Path("/Volumes/MediaOrchard")
    runtime_python_executable: str = "python3"
    whisper_python_executable: str = "python3"
    timeout_seconds: int = 10


@dataclass(frozen=True)
class WorkerPreflightResult:
    target: str
    checks: list[PreflightCheck]

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)


CompletedProcessRunner = Callable[[list[str], int], subprocess.CompletedProcess[str]]


def run_worker_preflight(
    config: WorkerPreflightConfig,
    *,
    command_runner: CompletedProcessRunner | None = None,
) -> WorkerPreflightResult:
    runner = command_runner or run_command
    runtime_python = shlex.quote(config.runtime_python_executable)
    whisper_python = shlex.quote(config.whisper_python_executable)
    shared_root = shlex.quote(str(config.shared_root.expanduser()))
    checks = [
        check_python_version(config, runner, runtime_python),
        check_command(config, runner, "ffmpeg"),
        check_command(config, runner, "ffprobe"),
        check_mlx_whisper(config, runner, whisper_python),
        check_shared_root(config, runner, shared_root),
    ]
    return WorkerPreflightResult(target=config.target, checks=checks)


def check_python_version(
    config: WorkerPreflightConfig,
    runner: CompletedProcessRunner,
    python: str,
) -> PreflightCheck:
    script = (
        f"{python} - <<'PY'\n"
        "import sys\n"
        "print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')\n"
        "PY"
    )
    completed = runner(build_command_argv(config.target, script), config.timeout_seconds)
    version = completed.stdout.strip()
    if completed.returncode != 0:
        return PreflightCheck("python>=3.11", False, _detail(completed))
    parts = version.split(".")
    try:
        major, minor = int(parts[0]), int(parts[1])
    except (IndexError, ValueError):
        return PreflightCheck("python>=3.11", False, f"unparseable version: {version}")
    ok = (major, minor) >= (3, 11)
    return PreflightCheck(
        "python>=3.11",
        ok,
        version if ok else f"found {version}",
    )


def check_command(
    config: WorkerPreflightConfig,
    runner: CompletedProcessRunner,
    command: str,
) -> PreflightCheck:
    completed = runner(build_command_argv(config.target, f"command -v {command}"), config.timeout_seconds)
    ok = completed.returncode == 0
    return PreflightCheck(command, ok, _detail(completed) if not ok else completed.stdout.strip())


def check_mlx_whisper(
    config: WorkerPreflightConfig,
    runner: CompletedProcessRunner,
    python: str,
) -> PreflightCheck:
    script = (
        f"{python} - <<'PY'\n"
        "import mlx_whisper\n"
        "print(getattr(mlx_whisper, '__version__', 'present'))\n"
        "PY"
    )
    completed = runner(build_command_argv(config.target, script), config.timeout_seconds)
    ok = completed.returncode == 0
    return PreflightCheck("mlx_whisper", ok, _detail(completed) if not ok else completed.stdout.strip())


def check_shared_root(
    config: WorkerPreflightConfig,
    runner: CompletedProcessRunner,
    shared_root: str,
) -> PreflightCheck:
    script = f"test -d {shared_root} && printf '%s\\n' {shared_root}"
    completed = runner(build_command_argv(config.target, script), config.timeout_seconds)
    ok = completed.returncode == 0
    return PreflightCheck("shared_root", ok, _detail(completed) if not ok else completed.stdout.strip())


def build_command_argv(target: str, script: str) -> list[str]:
    if target in {"", "local", "localhost", "127.0.0.1"}:
        return ["sh", "-lc", script]
    return [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=5",
        target,
        "sh",
        "-lc",
        shlex.quote(script),
    ]


def run_command(argv: list[str], timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv,
            shell=False,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            argv,
            1,
            "",
            f"timeout after {timeout_seconds}s",
        )


def _detail(completed: subprocess.CompletedProcess[str]) -> str:
    return completed.stderr.strip() or completed.stdout.strip() or f"exit {completed.returncode}"
