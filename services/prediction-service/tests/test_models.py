import math
import tempfile
import unittest
from pathlib import Path

from prediction_app.data import NodeSample, SampleStore
from prediction_app.evaluation import metrics, observed_coverage, residual_radius
from prediction_app.models import neural_network, persistence, statistical
from prediction_app.benchmark import benchmark
from prediction_app.registry import Registry
from prediction_app.training import run_training

from test_data import event


class ModelTests(unittest.TestCase):
    def test_baselines_and_metrics(self):
        self.assertEqual(persistence((0.1, 0.2), (1, 2)), [0.2, 0.2])
        self.assertEqual(metrics([1, 2], [1, 1])["mae"], 0.5)
        self.assertIsNone(metrics([0, 1], [0, 1])["mape"])
        self.assertIsNone(metrics([1, 1], [1, 1])["r2"])
        for kind in ("arima", "ets"):
            with self.subTest(kind=kind):
                result = statistical(kind, tuple(0.3 + i * 0.001 for i in range(20)), (1, 2))
                self.assertEqual(len(result), 2)
                self.assertTrue(all(math.isfinite(v) for v in result))

    def test_interval_calibration(self):
        result = residual_radius([1, 2, 3, 4], [1, 1, 1, 1], 0.5)
        self.assertEqual(result["radius"], 2)
        self.assertEqual(observed_coverage([1, 2], [1, 1], 1), 1.0)

    def test_recurrent_and_temporal_shapes(self):
        import torch
        for kind in ("lstm", "gru", "temporal"):
            with self.subTest(kind=kind):
                network = neural_network(kind, history_steps=8, outputs=2)
                output = network(torch.ones((3, 8)))
                self.assertEqual(tuple(output.shape), (3, 2))
                self.assertTrue(torch.isfinite(output).all())

    def test_persistence_and_gru_training_artifacts(self):
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "samples.db"
            output = Path(temp) / "models"
            store = SampleStore(database)
            for second in range(360):
                # A non-constant series avoids a degenerate smoke test.
                sample = NodeSample.from_event(event(second, cpu=0.2 + (second % 30) / 100))
                store.add(sample)
            store.close()
            baseline = run_training(str(database), str(output), metric="cpu",
                                    kind="persistence", history_steps=8,
                                    horizons=(1, 2), epochs=3,
                                    source_label="synthetic-test-fixture")
            self.assertGreater(baseline["test_windows"], 0)
            self.assertIsNone(baseline["artifact_hash"])
            gru = run_training(str(database), str(output), metric="cpu", kind="gru",
                               history_steps=8, horizons=(1, 2), epochs=3,
                               source_label="synthetic-test-fixture")
            for kind in ("lstm", "temporal"):
                other = run_training(str(database), str(output), metric="cpu",
                                     kind=kind, history_steps=8,
                                     horizons=(1, 2), epochs=2,
                                     source_label="synthetic-test-fixture")
                self.assertEqual(len(other["artifact_hash"]), 64)
            self.assertEqual(len(gru["artifact_hash"]), 64)
            self.assertEqual(gru["hyperparameters"]["seed"], 42)
            registry = Registry(output / "registry.json")
            self.assertEqual(len(registry.records()), 4)
            registry.activate(gru["model_id"])
            self.assertEqual(registry.selected("cpu")["model_id"], gru["model_id"])
            network, scale = registry.load_network(gru)
            self.assertTrue(math.isfinite(scale.center))
            self.assertIsNotNone(network)
            report = benchmark(str(database), str(output / "registry.json"), repeats=3)
            self.assertEqual(report["model_id"], gru["model_id"])
            self.assertEqual(report["repeats"], 3)
            weights = output / gru["weights_file"]
            weights.write_bytes(weights.read_bytes() + b"bad")
            with self.assertRaisesRegex(ValueError, "hash"):
                registry.load_network(gru)


if __name__ == "__main__":
    unittest.main()
