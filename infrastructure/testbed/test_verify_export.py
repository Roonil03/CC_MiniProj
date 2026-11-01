import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from verify_export import verify


class ExportVerificationTests(unittest.TestCase):
    def test_crlf_export_can_be_normalized_only_to_manifest_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            trace = Path(temp) / "events.jsonl"
            events = [
                {"event_type": "NODE_METRIC_UPDATED", "node_id": "edge-a",
                 "timestamp": f"2026-11-01T00:00:0{second}Z",
                 "metrics": {"cpu": 0.2, "memory": 0.3,
                             "network_in": 1.0, "network_out": 2.0}}
                for second in (0, 2)
            ]
            payload = ("\n".join(json.dumps(event) for event in events) + "\n").encode()
            trace.write_bytes(payload.replace(b"\n", b"\r\n"))
            manifest = {"schema_version": 1, "event_type": "NODE_METRIC_UPDATED",
                        "source_label": "k3d-test", "sample_count": 2,
                        "node_ids": ["edge-a"], "period_seconds": 1,
                        "first_timestamp": "2026-11-01T00:00:00+00:00",
                        "last_timestamp": "2026-11-01T00:00:02+00:00",
                        "sha256": hashlib.sha256(payload).hexdigest(),
                        "quality": {"edge-a": {"observed_buckets": 2,
                                               "missing_buckets_within_span": 1}}}
            trace.with_suffix(".jsonl.manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                verify(trace)
            report = verify(trace, normalize_lf=True, expected_nodes=1,
                            min_duration_seconds=2)
            self.assertTrue(report["normalized_lf"])
            self.assertEqual(trace.read_bytes(), payload)
            self.assertEqual(report["quality"]["edge-a"]["missing_buckets_within_span"], 1)
            with self.assertRaisesRegex(ValueError, "missing-bucket fraction"):
                verify(trace, max_missing_fraction=0.25)
            verify(trace, max_missing_fraction=0.34)
            with self.assertRaisesRegex(ValueError, "expected 2 nodes"):
                verify(trace, expected_nodes=2)
            with self.assertRaisesRegex(ValueError, "duration"):
                verify(trace, min_duration_seconds=3)
            trace.write_bytes(payload.replace(b"0.2", b"0.4"))
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                verify(trace, normalize_lf=True)


if __name__ == "__main__":
    unittest.main()
