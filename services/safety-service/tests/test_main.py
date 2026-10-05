"""Hermetic safety-service API tests (stdlib + fastapi only)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "simulation-service"))

try:
    from safety_app.main import ValidateRequest, healthz, validate
except ImportError as exc:
    raise unittest.SkipTest(f"fastapi unavailable: {exc}")


class TestSafetyAPI(unittest.TestCase):
    def test_healthz(self):
        self.assertEqual(healthz()["status"], "ok")

    def test_validate_approves_healthy(self):
        out = validate(ValidateRequest(
            action={"type": "MIGRATE", "service": "p", "source": "edge-a1", "destination": "edge-b1"},
            predicted={"slo_violation_probability": 0.04, "prediction_confidence": 0.9},
            dt_fidelity=0.97,
            destination_free_cpu=2.0,
            destination_healthy=True,
            source_healthy=True,
        ))
        self.assertTrue(out["approved"])

    def test_validate_rejects_stale(self):
        out = validate(ValidateRequest(
            action={"type": "MIGRATE", "service": "p", "source": "edge-a1", "destination": "edge-b1"},
            predicted={"slo_violation_probability": 0.04, "prediction_confidence": 0.9},
            dt_fidelity=0.2,
            destination_free_cpu=2.0,
            destination_healthy=True,
            source_healthy=True,
        ))
        self.assertFalse(out["approved"])


if __name__ == "__main__":
    unittest.main()
