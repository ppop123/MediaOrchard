# MediaOrchard Grove

MediaOrchard Grove is a local media processing scheduler for coordinating trusted Mac Workers that run `ffmpeg`, `ffprobe`, and `mlx-whisper` workloads.

The MVP is intentionally deterministic: the Controller owns policy, scheduling, durable state, and recovery; Workers authenticate, report resources, claim only assigned Steps, and execute registered structured tool calls.

## Status

This repository is in MVP release hardening. The durable architecture plan lives in [plan.md](plan.md), and release gates are tracked in [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md).

Implemented foundations:

- FastAPI Controller app with authenticated node/job/step lifecycle endpoints.
- SQLite/SQLModel persistence for release domain models.
- Scheduler hard filters and scoring helpers.
- WorkerAgent registration, heartbeat, assigned-step claim, and interruption reporting.
- Structured Worker command execution with `list[str]` argv, `shell=False`, timeout handling, and stdout/stderr logs.
- Mock `video_to_subtitle` pipeline that produces release-shaped artifacts without real media tools.

Still pending before a public 0.1 release:

- Real `ffmpeg`/`ffprobe`/`mlx-whisper` smoke test.
- Production Worker process loop and full CLI orchestration.
- Clean-checkout release verification and repository hygiene audit.

## Requirements

- Python 3.11 or newer.
- macOS for the intended Worker environment.
- A trusted local network for the MVP shared-key setup.
- Shared storage mounted at the same resolved path on Controller and Workers, for example `/Volumes/MediaOrchard`.
- For real-media smoke tests: `ffmpeg`, `ffprobe`, and the configured whisper backend such as `mlx-whisper`.

## Setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e ".[dev]"
bash scripts/verify.sh
bash scripts/smoke.sh
```

Without installing the console script, use:

```bash
.venv/bin/python -m mediaorchard.cli.main --help
```

After editable install, the CLI entrypoint is:

```bash
mediaorchard --help
```

## Configuration

Start from the example config:

```bash
cp config.example.yaml config.local.yaml
```

Important sections:

- `controller.database_url`: SQLite database path. Use a disposable local database during pre-release development.
- `controller.api_key_hash`: SHA-256 hash of the shared Worker API key.
- `storage.shared_root`: shared media root that must resolve to the same path on every schedulable Worker.
- `scheduler.*`: hard-filter thresholds for heartbeat age, CPU, memory, disk, thermal, and battery constraints.
- `worker.*`: heartbeat, claim, and shutdown timing.
- `whisper.*` and `ffmpeg.*`: real-media backend defaults.

Default shared storage layout:

```text
/Volumes/MediaOrchard/
  inbox/
  work/
  output/
  logs/
  cache/
```

Create it for local testing:

```bash
mkdir -p /Volumes/MediaOrchard/{inbox,work,output,logs,cache}
```

## API Key Hashing

Workers receive the raw key through environment or local config. The Controller stores only a hash.

Generate a hash:

```bash
.venv/bin/python -c 'from mediaorchard.shared.security import hash_api_key; print(hash_api_key("replace-me"))'
```

Use the printed value as `controller.api_key_hash` or `MEDIAORCHARD_API_KEY_HASH`.

Never commit raw API keys, real `config.local.yaml`, source media, generated outputs, or local databases.

## Controller API

The CLI `controller start` command is currently a shell placeholder. Run the Controller app with `uvicorn` for API-level testing:

```bash
export MEDIAORCHARD_API_KEY_HASH='sha256:replace-with-generated-hash'
export MEDIAORCHARD_SHARED_ROOT='/Volumes/MediaOrchard'
export MEDIAORCHARD_DATABASE_URL='sqlite:///mediaorchard.db'
.venv/bin/uvicorn mediaorchard.controller.main:app --host 0.0.0.0 --port 8765
```

Worker-facing requests require one of:

```text
Authorization: Bearer <raw-api-key>
X-MediaOrchard-Key: <raw-api-key>
```

Step claim and lifecycle requests also require:

```text
X-MediaOrchard-Node-Id: <node_id>
```

## Demo Commands

Current CLI smoke commands:

```bash
mediaorchard --help
mediaorchard controller start --help
mediaorchard worker start --node-id mac-studio --help
mediaorchard jobs --help
mediaorchard nodes --help
```

Mock `video_to_subtitle` demo without real media tools:

```bash
mkdir -p /tmp/mediaorchard-demo/inbox
printf 'mock video placeholder\n' > /tmp/mediaorchard-demo/inbox/demo.mp4

.venv/bin/python - <<'PY'
from pathlib import Path
from mediaorchard.worker.mock_pipeline import run_mock_video_to_subtitle_pipeline

root = Path("/tmp/mediaorchard-demo")
result = run_mock_video_to_subtitle_pipeline(
    input_file=root / "inbox" / "demo.mp4",
    output_dir=root / "output" / "job_demo",
    work_dir=root / "work" / "job_demo",
    requested_outputs=["srt", "txt", "json"],
    language="zh",
    job_id="job_demo",
)
print(result.status)
print(result.output_dir)
PY
```

Expected mock output files:

```text
/tmp/mediaorchard-demo/output/job_demo/
  input_meta.json
  audio.wav
  transcript.txt
  transcript.json
  subtitle.srt
  quality_report.json
  report.md
  logs/
```

## Verification

Routine local verification:

```bash
bash scripts/verify.sh
bash scripts/smoke.sh
```

Focused checks:

```bash
.venv/bin/pytest tests/test_api.py -q
.venv/bin/pytest tests/test_scheduler.py -q
.venv/bin/pytest tests/test_worker_lifecycle.py -q
.venv/bin/pytest tests/test_tool_execution.py tests/test_mock_pipeline.py -q
.venv/bin/pytest tests/test_db_persistence.py -q
```

## Troubleshooting

`401 invalid worker api key`

Regenerate the hash with `hash_api_key`, confirm the Controller uses the hash, and confirm Workers send the raw key.

`shared_root_missing` or `shared_root_mismatch`

Confirm the shared root exists, is a directory, and resolves to the same path on Controller and Worker.

`path is outside allowlisted roots`

Move input files under the configured shared root, usually `/Volumes/MediaOrchard/inbox`.

Worker claim returns `204 No Content`

The Worker can only claim Steps already assigned to its own `node_id`. Scheduler assignment must happen before `claim-next`.

Tool execution returns `unknown tool`

Only registered tools are executable. MVP command tools currently cover `probe_media`, `extract_audio`, and `transcribe_audio`; mock pipeline steps are pure Python test helpers.

Tool execution times out or exits nonzero

Check the Step stdout/stderr log paths in the `ToolExecutionResult`. Timeout output is captured and the Step should not be treated as completed.

CLI command says "not implemented yet"

The CLI command shape is present, but full Controller/Worker process orchestration is still a pre-release gate. Use `uvicorn` for Controller API testing and the mock pipeline command for artifact testing.
