# Release Checklist

This project is not ready for public release until every required gate below has current evidence.

## Release 0.1 Required Gates

- [x] Controller API exists and has tests for jobs, nodes, heartbeat, and authenticated Worker calls.
- [ ] Database models persist Node, Job, Plan, Step, ToolCall, AgentDecision, and QualityReport records.
- [x] State machine tests cover legal transitions, illegal transitions, `assignment_epoch`, and Worker timeout recovery.
- [x] Scheduler tests cover offline, stale heartbeat, CPU, memory, disk, thermal, battery, shared-root, and concurrency filters.
- [x] Worker lifecycle tests cover registration, heartbeat, assigned-step claim lease, node ownership checks, graceful shutdown, and stale completion rejection.
- [x] Tool execution uses structured `list[str]` argv with `shell=False`.
- [x] Mock `video_to_subtitle` pipeline completes without real media tools.
- [ ] Local real-media smoke test produces `srt`, `txt`, `json`, `quality_report.json`, `report.md`, and logs.
- [ ] README documents setup, config, API key hashing, demo commands, and troubleshooting.
- [ ] `bash scripts/verify.sh` and `bash scripts/smoke.sh` pass from a clean checkout.
- [ ] No secrets, source media, cache files, generated outputs, or local databases are tracked by Git.

## Current Evidence

- `bash scripts/verify.sh`: harness check plus 69 tests pass on `feature/tool-execution`.
- `bash scripts/smoke.sh`: CLI help renders successfully.
- Git repository initialized on `main`.
- Controller API and state machine tests are merged into `main`.
- Scheduler hard filters, scoring, assignment helper, active-count updates, and defensive scheduling checks are merged into `main`.
- Worker lifecycle API and WorkerAgent lifecycle tests are implemented on `feature/worker-lifecycle`, including JSON `claim-next`, `claimed_at` lease marking, and `X-MediaOrchard-Node-Id` ownership checks.
- Worker tool execution enforces registered command tools, existing input validation, structured `list[str]` argv, `shell=False`, subprocess timeout, timeout log capture, stdout/stderr log capture, log-write failure reporting, and failed exit-code reporting on `feature/tool-execution`.
- Mock `video_to_subtitle` pipeline produces `audio.wav`, `transcript.txt`, `transcript.json`, `subtitle.srt`, `quality_report.json`, `report.md`, and per-step logs without real media tools on `feature/tool-execution`.

## Current Release Status

Not releasable yet. The repository has verified Controller/API, scheduler, Worker lifecycle, structured tool execution, and mock media pipeline foundations, but real-media smoke test, full release documentation, clean-checkout verification, and repository hygiene audit are still pending.
