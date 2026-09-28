"""NetPulse chaos runner: break the transit side, time how long until the right alert arrives.

Each run: wait until the lab is healthy, note t0, inject one failure, wait for the matching
alert in results/alerts.jsonl, record (received_at - t0), restore, cool down, repeat.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

LAB = "clab-netpulse"
PROMETHEUS = "http://172.20.20.102:9090"
EXPECTED_SESSIONS = 8  # BGP sessions visible from the four cEOS routers (2 each: eBGP to transit + iBGP)
SCENARIOS = ("link_down", "bgp_shutdown", "silent_loss")
FIELDS = ("scenario", "transit", "iface", "site", "t0", "time_to_alert_s", "status")


@dataclass(frozen=True)
class Target:
    transit: str  # FRR node we break
    transit_iface: str
    transit_peer_ip: str  # the site router's address, as configured on the transit router
    site: str  # cEOS router that should raise the alert
    site_iface: str
    site_peer_ip: str  # the transit router's address, as seen from the site router


TARGETS = (
    Target("t1", "eth1", "10.0.4.0", "a1", "Ethernet2", "10.0.4.1"),
    Target("t2", "eth1", "10.0.5.0", "a2", "Ethernet2", "10.0.5.1"),
    Target("t1", "eth2", "10.0.6.0", "b1", "Ethernet2", "10.0.6.1"),
    Target("t2", "eth2", "10.0.7.0", "b2", "Ethernet2", "10.0.7.1"),
)


def plan(scenario: str, t: Target) -> tuple[list[list[str]], list[list[str]], dict[str, str]]:
    """Return (inject commands, restore commands, labels the expected alert must carry)."""
    node = f"{LAB}-{t.transit}"
    if scenario == "link_down":
        inject = [["docker", "exec", node, "ip", "link", "set", t.transit_iface, "down"]]
        restore = [["docker", "exec", node, "ip", "link", "set", t.transit_iface, "up"]]
        expect = {"alertname": "InterfaceDown", "source": t.site, "interface_name": t.site_iface}
    elif scenario == "bgp_shutdown":
        vtysh = ["docker", "exec", node, "vtysh", "-c", "configure terminal", "-c", "router bgp 65000"]
        inject = [[*vtysh, "-c", f"neighbor {t.transit_peer_ip} shutdown"]]
        restore = [[*vtysh, "-c", f"no neighbor {t.transit_peer_ip} shutdown"]]
        expect = {"alertname": "BGPSessionDown", "source": t.site, "neighbor_neighbor_address": t.site_peer_ip}
    elif scenario == "silent_loss":
        netem = ["sudo", "containerlab", "tools", "netem"]
        inject = [[*netem, "set", "-n", node, "-i", t.transit_iface, "--loss", "100"]]
        restore = [[*netem, "reset", "-n", node, "-i", t.transit_iface]]
        expect = {"alertname": "BGPSessionDown", "source": t.site, "neighbor_neighbor_address": t.site_peer_ip}
    else:
        raise ValueError(f"unknown scenario: {scenario}")
    return inject, restore, expect


def matches(record: dict, expect: dict[str, str], t0: float) -> bool:
    """True if this receiver record is the firing alert we're waiting for, received after t0."""
    if record.get("status") != "firing" or record.get("received_at", 0.0) < t0:
        return False
    labels = record.get("labels", {})
    return all(labels.get(key) == value for key, value in expect.items())


def complete_records(text: str) -> list[dict]:
    """Parse JSON lines, skipping a trailing line the receiver hasn't finished writing yet."""
    records = []
    for line in text.splitlines(keepends=True):
        if not line.endswith("\n"):
            break  # half-written; it will be complete on the next poll
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile: the smallest sample with at least pct% of samples at or below it."""
    if not values:
        raise ValueError("no values")
    ordered = sorted(values)
    rank = math.ceil(pct / 100 * len(ordered))
    return ordered[max(rank, 1) - 1]


def summarize(rows: list[dict]) -> dict[str, dict]:
    """Per-scenario and overall stats. Timeouts count as runs, not as detections."""
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row["scenario"], []).append(row)
    groups["all"] = rows
    summary = {}
    for name, group in groups.items():
        ok = [float(r["time_to_alert_s"]) for r in group if r["status"] == "ok"]
        summary[name] = {
            "runs": len(group),
            "detected": len(ok),
            "median_s": round(statistics.median(ok), 2) if ok else None,
            "p95_s": round(percentile(ok, 95), 2) if ok else None,
            "max_s": round(max(ok), 2) if ok else None,
        }
    return summary


def query(prometheus: str, promql: str) -> list[dict]:
    url = f"{prometheus}/api/v1/query?{urllib.parse.urlencode({'query': promql})}"
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.load(response)["data"]["result"]


def healthy(prometheus: str) -> bool:
    """Nothing firing, and all BGP sessions report Established."""
    try:
        if query(prometheus, 'ALERTS{alertstate="firing"}'):
            return False
        established = query(prometheus, "sum(netpulse_bgp_session_state)")
    except (urllib.error.URLError, TimeoutError, OSError):
        return False  # Prometheus not reachable yet counts as not healthy
    return bool(established) and float(established[0]["value"][1]) == EXPECTED_SESSIONS


def wait_healthy(prometheus: str, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if healthy(prometheus):
            return True
        time.sleep(1)
    return False


def wait_for_alert(alerts: Path, offset: int, expect: dict[str, str], t0: float, timeout: float) -> float | None:
    """Read only bytes written after `offset`; return seconds from t0 to the matching alert."""
    deadline = t0 + timeout
    while time.time() < deadline:
        if alerts.exists():
            with alerts.open("rb") as f:
                f.seek(offset)
                text = f.read().decode("utf-8", errors="replace")
            for record in complete_records(text):
                if matches(record, expect, t0):
                    return record["received_at"] - t0
        time.sleep(0.2)
    return None


def run(commands: list[list[str]], dry_run: bool) -> None:
    for command in commands:
        print("   $", " ".join(command))
        if not dry_run:
            subprocess.run(command, check=True, capture_output=True, text=True)


def write_results(rows: list[dict], out: Path, dry_run: bool) -> dict:
    """Write runs.csv and summary.json. Called after every run so an interrupted session keeps its data."""
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    summary = {} if dry_run else summarize(rows)
    out.with_name("summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", default=",".join(SCENARIOS))
    parser.add_argument("--runs", type=int, default=20, help="runs per scenario")
    parser.add_argument("--alerts", type=Path, default=Path("results/alerts.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("results/runs.csv"))
    parser.add_argument("--prometheus", default=PROMETHEUS)
    parser.add_argument("--timeout", type=float, default=60, help="seconds to wait for each alert")
    parser.add_argument("--cooldown", type=float, default=5)
    parser.add_argument("--dry-run", action="store_true", help="print commands, touch nothing")
    args = parser.parse_args()

    if args.dry_run:
        args.out = args.out.with_name("dry-run.csv")  # never overwrite real measurements

    rows: list[dict] = []
    summary: dict = {}
    for scenario in args.scenarios.split(","):
        for i in range(args.runs):
            target = TARGETS[i % len(TARGETS)]
            inject, restore, expect = plan(scenario, target)
            print(f"[{scenario} {i + 1}/{args.runs}] {target.transit}:{target.transit_iface} -> expect {expect}")
            if not args.dry_run and not wait_healthy(args.prometheus, timeout=120):
                raise SystemExit("Lab never became healthy; fix it before measuring.")
            offset = args.alerts.stat().st_size if args.alerts.exists() else 0
            t0 = time.time()  # stamped immediately before injection
            took: float | None = None
            try:
                run(inject, args.dry_run)
                if not args.dry_run:
                    took = wait_for_alert(args.alerts, offset, expect, t0, args.timeout)
            finally:
                run(restore, args.dry_run)  # always put the network back
            status = "dry-run" if args.dry_run else ("ok" if took is not None else "timeout")
            print(f"   -> {status}" + (f" in {took:.2f} s" if took is not None else ""))
            rows.append({
                "scenario": scenario, "transit": target.transit, "iface": target.transit_iface,
                "site": target.site, "t0": f"{t0:.3f}",
                "time_to_alert_s": f"{took:.3f}" if took is not None else "",
                "status": status,
            })
            summary = write_results(rows, args.out, args.dry_run)
            time.sleep(0 if args.dry_run else args.cooldown)

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
