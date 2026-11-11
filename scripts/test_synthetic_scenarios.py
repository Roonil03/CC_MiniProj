import unittest

from run_synthetic_scenarios import exercise


class SyntheticScenarioTests(unittest.TestCase):
    def test_unsafe_placement_and_zero_bandwidth_rejected(self):
        self.assertFalse(exercise("burst_memory", 42)["metrics"]["feasible"])
        self.assertFalse(exercise("degraded_migration", 42)["metrics"]["zero_bandwidth_feasible"])

    def test_replay_and_confidence_collapse(self):
        self.assertTrue(exercise("telemetry_replay", 42)["metrics"]["conflict_rejected"])
        self.assertFalse(exercise("forecast_drift", 42)["metrics"]["approved"])


if __name__ == "__main__":
    unittest.main()
