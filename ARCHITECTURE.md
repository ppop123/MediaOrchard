# MediaOrchard Grove Architecture

## Layers

- `mediaorchard/cli/`: Typer command surface for local development and operator workflows, including Controller/Worker start, job submit, and jobs/nodes inspection.
- `mediaorchard/shared/`: shared safety primitives, currently API key hashing, secret redaction, path allowlisting, and shared-root validation.
- `mediaorchard/controller/`: Controller API, SQLite/SQLModel persistence, state machine, scheduler policies, and heartbeat-triggered assignment.
- `mediaorchard/worker/`: Worker lifecycle client, structured tool execution, deterministic pipeline demo, real-media Worker pipeline, and real-media smoke helpers.
- `tests/`: executable behavior contract for the currently implemented MVP slice.

## Runtime Loops

The current single-machine runtime loop is:

1. `POST /jobs` validates the input path, creates a Job, deterministic Plan, and queued `video_to_subtitle_pipeline` Step.
2. Worker heartbeat updates node resource metrics and lets the scheduler move eligible queued Steps to `assigned`.
3. Worker `claim-next` only accepts work already assigned to its `node_id` and receives an `assignment_epoch` fence.
4. Worker starts the Step, executes either the deterministic pipeline demo or real-media mode through `ffprobe`, `ffmpeg`, and `mlx_whisper`, writes artifacts under shared output/work storage, and reports complete or failed.
5. Controller updates Step and Job status while rejecting stale lifecycle reports with `assignment_epoch`.

Until separate operator/user auth exists, all Controller API endpoints require the shared API key. This is intentionally conservative for the local MVP and can be split into user and Worker auth later.

## Verification Surfaces

- `bash scripts/verify.sh`: harness check plus unit tests.
- `bash scripts/smoke.sh`: CLI import/help smoke test.
- `.venv/bin/python -m pytest`: direct test invocation.
- Process-level CLI E2E smoke: Controller subprocess, CLI submit, Worker `--once`, completed job listing, and artifact checks for deterministic and real-media modes.
