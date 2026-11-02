"""Focused tests for the demo's read-only forecast confidence path."""

from datetime import datetime, timedelta, timezone
import io
import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(__file__))

from demo import TwinState, _ForecastTracker, _forecast_snapshot, main  # noqa: E402


class TestForecastSnapshot(unittest.TestCase):
    def setUp(self):
        self.twin = TwinState(stale_after_seconds=120)
        self.tracker = _ForecastTracker(["persistence"], history=13)
        self.now = datetime.now(timezone.utc)

    def sample(self, cpu, timestamp):
        self.twin.apply_telemetry("edge-a", cpu, 0.3, timestamp=timestamp)
        return _forecast_snapshot(self.twin, self.tracker)

    def test_confidence_starts_at_zero_and_scores_a_realized_forecast(self):
        _, confidence = self.sample(0.2, self.now)
        self.assertEqual(confidence, 0.0)

        _, confidence = self.sample(0.3, self.now + timedelta(seconds=5))
        self.assertAlmostEqual(confidence, 0.9)

    def test_repeated_timestamp_does_not_add_or_score_a_sample(self):
        self.sample(0.2, self.now)
        self.sample(0.8, self.now)
        self.assertEqual(self.tracker.samples("edge-a"), 1)

        _, confidence = self.sample(0.3, self.now + timedelta(seconds=5))
        self.assertAlmostEqual(confidence, 0.9)

    def test_stale_snapshot_forces_confidence_to_zero(self):
        self.sample(0.2, self.now - timedelta(minutes=3))
        self.twin.refresh_staleness()
        _, confidence = _forecast_snapshot(self.twin, self.tracker)
        self.assertEqual(confidence, 0.0)

    def test_one_shot_json_fails_closed_without_a_realized_forecast(self):
        output = io.StringIO()
        with patch.object(sys, "argv", ["demo.py", "--synthetic", "--json", "--once"]):
            with patch("sys.stdout", output):
                self.assertEqual(main(), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["prediction_confidence"], 0.0)
        self.assertIn("no realized forecast", result["prediction_confidence_note"])
        noop = next(
            candidate for candidate in result["candidates"]
            if candidate["action"] == "Keep current placement"
        )
        non_noops = [
            candidate for candidate in result["candidates"]
            if candidate["action"] != "Keep current placement"
        ]
        self.assertTrue(noop["safety"]["approved"])
        self.assertTrue(all(not candidate["safety"]["approved"] for candidate in non_noops))


if __name__ == "__main__":
    unittest.main()
