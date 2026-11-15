import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from prediction_app.bitbrains import import_trace
from prediction_app.data import SampleStore
from prediction_app.features import build_windows


class BitbrainsImportTest(unittest.TestCase):
    def test_units_missing_and_bounded_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "trace.zip"
            header = "Timestamp [ms];CPU cores;CPU capacity;CPU usage;CPU usage [%];Memory capacity;Memory usage;Disk read;Disk write;Network received;Network transmitted\n"
            rows = ("1376314846;1;100;20;20;1000;250;0;0;125;250\n"
                    "1376315146;1;100;20;20;0;250;0;0;125;250\n"
                    "1376315446000;1;100;20;20;1000;250;0;0;125;250\n")
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("fastStorage/1.csv", header + rows)
                z.writestr("fastStorage/2.csv", header + rows)
            db = root / "trace.sqlite"
            manifest = import_trace(str(archive), str(db), 1)
            self.assertEqual(manifest["rows_imported"], 2)
            self.assertEqual(manifest["rows_skipped"], 1)
            self.assertEqual(manifest["missing_buckets_by_vm"]["bitbrains-1"], 1)
            self.assertEqual(manifest["timestamp_representation_counts"], {"seconds": 1, "milliseconds": 1})
            self.assertEqual(json.loads(Path(str(db) + ".manifest.json").read_text())["cadence_seconds"], 300)
            store = SampleStore(db)
            try:
                samples = store.samples()
            finally:
                store.close()
            self.assertEqual(len(samples), 2)
            windows = build_windows(samples, "cpu", history_steps=1, horizons_seconds=(600,), period_seconds=300)
            self.assertEqual(windows[0].origin, samples[0].timestamp)
            self.assertEqual(windows[0].target_end, samples[1].timestamp)
            self.assertEqual((samples[0].cpu, samples[0].memory, samples[0].network_in, samples[0].network_out),
                             (0.2, 0.25, 1.0, 2.0))
            with self.assertRaises(ValueError):
                import_trace(str(archive), str(db), 1)


if __name__ == "__main__":
    unittest.main()

