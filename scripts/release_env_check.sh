#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

python_bin="${PYTHON_BIN:-.venv/bin/python}"
if [ ! -x "$python_bin" ]; then
  echo 'Run setup first: python3 -m venv .venv && .venv/bin/python -m pip install -e ".[dev]"' >&2
  exit 1
fi

echo "MediaOrchard release environment check (read-only)."
echo "This script does not execute remote bootstrap."

shared_root="${SHARED_ROOT:-/Volumes/MediaOrchard}"
install_root="${INSTALL_ROOT:-/Users/wangyan/.mediaorchard}"
worker_python="${WORKER_PYTHON:-/opt/homebrew/bin/python3.14}"
local_runtime_python="${LOCAL_RUNTIME_PYTHON:-.venv/bin/python}"
local_whisper_python="${LOCAL_WHISPER_PYTHON:-.venv/bin/python}"
remote_whisper_python="${REMOTE_WHISPER_PYTHON:-$install_root/venv/bin/python}"
timeout_seconds="${TIMEOUT_SECONDS:-10}"
local_preflight_targets="${LOCAL_PREFLIGHT_TARGETS-local}"
remote_preflight_targets="${REMOTE_PREFLIGHT_TARGETS-wangyan@192.168.50.8 wangyan@192.168.50.9}"
bootstrap_targets="${BOOTSTRAP_TARGETS-wangyan@192.168.50.8 wangyan@192.168.50.9}"
status=0

run_step() {
  local title="$1"
  shift
  echo
  echo "== $title =="
  if ! "$@"; then
    status=1
  fi
}

set_target_args() {
  target_args_result=()
  local target
  for target in "$@"; do
    target_args_result+=("--target" "$target")
  done
}

local_targets=()
remote_targets=()
bootstrap_target_values=()
if [ -n "$local_preflight_targets" ]; then
  read -r -a local_targets <<< "$local_preflight_targets"
fi
if [ -n "$remote_preflight_targets" ]; then
  read -r -a remote_targets <<< "$remote_preflight_targets"
fi
if [ -n "$bootstrap_targets" ]; then
  read -r -a bootstrap_target_values <<< "$bootstrap_targets"
fi

if [ "${#local_targets[@]}" -gt 0 ]; then
  set_target_args "${local_targets[@]}"
  run_step "Local Worker preflight" \
    "$python_bin" -m mediaorchard.cli.main doctor worker \
    "${target_args_result[@]}" \
    --shared-root "$shared_root" \
    --runtime-python "$local_runtime_python" \
    --whisper-python "$local_whisper_python" \
    --timeout-seconds "$timeout_seconds"
fi

if [ "${#remote_targets[@]}" -gt 0 ]; then
  set_target_args "${remote_targets[@]}"
  run_step "Remote Worker preflight" \
    "$python_bin" -m mediaorchard.cli.main doctor worker \
    "${target_args_result[@]}" \
    --shared-root "$shared_root" \
    --runtime-python "$worker_python" \
    --whisper-python "$remote_whisper_python" \
    --timeout-seconds "$timeout_seconds"
fi

if [ "${#bootstrap_target_values[@]}" -gt 0 ]; then
  build_dir=""
  wheel="${MEDIAORCHARD_WHEEL:-}"
  if [ -z "$wheel" ]; then
    build_dir="$(mktemp -d "${TMPDIR:-/tmp}/mediaorchard-env-dist.XXXXXX")"
    trap 'if [ -n "${build_dir:-}" ]; then rm -rf "$build_dir"; fi' EXIT
    if "$python_bin" -m build --wheel --outdir "$build_dir" >/dev/null; then
      wheel_candidates=("$build_dir"/*.whl)
      if [ "${#wheel_candidates[@]}" -eq 1 ] && [ -e "${wheel_candidates[0]}" ]; then
        wheel="${wheel_candidates[0]}"
      else
        echo "Expected exactly one wheel artifact in $build_dir." >&2
        status=1
      fi
    else
      echo "Wheel build failed; skipping Worker bootstrap dry-run." >&2
      status=1
    fi
  fi
  if [ -n "$wheel" ]; then
    set_target_args "${bootstrap_target_values[@]}"
    run_step "Worker bootstrap dry-run" \
      "$python_bin" -m mediaorchard.cli.main doctor worker-bootstrap \
      "${target_args_result[@]}" \
      --install-root "$install_root" \
      --shared-root "$shared_root" \
      --python "$worker_python" \
      --wheel "$wheel" \
      --copy-wheel
  fi
fi

exit "$status"
