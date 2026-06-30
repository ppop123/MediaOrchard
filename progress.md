# MediaOrchard Grove Progress

- Reviewed and consolidated `plan.md` with Claude feedback.
- Initialized Git repository on `main`.
- Added Python package skeleton, CLI shell, config example, README, and harness docs.
- Added tests for CLI import/help, API key hashing, secret redaction, path allowlisting, and shared-root validation.
- Added Controller SQLModel tables, state machine helpers, API-key-protected node endpoints, job creation/retrieval, and empty assigned-step claim behavior.
- Added scheduler hard-filter policies, deterministic scoring, selection decisions, and assignment helper.
- Added Step lifecycle endpoints and minimal WorkerAgent lifecycle methods for registration, heartbeat, claim, and shutdown interruption reporting.
- Hardened Worker step claiming with JSON `claim-next`, `claimed_at` lease marking, node header ownership checks, and real WorkerAgent-to-Controller contract coverage.
- Added structured Worker command execution and mock `video_to_subtitle` pipeline artifacts for non-real-media verification.
- Added release model persistence coverage for Node, Job, Plan, Step, ToolCall, AgentDecision, and QualityReport records.
- Added real Controller/Worker CLI orchestration for `controller start`, `worker start`, `submit`, `jobs`, and `nodes`.
- Added automatic `video_to_subtitle` Plan/Step creation on job submission, heartbeat-triggered scheduling, Worker step execution, and job completion reporting for the deterministic pipeline demo.
- Expanded README with setup, configuration, API key hashing, demo commands, verification, and troubleshooting.
- Verified clean checkout install/test/smoke flow and tracked-file hygiene for release.
- Added and ran local real-media smoke with `say`, `ffmpeg`, `ffprobe`, and `mlx_whisper`; artifacts passed quality checks.
- Verified process-level CLI E2E from a temp shared root: Controller start, job submit, Worker `--once`, completed job listing, and expected transcript/subtitle/quality artifacts.
- Refreshed target Worker probes for `192.168.50.8` and `192.168.50.9`: SSH works, but Python is 3.9.6, `mlx_whisper` is missing, `ffmpeg`/`ffprobe` are not on PATH, and `/Volumes/MediaOrchard` is missing.
- Current verification target: `bash scripts/verify.sh` with 92 passing tests; `bash scripts/smoke.sh` renders CLI help.
