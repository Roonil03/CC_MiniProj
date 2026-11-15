#!/usr/bin/env bash
# Offline all-model sweep over an existing SQLite telemetry database.
set -Eeuo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
venv="${DT_VENV:-$root/.venv-dt-models}"
if [[ ! -x "$venv/bin/python" ]]; then
  "${PYTHON:-python3}" -m venv "$venv"
fi
"$venv/bin/python" -m pip install -r "$root/services/prediction-service/requirements.txt" -r "$root/scripts/requirements-dt-models.txt"
export PYTHON="$venv/bin/python"
exec bash "$root/services/prediction-service/scripts/run_all_models.sh" "$@"
