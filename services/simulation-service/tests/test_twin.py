"""Hermetic twin-state tests (stdlib only)."""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.twin import TwinState, WorkloadState, autonomy_level, fidelity_score  # noqa: E402


class TestTwinSync(unittest.TestCase):
    def test_apply_valid(self):
        twin = TwinState()
        node = twin.apply_telemetry("edge-a1", 0.5, 0.25, network_in_mbps=10.0)
        self.assertEqual(node.node_id, "edge-a1")
        self.assertAlmostEqual(node.cpu_used, 4.0)
        self.assertFalse(node.stale)

    def test_reject_empty_node(self):
        with self.assertRaises(ValueError):
            TwinState().apply_telemetry("", 0.5, 0.5)

    def test_reject_out_of_range(self):
        with self.assertRaises(ValueError):
            TwinState().apply_telemetry("edge-a1", 2.0, 0.1)

    def test_stale_flag(self):
        twin = TwinState(stale_after_seconds=5.0)
        old = datetime.now(timezone.utc) - timedelta(hours=1)
        node = twin.apply_telemetry("edge-old", 0.5, 0.5, timestamp=old)
        self.assertTrue(node.stale)

    def test_workload_requires_service(self):
        with self.assertRaises(ValueError):
            TwinState().upsert_workload(WorkloadState(service_id=""))


class TestFidelity(unittest.TestCase):
    def test_perfect_match_is_one(self):
        twin = TwinState()
        twin.apply_telemetry("edge-a1", 0.5, 0.5, network_in_mbps=100.0, network_out_mbps=100.0)
        node = twin.get_node("edge-a1")
        assert node is not None
        self.assertAlmostEqual(
            fidelity_score(0.5, 0.5, 100.0, 100.0, node), 1.0, places=9
        )

    def test_autonomy_bands(self):
        self.assertEqual(autonomy_level(0.97, False), "autonomous")
        self.assertEqual(autonomy_level(0.92, False), "restricted")
        self.assertEqual(autonomy_level(0.85, False), "simulation-only")
        self.assertEqual(autonomy_level(0.50, False), "disabled")
        self.assertEqual(autonomy_level(0.99, True), "disabled-stale")


if __name__ == "__main__":
    unittest.main()
