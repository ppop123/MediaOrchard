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
- Until MediaOrchard is published to an index, Worker bootstrap should use `--wheel` with a locally built release wheel copied to each target's install root.
- Worker bootstrap can now use explicit `--copy-wheel --execute` to create the target package directory and copy the local wheel before running the setup script; without `--copy-wheel`, the dry-run remains a manual copy plan.
- Worker bootstrap now prepares the shared-root layout before creating the Worker virtual environment, so mount or permission failures fail fast instead of leaving a partially installed Worker runtime.
- `scripts/release_env_check.sh` gives a single read-only release environment gate for the multi-machine path: it aggregates local/remote preflight, builds or reuses a wheel, and prints bootstrap dry-run output without executing remote setup.
- `RELEASE.md` is now the durable public release runbook: package publication only requires `release_check`, while multi-machine claims require the read-only environment gate to pass on the real targets.
- Read-only probes found `192.168.50.8` has `/opt/homebrew/bin/python3.14` but not `python3.13`; `192.168.50.9` has both, so `/opt/homebrew/bin/python3.14` is the common bootstrap Python path for these two targets.
- `/Volumes/MediaOrchard` is still missing on local and both target machines, and `/Volumes` is not writable by the `wangyan` user on the remotes; public multi-Mac claims need the shared root mounted or an agreed writable shared path before final Worker preflight can pass.
- After `--copy-wheel` landed on `main`, read-only preflight with the intended Worker paths still fails because local `.venv` lacks `mlx_whisper`, the remote per-user Worker venvs have not been created yet, and the shared root is still absent on every target.

## Release Packaging Findings

- `python -m build` was unavailable until release build tooling was added to the dev extra.
- Public release needs explicit license text in the repository, not only `license = "MIT"` in `pyproject.toml`.
- `scripts/release_check.sh` now verifies tests, CLI smoke, package build, `twine check`, clean wheel install smoke, and tracked-file hygiene in one command.
