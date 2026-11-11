import asyncio
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from prediction_app.data import NodeSample, SampleStore, read_events
from prediction_app.collector import export_events, record_message
from prediction_app.features import build_windows, split_windows


def event(second=0, *, node="edge-a1", cpu=0.5):
    return {
        "event_type": "NODE_METRIC_UPDATED", "node_id": node,
        "timestamp": (datetime(2026, 1, 1, tzinfo=timezone.utc)
                      + timedelta(seconds=second)).isoformat().replace("+00:00", "Z"),
        "metrics": {"cpu": cpu, "memory": 0.4,
                    "network_in": 12.0, "network_out": 3.0},
    }


class DataTests(unittest.TestCase):
    def test_contract_validation(self):
        self.assertEqual(NodeSample.from_event(event()).cpu, 0.5)
        for bad in (float("nan"), -0.1, 1.1, True, "0.5"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                NodeSample.from_event(event(cpu=bad))
        absent = event()
        del absent["metrics"]["memory"]
        with self.assertRaises(ValueError):
            NodeSample.from_event(absent)
        missing_zone = event()
        missing_zone["timestamp"] = "2026-01-01T00:00:00"
        with self.assertRaises(ValueError):
            NodeSample.from_event(missing_zone)

    def test_idempotent_recording_and_conflict(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "samples.db"
            store = SampleStore(path)
            sample = NodeSample.from_event(event())
            self.assertTrue(store.add(sample))
            self.assertFalse(store.add(sample))
            with self.assertRaisesRegex(ValueError, "conflicting"):
                store.add(NodeSample.from_event(event(cpu=0.8)))
            store.close()
            reopened = SampleStore(path)
            self.assertEqual(reopened.samples(), [sample])
            reopened.close()

    def test_nats_ack_only_after_recording(self):
        class Message:
            def __init__(self, payload):
                self.data = payload
                self.acknowledged = False
                self.terminated = False

            async def ack(self):
                self.acknowledged = True

            async def term(self):
                self.terminated = True

        with tempfile.TemporaryDirectory() as temp:
            store = SampleStore(Path(temp) / "samples.db")
            valid = Message(json.dumps(event()).encode())
            self.assertTrue(asyncio.run(record_message(store, valid)))
            self.assertTrue(valid.acknowledged)
            duplicate = Message(json.dumps(event()).encode())
            self.assertFalse(asyncio.run(record_message(store, duplicate)))
            self.assertTrue(duplicate.acknowledged)
            conflict = Message(json.dumps(event(cpu=0.9)).encode())
            self.assertFalse(asyncio.run(record_message(store, conflict)))
            self.assertFalse(conflict.acknowledged)
            self.assertTrue(conflict.terminated)
            invalid = Message(b"bad")
            self.assertFalse(asyncio.run(record_message(store, invalid)))
            self.assertTrue(invalid.terminated)
            store.close()

    def test_store_outage_requests_bounded_redelivery(self):
        class BrokenStore:
            def add(self, sample):
                raise sqlite3.OperationalError("local store unavailable")

        class Message:
            data = json.dumps(event()).encode()

            def __init__(self, deliveries):
                self.metadata = type("Metadata", (), {"num_delivered": deliveries})()
                self.action = None

            async def nak(self, delay):
                self.action = ("nak", delay)

            async def term(self):
                self.action = ("term",)

        first = Message(1)
        self.assertFalse(asyncio.run(record_message(BrokenStore(), first)))
        self.assertEqual(first.action, ("nak", 1))
        exhausted = Message(3)
        self.assertFalse(asyncio.run(record_message(BrokenStore(), exhausted)))
        self.assertEqual(exhausted.action, ("term",))

    def test_replay_line_diagnostics(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "events.jsonl"
            path.write_text(json.dumps(event()) + "\n{" , encoding="utf-8")
            with self.assertRaisesRegex(ValueError, ":2:"):
                list(read_events(path))

    def test_export_replays_and_reports_gaps(self):
        with tempfile.TemporaryDirectory() as temp:
            store = SampleStore(Path(temp) / "samples.db")
            store.add(NodeSample.from_event(event(0)))
            store.add(NodeSample.from_event(event(2)))
            output = Path(temp) / "processed.jsonl"
            manifest = export_events(store, str(output), source_label="test-fixture")
            self.assertEqual(manifest["sample_count"], 2)
            self.assertEqual(manifest["quality"]["edge-a1"]["missing_buckets_within_span"], 1)
            self.assertEqual(len(list(read_events(output))), 2)
            self.assertTrue(output.with_suffix(".jsonl.manifest.json").exists())
            store.close()

    def test_causal_windows_and_splits(self):
        samples = [NodeSample.from_event(event(s, cpu=s / 400))
                   for s in range(300)]
        samples += [NodeSample.from_event(event(s, node="edge-b1", cpu=0.2))
                    for s in range(300)]
        windows = build_windows(samples, "cpu", history_steps=6,
                                horizons_seconds=(1, 3))
        first = next(w for w in windows if w.node_id == "edge-a1")
        self.assertEqual(first.history, tuple(s / 400 for s in range(6)))
        self.assertEqual(first.targets, (6 / 400, 8 / 400))
        self.assertTrue(all(w.targets == (0.2, 0.2) for w in windows
                            if w.node_id == "edge-b1"))
        parts = split_windows(windows, horizons_seconds=(1, 3))
        self.assertTrue(all(parts.values()))
        first_val = min(w.origin for w in parts["validation"])
        self.assertTrue(all(w.origin + timedelta(seconds=3) < first_val
                            for w in parts["train"]))
        gap = samples[:5] + samples[6:300]
        missing_origin = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=6)
        self.assertFalse(any(w.origin == missing_origin for w in build_windows(
            gap, "cpu", history_steps=6, horizons_seconds=(1, 3))
                             if w.node_id == "edge-a1"))


if __name__ == "__main__":
    unittest.main()
