"""Hermetic safety-service API tests (stdlib + fastapi only)."""
import os
import sys
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "simulation-service"))

try:
    from safety_app.main import ApproveRequest, ValidateRequest, approve, healthz, policies, validate
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

    def test_missing_confidence_is_rejected(self):
        out = validate(ValidateRequest(
            action={"type": "MIGRATE", "source": "edge-a1", "destination": "edge-b1"},
            predicted={"slo_violation_probability": 0.04},
            dt_fidelity=0.97,
            destination_free_cpu=2.0,
            destination_healthy=True,
            source_healthy=True,
        ))
        self.assertFalse(out["approved"])

    def test_policy_metadata_is_fail_closed(self):
        result = policies()
        self.assertEqual(result["execution_modes"], ["shadow"])
        self.assertFalse(result["physical_actuation"])


class SafetyApprovalTests(unittest.IsolatedAsyncioTestCase):
    async def test_shadow_approval_publishes_dry_run_event(self):
        request = ApproveRequest(
            decision_id="shadow-1",
            policy_version="policy-v1",
            execution_mode="shadow",
            action={"type": "SCALE", "service": "processor", "replicas": 2},
            predicted={"slo_violation_probability": 0.04, "prediction_confidence": 0.9},
            dt_fidelity=0.97,
            destination_free_cpu=2.0,
            destination_healthy=True,
            source_healthy=True,
        )
        with patch("safety_app.main._publish", new=AsyncMock(return_value={"stream": "DT_DECISIONS", "sequence": 1})) as publish:
            result = await approve(request)
        self.assertTrue(result["approved"])
        self.assertTrue(result["event"]["dry_run"])
        publish.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
