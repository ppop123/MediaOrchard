# MediaOrchard Grove

MediaOrchard Grove is a local media processing scheduler for coordinating trusted Mac Workers that run `ffmpeg`, `ffprobe`, and `mlx-whisper` workloads.

The MVP is intentionally deterministic: the Controller owns policy, scheduling, durable state, and recovery; Workers authenticate, report resources, claim only assigned Steps, and execute registered structured tool calls.

## Status

This repository is in MVP release hardening. The durable architecture plan lives in [plan.md](plan.md), and release gates are tracked in [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md).

Implemented foundations:

- FastAPI Controller app with authenticated node/job/step lifecycle endpoints.
- SQLite/SQLModel persistence for release domain models.
- Scheduler hard filters, scoring helpers, and heartbeat-triggered assignment for queued Steps.
- WorkerAgent registration, heartbeat, assigned-step claim, step start/complete/fail reporting, and interruption reporting.
- Typer CLI for starting the Controller, starting a Worker, submitting jobs, and listing jobs/nodes.
- Structured Worker command execution with `list[str]` argv, `shell=False`, timeout handling, and stdout/stderr logs.
- Deterministic `video_to_subtitle` pipeline demo that produces release-shaped artifacts without real media tools.
- Local real-media smoke path that verifies `say`, `ffmpeg`, `ffprobe`, and `mlx_whisper` can produce transcript and subtitle artifacts.

Known MVP boundaries:

- The CLI end-to-end Worker path currently runs the deterministic pipeline demo. Worker-orchestrated real `ffmpeg`/`mlx_whisper` multi-step execution is still hardening; use `scripts/real_media_smoke.py` to verify the real media toolchain on a Mac.
- Multi-Mac real-media execution requires each target Worker to have Python 3.11+, `ffmpeg`, `ffprobe`, the whisper backend, and the same resolved shared root mounted.

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

Start the Controller with the CLI:

```bash
export MEDIAORCHARD_API_KEY_HASH='sha256:replace-with-generated-hash'
export MEDIAORCHARD_SHARED_ROOT='/Volumes/MediaOrchard'
export MEDIAORCHARD_DATABASE_URL='sqlite:///mediaorchard.db'
mediaorchard controller start --host 0.0.0.0 --port 8765
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

CLI help smoke:

```bash
mediaorchard --help
mediaorchard controller start --help
mediaorchard worker start --node-id mac-studio --help
mediaorchard submit --help
mediaorchard jobs --help
mediaorchard nodes --help
```

Single-machine CLI demo without real media tools:

```bash
demo_root="$(mktemp -d /tmp/mediaorchard-demo.XXXXXX)"
mkdir -p "$demo_root"/{inbox,work,output,logs,cache}
printf 'mock video placeholder\n' > "$demo_root/inbox/demo.mp4"
echo "demo_root=$demo_root"

export MEDIAORCHARD_API_KEY='replace-me'
export MEDIAORCHARD_API_KEY_HASH="$(
  .venv/bin/python -c 'from mediaorchard.shared.security import hash_api_key; print(hash_api_key("replace-me"))'
)"
export MEDIAORCHARD_SHARED_ROOT="$demo_root"
export MEDIAORCHARD_DATABASE_URL="sqlite:///$demo_root/controller.db"

mediaorchard controller start --host 127.0.0.1 --port 8765
```

In a second terminal, set `demo_root` to the printed path from the first terminal:

```bash
demo_root=/tmp/mediaorchard-demo.XXXXXX
export MEDIAORCHARD_API_KEY='replace-me'
mediaorchard submit "$demo_root/inbox/demo.mp4" \
  --controller-url http://127.0.0.1:8765 \
  --goal video_to_subtitle \
  --output srt \
  --output txt \
  --output json \
  --language zh

mediaorchard worker start \
  --node-id local-demo \
  --controller-url http://127.0.0.1:8765 \
  --shared-root "$demo_root" \
  --once

mediaorchard jobs --controller-url http://127.0.0.1:8765
mediaorchard nodes --controller-url http://127.0.0.1:8765
```

Expected demo output files:

```text
$demo_root/output/<job_id>/
  input_meta.json
  audio.wav
  transcript.txt
  transcript.json
  subtitle.srt
  quality_report.json
  report.md
  logs/
```

Real-media smoke demo on a Mac with `say`, `ffmpeg`, `ffprobe`, and a Python executable that can import `mlx_whisper`:

```bash
smoke_root="$(mktemp -d /tmp/mediaorchard-real-smoke.XXXXXX)"
.venv/bin/python scripts/real_media_smoke.py \
  --root "$smoke_root" \
  --python python3 \
  --model mlx-community/whisper-tiny \
  --timeout-seconds 180
```

Expected real smoke output files:

```text
$smoke_root/output/real_smoke/
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

The Worker can only claim Steps already assigned to its own `node_id`. A successful heartbeat triggers scheduling for queued Steps, so confirm the Worker registered, heartbeated, and reported a matching shared root with enough free disk.

Tool execution returns `unknown tool`

Only registered tools are executable. MVP command tools currently cover `probe_media`, `extract_audio`, and `transcribe_audio`; mock pipeline steps are pure Python test helpers.

Tool execution times out or exits nonzero

Check the Step stdout/stderr log paths in the `ToolExecutionResult`. Timeout output is captured and the Step should not be treated as completed.

Job stays `queued`

Run `mediaorchard nodes` and confirm at least one Worker is `online`, has a fresh heartbeat, has the same shared root, and is below the configured CPU, memory, disk, thermal, and battery limits.
