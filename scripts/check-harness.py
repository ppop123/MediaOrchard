#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

REQUIRED = [
    "AGENTS.md",
    "README.md",
    "ARCHITECTURE.md",
    "docs/README.md",
    "docs/QUALITY.md",
    "task_plan.md",
    "findings.md",
    "progress.md",
    "scripts/verify.sh",
    "scripts/smoke.sh",
]

root = Path.cwd()
missing = [path for path in REQUIRED if not (root / path).exists()]

if missing:
    print("Missing harness files:")
    for item in missing:
        print(f"  - {item}")
    sys.exit(1)

print("Harness check passed.")
