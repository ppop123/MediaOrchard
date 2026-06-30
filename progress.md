# MediaOrchard Grove Progress

- Reviewed and consolidated `plan.md` with Claude feedback.
- Initialized Git repository on `main`.
- Added Python package skeleton, CLI shell, config example, README, and harness docs.
- Added tests for CLI import/help, API key hashing, secret redaction, path allowlisting, and shared-root validation.
- Added Controller SQLModel tables, state machine helpers, API-key-protected node endpoints, job creation/retrieval, and empty assigned-step claim behavior.
- Added scheduler hard-filter policies, deterministic scoring, selection decisions, and assignment helper.
- Added Step lifecycle endpoints and minimal WorkerAgent lifecycle methods for registration, heartbeat, claim, and shutdown interruption reporting.
- Hardened Worker step claiming with JSON `claim-next`, `claimed_at` lease marking, node header ownership checks, and real WorkerAgent-to-Controller contract coverage.
- Current verification target: `bash scripts/verify.sh` with 55 passing tests; `bash scripts/smoke.sh` renders CLI help.
