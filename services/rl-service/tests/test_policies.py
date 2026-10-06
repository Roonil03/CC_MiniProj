"""Hermetic policy-registry tests (stdlib only; no torch/SB3)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rl_app.policies import git_sha, policy_record  # noqa: E402


class TestPolicies(unittest.TestCase):
    def test_record_schema(self):
        rec = policy_record("ppo-test", "v0.1.0", "synthetic", {"gamma": 0.99}, {"reward": 1.0})
        for key in ("model_id", "version", "training_dataset", "training_timestamp",
                    "hyperparameters", "metrics", "git_commit", "artifact_hash"):
            self.assertIn(key, rec)

    def test_git_sha_is_str(self):
        self.assertIsInstance(git_sha(), str)


if __name__ == "__main__":
    unittest.main()
