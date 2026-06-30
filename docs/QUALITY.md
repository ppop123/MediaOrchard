# Quality Snapshot

## Verified Surfaces

- CLI app imports and renders help.
- API key hashes verify without storing raw keys.
- Secret redaction handles nested mappings and lists.
- Path allowlisting rejects outside-root paths.
- Job output paths are derived from safe job ids.
- Shared-root validation detects missing and mismatched roots.
- Controller Worker endpoints reject missing authentication.
- Node registration, heartbeat, job creation, job retrieval, and empty `claim-next` are covered by API tests.
- Step state transitions, `assignment_epoch` fencing, and timeout recovery are covered by unit tests.
- Scheduler hard filters cover offline, stale heartbeat, shared-root mismatch, CPU, memory, disk, thermal, avoid-nodes, battery runtime, and per-tool concurrency.
- Scheduler scoring and assignment helper are covered by unit tests.
- Step claim/start/progress/complete/fail API paths validate `assignment_epoch` and assigned-node ownership.
- Assigned Step claims write a `claimed_at` lease and do not return the same Step twice.
- WorkerAgent registration, heartbeat, real Controller `claim-next`, and shutdown interruption reporting are covered by unit tests.
- Worker command execution rejects unknown tools, rejects missing inputs, rejects non-`list[str]` argv, calls subprocess with `shell=False` and a bounded timeout, records timeout output, and records stdout/stderr logs, log-write failures, and failed exit codes.
- Mock `video_to_subtitle` pipeline completes without real media tools and produces transcript, subtitle, quality report, human report, and per-step logs.
- Database persistence coverage verifies Node, Job, Plan, Step, ToolCall, AgentDecision, and QualityReport records across sessions, including UTC datetime round-trips.
- README covers setup, configuration, API key hashing, Controller API startup, mock demo commands, verification, and troubleshooting.

## Partial Surfaces

- MVP Worker authentication still uses a shared API key plus node-id header binding; per-node credentials or mTLS are post-MVP hardening.
- Real ffmpeg/whisper execution still needs local media smoke coverage.
- End-to-end production media processing cannot be claimed until the real-media path is verified on the target Macs.
