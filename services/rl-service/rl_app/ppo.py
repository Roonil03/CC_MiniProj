"""Single-agent PPO baseline (Member-4).

PPO first per AGENTS.md: stable, reproducible, discrete/mixed-action
friendly. MARL only after this baseline is reliable. Training target is
always the simulator/twin — never physical infrastructure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
    )


def rollout(model: Any, env: EdgeResourceEnv, episodes: int = 2) -> list[dict[str, Any]]:
    """Deterministic policy rollout for evaluation (no training here)."""
    results: list[dict[str, Any]] = []
    for _ in range(episodes):
        obs, _ = env.reset(seed=env.config.seed)
        done = False
        ep_reward = 0.0
        steps = 0
        while not done:
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, info = env.step(int(action))
            ep_reward += float(reward)
            steps += 1
            done = terminated or truncated
        results.append({"episodes_reward": ep_reward, "steps": steps, "last_info": info})
    return results
