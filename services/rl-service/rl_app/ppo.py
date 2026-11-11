"""Single-agent PPO baseline (Member-4).

PPO first per docs/AGENTS.md: stable, reproducible, discrete/mixed-action
friendly. MARL only after this baseline is reliable. Training target is
always the simulator/twin — never physical infrastructure.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any

import numpy as np

from .env import EdgeResourceEnv, EnvConfig

DEFAULT_PPO = {
    "algorithm": "PPO",
    "gamma": 0.99,
    "learning_rate": 0.0003,
    "n_steps": 2048,
    "batch_size": 64,
    "n_epochs": 10,
    "seed": 42,
}


@dataclass
class PPOConfig:
    gamma: float = 0.99
    learning_rate: float = 0.0003
    n_steps: int = 2048
    batch_size: int = 64
    n_epochs: int = 10
    total_timesteps: int = 10_000
    seed: int = 42

    def as_dict(self) -> dict[str, Any]:
        return {
            "algorithm": "PPO",
            "gamma": self.gamma,
            "learning_rate": self.learning_rate,
            "n_steps": self.n_steps,
            "batch_size": self.batch_size,
            "n_epochs": self.n_epochs,
            "total_timesteps": self.total_timesteps,
            "seed": self.seed,
        }


def make_model(env_config: EnvConfig | None = None, ppo_config: PPOConfig | None = None):
    """Build an SB3 PPO model on the DT-RL environment (import SB3 lazily)."""
    from stable_baselines3 import PPO
    import torch

    require_cuda = os.getenv("DT_RAM_REQUIRE_CUDA") == "1"
    if require_cuda and not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU required for PPO but PyTorch cannot access it")

    ppo = ppo_config or PPOConfig()
    env = EdgeResourceEnv(env_config or EnvConfig(seed=ppo.seed))
    return PPO(
        "MlpPolicy",
        env,
        gamma=ppo.gamma,
        learning_rate=ppo.learning_rate,
        n_steps=ppo.n_steps,
        batch_size=ppo.batch_size,
        n_epochs=ppo.n_epochs,
        seed=ppo.seed,
        verbose=0,
        device="cuda" if require_cuda else "auto",
    )


def rollout(model: Any, env: EdgeResourceEnv, episodes: int = 2) -> dict[str, Any]:
    """Deterministic rollout using distinct episode seeds."""
    return evaluate_policy(
        lambda obs, _info, _rng: int(model.predict(obs, deterministic=True)[0]),
        env,
        [env.config.seed + 100_000 + index for index in range(episodes)],
    )


def evaluate_policy(policy: Any, env: EdgeResourceEnv, seeds: list[int],
                    include_objectives: bool = False) -> dict[str, Any]:
    """Evaluate a callable policy on explicit, held-out episode seeds."""
    results: list[dict[str, Any]] = []
    for episode_seed in seeds:
        obs, current_info = env.reset(seed=episode_seed)
        done = False
        ep_reward = 0.0
        steps = 0
        latencies: list[float] = []
        slo_hits = 0
        migrations = 0
        energies: list[float] = []
        migration_costs: list[float] = []
        while not done:
            action = policy(obs, current_info, env.np_random)
            obs, reward, terminated, truncated, info = env.step(int(action))
            current_info = info
            ep_reward += float(reward)
            steps += 1
            latencies.append(float(info["latency_ms"]))
            slo_hits += int(info["slo_hit"])
            migrations += int(info["action_type"] != "NOOP")
            if include_objectives:
                energies.append(float(info["energy_proxy"]))
                migration_costs.append(float(info["migration_cost"]))
            done = terminated or truncated
        episode = {
            "seed": episode_seed,
            "episode_reward": ep_reward,
            "steps": steps,
            "mean_latency_ms": float(sum(latencies) / len(latencies)),
            "slo_violation_rate": float(slo_hits / steps),
            "non_noop_actions": migrations,
            "last_info": info,
        }
        if include_objectives:
            episode["mean_energy_proxy"] = float(np.mean(energies))
            episode["total_migration_cost"] = float(sum(migration_costs))
        results.append(episode)
    summary = {
        "episodes": results,
        "mean_reward": float(np.mean([item["episode_reward"] for item in results])) if results else 0.0,
        "mean_latency_ms": float(np.mean([item["mean_latency_ms"] for item in results])) if results else 0.0,
        "mean_slo_violation_rate": float(np.mean([item["slo_violation_rate"] for item in results])) if results else 0.0,
        "mean_non_noop_actions": float(np.mean([item["non_noop_actions"] for item in results])) if results else 0.0,
    }
    if include_objectives:
        summary["mean_energy_proxy"] = float(np.mean([item["mean_energy_proxy"] for item in results])) if results else 0.0
        summary["mean_migration_cost"] = float(np.mean([item["total_migration_cost"] for item in results])) if results else 0.0
        summary["reward_std"] = float(np.std([item["episode_reward"] for item in results])) if results else 0.0
    return summary


def evaluate_comparators(env: EdgeResourceEnv, seeds: list[int],
                         include_objectives: bool = False) -> dict[str, dict[str, Any]]:
    """Evaluate fixed, transparent policy baselines on identical seeds."""
    from .env import ACTION_TYPES

    def no_op(_obs: np.ndarray, _info: dict, _rng: np.random.Generator) -> int:
        return ACTION_TYPES.index("NOOP")

    def reactive(obs: np.ndarray, _info: dict, _rng: np.random.Generator) -> int:
        feature_count = 8 + 2 * env.config.horizon
        cpus = obs[::feature_count][:env.config.num_nodes]
        return ACTION_TYPES.index("MIGRATE" if float(np.max(cpus)) >= 0.65 else "NOOP")

    def random_policy(_obs: np.ndarray, _info: dict, rng: np.random.Generator) -> int:
        return int(rng.integers(0, env.action_space.n))

    def forecast_only(obs: np.ndarray, _info: dict, _rng: np.random.Generator) -> int:
        features = 8 + 2 * env.config.horizon
        predicted = [float(obs[node * features + 8 + 2 * (env.config.horizon - 1)])
                     for node in range(env.config.num_nodes)]
        return ACTION_TYPES.index("MIGRATE" if max(predicted) >= 0.65 else "NOOP")

    return {
        name: evaluate_policy(policy, env, seeds, include_objectives)
        for name, policy in (("no_op", no_op), ("reactive_threshold", reactive),
                             ("forecast_only", forecast_only), ("random", random_policy))
    }
