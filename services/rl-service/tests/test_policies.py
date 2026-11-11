"""Hermetic policy-registry tests (stdlib only; no torch/SB3)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rl_app.policies import git_sha, policy_record  # noqa: E402
from rl_app.env import EdgeResourceEnv, EnvConfig  # noqa: E402
from rl_app.ppo import evaluate_comparators  # noqa: E402


class TestPolicies(unittest.TestCase):
    def test_record_schema(self):
        rec = policy_record("ppo-test", "v0.1.0", "synthetic", {"gamma": 0.99}, {"reward": 1.0})
        for key in ("model_id", "version", "training_dataset", "training_timestamp",
                    "hyperparameters", "metrics", "git_commit", "artifact_hash"):
            self.assertIn(key, rec)

    def test_git_sha_is_str(self):
        self.assertIsInstance(git_sha(), str)

    def test_comparators_use_same_explicit_episode_seeds(self):
        seeds = [1001, 1002]
        results = evaluate_comparators(EdgeResourceEnv(EnvConfig(max_steps=3)), seeds)
        self.assertEqual(set(results), {"no_op", "reactive_threshold", "forecast_only", "random"})
        for result in results.values():
            self.assertEqual([episode["seed"] for episode in result["episodes"]], seeds)
            self.assertIn("mean_slo_violation_rate", result)

    def test_multi_objective_reports_separate_proxies(self):
        result = evaluate_comparators(EdgeResourceEnv(EnvConfig(max_steps=2)), [101, 102], True)
        for comparator in result.values():
            self.assertIn("mean_energy_proxy", comparator)
            self.assertIn("mean_migration_cost", comparator)
            self.assertIn("reward_std", comparator)


if __name__ == "__main__":
    unittest.main()
