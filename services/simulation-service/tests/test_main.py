import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from app.main import SimulateRequest, simulate
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


if __name__ == "__main__":
    unittest.main()
