#!/usr/bin/env bash
# Run every configured prediction model, resume failed/interrupted jobs, and
# produce one portable archive containing logs, JSON, plots, registries, and
# model artifacts. No API server, NATS consumer, Kubernetes client, or live
# workload is started by this script.
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SERVICE_ROOT/../.." && pwd)"
PYTHON="${PYTHON:-python3}"
RUN_DIR="${RUN_DIR:-$REPO_ROOT/experiments/runs/model-sweep}"
DB="${PREDICTION_DB:-$SERVICE_ROOT/data/node_samples.sqlite}"
MAX_PROCESS_RETRIES="${MAX_PROCESS_RETRIES:-3}"
EPOCHS="${EPOCHS:-20}"
SEED="${SEED:-42}"
SOURCE_LABEL="${SOURCE_LABEL:-recorded-telemetry}"

if [[ "${ALL_METRICS:-0}" == "1" ]]; then
  METRICS=(cpu memory network_in network_out)
elif [[ -n "${PREDICTION_METRICS:-}" ]]; then
  read -r -a METRICS <<< "$PREDICTION_METRICS"
else
  METRICS=(cpu)
fi

if [[ -n "${PREDICTION_MODELS:-}" ]]; then
  read -r -a MODELS <<< "$PREDICTION_MODELS"
else
  MODELS=(persistence arima ets lstm gru temporal transformer)
fi

mkdir -p "$RUN_DIR"
MANIFEST="$RUN_DIR/sweep_manifest.json"
ARCHIVE="${RUN_DIR%/}.zip"

package_outputs() {
  local status="${1:-partial}"
  "$PYTHON" -c 'import json, pathlib, sys; p=pathlib.Path(sys.argv[1]); rows=[]; failed=[]; 
for state_path in sorted(p.glob("*/run_state.json")):
    state=json.loads(state_path.read_text(encoding="utf-8")); rows.append({"run_id":state.get("run_id"),"status":state.get("status"),"config":state.get("config"),"jobs":state.get("jobs")}); failed.extend([k for k,v in state.get("jobs",{}).items() if v.get("status") != "completed"])
payload={"status":sys.argv[2],"generated_at":__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),"models":rows,"failed_jobs":failed}; (p/"sweep_manifest.json").write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n",encoding="utf-8")' "$RUN_DIR" "$status"
  rm -f "$ARCHIVE"
  if command -v zip >/dev/null 2>&1; then
    (cd "$RUN_DIR" && zip -qr "$ARCHIVE" .)
  else
    (cd "$SERVICE_ROOT" && "$PYTHON" -m prediction_app.scripts.run_all_models --package-only --run-dir "$RUN_DIR")
  fi
  echo "Output archive: $ARCHIVE"
}

trap 'package_outputs "partial"' EXIT

overall_status=0
for model in "${MODELS[@]}"; do
  model_dir="$RUN_DIR/$model"
  completed=0
  for process_attempt in $(seq 1 "$MAX_PROCESS_RETRIES"); do
    echo "[$(date -u +%FT%TZ)] starting model=$model process_attempt=$process_attempt"
    set +e
    (
      cd "$SERVICE_ROOT"
      "$PYTHON" -m prediction_app.scripts.run_all_models \
        --db "$DB" \
        --run-dir "$model_dir" \
        --models "$model" \
        --metrics "${METRICS[@]}" \
        --epochs "$EPOCHS" \
        --seed "$SEED" \
        --source-label "$SOURCE_LABEL" \
        --max-attempts "$MAX_PROCESS_RETRIES"
    )
    exit_code=$?
    set -e
    if [[ "$exit_code" -eq 0 ]]; then
      completed=1
      break
    fi
    echo "[$(date -u +%FT%TZ)] model=$model failed with exit=$exit_code; state is resumable" >&2
  done
  if [[ "$completed" -ne 1 ]]; then
    overall_status=1
    echo "[$(date -u +%FT%TZ)] model=$model did not complete; continuing to preserve other outputs" >&2
  fi
done

if [[ "$overall_status" -eq 0 ]]; then
  trap - EXIT
  package_outputs "completed"
else
  echo "One or more models failed; the archive will contain resumable partial state." >&2
fi
exit "$overall_status"
