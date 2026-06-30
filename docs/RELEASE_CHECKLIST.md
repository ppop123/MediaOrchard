# Release Checklist

This project is not ready for public release until every required gate below has current evidence.

## Release 0.1 Required Gates

- [x] Controller API exists and has tests for jobs, nodes, heartbeat, and authenticated Worker calls.
- [ ] Database models persist Node, Job, Plan, Step, ToolCall, AgentDecision, and QualityReport records.
- [x] State machine tests cover legal transitions, illegal transitions, `assignment_epoch`, and Worker timeout recovery.
- [x] Scheduler tests cover offline, stale heartbeat, CPU, memory, disk, thermal, battery, shared-root, and concurrency filters.
- [ ] Worker lifecycle tests cover registration, heartbeat, assigned-step claim, graceful shutdown, and stale completion rejection.
- [ ] Tool execution uses structured `list[str]` argv with `shell=False`.
- [ ] Mock `video_to_subtitle` pipeline completes without real media tools.
- [ ] Local real-media smoke test produces `srt`, `txt`, `json`, `quality_report.json`, `report.md`, and logs.
- [ ] README documents setup, config, API key hashing, demo commands, and troubleshooting.
- [ ] `bash scripts/verify.sh` and `bash scripts/smoke.sh` pass from a clean checkout.
- [ ] No secrets, source media, cache files, generated outputs, or local databases are tracked by Git.

## Current Evidence

- `bash scripts/verify.sh`: harness check plus 43 tests pass on `main`.
- `bash scripts/smoke.sh`: CLI help renders successfully.
- Git repository initialized on `main`.
- Controller API and state machine tests are merged into `main`.
- Scheduler hard filters, scoring, assignment helper, active-count updates, and defensive scheduling checks are merged into `main`.

## Current Release Status

Not releasable yet. The repository has verified Controller/API and scheduler foundations, but Worker runtime, media tools, mock pipeline, real-media smoke test, and full release documentation are still pending.
