"""Hermetic counterfactual-simulator tests (stdlib only)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.simulator import evaluate_candidates, migration_cost, migration_duration, simulate_action  # noqa: E402
from app.twin import TwinState  # noqa: E402


def _twin() -> TwinState:
    twin = TwinState()
    twin.apply_telemetry("edge-a1", 0.70, 0.55)
    twin.apply_telemetry("edge-b1", 0.30, 0.35)
    return twin


class TestSimulator(unittest.TestCase):
    def test_noop_is_baseline(self):
        res = simulate_action(_twin(), {"type": "NOOP", "source": "edge-a1"})
        self.assertTrue(res.feasible)
        self.assertEqual(res.migration_cost, 0.0)

    def test_migration_not_free(self):
        res = simulate_action(
            _twin(),
            {"type": "MIGRATE", "service": "p", "source": "edge-a1", "destination": "edge-b1"},
        )
        self.assertTrue(res.feasible)
        self.assertGreater(res.migration_cost, 0.0)
        self.assertGreater(res.migration_duration_s, 0.0)

    def test_unknown_destination_infeasible(self):
        res = simulate_action(
            _twin(),
            {"type": "MIGRATE", "service": "p", "source": "edge-a1", "destination": "edge-zz"},
        )
        self.assertFalse(res.feasible)

    def test_duration_model(self):
        self.assertAlmostEqual(migration_duration(100.0, 100.0, 2.0), 10.0)
        self.assertEqual(migration_duration(100.0, 0.0, 2.0), -1.0)
        self.assertGreater(migration_cost(), 0.0)

    def test_evaluate_candidates(self):
        twin = _twin()
        out = evaluate_candidates(
            twin,
            [
                {"type": "NOOP", "source": "edge-a1"},
                {"type": "SCALE", "service": "p", "source": "edge-a1", "replicas": 4},
            ],
        )
        self.assertEqual(len(out), 2)
        self.assertTrue(all(r.feasible for r in out))


if __name__ == "__main__":
    unittest.main()
