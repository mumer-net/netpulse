from datetime import UTC, datetime

from handoff import incidents, load_records, parse_ts, render

BGP = {"alertname": "BGPSessionDown", "source": "a1", "neighbor_neighbor_address": "10.0.4.1"}
INTF = {"alertname": "InterfaceDown", "source": "b2", "interface_name": "Ethernet2"}


def test_parse_ts_handles_nanoseconds_and_zero_time():
    ts = parse_ts("2026-09-26T14:03:07.123456789Z")
    assert ts == datetime(2026, 9, 26, 14, 3, 7, 123456, tzinfo=UTC)
    assert parse_ts("0001-01-01T00:00:00Z") is None


def test_incidents_pair_firing_with_resolved():
    start = "2026-09-26T14:00:00.5Z"
    records = [
        {"received_at": 1.0, "status": "firing", "labels": BGP, "starts_at": start, "ends_at": "0001-01-01T00:00:00Z"},
        {"received_at": 9.0, "status": "resolved", "labels": BGP, "starts_at": start, "ends_at": "2026-09-26T14:00:08.5Z"},
        {"received_at": 5.0, "status": "firing", "labels": INTF, "starts_at": "2026-09-26T14:00:04Z"},
    ]
    incs = incidents(records)
    assert len(incs) == 2
    bgp = next(i for i in incs if i["alertname"] == "BGPSessionDown")
    assert (bgp["resolved"] - bgp["started"]).total_seconds() == 8
    report = render(incs, datetime(2026, 9, 26, 6, tzinfo=UTC),
                    datetime(2026, 9, 26, 14, 30, tzinfo=UTC), "US East", "APJC")
    assert "# Shift handoff: US East → APJC" in report
    assert "| InterfaceDown | b2 Ethernet2 |" in report  # still open
    assert "| BGPSessionDown | a1 peer 10.0.4.1 |" in report and "| 8 s |" in report


def test_load_records_skips_broken_lines(tmp_path):
    path = tmp_path / "alerts.jsonl"
    path.write_text('{"received_at": 1.0}\n{"received_at": 2\n', encoding="utf-8")
    assert load_records(path) == [{"received_at": 1.0}]
    assert load_records(tmp_path / "missing.jsonl") == []
