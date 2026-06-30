# MediaOrchard 0.1 Release Runbook

MediaOrchard 0.1 is a local-first release for a single Mac running real-media
jobs through the Controller and Worker CLI. Multi-machine execution is supported
by the code paths and bootstrap tooling, but must not be advertised as ready
until the target Worker machines pass the release environment gate.

## Release States

- Package release candidate: `bash scripts/release_check.sh` passes.
- Single-machine real-media candidate: package checks pass and the README
  real-media CLI demo has current evidence.
- Multi-machine candidate: `bash scripts/release_env_check.sh` exits `0` for
  local plus SSH targets after Worker environments and the shared root are
  prepared.

Do not claim multi-machine real-media execution until every target has Python
3.11+, `ffmpeg`, `ffprobe`, a working `mlx_whisper` import, a Worker virtual
environment, and the same resolved shared root such as `/Volumes/MediaOrchard`.

## Required Checks

Run the local package and smoke gate:

```bash
bash scripts/release_check.sh
```

This command runs the harness check, full test suite, CLI smoke, package build,
`twine check`, clean wheel install smoke, and tracked-file hygiene guard.

Run the read-only multi-machine environment gate:

```bash
bash scripts/release_env_check.sh
```

This command does not execute remote bootstrap. It runs Worker preflight checks,
builds or reuses a wheel, and prints the `mediaorchard doctor worker-bootstrap`
dry-run with `--copy-wheel` for the configured SSH targets.

## Worker Bootstrap

Remote bootstrap changes target machines. Get explicit confirmation before
running any command with `--execute`.

After confirmation, the bootstrap flow is:

```bash
.venv/bin/python -m build --wheel --outdir dist
wheel="$(ls dist/*.whl)"
mediaorchard doctor worker-bootstrap \
  --target wangyan@192.168.50.8 \
  --target wangyan@192.168.50.9 \
  --install-root /Users/wangyan/.mediaorchard \
  --shared-root /Volumes/MediaOrchard \
  --python /opt/homebrew/bin/python3.14 \
  --wheel "$wheel" \
  --copy-wheel \
  --execute
```

Prepare or mount `/Volumes/MediaOrchard` before executing bootstrap. The
bootstrap script intentionally creates the shared-root layout before creating
the Worker virtual environment so mount or permission failures stop early.

## Release Decision

Publish the 0.1 package only when `bash scripts/release_check.sh` passes on
`main`. Announce multi-machine support only when `bash scripts/release_env_check.sh`
also exits `0` on `main` for the actual target machines.
