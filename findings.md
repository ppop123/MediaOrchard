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
- `httpx2` is required by the current Starlette 1.x `TestClient` path: `starlette.testclient` imports `httpx2 as httpx`, and Starlette metadata advertises `httpx2>=2.0.0` for its `full` extra. It is not an accidental misspelling of `httpx` in the current dependency set.
- Target Workers do not need system Python changes for MVP if each machine gets a per-user MediaOrchard virtual environment with Python 3.11+ and the whisper backend.
- Missing Worker directories and programs may be prepared through an explicit bootstrap step: create the shared root layout on each target and install or copy required tools such as Python, `ffmpeg`, `ffprobe`, and `mlx_whisper` before enabling multi-Mac real-media scheduling.
- Worker bootstrap should be dry-run first because it creates directories and installs packages on local or SSH targets; execution requires explicit `--execute`.

## Release Packaging Findings

- `python -m build` was unavailable until release build tooling was added to the dev extra.
- Public release needs explicit license text in the repository, not only `license = "MIT"` in `pyproject.toml`.
- `scripts/release_check.sh` now verifies tests, CLI smoke, package build, `twine check`, clean wheel install smoke, and tracked-file hygiene in one command.
