import json

from mediaorchard.worker.mock_pipeline import run_mock_video_to_subtitle_pipeline


def test_mock_video_to_subtitle_pipeline_produces_release_artifacts(tmp_path):
    input_file = tmp_path / "inbox" / "demo.mp4"
    output_dir = tmp_path / "output" / "job_1"
    work_dir = tmp_path / "work" / "job_1"
    input_file.parent.mkdir()
    input_file.write_text("mock video placeholder")

    result = run_mock_video_to_subtitle_pipeline(
        input_file=input_file,
        output_dir=output_dir,
        work_dir=work_dir,
        requested_outputs=["srt", "txt", "json"],
        language="zh",
        job_id="job_1",
    )

    assert result.status == "completed"
    assert result.steps == [
        "probe_media",
        "extract_audio",
        "transcribe_audio",
        "collect_outputs",
        "quality_check",
        "write_report",
    ]
    assert (output_dir / "input_meta.json").is_file()
    assert (output_dir / "audio.wav").is_file()
    assert (output_dir / "transcript.txt").read_text().strip()
    assert (output_dir / "transcript.json").is_file()
    assert (output_dir / "subtitle.srt").read_text().startswith("1\n00:00:00,000 --> 00:00:02,000")
    assert (output_dir / "quality_report.json").is_file()
    assert (output_dir / "report.md").read_text().startswith("# MediaOrchard Job Report")
    assert sorted(path.name for path in (output_dir / "logs").iterdir()) == [
        "collect_outputs.log",
        "extract_audio.log",
        "probe_media.log",
        "quality_check.log",
        "transcribe_audio.log",
        "write_report.log",
    ]

    transcript = json.loads((output_dir / "transcript.json").read_text())
    quality = json.loads((output_dir / "quality_report.json").read_text())

    assert transcript["language"] == "zh"
    assert transcript["segments"][0]["text"] == "Mock transcript for demo.mp4."
    assert quality["status"] == "passed"
    assert quality["checks"]["subtitle_srt_exists"] is True


def test_mock_video_to_subtitle_pipeline_rejects_unsupported_output(tmp_path):
    input_file = tmp_path / "inbox" / "demo.mp4"
    input_file.parent.mkdir()
    input_file.write_text("mock video placeholder")

    result = run_mock_video_to_subtitle_pipeline(
        input_file=input_file,
        output_dir=tmp_path / "output" / "job_1",
        work_dir=tmp_path / "work" / "job_1",
        requested_outputs=["docx"],
        language="zh",
        job_id="job_1",
    )

    assert result.status == "failed"
    assert result.error_message == "unsupported outputs: docx"
