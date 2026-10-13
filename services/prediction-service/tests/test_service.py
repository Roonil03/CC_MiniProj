import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from prediction_app.data import NodeSample, SampleStore
from prediction_app.registry import Registry
from prediction_app.service import create_app
from prediction_app.training import run_training

from test_data import event


class ServiceTests(unittest.TestCase):
    def test_invalid_freshness_limit_is_rejected(self):
        with patch.dict(os.environ, {"PREDICTION_MAX_AGE_SECONDS": "nan"}):
            with self.assertRaises(ValueError):
                create_app()

    def test_health_auth_forecasts_and_staleness(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "samples.db"
            registry_path = Path(temp) / "models" / "registry.json"
            current = [datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=359)]
            app = create_app(db_path=db, registry_path=registry_path, now=lambda: current[0])
            with patch.dict(os.environ, {"DT_RAM_SERVICE_TOKEN": "test-secret"}):
                client = TestClient(app)
                self.assertEqual(client.get("/healthz").status_code, 200)
                self.assertEqual(client.get("/readyz").status_code, 503)
                self.assertEqual(client.get("/models").status_code, 401)
                self.assertEqual(client.get("/predictions", headers={"x-service-token": "test-secret"}).status_code, 503)
                store = SampleStore(db)
                for second in range(360):
                    store.add(NodeSample.from_event(event(second, cpu=0.3 + (second % 30) / 100)))
                store.close()
                baseline = run_training(str(db), str(registry_path.parent), kind="persistence",
                                        history_steps=8, horizons=(1, 2),
                                        source_label="synthetic-test-fixture")
                Registry(registry_path).activate(baseline["model_id"])
                headers = {"x-service-token": "test-secret"}
                self.assertEqual(client.get("/readyz").status_code, 200)
                models = client.get("/models", headers=headers)
                self.assertEqual(models.status_code, 200)
                self.assertTrue(models.json()["models"][0]["active"])
                response = client.get("/predictions?node_id=edge-a1&metric=cpu", headers=headers)
                self.assertEqual(response.status_code, 200)
                predictions = response.json()["predictions"]
                self.assertEqual([p["horizon_seconds"] for p in predictions], [1, 2])
                self.assertTrue(all(p["unit"] == "fraction" for p in predictions))
                self.assertTrue(all(p["value"] == 0.59 for p in predictions))
                self.assertTrue(all(p["model_id"] == baseline["model_id"] for p in predictions))
                self.assertEqual(client.get("/predictions?metric=queue", headers=headers).status_code, 422)
                current[0] += timedelta(seconds=10)
                self.assertEqual(client.get("/readyz").status_code, 503)
                stale = client.get("/predictions", headers=headers)
                self.assertEqual(stale.status_code, 503)
                self.assertIn("stale", str(stale.json()))


if __name__ == "__main__":
    unittest.main()
