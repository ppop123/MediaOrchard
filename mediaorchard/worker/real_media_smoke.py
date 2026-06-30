from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class RealMediaSmokeError(RuntimeError):
    """Raised when the real-media smoke path cannot complete."""


@dataclass(frozen=True)
class RealMediaSmokeResult:
    status: str
    output_dir: Path
    transcript_text: str
    quality_report: dict[str, Any]


def format_srt_timestamp(seconds: float) -> str:
    milliseconds = int(round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1_000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def build_quality_report(output_dir: Path) -> dict[str, Any]:
    logs_dir = output_dir / "logs"
    checks = {
        "input_meta_json_exists": _non_empty(output_dir / "input_meta.json"),
        "audio_wav_exists": _non_empty(output_dir / "audio.wav"),
        "transcript_txt_exists": _non_empty(output_dir / "transcript.txt"),
        "transcript_json_exists": _non_empty(output_dir / "transcript.json"),
        "subtitle_srt_exists": _non_empty(output_dir / "subtitle.srt"),
        "logs_exist": logs_dir.is_dir()
        and any(path.is_file() and path.stat().st_size > 0 for path in logs_dir.iterdir()),
    }
    return {
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "warnings": [],
        "recommendations": [],
    }


def write_human_report(
    *,
    output_dir: Path,
    job_id: str,
    input_name: str,
    transcript_text: str,
    model: str,
    quality_report: dict[str, Any],
) -> None:
    _write_json(output_dir / "quality_report.json", quality_report)
    body = "\n".join(
        [
            "# MediaOrchard Real Media Smoke Report",
            "",
            f"- Job: {job_id}",
            f"- Input: {input_name}",
            f"- Whisper model: {model}",
            f"- Quality: {quality_report['status']}",
            "",
            "## Transcript Preview",
            "",
            transcript_text.strip(),
            "",
        ]
    )
    _write_text(output_dir / "report.md", body)


def run_real_media_smoke(
    *,
    root: Path,
    python_executable: str = "python3",
    whisper_model: str = "mlx-community/whisper-tiny",
    voice: str = "Samantha",
    phrase: str = "hello media orchard smoke test",
    timeout_seconds: int = 120,
) -> RealMediaSmokeResult:
    job_id = "real_smoke"
    output_dir = root / "output" / job_id
    work_dir = root / "work" / job_id
    logs_dir = output_dir / "logs"
    output_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    speech_aiff = work_dir / "speech.aiff"
    input_video = work_dir / "demo.mp4"
    audio_wav = output_dir / "audio.wav"

    _run_command(
        "say",
        ["say", "-v", voice, "-o", str(speech_aiff), phrase],
        logs_dir,
        timeout_seconds,
    )
    _run_command(
        "ffmpeg_generate",
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=320x240:d=4",
            "-i",
            str(speech_aiff),
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(input_video),
        ],
        logs_dir,
        timeout_seconds,
    )
    probe = _run_command(
        "ffprobe",
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(input_video),
        ],
        logs_dir,
        timeout_seconds,
    )
    _write_text(output_dir / "input_meta.json", probe.stdout)
    _run_command(
        "ffmpeg_extract_audio",
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_video),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            str(audio_wav),
        ],
        logs_dir,
        timeout_seconds,
    )

    raw_transcript_json = work_dir / "whisper_result.json"
    _run_command(
        "mlx_whisper",
        [
            python_executable,
            "-c",
            _TRANSCRIBE_CODE,
            str(audio_wav),
            str(raw_transcript_json),
            whisper_model,
        ],
        logs_dir,
        timeout_seconds,
    )

    transcript_payload = json.loads(raw_transcript_json.read_text())
    transcript_text = (transcript_payload.get("text") or "").strip()
    segments = transcript_payload.get("segments") or [
        {"start": 0.0, "end": 1.0, "text": transcript_text}
    ]
    _write_text(output_dir / "transcript.txt", transcript_text + "\n")
    _write_json(
        output_dir / "transcript.json",
        {
            "text": transcript_text,
            "segments": segments,
            "model": whisper_model,
        },
    )
    _write_text(output_dir / "subtitle.srt", _segments_to_srt(segments))

    quality_report = build_quality_report(output_dir)
    write_human_report(
        output_dir=output_dir,
        job_id=job_id,
        input_name=input_video.name,
        transcript_text=transcript_text,
        model=whisper_model,
        quality_report=quality_report,
    )
    if quality_report["status"] != "passed":
        raise RealMediaSmokeError(f"quality report failed: {quality_report['checks']}")

    return RealMediaSmokeResult(
        status="completed",
        output_dir=output_dir,
        transcript_text=transcript_text,
        quality_report=quality_report,
    )


def _run_command(
    name: str,
    argv: list[str],
    logs_dir: Path,
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            argv,
            shell=False,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        _write_text(logs_dir / f"{name}.stdout.log", _stream_to_text(exc.output))
        _write_text(
            logs_dir / f"{name}.stderr.log",
            f"{_stream_to_text(exc.stderr)}command timed out after {exc.timeout} seconds\n",
        )
        raise RealMediaSmokeError(f"{name} timed out after {exc.timeout} seconds") from exc

    _write_text(logs_dir / f"{name}.stdout.log", completed.stdout)
    _write_text(logs_dir / f"{name}.stderr.log", completed.stderr)
    if completed.returncode != 0:
        raise RealMediaSmokeError(f"{name} failed with exit code {completed.returncode}")
    return completed


def _segments_to_srt(segments: list[dict[str, Any]]) -> str:
    chunks = []
    for index, segment in enumerate(segments, start=1):
        start = format_srt_timestamp(float(segment.get("start", 0.0)))
        end = format_srt_timestamp(float(segment.get("end", 0.0)))
        text = (segment.get("text") or "").strip()
        chunks.append(f"{index}\n{start} --> {end}\n{text}\n")
    return "\n".join(chunks)


def _non_empty(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _stream_to_text(stream: str | bytes | None) -> str:
    if stream is None:
        return ""
    if isinstance(stream, bytes):
        return stream.decode(errors="replace")
    return stream


_TRANSCRIBE_CODE = r"""
import json
import sys
import mlx_whisper

audio_path, output_path, model = sys.argv[1:]
result = mlx_whisper.transcribe(
    audio_path,
    path_or_hf_repo=model,
    verbose=False,
    language="en",
)
with open(output_path, "w") as f:
    json.dump(result, f, indent=2)
"""
