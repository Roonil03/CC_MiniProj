import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from app.main import SimulateRequest, simulate
    from pydantic import ValidationError
except ImportError as exc:
    raise unittest.SkipTest(f"fastapi unavailable: {exc}")


class SimulationContractTests(unittest.TestCase):
    def test_go_twin_node_shape_is_accepted(self):
        response = simulate(SimulateRequest(
            nodes=[{
                "node_id": "edge-b1",
                "cpu_total": 8.0,
                "cpu_used": 1.6,
                "memory_total_mb": 16384.0,
                "memory_used_mb": 4096.0,
                "health": "healthy",
                "network_in_mbps": 10.0,
                "network_out_mbps": 5.0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "stale": False,
            }],
            candidates=[{"type": "PLACE", "destination": "edge-b1"}],
            predicted={"prediction_confidence": 0.9},
            dt_fidelity=0.97,
        ))
        result = response["results"][0]
        self.assertTrue(result["feasible"])
        self.assertIn("predicted_mem", result)
        self.assertIn("migration_duration_s", result)
        self.assertEqual(result["dt_fidelity"], 0.97)

    def test_stale_go_twin_state_is_not_simulated_as_feasible(self):
        response = simulate(SimulateRequest(
            nodes=[{
                "node_id": "edge-b1", "cpu_total": 8, "cpu_used": 1,
                "memory_total_mb": 1000, "memory_used_mb": 100,
                "network_in_mbps": 0, "network_out_mbps": 0,
                "health": "healthy", "timestamp": (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat(),
            }],
            candidates=[{"type": "PLACE", "destination": "edge-b1"}],
        ))
        self.assertFalse(response["results"][0]["feasible"])
        self.assertIn("stale", response["results"][0]["notes"][0])

    def test_rejects_invalid_simulation_contract_values(self):
        with self.assertRaises(ValidationError):
            SimulateRequest(nodes=[{"node_id": "edge-b1", "cpu": 1.2}])
        with self.assertRaises(ValidationError):
            SimulateRequest(dt_fidelity=1.1)
        with self.assertRaises(ValidationError):
            SimulateRequest(candidates=[{"type": "DELETE_NODE"}])
        with self.assertRaises(ValidationError):
            SimulateRequest(nodes=[{"node_id": "edge-b1", "memory": 0.2}])
        with self.assertRaises(ValidationError):
            SimulateRequest(candidates=[{"type": "MIGRATE", "destination": "edge-b1"}])
        with self.assertRaises(ValidationError):
            SimulateRequest(candidates=[{"type": "MIGRATE", "source": "edge-a1", "destination": "edge-b1", "bandwidth_mbps": 0}])

    def test_raw_capacity_is_not_misread_as_low_utilization(self):
        response = simulate(SimulateRequest(
            nodes=[{"node_id": "edge-b1", "cpu_total": 8, "cpu_used": 7.8,
                    "memory_total_mb": 16384, "memory_used_mb": 1000,
                    "network_in_mbps": 0, "network_out_mbps": 0,
                    "timestamp": datetime.now(timezone.utc).isoformat()}],
            candidates=[{"type": "PLACE", "destination": "edge-b1"}], service_cpu=0.5,
        ))
        self.assertFalse(response["results"][0]["feasible"])

    def test_fresh_aligned_forecast_changes_placement(self):
        node = {"node_id": "edge-b1", "cpu_total": 8, "cpu_used": 1,
                "memory_total_mb": 16384, "memory_used_mb": 1000,
                "network_in_mbps": 0, "network_out_mbps": 0,
                "timestamp": datetime.now(timezone.utc).isoformat()}
        candidate = {"type": "PLACE", "destination": "edge-b1"}
        baseline = simulate(SimulateRequest(nodes=[node], candidates=[candidate]))
        forecast = {"node_id": "edge-b1", "metric": "cpu", "value": 0.98,
                    "horizon_seconds": 5, "timestamp": datetime.now(timezone.utc).isoformat(),
                    "source": "fixture-model-v1"}
        changed = simulate(SimulateRequest(nodes=[node], candidates=[candidate],
                                           predicted={"forecasts": [forecast]}))
        self.assertTrue(baseline["results"][0]["feasible"])
        self.assertFalse(changed["results"][0]["feasible"])


if __name__ == "__main__":
    unittest.main()
