"""NetPulse alert receiver: an Alertmanager webhook that logs every alert with its arrival time.

Each alert in a webhook POST becomes one JSON line in the output file. chaos.py compares
`received_at` with the moment it injected a failure to get time-to-alert.
"""

from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, HTTPServer


def records_from_payload(payload: dict, received_at: float) -> list[dict]:
    """Flatten one Alertmanager webhook payload into one record per alert."""
    return [
        {
            "received_at": received_at,
            "status": alert.get("status"),
            "labels": alert.get("labels", {}),
            "annotations": alert.get("annotations", {}),
            "starts_at": alert.get("startsAt"),
            "ends_at": alert.get("endsAt"),
        }
        for alert in payload.get("alerts", [])
    ]


def make_handler(out_path: str) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            received_at = time.time()  # stamp first, so parsing time isn't counted
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
            lines = "".join(json.dumps(record) + "\n" for record in records_from_payload(payload, received_at))
            with open(out_path, "a", encoding="utf-8") as f:
                f.write(lines)  # one write per POST, so readers rarely see a half-written batch
            self.send_response(200)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            return  # keep container logs quiet

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=9095)
    parser.add_argument("--out", default="/results/alerts.jsonl")
    args = parser.parse_args()
    HTTPServer(("0.0.0.0", args.port), make_handler(args.out)).serve_forever()


if __name__ == "__main__":
    main()
