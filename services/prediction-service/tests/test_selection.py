import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from prediction_app.data import NodeSample, SampleStore
from prediction_app.training import run_training


class SelectionTest(unittest.TestCase):
    def test_statistical_selection_uses_tune_then_evaluates_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = SampleStore(root / "samples.sqlite")
            start = datetime(2013, 8, 13, tzinfo=timezone.utc)
            for i in range(360):
                store.add(NodeSample("vm", start + timedelta(seconds=i), 0.2, 0.3, 1, 1))
            store.close()
            calls = []
            def predict(kind, history, horizons, period, **params):
                calls.append(params["order"])
                return [0.2 if params["order"] == (2, 0, 0) else 0.4] * len(horizons)
            with patch("prediction_app.training.statistical", side_effect=predict), \
                 patch("prediction_app.training._versions", return_value={}), \
                 patch("prediction_app.training._git_info", return_value={}):
                result = run_training(str(root / "samples.sqlite"), str(root / "models"),
                                      kind="arima", history_steps=12, horizons=(1, 2),
                                      source_label="unit fixture", tune=True)
            self.assertEqual(result["selection"]["selected"]["order"], (2, 0, 0))
            self.assertEqual(len(result["selection"]["candidates"]), 2)
            self.assertEqual(result["metrics"]["test"]["1"]["rmse"], 0)
            self.assertEqual(calls[-1], (2, 0, 0))


if __name__ == "__main__":
    unittest.main()

