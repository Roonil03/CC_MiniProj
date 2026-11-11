import json
import logging
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from prediction_app.scripts.run_all_models import (
    EventRecorder,
    format_duration,
    new_state,
    package_run,
    run_job,
    write_estimate,
)


class RunnerTests(unittest.TestCase):
    def test_failed_job_can_retry_on_later_invocation(self):
        config = {"models": ["persistence"], "metrics": ["cpu"], "epochs": 1}
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)
            state = new_state(config)
            state["jobs"]["persistence__cpu"].update(status="failed", attempts=2)
            recorder = EventRecorder(run_dir, logging.getLogger("runner-resume-test"))
            args = Namespace(max_attempts=1, retry_delay_seconds=0, fail_fast=False,
                             db="unused", history_steps=8, horizons=[1], period_seconds=1,
                             seed=42, epochs=1, source_label="fixture")
            with patch("prediction_app.scripts.run_all_models.run_training", return_value={"model_id": "fixture", "metrics": {}}):
                run_job(args, run_dir, state, recorder, logging.getLogger("runner-resume-test"), "persistence__cpu")
            self.assertEqual(state["jobs"]["persistence__cpu"]["attempts"], 3)
            self.assertEqual(state["jobs"]["persistence__cpu"]["status"], "completed")

    def test_state_estimate_and_package_are_restart_safe(self):
        config = {
            "models": ["persistence", "gru"],
            "metrics": ["cpu"],
            "history_steps": 8,
            "horizons": [1, 2],
            "period_seconds": 1,
            "seed": 42,
            "epochs": 3,
            "source_label": "fixture",
            "db": "/tmp/fixture.sqlite",
        }
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)
            logger = logging.getLogger("runner-test")
            recorder = EventRecorder(run_dir, logger)
            recorder.emit("test_event", value=1)
            state = new_state(config)
            state["jobs"]["persistence__cpu"].update({
                "status": "completed", "duration_seconds": 1.5,
                "result_file": str(run_dir / "result.json"),
            })
            (run_dir / "result.json").write_text(json.dumps({"kind": "persistence"}), encoding="utf-8")
            estimate = write_estimate(run_dir, state)
            self.assertGreaterEqual(estimate["estimated_total_seconds"], 1.5)
            self.assertEqual(format_duration(65), "1m 5s")
            archive = package_run(run_dir)
            self.assertTrue(archive.exists())
            self.assertGreater(archive.stat().st_size, 0)
            self.assertTrue((run_dir / "events.jsonl").exists())
            self.assertTrue((run_dir / "timeline.json").exists())


if __name__ == "__main__":
    unittest.main()
