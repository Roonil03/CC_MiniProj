#!/usr/bin/env bash
# Use the same resumable GPU container workflow on Linux/macOS or Git Bash.
set -Eeuo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if ! command -v pwsh >/dev/null 2>&1; then
  echo "PowerShell 7 (pwsh) is required for the GPU model runner." >&2
  exit 1
fi
exec pwsh -NoProfile -File "$root/scripts/run_dt_models.ps1" "$@"
