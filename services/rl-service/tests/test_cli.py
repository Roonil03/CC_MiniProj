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
        json.dumps(result)


if __name__ == "__main__":
    unittest.main()
