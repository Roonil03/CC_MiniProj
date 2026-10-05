"""RL MDP environment (Member-4): single-agent PPO baseline.

State (Design Sec 22): per-node CPU, MEM, NET, LAT, LOAD, QUEUE, SLO slack,
HEALTH plus predicted horizon values. The agent sees current + predicted
future state. Action space (Sec 23): NOOP / MIGRATE / SCALE / PLACE /
RESOURCE_ADJUST encoded discretely. Reward (Sec 25): multi-objective with
SLO violation dominant. Simulation is the training environment — never the
physical cluster.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import gymnasium as gym
import numpy as np
from gymnasium import spaces

ACTION_TYPES = ["NOOP", "MIGRATE", "SCALE", "PLACE", "RESOURCE_ADJUST"]

DEFAULT_REWARD_WEIGHTS = {
    "slo": 10.0,
    "latency": 3.0,
    "migration": 2.5,
    "energy": 1.5,
    "fragmentation": 1.5,
    "cost": 1.0,
}


@dataclass
class EnvConfig:
    num_nodes: int = 3
    horizon: int = 4
    slo_ms: float = 50.0
    max_steps: int = 64
    seed: int = 42
    reward_weights: dict[str, float] | None = None

    @property
    def weights(self) -> dict[str, float]:
        return self.reward_weights or dict(DEFAULT_REWARD_WEIGHTS)


class EdgeResourceEnv(gym.Env):
    """Deterministic-when-seeded edge resource-management MDP."""

    metadata = {"render_modes": []}

    def __init__(self, config: EnvConfig | None = None) -> None:
        super().__init__()
        self.config = config or EnvConfig()
        n = self.config.num_nodes
        h = self.config.horizon
        # Per-node features: cpu, mem, net, lat, load, queue, slo_slack, health
        # plus predicted cpu/mem for h steps.
        self._feat = 8 + 2 * h
        self.observation_space = spaces.Box(
            low=0.0, high=1.0, shape=(n * self._feat,), dtype=np.float32
        )
        self.action_space = spaces.Discrete(len(ACTION_TYPES))
        self._rng = np.random.default_rng(self.config.seed)
        self._state: np.ndarray = np.zeros(n * self._feat, dtype=np.float32)
        self._step = 0

    # -- gymnasium API --------------------------------------------------
    def reset(self, *, seed: int | None = None, options: dict | None = None) -> tuple[np.ndarray, dict]:
        if seed is not None:
            self._rng = np.random.default_rng(seed)
        self._step = 0
        self._state = self._rng.uniform(0.2, 0.7, size=self._state.shape).astype(np.float32)
        return self._state.copy(), {"step": 0}

    def step(self, action: int) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        assert self.action_space.contains(action), f"invalid action {action}"
        atype = ACTION_TYPES[int(action)]
        cpu = float(self._state[0])
        # Workload drift: bursty upward pressure, action relieves hotspot.
        drift = float(self._rng.normal(0.02, 0.02))
        relief = {"NOOP": 0.0, "MIGRATE": 0.15, "SCALE": 0.10, "PLACE": 0.12, "RESOURCE_ADJUST": 0.05}[atype]
        cpu = min(1.0, max(0.0, cpu + drift - relief))
        self._state[0] = cpu
        latency_ms = 8.0 * (1.0 + 6.0 * cpu**3)
        slo_hit = 1.0 if latency_ms > self.config.slo_ms else 0.0
        migrated = 0.0 if atype == "NOOP" else 1.0
        w = self.config.weights
        reward = (
            -w["slo"] * slo_hit
            - w["latency"] * (latency_ms / 100.0)
            - w["migration"] * migrated
            + w["fragmentation"] * (1.0 - abs(cpu - 0.6))
        )
        self._step += 1
        terminated = False
        truncated = self._step >= self.config.max_steps
        info = {"action_type": atype, "cpu": cpu, "latency_ms": latency_ms, "slo_hit": slo_hit}
        return self._state.copy(), float(reward), terminated, truncated, info

    # -- helpers --------------------------------------------------------
    def action_from_name(self, name: str) -> int:
        return ACTION_TYPES.index(name.upper())

    def describe(self) -> dict[str, Any]:
        return {
            "num_nodes": self.config.num_nodes,
            "horizon": self.config.horizon,
            "actions": ACTION_TYPES,
            "reward_weights": self.config.weights,
            "algorithm": "PPO (single-agent baseline)",
        }
