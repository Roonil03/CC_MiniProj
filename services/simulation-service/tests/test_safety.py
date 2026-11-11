"""Hermetic safety-gate tests (stdlib only)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.safety import GateConfig, SafetyGate  # noqa: E402


def _req(**overrides):
    base = {
        "decision_id": "d-1",
        "action": {"type": "MIGRATE", "service": "p", "source": "edge-a1", "destination": "edge-b1"},
        "predicted": {"slo_violation_probability": 0.04, "prediction_confidence": 0.9},
        "dt_fidelity": 0.97,
        "destination_free_cpu": 2.0,
        "destination_healthy": True,
        "source_healthy": True,
    }
    base.update(overrides)
    return base


class TestSafetyGate(unittest.TestCase):
    def test_approve_healthy(self):
        self.assertTrue(SafetyGate(GateConfig()).evaluate(_req()).approved)

    def test_noop_always_safe(self):
        req = _req(dt_fidelity=0.0)
        req["action"] = {"type": "NOOP"}
        self.assertTrue(SafetyGate(GateConfig()).evaluate(req).approved)

    def test_reject_stale_twin(self):
        self.assertFalse(SafetyGate(GateConfig()).evaluate(_req(dt_fidelity=0.5)).approved)

    def test_reject_slo(self):
        req = _req()
        req["predicted"] = {"slo_violation_probability": 0.5, "prediction_confidence": 0.9}
        self.assertFalse(SafetyGate(GateConfig()).evaluate(req).approved)

    def test_storm_protection(self):
        gate = SafetyGate(GateConfig(max_migrations_per_minute=1))
        self.assertTrue(gate.evaluate(_req()).approved)
        gate.record_migration("edge-a1")
        self.assertFalse(gate.evaluate(_req()).approved)

    def test_unknown_action_and_out_of_range_evidence_fail_closed(self):
        gate = SafetyGate(GateConfig())
        self.assertFalse(gate.evaluate(_req(action={"type": "DELETE_NODE"})).approved)
        self.assertFalse(gate.evaluate(_req(action={})).approved)
        self.assertFalse(gate.evaluate(_req(dt_fidelity=1.1)).approved)
        req = _req()
        req["predicted"] = {"slo_violation_probability": 0.01, "prediction_confidence": 1.1}
        self.assertFalse(gate.evaluate(req).approved)


if __name__ == "__main__":
    unittest.main()
