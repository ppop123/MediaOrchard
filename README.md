# MediaOrchard Grove

MediaOrchard Grove is a local media processing scheduler for coordinating trusted Mac Workers that run `ffmpeg`, `ffprobe`, and `mlx-whisper` workloads.

The MVP is intentionally deterministic: the Controller owns policy, scheduling, durable state, and recovery; Workers authenticate, report resources, and execute only validated structured tool calls.

## Status

This repository is in early MVP implementation. The durable plan lives in [plan.md](plan.md).

## Local Development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e ".[dev]"
bash scripts/verify.sh
```

## CLI

```bash
mediaorchard --help
mediaorchard controller start --help
mediaorchard worker start --help
```

Without installing the package, use:

```bash
.venv/bin/python -m mediaorchard.cli.main --help
```

## Verification

```bash
bash scripts/verify.sh
bash scripts/smoke.sh
```

## API Key Hashing

Workers receive the raw key through `MEDIAORCHARD_API_KEY`. The Controller stores only a SHA-256 hash in config.

```bash
.venv/bin/python -c 'from mediaorchard.shared.security import hash_api_key; print(hash_api_key("replace-me"))'
```

Do not commit real raw API keys.
