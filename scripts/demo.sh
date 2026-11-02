#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
demo_script="$script_dir/demo.py"

if [[ ! -f "$demo_script" ]]; then
  printf 'DT-RAM demo launcher: expected demo script at %s\n' "$demo_script" >&2
  exit 1
fi

if [[ -n "${PYTHON:-}" ]]; then
  python_cmd="$PYTHON"
  if ! command -v "$python_cmd" >/dev/null 2>&1; then
    printf 'DT-RAM demo launcher: PYTHON points to an unavailable executable: %s\n' "$python_cmd" >&2
    exit 1
  fi
elif command -v python3 >/dev/null 2>&1; then
  python_cmd="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  python_cmd="$(command -v python)"
else
  printf 'DT-RAM demo requires Python. Install Python 3 and ensure python3 or python is on PATH, or set PYTHON to its executable path.\n' >&2
  exit 127
fi

exec "$python_cmd" "$demo_script" "$@"
