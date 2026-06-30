import json
from pathlib import Path
from types import SimpleNamespace

from mediaorchard.worker import real_media_smoke
from mediaorchard.worker.real_media_smoke import (
    build_quality_report,
    format_srt_timestamp,
    write_human_report,
)


def test_format_srt_timestamp_rounds_milliseconds():
    assert format_srt_timestamp(0) == "00:00:00,000"
    assert format_srt_timestamp(62.3456) == "00:01:02,346"
    assert format_srt_timestamp(3661.2) == "01:01:01,200"


def test_build_quality_report_passes_when_release_artifacts_exist(tmp_path):
    output_dir = tmp_path / "output"
    logs_dir = output_dir / "logs"
    logs_dir.mkdir(parents=True)
    for name in [
        "input_meta.json",
        "audio.wav",
        "transcript.txt",
        "transcript.json",
        "subtitle.srt",
    ]:
        (output_dir / name).write_text("content\n")
    (logs_dir / "ffprobe.stderr.log").write_text("log content\n")

    report = build_quality_report(output_dir)

    assert report["status"] == "passed"
    assert all(report["checks"].values())


def test_build_quality_report_fails_when_required_artifact_is_missing(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    report = build_quality_report(output_dir)

    assert report["status"] == "failed"
    assert report["checks"]["subtitle_srt_exists"] is False


def test_write_human_report_summarizes_outputs(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    quality_report = {"status": "passed", "checks": {"subtitle_srt_exists": True}}

    write_human_report(
        output_dir=output_dir,
        job_id="real_smoke",
        input_name="demo.mp4",
        transcript_text="hello media orchard",
        model="mlx-community/whisper-tiny",
        quality_report=quality_report,
    )

    report = (output_dir / "report.md").read_text()
    assert report.startswith("# MediaOrchard Real Media Smoke Report")
    assert "- Quality: passed" in report
    assert "hello media orchard" in report
    assert json.loads((output_dir / "quality_report.json").read_text()) == quality_report


def test_run_real_video_to_subtitle_pipeline_processes_submitted_input(tmp_path, monkeypatch):
    input_file = tmp_path / "inbox" / "demo.mp4"
    input_file.parent.mkdir()
    input_file.write_text("video placeholder")
    output_dir = tmp_path / "output" / "job_1"
    work_dir = tmp_path / "work" / "job_1"
    calls = []

    def fake_run_command(name, argv, logs_dir, timeout_seconds):
        calls.append(
            {
                "name": name,
                "argv": argv,
                "logs_dir": logs_dir,
                "timeout_seconds": timeout_seconds,
            }
        )
        logs_dir.mkdir(parents=True, exist_ok=True)
        (logs_dir / f"{name}.stdout.log").write_text("stdout\n")
        (logs_dir / f"{name}.stderr.log").write_text("stderr\n")
        if name == "ffprobe":
            return SimpleNamespace(returncode=0, stdout='{"format": {"duration": "4.0"}}\n', stderr="")
        if name == "ffmpeg_extract_audio":
            audio_wav = Path(argv[-1])
            audio_wav.parent.mkdir(parents=True, exist_ok=True)
            audio_wav.write_bytes(b"audio")
        if name == "mlx_whisper":
            raw_transcript_json = Path(argv[4])
            raw_transcript_json.parent.mkdir(parents=True, exist_ok=True)
            raw_transcript_json.write_text(
                json.dumps(
                    {
                        "text": "hello media orchard",
                        "segments": [
                            {"start": 0.0, "end": 1.25, "text": "hello media orchard"}
                        ],
                    }
                )
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(real_media_smoke, "_run_command", fake_run_command)

    result = real_media_smoke.run_real_video_to_subtitle_pipeline(
        input_file=input_file,
        output_dir=output_dir,
        work_dir=work_dir,
        requested_outputs=["srt", "txt", "json"],
        language="zh",
        job_id="job_1",
        python_executable="python3.11",
        whisper_model="mlx-community/whisper-small",
        timeout_seconds=77,
    )

    assert result.status == "completed"
    assert result.steps == ["ffprobe", "ffmpeg_extract_audio", "mlx_whisper"]
    assert result.error_message is None
    assert result.output_dir == output_dir
    assert result.work_dir == work_dir
    assert result.transcript_text == "hello media orchard"
    assert (output_dir / "input_meta.json").read_text() == '{"format": {"duration": "4.0"}}\n'
    assert (output_dir / "audio.wav").parent.is_dir()
    assert (output_dir / "transcript.txt").read_text() == "hello media orchard\n"
    assert json.loads((output_dir / "transcript.json").read_text())["model"] == "mlx-community/whisper-small"
    assert "hello media orchard" in (output_dir / "subtitle.srt").read_text()
    assert json.loads((output_dir / "quality_report.json").read_text())["status"] == "passed"
    assert (output_dir / "report.md").read_text().startswith("# MediaOrchard Real Media Smoke Report")
    assert [call["name"] for call in calls] == ["ffprobe", "ffmpeg_extract_audio", "mlx_whisper"]
    assert str(input_file) in calls[0]["argv"]
    assert str(input_file) in calls[1]["argv"]
    assert str(output_dir / "audio.wav") in calls[1]["argv"]
    assert calls[2]["argv"][0] == "python3.11"
    assert str(output_dir / "audio.wav") in calls[2]["argv"]
    assert "mlx-community/whisper-small" in calls[2]["argv"]
    assert "zh" in calls[2]["argv"]
    assert all(call["timeout_seconds"] == 77 for call in calls)
