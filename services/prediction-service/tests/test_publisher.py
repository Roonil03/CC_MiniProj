import asyncio
import json
import unittest

from prediction_app.publisher import EVENT_TYPE, SUBJECT, event_from_response, publish_event


class PublisherTests(unittest.TestCase):
    def test_proposal_event_and_ack(self):
        class JetStream:
            def __init__(self):
                self.subject = self.payload = None

            async def publish(self, subject, payload):
                self.subject, self.payload = subject, payload
                return {"ack": True}

        event = event_from_response({"status": "degraded", "predictions": [
            {"node_id": "edge-a1", "metric": "cpu", "value": 0.4,
             "confidence": None}]})
        transport = JetStream()
        self.assertEqual(asyncio.run(publish_event(transport, event)), {"ack": True})
        self.assertEqual(transport.subject, SUBJECT)
        payload = json.loads(transport.payload)
        self.assertEqual(payload["event_type"], EVENT_TYPE)
        self.assertIsNone(payload["predictions"][0]["confidence"])

    def test_empty_event_rejected(self):
        with self.assertRaises(ValueError):
            event_from_response({"predictions": []})


if __name__ == "__main__":
    unittest.main()
