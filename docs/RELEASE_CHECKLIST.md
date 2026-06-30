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
- [x] Local real-media smoke test produces `srt`, `txt`, `json`, `quality_report.json`, `report.md`, and logs.
- [x] README documents setup, config, API key hashing, demo commands, and troubleshooting.
- [x] `bash scripts/verify.sh` and `bash scripts/smoke.sh` pass from a clean checkout.
- [x] No secrets, source media, cache files, generated outputs, or local databases are tracked by Git.

## Current Evidence

- `bash scripts/verify.sh`: harness check plus 75 tests pass on `feature/real-media-smoke`.
- `bash scripts/smoke.sh`: CLI help renders successfully.
- Git repository initialized on `main`.
- Controller API and state machine tests are merged into `main`.
- Scheduler hard filters, scoring, assignment helper, active-count updates, and defensive scheduling checks are merged into `main`.
- Worker lifecycle API and WorkerAgent lifecycle tests are implemented on `feature/worker-lifecycle`, including JSON `claim-next`, `claimed_at` lease marking, and `X-MediaOrchard-Node-Id` ownership checks.
- Worker tool execution enforces registered command tools, existing input validation, structured `list[str]` argv, `shell=False`, subprocess timeout, timeout log capture, stdout/stderr log capture, log-write failure reporting, and failed exit-code reporting on `feature/tool-execution`.
- Mock `video_to_subtitle` pipeline produces `audio.wav`, `transcript.txt`, `transcript.json`, `subtitle.srt`, `quality_report.json`, `report.md`, and per-step logs without real media tools on `feature/tool-execution`.
- Database persistence tests verify all release models can be created, committed, and read back across sessions, including UTC datetime round-trips, on `feature/persistence-coverage`.
- README documents setup, configuration, API key hashing, Controller API startup, mock demo commands, verification commands, and troubleshooting on `feature/docs-readme-release`.
- Clean checkout verification passed from `/tmp/mediaorchard-clean-check.MlyHUq` after fresh clone, new venv, editable install, `bash scripts/verify.sh`, and `bash scripts/smoke.sh`.
- Git tracked-file hygiene audit found no tracked local DB files, env/config-local files, media files, cache/work/output/log directories, pyc files, or actual API key/hash patterns; placeholder `<shared-secret>` references remain documented in `plan.md`.
- Local real-media smoke passed at `/tmp/mediaorchard-real-smoke.4Jc4aF/output/real_smoke` using macOS `say`, `ffmpeg` 7.1.1, `ffprobe` 7.1.1, system Python `mlx-whisper` 0.4.3, and model `mlx-community/whisper-tiny`; produced `subtitle.srt`, `transcript.txt`, `transcript.json`, `quality_report.json`, `report.md`, `audio.wav`, `input_meta.json`, and logs.

## Current Release Status

Not releasable yet. Release evidence gates are now covered, including one local synthetic real-media smoke run on the developer Mac. The remaining product gap before a polished public 0.1 is full Controller/Worker CLI process orchestration, which is currently documented as a pre-release limitation in `README.md`.
