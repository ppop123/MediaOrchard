from __future__ import annotations

import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from mediaorchard.shared.paths import PathSecurityError, resolve_allowlisted_path


class ToolExecutionError(ValueError):
    """Raised when a Worker tool call violates the execution contract."""


class CompletedProcessLike(Protocol):
    returncode: int
    stdout: str
    stderr: str


Runner = Callable[..., CompletedProcessLike]
ArgvBuilder = Callable[[dict[str, Any], "ToolExecutionContext"], list[str]]


@dataclass(frozen=True)
class ToolExecutionContext:
    job_id: str
    step_id: str
    node_id: str
    shared_root: Path
    work_dir: Path
    output_dir: Path
    log_dir: Path


@dataclass(frozen=True)
class ToolExecutionResult:
    tool_name: str
    status: str
    argv: list[str]
    exit_code: int
    stdout_path: Path
    stderr_path: Path
    output_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CommandToolSpec:
    name: str
    build_argv: ArgvBuilder


class ToolExecutor:
    def __init__(
        self,
        tools: Mapping[str, CommandToolSpec],
        *,
        runner: Runner = subprocess.run,
        timeout_seconds: int = 30,
    ):
        self._tools = dict(tools)
        self._runner = runner
        self._timeout_seconds = timeout_seconds

    def execute(
        self,
        tool_name: str,
        args_json: dict[str, Any],
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        spec = self._tools.get(tool_name)
        if spec is None:
            raise ToolExecutionError(f"unknown tool: {tool_name}")

        argv = spec.build_argv(args_json, context)
        self._validate_argv(argv)

        context.log_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = context.log_dir / f"{context.step_id}.{tool_name}.stdout.log"
        stderr_path = context.log_dir / f"{context.step_id}.{tool_name}.stderr.log"

        try:
            completed = self._runner(
                argv,
                shell=False,
                capture_output=True,
                text=True,
                check=False,
                timeout=self._timeout_seconds,
            )
            exit_code = completed.returncode
            stdout = completed.stdout
            stderr = completed.stderr
        except subprocess.TimeoutExpired as exc:
            exit_code = -1
            stdout = _normalize_timeout_stream(exc.output)
            stderr = _normalize_timeout_stream(exc.stderr)
            timeout_message = f"tool timed out after {exc.timeout} seconds"
            stderr = f"{stderr}{timeout_message}\n"

        log_write_errors = _write_tool_logs(
            [
                (stdout_path, stdout),
                (stderr_path, stderr),
            ]
        )
        if log_write_errors:
            exit_code = -2

        return ToolExecutionResult(
            tool_name=tool_name,
            status="completed" if exit_code == 0 else "failed",
            argv=argv,
            exit_code=exit_code,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            output_json={
                "tool_name": tool_name,
                "argv": argv,
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
                "exit_code": exit_code,
                "log_write_errors": log_write_errors,
            },
        )

    def _validate_argv(self, argv: object) -> None:
        if not isinstance(argv, list):
            raise ToolExecutionError("argv must be list[str]")
        if not argv:
            raise ToolExecutionError("argv must not be empty")
        if any(not isinstance(part, str) or not part for part in argv):
            raise ToolExecutionError("argv must contain only non-empty strings")


def build_default_command_tools() -> dict[str, CommandToolSpec]:
    return {
        "probe_media": CommandToolSpec("probe_media", _build_probe_media_argv),
        "extract_audio": CommandToolSpec("extract_audio", _build_extract_audio_argv),
        "transcribe_audio": CommandToolSpec("transcribe_audio", _build_transcribe_audio_argv),
    }


def _required_str(args_json: dict[str, Any], key: str) -> str:
    value = args_json.get(key)
    if not isinstance(value, str) or not value:
        raise ToolExecutionError(f"missing required string argument: {key}")
    return value


def _resolve_input(path: str, context: ToolExecutionContext) -> Path:
    try:
        resolved = resolve_allowlisted_path(path, [context.shared_root])
    except PathSecurityError as exc:
        raise ToolExecutionError(str(exc)) from exc
    if not resolved.exists():
        raise ToolExecutionError(f"input does not exist: {resolved}")
    return resolved


def _resolve_intermediate(path: str, context: ToolExecutionContext) -> Path:
    try:
        resolved = resolve_allowlisted_path(path, [context.shared_root, context.work_dir])
    except PathSecurityError as exc:
        raise ToolExecutionError(str(exc)) from exc
    if not resolved.exists():
        raise ToolExecutionError(f"input does not exist: {resolved}")
    return resolved


def _resolve_output(path: str, context: ToolExecutionContext) -> Path:
    try:
        resolved = resolve_allowlisted_path(path, [context.work_dir, context.output_dir])
    except PathSecurityError as exc:
        raise ToolExecutionError(str(exc)) from exc
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def _resolve_output_dir(path: str, context: ToolExecutionContext) -> Path:
    resolved = _resolve_output(path, context)
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _normalize_timeout_stream(stream: str | bytes | None) -> str:
    if stream is None:
        return ""
    if isinstance(stream, bytes):
        return stream.decode(errors="replace")
    return stream


def _write_tool_logs(entries: list[tuple[Path, str]]) -> list[str]:
    errors = []
    for path, content in entries:
        try:
            path.write_text(content)
        except OSError as exc:
            errors.append(f"{path.name}: {exc}")
    return errors


def _build_probe_media_argv(args_json: dict[str, Any], context: ToolExecutionContext) -> list[str]:
    input_file = _resolve_input(_required_str(args_json, "input_file"), context)
    return [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(input_file),
    ]


def _build_extract_audio_argv(args_json: dict[str, Any], context: ToolExecutionContext) -> list[str]:
    input_file = _resolve_input(_required_str(args_json, "input_file"), context)
    output_audio = _resolve_output(_required_str(args_json, "output_audio"), context)
    return [
        "ffmpeg",
        "-y",
        "-i",
        str(input_file),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        str(output_audio),
    ]


def _build_transcribe_audio_argv(args_json: dict[str, Any], context: ToolExecutionContext) -> list[str]:
    audio_file = _resolve_intermediate(_required_str(args_json, "audio_file"), context)
    transcript_dir = _resolve_output_dir(_required_str(args_json, "transcript_dir"), context)
    language = args_json.get("language")
    if language is None or language == "":
        language = "auto"
    if not isinstance(language, str):
        raise ToolExecutionError("language must be a string")
    return [
        "mlx-whisper",
        str(audio_file),
        "--language",
        language,
        "--output-dir",
        str(transcript_dir),
    ]
