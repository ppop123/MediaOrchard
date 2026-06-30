import subprocess
from pathlib import Path

import pytest

from mediaorchard.worker.executor import (
    CommandToolSpec,
    ToolExecutionContext,
    ToolExecutionError,
    ToolExecutor,
    build_default_command_tools,
)


class FakeCompletedProcess:
    def __init__(self, *, returncode=0, stdout="ok\n", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class FakeRunner:
    def __init__(self, result=None):
        self.calls = []
        self.result = result or FakeCompletedProcess()

    def __call__(self, argv, **kwargs):
        self.calls.append({"argv": argv, **kwargs})
        return self.result


def make_context(tmp_path: Path) -> ToolExecutionContext:
    return ToolExecutionContext(
        job_id="job_1",
        step_id="step_1",
        node_id="mac-studio",
        shared_root=tmp_path,
        work_dir=tmp_path / "work" / "job_1",
        output_dir=tmp_path / "output" / "job_1",
        log_dir=tmp_path / "logs" / "job_1",
    )


def test_tool_executor_uses_structured_argv_and_shell_false(tmp_path):
    runner = FakeRunner(FakeCompletedProcess(stdout='{"format": {}}\n'))
    executor = ToolExecutor(build_default_command_tools(), runner=runner)
    input_file = tmp_path / "inbox" / "demo.mp4"
    input_file.parent.mkdir()
    input_file.write_text("placeholder")
    context = make_context(tmp_path)

    result = executor.execute(
        "probe_media",
        {"input_file": str(input_file)},
        context,
    )

    assert result.status == "completed"
    assert runner.calls == [
        {
            "argv": [
                "ffprobe",
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(input_file),
            ],
            "shell": False,
            "capture_output": True,
            "text": True,
            "check": False,
            "timeout": 30,
        }
    ]
    assert result.stdout_path.read_text() == '{"format": {}}\n'
    assert result.stderr_path.read_text() == ""


def test_tool_executor_rejects_unknown_tool(tmp_path):
    executor = ToolExecutor(build_default_command_tools(), runner=FakeRunner())

    with pytest.raises(ToolExecutionError, match="unknown tool"):
        executor.execute("shell", {}, make_context(tmp_path))


def test_tool_executor_rejects_missing_input_before_subprocess(tmp_path):
    runner = FakeRunner()
    executor = ToolExecutor(build_default_command_tools(), runner=runner)
    missing_file = tmp_path / "inbox" / "missing.mp4"

    with pytest.raises(ToolExecutionError, match="input does not exist"):
        executor.execute(
            "probe_media",
            {"input_file": str(missing_file)},
            make_context(tmp_path),
        )

    assert runner.calls == []


def test_tool_executor_rejects_string_argv_before_subprocess(tmp_path):
    runner = FakeRunner()
    executor = ToolExecutor(
        {
            "bad_tool": CommandToolSpec(
                name="bad_tool",
                build_argv=lambda _args, _context: "ffmpeg -i input output",
            )
        },
        runner=runner,
    )

    with pytest.raises(ToolExecutionError, match="argv must be list"):
        executor.execute("bad_tool", {}, make_context(tmp_path))

    assert runner.calls == []


def test_extract_audio_argv_is_bounded_to_known_ffmpeg_shape(tmp_path):
    runner = FakeRunner()
    executor = ToolExecutor(build_default_command_tools(), runner=runner)
    input_file = tmp_path / "inbox" / "demo.mp4"
    audio_file = tmp_path / "work" / "job_1" / "extract_audio" / "attempt_1" / "audio.wav"
    input_file.parent.mkdir()
    input_file.write_text("placeholder")

    result = executor.execute(
        "extract_audio",
        {
            "input_file": str(input_file),
            "output_audio": str(audio_file),
        },
        make_context(tmp_path),
    )

    assert result.status == "completed"
    assert runner.calls[0]["argv"] == [
        "ffmpeg",
        "-y",
        "-i",
        str(input_file),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        str(audio_file),
    ]
    assert runner.calls[0]["shell"] is False
    assert runner.calls[0]["timeout"] == 30


def test_tool_executor_passes_configured_subprocess_timeout(tmp_path):
    runner = FakeRunner()
    executor = ToolExecutor(build_default_command_tools(), runner=runner, timeout_seconds=12)
    input_file = tmp_path / "inbox" / "demo.mp4"
    input_file.parent.mkdir()
    input_file.write_text("placeholder")

    executor.execute("probe_media", {"input_file": str(input_file)}, make_context(tmp_path))

    assert runner.calls[0]["timeout"] == 12


def test_transcribe_audio_requires_existing_intermediate_without_creating_parent(tmp_path):
    runner = FakeRunner()
    executor = ToolExecutor(build_default_command_tools(), runner=runner)
    missing_audio = tmp_path / "work" / "job_1" / "extract_audio" / "attempt_1" / "audio.wav"
    transcript_dir = tmp_path / "work" / "job_1" / "transcribe_audio" / "attempt_1"

    with pytest.raises(ToolExecutionError, match="input does not exist"):
        executor.execute(
            "transcribe_audio",
            {
                "audio_file": str(missing_audio),
                "transcript_dir": str(transcript_dir),
                "language": "zh",
            },
            make_context(tmp_path),
        )

    assert not missing_audio.parent.exists()
    assert runner.calls == []


def test_tool_executor_records_failed_exit_without_claiming_success(tmp_path):
    runner = FakeRunner(FakeCompletedProcess(returncode=2, stdout="", stderr="boom\n"))
    executor = ToolExecutor(build_default_command_tools(), runner=runner)
    input_file = tmp_path / "inbox" / "demo.mp4"
    input_file.parent.mkdir()
    input_file.write_text("placeholder")

    result = executor.execute(
        "probe_media",
        {"input_file": str(input_file)},
        make_context(tmp_path),
    )

    assert result.status == "failed"
    assert result.exit_code == 2
    assert result.stderr_path.read_text() == "boom\n"


def test_tool_executor_returns_failed_result_when_log_write_fails(tmp_path, monkeypatch):
    runner = FakeRunner(FakeCompletedProcess(stdout="ok\n", stderr=""))
    executor = ToolExecutor(build_default_command_tools(), runner=runner)
    input_file = tmp_path / "inbox" / "demo.mp4"
    input_file.parent.mkdir()
    input_file.write_text("placeholder")
    original_write_text = Path.write_text

    def flaky_write_text(self, content):
        if self.name.endswith(".stderr.log"):
            raise OSError("disk full")
        return original_write_text(self, content)

    monkeypatch.setattr(Path, "write_text", flaky_write_text)

    result = executor.execute(
        "probe_media",
        {"input_file": str(input_file)},
        make_context(tmp_path),
    )

    assert result.status == "failed"
    assert result.exit_code == -2
    assert result.output_json["log_write_errors"] == [
        "step_1.probe_media.stderr.log: disk full"
    ]


def test_tool_executor_records_timeout_as_failed_result(tmp_path):
    def timeout_runner(argv, **_kwargs):
        raise subprocess.TimeoutExpired(
            cmd=argv,
            timeout=30,
            output="partial stdout\n",
            stderr="partial stderr\n",
        )

    executor = ToolExecutor(build_default_command_tools(), runner=timeout_runner)
    input_file = tmp_path / "inbox" / "demo.mp4"
    input_file.parent.mkdir()
    input_file.write_text("placeholder")

    result = executor.execute(
        "probe_media",
        {"input_file": str(input_file)},
        make_context(tmp_path),
    )

    assert result.status == "failed"
    assert result.exit_code == -1
    assert result.stdout_path.read_text() == "partial stdout\n"
    assert "timed out after 30 seconds" in result.stderr_path.read_text()


def test_transcribe_audio_creates_transcript_output_directory(tmp_path):
    runner = FakeRunner()
    executor = ToolExecutor(build_default_command_tools(), runner=runner)
    audio_file = tmp_path / "work" / "job_1" / "extract_audio" / "attempt_1" / "audio.wav"
    transcript_dir = tmp_path / "work" / "job_1" / "transcribe_audio" / "attempt_1"
    audio_file.parent.mkdir(parents=True)
    audio_file.write_text("audio placeholder")

    result = executor.execute(
        "transcribe_audio",
        {
            "audio_file": str(audio_file),
            "transcript_dir": str(transcript_dir),
            "language": "zh",
        },
        make_context(tmp_path),
    )

    assert result.status == "completed"
    assert transcript_dir.is_dir()
    assert runner.calls[0]["argv"] == [
        "mlx-whisper",
        str(audio_file),
        "--language",
        "zh",
        "--output-dir",
        str(transcript_dir),
    ]


def test_transcribe_audio_rejects_non_string_language(tmp_path):
    runner = FakeRunner()
    executor = ToolExecutor(build_default_command_tools(), runner=runner)
    audio_file = tmp_path / "work" / "job_1" / "extract_audio" / "attempt_1" / "audio.wav"
    transcript_dir = tmp_path / "work" / "job_1" / "transcribe_audio" / "attempt_1"
    audio_file.parent.mkdir(parents=True)
    audio_file.write_text("audio placeholder")

    with pytest.raises(ToolExecutionError, match="language must be a string"):
        executor.execute(
            "transcribe_audio",
            {
                "audio_file": str(audio_file),
                "transcript_dir": str(transcript_dir),
                "language": 0,
            },
            make_context(tmp_path),
        )

    assert runner.calls == []
