# MediaOrchard Grove Findings

## Product Findings

- MVP should stay deterministic first: agent-readable records now, LLM automation later.
- Public release requires a runnable demo, clear safety boundaries, and fixed verification scripts.

## Architecture Findings

- Worker/Controller calls require shared API key authentication.
- Scheduler owns `queued -> assigned`; Worker polling only claims assigned work.
- Cross-machine artifacts must use shared work storage, not another Worker's local cache.
- `assignment_epoch` is required to reject stale late completions.

## Environment Findings

- This project started as a planning-only directory and is now initialized as a Git repo on `main`.
- System Python is 3.14.3; project-local `.venv` is used for dependencies.
- `pytest` is installed only in `.venv`, not globally.
