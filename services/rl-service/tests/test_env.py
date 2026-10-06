"""Hermetic RL-environment tests (stdlib + gymnasium only; no torch/SB3)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from rl_app.env import ACTION_TYPES, EdgeResourceEnv, EnvConfig
except ImportError as exc:  # gymnasium missing -> skip whole module
    raise unittest.SkipTest(f"gymnasium unavailable: {exc}")


class TestEdgeResourceEnv(unittest.TestCase):
    def test_reset_deterministic(self):
        a, _ = EdgeResourceEnv(EnvConfig(seed=7)).reset(seed=7)
        b, _ = EdgeResourceEnv(EnvConfig(seed=7)).reset(seed=7)
        self.assertTrue((a == b).all())

    def test_step_contract(self):
        env = EdgeResourceEnv(EnvConfig(seed=7, max_steps=4))
        env.reset(seed=7)
        _, reward, terminated, truncated, info = env.step(0)
        self.assertIsInstance(reward, float)
        self.assertIn(info["action_type"], ACTION_TYPES)
        self.assertFalse(terminated)

    def test_invalid_action_rejected(self):
        env = EdgeResourceEnv(EnvConfig(seed=7))
        env.reset(seed=7)
        with self.assertRaises(AssertionError):
            env.step(999)

    def test_describe(self):
        d = EdgeResourceEnv(EnvConfig()).describe()
        self.assertEqual(d["algorithm"], "PPO (single-agent baseline)")
        self.assertIn("MIGRATE", d["actions"])


if __name__ == "__main__":
    unittest.main()
