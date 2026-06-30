#!/usr/bin/env bash
set -euo pipefail

python3 scripts/check-harness.py
.venv/bin/python -m pytest
