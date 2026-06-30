#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from mediaorchard.worker.real_media_smoke import run_real_media_smoke


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the MediaOrchard real-media smoke test.")
    parser.add_argument("--root", type=Path, required=True, help="Scratch root for work and output files.")
    parser.add_argument("--python", default="python3", help="Python executable with mlx_whisper installed.")
    parser.add_argument("--model", default="mlx-community/whisper-tiny", help="mlx-whisper model repo.")
    parser.add_argument("--voice", default="Samantha", help="macOS say voice for generating speech.")
    parser.add_argument("--phrase", default="hello media orchard smoke test")
    parser.add_argument("--timeout-seconds", type=int, default=120)
    args = parser.parse_args()

    result = run_real_media_smoke(
        root=args.root,
        python_executable=args.python,
        whisper_model=args.model,
        voice=args.voice,
        phrase=args.phrase,
        timeout_seconds=args.timeout_seconds,
    )
    print(result.status)
    print(result.output_dir)


if __name__ == "__main__":
    main()
