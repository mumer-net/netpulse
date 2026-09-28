from alert_receiver import records_from_payload


def test_one_record_per_alert():
    payload = {"status": "firing", "alerts": [
        {"status": "firing", "labels": {"alertname": "InterfaceDown"}, "startsAt": "s", "endsAt": "e"},
        {"status": "resolved", "labels": {"alertname": "BGPSessionDown"}},
    ]}
    records = records_from_payload(payload, received_at=42.0)
    assert [r["status"] for r in records] == ["firing", "resolved"]
    assert all(r["received_at"] == 42.0 for r in records)
