"""RL MDP environment (Member-4): single-agent PPO baseline.

State: per-node CPU, MEM, NET, LAT, LOAD, QUEUE, SLO slack,
HEALTH plus predicted horizon values. The agent sees current + predicted
future state. Action space (Sec 23): NOOP / MIGRATE / SCALE / PLACE /
RESOURCE_ADJUST encoded discretely. Reward (Sec 25): multi-objective with
SLO violation dominant. Simulation is the training environment — never the
physical cluster.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
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
    domain_randomization: bool = False

    def __post_init__(self) -> None:
        if any(not isinstance(value, int) or isinstance(value, bool) or value < 1
               for value in (self.num_nodes, self.horizon, self.max_steps)):
            raise ValueError("num_nodes, horizon, and max_steps must be positive")
        if not isinstance(self.seed, int) or isinstance(self.seed, bool) or self.seed < 0:
            raise ValueError("seed must be a non-negative integer")
        if not math.isfinite(self.slo_ms) or self.slo_ms <= 0:
            raise ValueError("slo_ms must be a finite positive number")
        expected = set(DEFAULT_REWARD_WEIGHTS)
        if set(self.weights) != expected:
            raise ValueError(f"reward weights must define exactly: {', '.join(sorted(expected))}")
        for name, value in self.weights.items():
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value < 0:
                raise ValueError(f"reward weight {name!r} must be finite and non-negative")

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
        self._drift_bias = 0.02
        self._drift_scale = 0.02
        self._relief_scale = 1.0

    # -- gymnasium API --------------------------------------------------
    def reset(self, *, seed: int | None = None, options: dict | None = None) -> tuple[np.ndarray, dict]:
        super().reset(seed=seed)
        self._rng = self.np_random
        self._step = 0
        self._state = self._rng.uniform(0.2, 0.7, size=self._state.shape).astype(np.float32)
        if self.config.domain_randomization:
            # Sample plausible dynamics per episode to reduce dependence on a
            # single synthetic workload. The sampled parameters are observable
            # in info so runs remain auditable and reproducible from the seed.
            self._drift_bias = float(self._rng.uniform(0.005, 0.04))
            self._drift_scale = float(self._rng.uniform(0.005, 0.035))
            self._relief_scale = float(self._rng.uniform(0.7, 1.3))
        else:
            self._drift_bias, self._drift_scale, self._relief_scale = 0.02, 0.02, 1.0
        for node in range(self.config.num_nodes):
            index = node * self._feat
            for horizon in range(self.config.horizon):
                projected = (horizon + 1) * self._drift_bias
                self._state[index + 8 + 2 * horizon] = np.clip(self._state[index] + projected, 0, 1)
                self._state[index + 9 + 2 * horizon] = np.clip(self._state[index + 1] + projected * 0.4, 0, 1)
        return self._state.copy(), {"step": 0, "dynamics": self._dynamics_info()}

    def step(self, action: int) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        if not self.action_space.contains(action):
            raise ValueError(f"invalid action {action}")
        atype = ACTION_TYPES[int(action)]
        cpu_indices = [node * self._feat for node in range(self.config.num_nodes)]
        node_cpus = []
        for index in cpu_indices:
            drift = float(self._rng.normal(self._drift_bias, self._drift_scale))
            cpu = min(1.0, max(0.0, float(self._state[index]) + drift))
            self._state[index] = cpu
            self._state[index + 1] = np.clip(self._state[index + 1] + drift * 0.4, 0, 1)
            self._state[index + 2] = np.clip(self._state[index + 2] + drift * 0.7, 0, 1)
            self._state[index + 4] = np.clip(self._state[index + 4] + drift, 0, 1)
            self._state[index + 5] = np.clip(self._state[index + 5] + drift * 0.5, 0, 1)
            node_cpus.append(cpu)
        hotspot = int(np.argmax(node_cpus))
        coolest = int(np.argmin(node_cpus))
        source = hotspot * self._feat
        destination = coolest * self._feat
        migration_cost = 0.0
        if atype in {"MIGRATE", "PLACE"} and hotspot != coolest:
            amount = min(0.15 * self._relief_scale, float(self._state[source]))
            memory = min(0.08 * self._relief_scale, float(self._state[source + 1]))
            if self._state[destination] + amount <= 1 and self._state[destination + 1] + memory <= 1:
                self._state[source] -= amount
                self._state[destination] += amount
                self._state[source + 1] -= memory
                self._state[destination + 1] += memory
                self._state[source + 2] = np.clip(self._state[source + 2] + 0.08, 0, 1)
                migration_cost = 1.0
        elif atype in {"SCALE", "RESOURCE_ADJUST"}:
            self._state[source] = np.clip(self._state[source] - (0.10 if atype == "SCALE" else 0.05) * self._relief_scale, 0, 1)
            self._state[source + 1] = np.clip(self._state[source + 1] + (0.06 if atype == "SCALE" else 0.02), 0, 1)
        node_cpus = [float(self._state[index]) for index in cpu_indices]
        for index in cpu_indices:
            for horizon in range(self.config.horizon):
                projected = (horizon + 1) * self._drift_bias
                self._state[index + 8 + 2 * horizon] = np.clip(self._state[index] + projected, 0, 1)
                self._state[index + 9 + 2 * horizon] = np.clip(self._state[index + 1] + projected * 0.4, 0, 1)
        cpu = max(node_cpus)
        latency_ms = 8.0 * (1.0 + 6.0 * cpu**3)
        slo_hit = 1.0 if latency_ms > self.config.slo_ms else 0.0
        energy = float(np.mean(np.square(node_cpus)))
        fragmentation = float(np.std(node_cpus))
        action_cost = 0.0 if atype == "NOOP" else 1.0
        w = self.config.weights
        reward = (
            -w["slo"] * slo_hit
            - w["latency"] * (latency_ms / 100.0)
            - w["migration"] * migration_cost
            - w["energy"] * energy
            - w["fragmentation"] * fragmentation
            - w["cost"] * action_cost
        )
        self._step += 1
        terminated = False
        truncated = self._step >= self.config.max_steps
        info = {
            "action_type": atype,
            "cpu": cpu,
            "mean_cpu": float(np.mean(node_cpus)),
            "latency_ms": latency_ms,
            "slo_hit": slo_hit,
            "energy_proxy": energy,
            "migration_cost": migration_cost,
            "fragmentation": fragmentation,
            "dynamics": self._dynamics_info(),
        }
        return self._state.copy(), float(reward), terminated, truncated, info

    def _dynamics_info(self) -> dict[str, float]:
        return {
            "drift_bias": self._drift_bias,
            "drift_scale": self._drift_scale,
            "relief_scale": self._relief_scale,
        }

    # -- helpers --------------------------------------------------------
    def action_from_name(self, name: str) -> int:
        return ACTION_TYPES.index(name.upper())

    def describe(self) -> dict[str, Any]:
        return {
            "num_nodes": self.config.num_nodes,
            "horizon": self.config.horizon,
            "actions": ACTION_TYPES,
            "reward_weights": self.config.weights,
            "domain_randomization": self.config.domain_randomization,
            "algorithm": "PPO (single-agent baseline)",
        }
