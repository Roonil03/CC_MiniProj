import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))

try:
    from cli import workflow
except (ImportError, ModuleNotFoundError) as exc:
    raise unittest.SkipTest(f"RL runtime unavailable: {exc}")


class CliWorkflowTests(unittest.TestCase):
    def test_default_workflow_is_simulation_only(self):
        result = workflow(seed=42, train=False, timesteps=1, episodes=1)
        self.assertEqual(result["seed"], 42)
        self.assertFalse(result["actuation"]["allowed"])
        self.assertEqual(len(result["simulations"]), 4)
        self.assertNotIn("ppo", result)
        self.assertEqual(result["evaluation"]["split"], "held_out_episode_seeds")
        self.assertEqual(result["evaluation"]["seeds"], [100042])
        self.assertIn("reactive_threshold", result["evaluation"]["comparators"])
        json.dumps(result)

    def test_workflow_rejects_invalid_episode_and_seed_values(self):
        with self.assertRaises(ValueError):
            workflow(seed=42, train=False, timesteps=1, episodes=0)
        with self.assertRaises(ValueError):
            workflow(seed=-1, train=False, timesteps=1, episodes=1)


if __name__ == "__main__":
    unittest.main()
