"""Opt-in prediction event emission; shared stream provisioning is pending."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime, timezone
from urllib.request import Request, urlopen

SUBJECT = "dt.predictions.node_forecast"
EVENT_TYPE = "NODE_FORECAST_UPDATED"


def event_from_response(response: dict) -> dict:
    forecasts = response.get("predictions")
    if not isinstance(forecasts, list) or not forecasts:
        raise ValueError("no forecasts to publish")
    return {"event_type": EVENT_TYPE,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "status": response.get("status", "degraded"),
            "predictions": forecasts}


async def publish_event(jetstream, event: dict):
    if event.get("event_type") != EVENT_TYPE or not event.get("predictions"):
        raise ValueError("invalid forecast event")
    payload = json.dumps(event, allow_nan=False).encode("utf-8")
    return await jetstream.publish(SUBJECT, payload)


def _fetch(url: str, token: str | None) -> dict:
    headers = {"accept": "application/json"}
    if token:
        headers["x-service-token"] = token
    with urlopen(Request(url.rstrip("/") + "/predictions", headers=headers), timeout=5) as reply:
        return json.load(reply)


async def emit_once(service_url: str, nats_url: str, token: str | None = None) -> dict:
    import nats

    response = await asyncio.to_thread(_fetch, service_url, token)
    event = event_from_response(response)
    connection = await nats.connect(nats_url)
    try:
        acknowledgement = await publish_event(connection.jetstream(), event)
        return {"stream": acknowledgement.stream, "sequence": acknowledgement.seq,
                "forecasts": len(event["predictions"])}
    finally:
        await connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish one reviewed prediction event")
    parser.add_argument("--service-url", default="http://localhost:5000")
    parser.add_argument("--nats-url", default="nats://localhost:4222")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(emit_once(args.service_url, args.nats_url,
                                         os.getenv("DT_RAM_SERVICE_TOKEN")))))


if __name__ == "__main__":
    main()
