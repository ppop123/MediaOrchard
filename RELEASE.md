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

## Shared Storage Scope

Single-machine release does not require shared storage. Package checks,
deterministic demos, and the single-machine real-media CLI demo can use a local
temporary root because the Controller and Worker run on the same Mac and read
the same filesystem directly.

Multi-machine release requires marker-verified shared storage. Every Worker
must see the same real shared filesystem mounted at the same resolved path,
for example `/Volumes/MediaOrchard`; the same local path on separate disks is not
sufficient. Use a marker token stored inside the shared root as the release
proof that local and remote targets are reading the same storage.

Do not claim multi-machine real-media execution until every target has Python
3.11+, `ffmpeg`, `ffprobe`, a working `mlx_whisper` import, a Worker virtual
environment, and the same resolved shared root such as `/Volumes/MediaOrchard`.
For the final multi-machine gate, place a marker file in that real shared root
and set `SHARED_ROOT_MARKER` plus `SHARED_ROOT_MARKER_VALUE` so every target
proves it can read the same shared storage, not merely a local directory with
the same path. Generate the token from the shared root, for example with
`uuidgen > /Volumes/MediaOrchard/.mediaorchard-shared-root-id`.

## Required Checks

Run the local package and smoke gate:

```bash
bash scripts/release_check.sh
```

This command runs the harness check, full test suite, CLI smoke, package build,
`twine check`, clean wheel install smoke, and tracked-file hygiene guard.

Run the read-only multi-machine environment gate:

```bash
export SHARED_ROOT_MARKER=.mediaorchard-shared-root-id
export SHARED_ROOT_MARKER_VALUE='replace-with-token-from-the-shared-root-marker'
bash scripts/release_env_check.sh
```

This command does not execute remote bootstrap. It runs Worker preflight checks,
builds or reuses a wheel, and prints the `mediaorchard doctor worker-bootstrap`
dry-run with `--copy-wheel` for the configured SSH targets. When the marker
environment variables are set, the preflight also verifies every target reads
the expected marker token from the shared root.

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
