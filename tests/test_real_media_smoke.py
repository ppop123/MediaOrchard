import json

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
