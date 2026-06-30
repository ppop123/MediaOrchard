# MediaOrchard Grove Task Plan

## Goal

Local multi-Mac media processing scheduler for ffmpeg and whisper workloads.

## Phases

- [x] Phase 1: Define product direction in `plan.md`
- [x] Phase 2: Create reviewed implementation plan
- [x] Phase 3: Bootstrap package, tests, docs harness, and Git repo
- [x] Phase 4: Implement Controller models/API/state machine
- [x] Phase 5: Implement scheduler and Worker runtime
- [x] Phase 6: Run mock pipeline and real local media smoke test
- [ ] Phase 7: Prepare public release artifacts

Release gates are tracked in `docs/RELEASE_CHECKLIST.md`.

## Current Focus

- Phase 7 release hardening: package release checks are now in place; next focus is a repeatable Worker bootstrap path for per-target virtual environments, shared root layout, and required media tools.

## Errors Encountered

| Error | Attempt | Resolution |
|---|---|---|
| `/Users/wy/MediaOrchard/.venv/bin/python: No module named build` | Checked package build readiness on `main` | Added `build` and `twine` to the dev extra and created `scripts/release_check.sh` to verify release artifacts. |
