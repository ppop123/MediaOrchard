# Release Checklist

This project is not ready for public release until every required gate below has current evidence.

## Release 0.1 Required Gates

- [x] Controller API exists and has tests for jobs, nodes, heartbeat, and authenticated Worker calls.
- [x] Database models persist Node, Job, Plan, Step, ToolCall, AgentDecision, and QualityReport records.
- [x] State machine tests cover legal transitions, illegal transitions, `assignment_epoch`, and Worker timeout recovery.
- [x] Scheduler tests cover offline, stale heartbeat, CPU, memory, disk, thermal, battery, shared-root, and concurrency filters.
- [x] Worker lifecycle tests cover registration, heartbeat, assigned-step claim lease, node ownership checks, graceful shutdown, and stale completion rejection.
- [x] Tool execution uses structured `list[str]` argv with `shell=False`.
- [x] Mock `video_to_subtitle` pipeline completes without real media tools.
- [x] CLI can start a Controller, submit a job, run one Worker poll, complete the deterministic pipeline, and list completed job/node state.
- [x] Local real-media smoke test produces `srt`, `txt`, `json`, `quality_report.json`, `report.md`, and logs.
- [x] CLI can run one Worker poll in real media mode and produce `srt`, `txt`, `json`, `quality_report.json`, `report.md`, and logs from submitted media.
- [x] README documents setup, config, API key hashing, demo commands, and troubleshooting.
- [x] `bash scripts/verify.sh` and `bash scripts/smoke.sh` pass from a clean checkout.
- [x] No secrets, source media, cache files, generated outputs, or local databases are tracked by Git.
- [x] Worker preflight can check local and SSH targets without modifying remote machines.

## Current Evidence

- `bash scripts/verify.sh`: harness check plus 99 tests pass on `feature/worker-preflight`.
- `bash scripts/smoke.sh`: CLI help renders successfully.
- Process-level CLI E2E smoke passed on `main` from a temp shared root at `/tmp/mediaorchard-main-cli-e2e.GldT3h/output/job_027f3f57c6f2`: `controller start`, `submit`, `worker start --once`, `jobs`, and artifact checks for `subtitle.srt`, `transcript.txt`, `transcript.json`, and `quality_report.json`.
- Process-level real-media CLI E2E smoke passed on `main` from `/tmp/mediaorchard-main-real-cli-e2e.B8Gvyp/output/job_825c8527e177`: generated an input mp4 with `say` and `ffmpeg`, then ran `controller start`, `submit`, `worker start --execution-mode real --once`, `jobs`, and artifact checks for `input_meta.json`, `audio.wav`, `subtitle.srt`, `transcript.txt`, `transcript.json`, `quality_report.json`, `report.md`, and passed quality status.
- Git repository initialized on `main`.
- Controller API and state machine tests are merged into `main`.
- Scheduler hard filters, scoring, assignment helper, active-count updates, and defensive scheduling checks are merged into `main`.
- Worker lifecycle API and WorkerAgent lifecycle tests are implemented on `feature/worker-lifecycle`, including JSON `claim-next`, `claimed_at` lease marking, and `X-MediaOrchard-Node-Id` ownership checks.
- Worker tool execution enforces registered command tools, existing input validation, structured `list[str]` argv, `shell=False`, subprocess timeout, timeout log capture, stdout/stderr log capture, log-write failure reporting, and failed exit-code reporting on `feature/tool-execution`.
- Mock `video_to_subtitle` pipeline produces `audio.wav`, `transcript.txt`, `transcript.json`, `subtitle.srt`, `quality_report.json`, `report.md`, and per-step logs without real media tools on `feature/tool-execution`.
- Database persistence tests verify all release models can be created, committed, and read back across sessions, including UTC datetime round-trips, on `feature/persistence-coverage`.
- README documents setup, configuration, API key hashing, Controller CLI startup, single-machine CLI demo commands, verification commands, and troubleshooting on `feature/cli-orchestration`.
- Clean checkout verification passed from `/tmp/mediaorchard-clean-check.wcKBCH/repo` after fresh clone, new venv, editable install, `bash scripts/verify.sh` with 94 tests, and `bash scripts/smoke.sh`.
- Git tracked-file hygiene audit found no tracked local DB files, env/config-local files, media files, cache/work/output/log directories, pyc files, or actual API key/hash patterns; placeholder `<shared-secret>` references remain documented in `plan.md`.
- Local real-media smoke passed at `/tmp/mediaorchard-real-smoke.4Jc4aF/output/real_smoke` using macOS `say`, `ffmpeg` 7.1.1, `ffprobe` 7.1.1, system Python `mlx-whisper` 0.4.3, and model `mlx-community/whisper-tiny`; produced `subtitle.srt`, `transcript.txt`, `transcript.json`, `quality_report.json`, `report.md`, `audio.wav`, `input_meta.json`, and logs.
- Read-only Worker preflight command added as `mediaorchard doctor worker`.
- `mediaorchard doctor worker --target local --target wangyan@192.168.50.8 --target wangyan@192.168.50.9 --shared-root /Volumes/MediaOrchard --runtime-python python3 --whisper-python python3` found local system `python3` is 3.9.6, local ffmpeg/ffprobe/mlx_whisper are available, and local shared root is missing; both remotes have system `python3` 3.9.6 plus ffmpeg/ffprobe, but lack `mlx_whisper` and `/Volumes/MediaOrchard`.
- Worker preflight timeout handling is covered by a regression test so a slow local command or SSH target is reported as a failed check instead of crashing the diagnostic run.

## Current Release Status

Single-Mac release candidate for real-media CLI execution. The code now has current evidence for Controller/Worker CLI orchestration, durable state, scheduling, deterministic smoke mode, one local real-media Worker run through `ffprobe`, `ffmpeg`, and `mlx_whisper`, and read-only Worker preflight diagnostics. Do not promise multi-Mac real-media execution publicly until the target Workers pass `mediaorchard doctor worker` with Python 3.11+, `ffmpeg`, `ffprobe`, a working whisper backend, and the shared root mounted at the same resolved path.
