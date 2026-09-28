"""NetPulse shift handoff: turn the last N hours of alerts into a Markdown report for the next shift."""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

IDENTITY = ("source", "interface_name", "neighbor_neighbor_address")


def parse_ts(value: str | None) -> datetime | None:
    """Parse Alertmanager RFC 3339 timestamps (nanoseconds, 'Z'). Zero time means 'not set'."""
    if not value or value.startswith("0001-01-01"):
        return None
    value = value.replace("Z", "+00:00")
    head, dot, rest = value.partition(".")
    if dot:
        digits = len(rest) - len(rest.lstrip("0123456789"))
        value = f"{head}.{rest[:digits][:6].ljust(6, '0')}{rest[digits:]}"
    return datetime.fromisoformat(value)


def load_records(path: Path) -> list[dict]:
    """Read the receiver's JSON lines, skipping any line that isn't complete JSON."""
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def where(labels: dict) -> str:
    parts = [labels.get("source", "?")]
    if labels.get("interface_name"):
        parts.append(labels["interface_name"])
    if labels.get("neighbor_neighbor_address"):
        parts.append(f"peer {labels['neighbor_neighbor_address']}")
    return " ".join(parts)


def incidents(records: list[dict]) -> list[dict]:
    """Pair firing and resolved notifications into incidents (same alert identity and start time)."""
    found: dict[tuple, dict] = {}
    for rec in sorted(records, key=lambda r: r["received_at"]):
        labels = rec.get("labels", {})
        key = (labels.get("alertname"), *(labels.get(k) for k in IDENTITY), rec.get("starts_at"))
        inc = found.setdefault(key, {
            "alertname": labels.get("alertname", "?"),
            "where": where(labels),
            "runbook": rec.get("annotations", {}).get("runbook_url", ""),
            "started": parse_ts(rec.get("starts_at")),
            "resolved": None,
        })
        if rec.get("status") == "resolved":
            inc["resolved"] = parse_ts(rec.get("ends_at"))
    return list(found.values())


def fmt(dt: datetime | None) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S") if dt else "?"


def render(incs: list[dict], start: datetime, end: datetime, from_shift: str, to_shift: str,
           latency: dict | None = None) -> str:
    still_open = sorted((i for i in incs if i["resolved"] is None), key=lambda i: i["started"] or end)
    closed = sorted((i for i in incs if i["resolved"] is not None), key=lambda i: i["started"] or end)
    out = [f"# Shift handoff: {from_shift} → {to_shift}", "",
           f"Window {fmt(start)} to {fmt(end)} UTC · incidents: {len(incs)} · still open: {len(still_open)}", "",
           "## Still open", ""]
    if still_open:
        out += ["| Alert | Where | Since (UTC) | Runbook |", "| --- | --- | --- | --- |"]
        out += [f"| {i['alertname']} | {i['where']} | {fmt(i['started'])} | [runbook]({i['runbook']}) |"
                for i in still_open]
    else:
        out.append("Nothing open. The network is healthy at handoff.")
    out += ["", "## Resolved this shift", ""]
    if closed:
        out += ["| Alert | Where | Started (UTC) | Duration |", "| --- | --- | --- | --- |"]
        for i in closed:
            secs = (i["resolved"] - i["started"]).total_seconds() if i["started"] else None
            duration = f"{secs:.0f} s" if secs is not None else "?"
            out.append(f"| {i['alertname']} | {i['where']} | {fmt(i['started'])} | {duration} |")
    else:
        out.append("None.")
    out += ["", "## Most frequent", ""]
    top = Counter(i["where"] for i in incs).most_common(3)
    out += [f"- {place}: {count}" for place, count in top] or ["- None"]
    if latency and latency.get("detected"):
        out += ["", "## Detection latency (chaos runs)", "",
                (f"- Median {latency['median_s']} s, p95 {latency['p95_s']} s, "
                 f"{latency['detected']}/{latency['runs']} failures detected")]
    out += ["", "## Notes for the next shift", ""]
    if still_open:
        first = still_open[0]
        out.append(f"- Start with {first['alertname']} on {first['where']} and follow its runbook.")
    else:
        out.append("- No action needed. Watch the most frequent items above for repeats.")
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alerts", type=Path, default=Path("results/alerts.jsonl"))
    parser.add_argument("--summary", type=Path, default=Path("results/summary.json"))
    parser.add_argument("--hours", type=float, default=8)
    parser.add_argument("--from-shift", default="US East")
    parser.add_argument("--to-shift", default="APJC")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    now = time.time()
    records = [r for r in load_records(args.alerts) if r.get("received_at", 0) >= now - args.hours * 3600]
    latency = json.loads(args.summary.read_text()).get("all") if args.summary.exists() else None
    report = render(incidents(records), datetime.fromtimestamp(now - args.hours * 3600, UTC),
                    datetime.fromtimestamp(now, UTC), args.from_shift, args.to_shift, latency)
    out = args.out or Path(f"results/handoff-{datetime.now(UTC):%Y%m%d-%H%M}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
