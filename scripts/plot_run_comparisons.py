"""Plot numeric forecast and policy comparisons from one offline run directory."""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import defaultdict
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    groups: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for result_path in args.run_dir.glob("*/forecast/results/*.json"):
        result = json.loads(result_path.read_text(encoding="utf-8"))
        label = f"{result_path.parents[2].name}/{result.get('kind')}/{result.get('metric')}"
        for horizon, values in result.get("metrics", {}).get("test", {}).items():
            for name, value in values.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                    groups[f"forecast_{name}_h{horizon}"].append((label, float(value)))
        latency = result.get("inference_latency_ms", {}).get("test_mean")
        if isinstance(latency, (int, float)) and math.isfinite(latency):
            groups["forecast_inference_latency_ms"].append((label, float(latency)))
    for policy_path in args.run_dir.glob("*/ppo.json"):
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        for comparator, metrics in policy.get("evaluation", {}).get("comparators", {}).items():
            label = f"{policy_path.parent.name}/{comparator}"
            for name, value in metrics.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                    groups[f"policy_{name}"].append((label, float(value)))
    plots = args.run_dir / "comparison-plots"
    plots.mkdir(exist_ok=True)
    for metric, rows in groups.items():
        if not rows:
            continue
        fig, axis = plt.subplots(figsize=(max(8, len(rows) * 0.8), 5))
        axis.bar([row[0] for row in rows], [row[1] for row in rows])
        axis.set_title(metric.replace("_", " "))
        axis.tick_params(axis="x", rotation=60)
        axis.grid(axis="y", alpha=0.25)
        fig.tight_layout()
        fig.savefig(plots / (re.sub(r"[^a-zA-Z0-9_-]", "_", metric) + ".png"), dpi=140)
        plt.close(fig)
    (plots / "plot-manifest.json").write_text(json.dumps({"metrics": {key: len(value) for key, value in groups.items()},
                                                           "synthetic_or_local": True}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
