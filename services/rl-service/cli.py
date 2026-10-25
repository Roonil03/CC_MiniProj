"""Reproducible Member-4 DT/simulation/RL smoke workflow.

The command evaluates a synthetic twin and counterfactual candidates by
default. PPO training is deliberately opt-in with ``--train`` and always
runs against the simulation environment, never Kubernetes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

SERVICE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SERVICE_ROOT.parent.parent
sys.path.insert(0, str(SERVICE_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services" / "simulation-service"))

from app.safety import GateConfig, SafetyGate  # noqa: E402
from app.simulator import evaluate_candidates  # noqa: E402
from app.twin import TwinState  # noqa: E402
from rl_app.env import EdgeResourceEnv, EnvConfig  # noqa: E402
from rl_app.policies import git_sha, policy_record  # noqa: E402


def workflow(seed: int, train: bool, timesteps: int, episodes: int) -> dict:
    np.random.seed(seed)
    twin = TwinState(stale_after_seconds=5.0)
    twin.apply_telemetry("edge-a1", 0.70, 0.55, 210.0, 180.0)
    twin.apply_telemetry("edge-b1", 0.35, 0.40, 90.0, 70.0)
    twin.apply_telemetry(
        "edge-c1", 0.50, 0.50,
        timestamp=datetime.now(timezone.utc) - timedelta(seconds=3600),
    )
    physical = {
        "edge-a1": {"cpu": 0.72, "memory": 0.56, "network_in": 212.0, "network_out": 181.0},
        "edge-b1": {"cpu": 0.34, "memory": 0.41, "network_in": 91.0, "network_out": 69.0},
        "edge-c1": {"cpu": 0.90, "memory": 0.90, "network_in": 400.0, "network_out": 400.0},
    }
    scores = twin.score_all(physical)
    candidates = [
        {"type": "NOOP", "service": "processor", "source": "edge-a1"},
        {"type": "MIGRATE", "service": "processor", "source": "edge-a1", "destination": "edge-b1"},
        {"type": "MIGRATE", "service": "processor", "source": "edge-a1", "destination": "edge-c1"},
        {"type": "SCALE", "service": "processor", "source": "edge-a1", "replicas": 4},
    ]
    results = evaluate_candidates(twin, candidates, service_cpu=0.5, service_mem_mb=512.0)
    gate = SafetyGate(GateConfig())
    decisions = []
    for index, (candidate, result) in enumerate(zip(candidates, results)):
        request = {
            "decision_id": f"cli-{seed}-{index}",
            "action": candidate,
            "predicted": {
                "latency": result.predicted_latency_ms,
                "cpu": result.predicted_cpu,
                "slo_violation_probability": result.slo_violation_prob,
                "prediction_confidence": 0.87,
            },
            "dt_fidelity": scores.get(candidate.get("source", ""), 0.0),
            "destination_free_cpu": 2.0,
            "destination_healthy": candidate.get("destination") != "edge-c1",
            "source_healthy": True,
        }
        verdict = gate.evaluate(request)
        decisions.append({"request": request, "approved": verdict.approved, "reasons": verdict.reasons})

    output: dict = {
        "git_commit": git_sha(),
        "seed": seed,
        "config": {"algorithm": "PPO", "training": train, "timesteps": timesteps},
        "fidelity": scores,
        "simulations": [
            {
                "action": candidate,
                "predicted_cpu": result.predicted_cpu,
                "predicted_mem": result.predicted_mem,
                "predicted_latency_ms": result.predicted_latency_ms,
                "slo_violation_probability": result.slo_violation_prob,
                "migration_cost": result.migration_cost,
                "migration_duration_s": result.migration_duration_s,
                "feasible": result.feasible,
                "notes": result.notes,
            }
            for candidate, result in zip(candidates, results)
        ],
        "decisions": decisions,
        "actuation": {"allowed": False, "controller": "infrastructure-controller", "dry_run": True},
    }
    if train:
        from rl_app.ppo import PPOConfig, make_model, rollout

        ppo_config = PPOConfig(total_timesteps=timesteps, seed=seed)
        model = make_model(EnvConfig(num_nodes=3, horizon=4, seed=seed), ppo_config)
        model.learn(total_timesteps=timesteps)
        output["ppo"] = {
            "rollout": rollout(model, EdgeResourceEnv(EnvConfig(num_nodes=3, horizon=4, seed=seed + 1)), episodes),
            "policy": policy_record(
                "ppo-edge-migration", "v0.1.0", f"synthetic-seed-{seed}",
                ppo_config.as_dict(), {"note": "simulation-only baseline"},
            ),
        }
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=int(os.getenv("RL_SEED", "42")))
    parser.add_argument("--train", action="store_true", help="run opt-in PPO training in simulation")
    parser.add_argument("--timesteps", type=int, default=2048)
    parser.add_argument("--episodes", type=int, default=2)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    result = workflow(args.seed, args.train, args.timesteps, args.episodes)
    payload = json.dumps(result, indent=2, sort_keys=True, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)


if __name__ == "__main__":
    main()
