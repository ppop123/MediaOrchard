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
- [x] CLI can start a Controller, submit a job, run one Worker poll, complete the deterministic pipeline, and list completed job/node state.
- [x] Local real-media smoke test produces `srt`, `txt`, `json`, `quality_report.json`, `report.md`, and logs.
- [x] CLI can run one Worker poll in real media mode and produce `srt`, `txt`, `json`, `quality_report.json`, `report.md`, and logs from submitted media.
- [x] README documents setup, config, API key hashing, demo commands, and troubleshooting.
- [x] `bash scripts/verify.sh` and `bash scripts/smoke.sh` pass from a clean checkout.
- [x] No secrets, source media, cache files, generated outputs, or local databases are tracked by Git.
- [x] Worker preflight can check local and SSH targets without modifying remote machines.
- [x] Repository has explicit BSD-2-Clause license text.
- [x] Release check builds `sdist` and wheel artifacts and validates metadata with `twine check`.
- [x] Worker bootstrap commands can be generated in dry-run mode before any target machine is modified.
- [x] Worker bootstrap can target a local release wheel instead of assuming the package is already published to an index.
- [x] Worker bootstrap can copy the local release wheel to local or SSH targets before executing the remote setup script.
- [x] Worker bootstrap prepares the shared-root layout before creating the Worker virtual environment so missing mounts fail fast.
- [x] A read-only release environment check aggregates Worker preflight and bootstrap dry-run output before multi-machine release.
- [x] `RELEASE.md` defines package, single-machine, and multi-machine release decision gates.
- [x] Worker preflight can verify a shared-root marker token so multi-machine release checks can prove targets read the same shared storage.
- [x] GitHub Actions release-check workflow runs the public release gate on push and pull request events for `main`.
- [x] Target Workers on `192.168.50.8` and `192.168.50.9` are bootstrapped from a local release wheel with `mlx-whisper` installed in per-user virtual environments.
- [x] Marker-verified multi-machine release environment check exits `0` for local, `192.168.50.8`, and `192.168.50.9`.

## Current Evidence

- `bash scripts/verify.sh`: harness check plus 140 tests pass on `main`.
- `bash scripts/smoke.sh`: CLI help renders successfully.
- `bash scripts/release_check.sh`: harness check, 140 tests, CLI smoke, `python -m build`, `twine check`, clean wheel install smoke, and tracked-file hygiene guard pass on `main`.
- `bash scripts/release_env_check.sh` with `SHARED_ROOT_MARKER=.mediaorchard-shared-root-id` and the marker value read from `/Volumes/MediaOrchard`: exits `0` on `main`; local, `192.168.50.8`, and `192.168.50.9` all pass Python 3.11+, `ffmpeg`, `ffprobe`, `mlx_whisper` 0.4.3, `/Volumes/MediaOrchard`, and shared-root marker checks.
- NAS mount verification found `/Volumes/MediaOrchard` mounted as `smbfs` on local, `192.168.50.8`, and `192.168.50.9`, with 29Ti total and 26Ti available on each target. The marker file is readable with the same value from all three targets.
- Process-level CLI E2E smoke passed on `main` from a temp shared root at `/tmp/mediaorchard-main-cli-e2e.GldT3h/output/job_027f3f57c6f2`: `controller start`, `submit`, `worker start --once`, `jobs`, and artifact checks for `subtitle.srt`, `transcript.txt`, `transcript.json`, and `quality_report.json`.
- Process-level real-media CLI E2E smoke passed on `main` from `/tmp/mediaorchard-main-real-cli-e2e.B8Gvyp/output/job_825c8527e177`: generated an input mp4 with `say` and `ffmpeg`, then ran `controller start`, `submit`, `worker start --execution-mode real --once`, `jobs`, and artifact checks for `input_meta.json`, `audio.wav`, `subtitle.srt`, `transcript.txt`, `transcript.json`, `quality_report.json`, `report.md`, and passed quality status.
- Git repository initialized on `main`.
- Controller API and state machine tests are merged into `main`.
- Scheduler hard filters, scoring, assignment helper, active-count updates, and defensive scheduling checks are merged into `main`.
- Worker lifecycle API and WorkerAgent lifecycle tests are merged into `main`, including JSON `claim-next`, `claimed_at` lease marking, and `X-MediaOrchard-Node-Id` ownership checks.
- Worker tool execution is merged into `main` with registered command tools, existing input validation, structured `list[str]` argv, `shell=False`, subprocess timeout, timeout log capture, stdout/stderr log capture, log-write failure reporting, and failed exit-code reporting.
- Mock `video_to_subtitle` pipeline is merged into `main` and produces `audio.wav`, `transcript.txt`, `transcript.json`, `subtitle.srt`, `quality_report.json`, `report.md`, and per-step logs without real media tools.
- Database persistence tests are merged into `main` and verify all release models can be created, committed, and read back across sessions, including UTC datetime round-trips.
- README documents setup, configuration, API key hashing, Controller CLI startup, single-machine CLI demo commands, verification commands, and troubleshooting on `main`.
- Clean checkout verification passed from `/tmp/mediaorchard-clean-check.wcKBCH/repo` after fresh clone, new venv, editable install, `bash scripts/verify.sh` with 94 tests, and `bash scripts/smoke.sh`.
- Git tracked-file hygiene audit found no tracked local DB files, env/config-local files, media files, cache/work/output/log directories, pyc files, or actual API key/hash patterns; placeholder `<shared-secret>` references remain documented in `plan.md`.
- Local real-media smoke passed at `/tmp/mediaorchard-real-smoke.4Jc4aF/output/real_smoke` using macOS `say`, `ffmpeg` 7.1.1, `ffprobe` 7.1.1, system Python `mlx-whisper` 0.4.3, and model `mlx-community/whisper-tiny`; produced `subtitle.srt`, `transcript.txt`, `transcript.json`, `quality_report.json`, `report.md`, `audio.wav`, `input_meta.json`, and logs.
- Read-only Worker preflight command added as `mediaorchard doctor worker`.
- `mediaorchard doctor worker --target local --target wangyan@192.168.50.8 --target wangyan@192.168.50.9 --shared-root /Volumes/MediaOrchard --runtime-python python3 --whisper-python python3` found local system `python3` is 3.9.6, local ffmpeg/ffprobe/mlx_whisper are available, and local shared root is missing; both remotes have system `python3` 3.9.6 plus ffmpeg/ffprobe, but lack `mlx_whisper` and `/Volumes/MediaOrchard`.
- Worker preflight timeout handling is covered by a regression test so a slow local command or SSH target is reported as a failed check instead of crashing the diagnostic run.
- Release metadata tests verify `LICENSE`, release build tooling in the dev extra, and executable `scripts/release_check.sh` coverage for build, metadata, clean install, and hygiene gates.
- Worker bootstrap dry-run added as `mediaorchard doctor worker-bootstrap`; it generates the per-target script for virtualenv setup, package install, shared-root directory creation, and media tool verification without modifying targets unless `--execute` is explicitly supplied.
- Worker bootstrap supports `--wheel` dry-run plans so the same locally built release wheel can be copied to target Workers and installed from `/Users/wangyan/.mediaorchard/packages/` without requiring an already-published package index.
- Worker bootstrap supports explicit `--copy-wheel --execute` mode, which creates the target package directory, copies the local release wheel with `cp` or `scp`, and stops before running the bootstrap script if the copy fails.
- Worker bootstrap creates the shared-root layout before creating the Worker virtual environment, so `/Volumes/MediaOrchard` mount or permission failures stop before package installation leaves a partial Worker runtime.
- `bash scripts/release_env_check.sh` is a read-only multi-machine release gate: it runs local and remote Worker preflight checks, builds or reuses a release wheel, and prints `worker-bootstrap --copy-wheel` dry-run output without passing `--execute`.
- `RELEASE.md` documents the 0.1 release states, required gates, explicit confirmation requirement before remote `--execute`, and the rule not to claim multi-machine real-media execution until `bash scripts/release_env_check.sh` exits `0`.
- Worker preflight supports optional shared-root marker validation via `--shared-root-marker` and `--shared-root-marker-value`; `scripts/release_env_check.sh` passes `SHARED_ROOT_MARKER` and `SHARED_ROOT_MARKER_VALUE` through to local and SSH preflight so the final multi-machine gate can verify the targets read the same shared storage.
- `.github/workflows/release-check.yml` runs `PYTHON_FOR_VENV=.venv/bin/python bash scripts/release_check.sh` on `macos-14` with Python 3.12 for push and pull request events targeting `main`.
- Worker bootstrap execution with `--copy-wheel --execute` passes on `192.168.50.8` and `192.168.50.9` after exporting Homebrew paths in the bootstrap script for non-login SSH shells.
- Post-bootstrap Worker verification passes on both remotes: `/Users/wangyan/.mediaorchard/venv/bin/python` imports `mlx_whisper` 0.4.3, `mediaorchard --help` runs, and `pip check` reports no broken requirements.

## Current Release Status

Release 0.1 candidate for package, single-Mac real-media CLI execution, and marker-verified multi-Mac Worker readiness. The code now has current evidence for Controller/Worker CLI orchestration, durable state, scheduling, deterministic smoke mode, one local real-media Worker run through `ffprobe`, `ffmpeg`, and `mlx_whisper`, NAS-backed shared-root mounting, bootstrapped target Worker virtual environments, and a passing marker-verified multi-machine release environment gate.
