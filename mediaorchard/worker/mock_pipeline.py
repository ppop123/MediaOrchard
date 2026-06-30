from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


VIDEO_TO_SUBTITLE_STEPS = [
    "probe_media",
    "extract_audio",
    "transcribe_audio",
    "collect_outputs",
    "quality_check",
    "write_report",
]
SUPPORTED_OUTPUTS = {"srt", "txt", "json"}


@dataclass(frozen=True)
class MockPipelineResult:
    status: str
    steps: list[str]
    output_dir: Path
    work_dir: Path
    error_message: str | None = None


def run_mock_video_to_subtitle_pipeline(
    *,
    input_file: str | Path,
    output_dir: str | Path,
    work_dir: str | Path,
    requested_outputs: list[str],
    language: str | None,
    job_id: str,
) -> MockPipelineResult:
    unsupported = sorted(set(requested_outputs) - SUPPORTED_OUTPUTS)
    output_path = Path(output_dir)
    work_path = Path(work_dir)
    if unsupported:
        return MockPipelineResult(
            status="failed",
            steps=[],
            output_dir=output_path,
            work_dir=work_path,
            error_message=f"unsupported outputs: {', '.join(unsupported)}",
        )

    source = Path(input_file)
    output_path.mkdir(parents=True, exist_ok=True)
    work_path.mkdir(parents=True, exist_ok=True)
    logs_dir = output_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    _write_log(logs_dir, "probe_media", f"probed {source.name}")
    media_meta = {
        "job_id": job_id,
        "input_file": str(source),
        "duration_seconds": 4.0,
        "video_codec": "mock",
        "audio_codec": "mock",
    }
    _write_json(work_path / "probe_media" / "input_meta.json", media_meta)
    _write_json(output_path / "input_meta.json", media_meta)

    _write_log(logs_dir, "extract_audio", "created mock 16 kHz mono audio")
    audio_bytes = b"MOCK-WAV-DATA\n"
    _write_bytes(work_path / "extract_audio" / "attempt_1" / "audio.wav", audio_bytes)
    _write_bytes(output_path / "audio.wav", audio_bytes)

    _write_log(logs_dir, "transcribe_audio", "created mock transcript and subtitle")
    transcript_text = f"Mock transcript for {source.name}."
    transcript_json = {
        "language": language or "auto",
        "text": transcript_text,
        "segments": [
            {
                "start": 0.0,
                "end": 2.0,
                "text": transcript_text,
            }
        ],
    }
    subtitle = f"1\n00:00:00,000 --> 00:00:02,000\n{transcript_text}\n"
    transcript_work = work_path / "transcribe_audio" / "attempt_1"
    _write_text(transcript_work / "transcript.txt", transcript_text + "\n")
    _write_json(transcript_work / "transcript.json", transcript_json)
    _write_text(transcript_work / "subtitle.srt", subtitle)

    _write_log(logs_dir, "collect_outputs", "published requested outputs")
    if "txt" in requested_outputs:
        _write_text(output_path / "transcript.txt", transcript_text + "\n")
    if "json" in requested_outputs:
        _write_json(output_path / "transcript.json", transcript_json)
    if "srt" in requested_outputs:
        _write_text(output_path / "subtitle.srt", subtitle)

    _write_log(logs_dir, "quality_check", "quality checks passed")
    quality_report = {
        "status": "passed",
        "checks": {
            "transcript_txt_exists": (output_path / "transcript.txt").is_file(),
            "transcript_json_exists": (output_path / "transcript.json").is_file(),
            "subtitle_srt_exists": (output_path / "subtitle.srt").is_file(),
            "subtitle_text_non_empty": bool(subtitle.strip()),
        },
        "warnings": [],
        "recommendations": [],
    }
    _write_json(output_path / "quality_report.json", quality_report)

    _write_log(logs_dir, "write_report", "wrote human-readable report")
    report = "\n".join(
        [
            "# MediaOrchard Job Report",
            "",
            f"- Job: {job_id}",
            f"- Input: {source.name}",
            "- Status: completed",
            "- Quality: passed",
            "",
        ]
    )
    _write_text(output_path / "report.md", report)

    return MockPipelineResult(
        status="completed",
        steps=list(VIDEO_TO_SUBTITLE_STEPS),
        output_dir=output_path,
        work_dir=work_path,
    )


def _write_log(logs_dir: Path, step_name: str, message: str) -> None:
    _write_text(logs_dir / f"{step_name}.log", message + "\n")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _write_json(path: Path, payload: dict) -> None:
    _write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
