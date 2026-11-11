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
    def test_gymnasium_checker(self):
        from gymnasium.utils.env_checker import check_env
        check_env(EdgeResourceEnv(EnvConfig(num_nodes=2, max_steps=3)), skip_render_check=True)

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
        with self.assertRaises(ValueError):
            env.step(999)

    def test_seed_controls_full_rollout_and_state_is_bounded(self):
        first = EdgeResourceEnv(EnvConfig(num_nodes=4, seed=9, max_steps=3))
        second = EdgeResourceEnv(EnvConfig(num_nodes=4, seed=9, max_steps=3))
        obs_a, _ = first.reset(seed=13)
        obs_b, _ = second.reset(seed=13)
        self.assertTrue((obs_a == obs_b).all())
        for action in (1, 0, 2):
            out_a = first.step(action)
            out_b = second.step(action)
            self.assertTrue((out_a[0] == out_b[0]).all())
            self.assertEqual(out_a[1:], out_b[1:])
            self.assertTrue(((out_a[0] >= 0) & (out_a[0] <= 1)).all())
        self.assertTrue(out_a[3])

    def test_domain_randomization_is_opt_in_and_seeded(self):
        fixed = EdgeResourceEnv(EnvConfig(seed=5))
        _, fixed_info = fixed.reset(seed=17)
        self.assertEqual(fixed_info["dynamics"]["drift_bias"], 0.02)

        config = EnvConfig(seed=5, domain_randomization=True)
        a, info_a = EdgeResourceEnv(config).reset(seed=17)
        b, info_b = EdgeResourceEnv(config).reset(seed=17)
        self.assertTrue((a == b).all())
        self.assertEqual(info_a, info_b)
        self.assertNotEqual(info_a["dynamics"]["drift_bias"], 0.02)

    def test_invalid_config_rejected(self):
        with self.assertRaises(ValueError):
            EnvConfig(num_nodes=0)
        with self.assertRaises(ValueError):
            EnvConfig(reward_weights={"slo": -1.0})

    def test_describe(self):
        d = EdgeResourceEnv(EnvConfig()).describe()
        self.assertEqual(d["algorithm"], "PPO (single-agent baseline)")
        self.assertIn("MIGRATE", d["actions"])


if __name__ == "__main__":
    unittest.main()
