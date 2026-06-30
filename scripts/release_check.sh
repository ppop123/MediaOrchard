#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

python_bin=".venv/bin/python"
if [ ! -x "$python_bin" ]; then
  echo 'Run setup first: python3 -m venv .venv && .venv/bin/python -m pip install -e ".[dev]"' >&2
  exit 1
fi

.venv/bin/python scripts/check-harness.py
"$python_bin" -m pytest
"$python_bin" -m mediaorchard.cli.main --help >/dev/null

build_dir="$(mktemp -d "${TMPDIR:-/tmp}/mediaorchard-dist.XXXXXX")"
install_venv="$(mktemp -d "${TMPDIR:-/tmp}/mediaorchard-install.XXXXXX")"
trap 'rm -rf "$build_dir" "$install_venv"' EXIT

"$python_bin" -m build --outdir "$build_dir"
artifacts=("$build_dir"/*)
if [ ${#artifacts[@]} -eq 0 ] || [ ! -e "${artifacts[0]}" ]; then
  echo "No release artifacts were built." >&2
  exit 1
fi

"$python_bin" -m twine check "${artifacts[@]}"

wheels=("$build_dir"/*.whl)
if [ ${#wheels[@]} -eq 0 ] || [ ! -e "${wheels[0]}" ]; then
  echo "No wheel artifact was built." >&2
  exit 1
fi

venv_python="${PYTHON_FOR_VENV:-python3}"
"$venv_python" -m venv "$install_venv"
"$install_venv/bin/python" -m pip install -U pip >/dev/null
"$install_venv/bin/python" -m pip install "${wheels[0]}" >/dev/null
"$install_venv/bin/mediaorchard" --help >/dev/null

if git ls-files | grep -E '(^|/)(dist|build|logs|work|output|cache)/|(^|/)(config\.local\.yaml|\.env|.*\.pem|.*\.key|credentials\.json|.*\.db|.*\.sqlite3?)$|\.(mp4|mov|wav|aiff|srt)$'; then
  echo "Tracked release-blocking local artifact, secret, database, or media file found." >&2
  exit 1
fi
