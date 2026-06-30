# Quality Snapshot

## Verified Surfaces

- CLI app imports, renders help, starts Controller/Worker runtimes, submits jobs, and lists jobs/nodes.
- API key hashes verify without storing raw keys.
- Secret redaction handles nested mappings and lists.
- Path allowlisting rejects outside-root paths.
- Job output paths are derived from safe job ids.
- Shared-root validation detects missing and mismatched roots.
- Controller Worker endpoints reject missing authentication.
- Node registration, heartbeat, job creation, plan/step creation, job retrieval, heartbeat-triggered assignment, and empty `claim-next` are covered by API tests.
- Step state transitions, `assignment_epoch` fencing, and timeout recovery are covered by unit tests.
- Scheduler hard filters cover offline, stale heartbeat, shared-root mismatch, CPU, memory, disk, thermal, avoid-nodes, battery runtime, and per-tool concurrency.
- Scheduler scoring and assignment helper are covered by unit tests.
- Step claim/start/progress/complete/fail API paths validate `assignment_epoch` and assigned-node ownership.
- Assigned Step claims write a `claimed_at` lease and do not return the same Step twice.
- WorkerAgent registration, heartbeat, real Controller `claim-next`, and shutdown interruption reporting are covered by unit tests.
- Worker runtime integration covers submitted job claim, deterministic pipeline execution, Controller completion reporting, and release-shaped artifact generation.
- Worker command execution rejects unknown tools, rejects missing inputs, rejects non-`list[str]` argv, calls subprocess with `shell=False` and a bounded timeout, records timeout output, and records stdout/stderr logs, log-write failures, and failed exit codes.
- Mock `video_to_subtitle` pipeline completes without real media tools and produces transcript, subtitle, quality report, human report, and per-step logs.
- Database persistence coverage verifies Node, Job, Plan, Step, ToolCall, AgentDecision, and QualityReport records across sessions, including UTC datetime round-trips.
- README covers setup, configuration, API key hashing, Controller CLI startup, single-machine CLI demo commands, verification, and troubleshooting.
- Clean-checkout verification passes after fresh clone, new virtualenv, editable install, `bash scripts/verify.sh`, and `bash scripts/smoke.sh`.
- Tracked-file hygiene audit found no local databases, env/config-local files, source media, generated media outputs, cache/work/output/log directories, pyc files, or actual API key/hash patterns.
- Local real-media smoke produced transcript, subtitle, quality report, human report, extracted audio, media metadata, and command logs with `ffmpeg`, `ffprobe`, and `mlx_whisper`.
- Process-level CLI E2E smoke verified `controller start`, `submit`, `worker start --once`, `jobs`, and expected artifact files from a temp shared root.

## Partial Surfaces

- MVP Worker authentication still uses a shared API key plus node-id header binding; per-node credentials or mTLS are post-MVP hardening.
- The Worker CLI E2E path executes the deterministic pipeline demo; Worker-orchestrated real `ffmpeg`/`mlx_whisper` multi-step execution remains a hardening item.
- Multi-Mac real-media execution still needs validation after target Workers have Python 3.11+, `ffmpeg`, `ffprobe`, `mlx_whisper`, and the shared root mounted.
