"""Hermetic safety-service API tests (stdlib + fastapi only)."""
import os
import sys
import asyncio
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "simulation-service"))

try:
    from safety_app.main import ApproveRequest, ValidateRequest, approve, gate, _pending_migrations, healthz, policies, validate
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

    def test_validate_rejects_malformed_action_even_if_prediction_is_safe(self):
        out = validate(ValidateRequest(
            action={"type": "MIGRATE", "service": "p", "destination": "edge-b1"},
            predicted={"slo_violation_probability": 0.01, "prediction_confidence": 0.99},
            dt_fidelity=0.99, destination_free_cpu=2, destination_healthy=True, source_healthy=True,
        ))
        self.assertFalse(out["approved"])
        self.assertIn("source is required", out["reasons"][-1])

    def test_validate_rejects_missing_action_type(self):
        out = validate(ValidateRequest(action={}, predicted={}))
        self.assertFalse(out["approved"])
        self.assertIn("action type is required", out["reasons"])


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

    async def test_duplicate_decision_returns_prior_result_without_republish(self):
        request = ApproveRequest(
            decision_id="idempotent-approval-1", policy_version="policy-v1",
            action={"type": "SCALE", "service": "worker", "replicas": 2},
            predicted={"slo_violation_probability": 0.01, "prediction_confidence": 0.99},
            dt_fidelity=0.99, source_healthy=True,
        )
        with patch("safety_app.main._publish", new=AsyncMock(return_value={"stream": "DT_DECISIONS", "sequence": 1})) as publish:
            first = await approve(request)
            again = await approve(request)
        self.assertEqual(first, again)
        publish.assert_awaited_once()

    async def test_concurrent_migrations_reserve_single_remaining_slot(self):
        original_limit = gate.config.max_migrations_per_minute
        gate.config.max_migrations_per_minute = 1
        _pending_migrations.clear()
        started, release = asyncio.Event(), asyncio.Event()

        async def delayed_publish(_event):
            started.set()
            await release.wait()
            return {"stream": "DT_DECISIONS", "sequence": 10}

        request = ApproveRequest(
            decision_id="reserve-1", policy_version="policy-v1", action={"type": "MIGRATE", "service": "worker", "source": "reserve-src", "destination": "reserve-dst"},
            predicted={"slo_violation_probability": 0.01, "prediction_confidence": 0.99}, dt_fidelity=0.99,
            destination_free_cpu=4, destination_healthy=True, source_healthy=True,
        )
        try:
            with patch("safety_app.main._publish", new=delayed_publish):
                first = asyncio.create_task(approve(request))
                await started.wait()
                competing = request.model_copy(update={"decision_id": "reserve-2", "action": {**request.action, "source": "other-src"}})
                with self.assertRaises(Exception) as raised:
                    await approve(competing)
                self.assertEqual(getattr(raised.exception, "status_code", None), 422)
                release.set()
                self.assertTrue((await first)["approved"])
        finally:
            release.set()
            _pending_migrations.clear()
            gate.config.max_migrations_per_minute = original_limit


if __name__ == "__main__":
    unittest.main()
