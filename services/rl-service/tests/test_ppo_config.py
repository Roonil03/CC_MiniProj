import unittest

from rl_app.ppo import PPOConfig


class PPOConfigTests(unittest.TestCase):
    def test_defaults_are_valid(self):
        self.assertEqual(PPOConfig().as_dict()["algorithm"], "PPO")

    def test_rejects_invalid_values(self):
        for options in ({"gamma": float("nan")}, {"gamma": 1.1},
                        {"learning_rate": float("inf")}, {"learning_rate": 0},
                        {"n_steps": 1}, {"batch_size": 1},
                        {"n_steps": 4, "batch_size": 8}, {"n_epochs": True},
                        {"total_timesteps": 0}, {"seed": -1}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                PPOConfig(**options)
