import pytest
from chaos import TARGETS, complete_records, matches, percentile, plan, summarize


def test_percentile_nearest_rank():
    values = [float(v) for v in range(1, 21)]  # 1..20
    assert percentile(values, 50) == 10
    assert percentile(values, 95) == 19
    assert percentile([4.2], 95) == 4.2
    with pytest.raises(ValueError):
        percentile([], 95)


@pytest.mark.parametrize("scenario,alert", [
    ("link_down", "InterfaceDown"), ("bgp_shutdown", "BGPSessionDown"), ("silent_loss", "BGPSessionDown"),
])
def test_plan_expects_alert_on_site_router(scenario, alert):
    inject, restore, expect = plan(scenario, TARGETS[0])
    assert expect["alertname"] == alert and expect["source"] == "a1"
    assert inject and restore and inject != restore


def test_plan_rejects_unknown_scenario():
    with pytest.raises(ValueError):
        plan("meteor_strike", TARGETS[0])


def test_matches_only_firing_after_t0_with_right_labels():
    expect = {"alertname": "BGPSessionDown", "source": "a1", "neighbor_neighbor_address": "10.0.4.1"}
    good = {"status": "firing", "received_at": 100.5, "labels": dict(expect, severity="critical")}
    assert matches(good, expect, t0=100.0)
    assert not matches(dict(good, received_at=99.0), expect, t0=100.0)
    assert not matches(dict(good, status="resolved"), expect, t0=100.0)
    assert not matches(dict(good, labels=dict(expect, source="a2")), expect, t0=100.0)


def test_complete_records_skips_half_written_line():
    text = '{"status": "firing"}\n{"status": "resol'
    assert complete_records(text) == [{"status": "firing"}]


def test_summarize_counts_timeouts_as_runs():
    rows = [{"scenario": "link_down", "status": "ok", "time_to_alert_s": s} for s in ("2.0", "3.0", "4.0")]
    rows.append({"scenario": "link_down", "status": "timeout", "time_to_alert_s": ""})
    s = summarize(rows)
    assert s["link_down"]["runs"] == 4 and s["link_down"]["detected"] == 3
    assert s["all"]["median_s"] == 3.0 and s["all"]["p95_s"] == 4.0


def test_zero_second_detection_is_kept():
    rows = [{"scenario": "link_down", "status": "ok", "time_to_alert_s": "0.000"}]
    assert summarize(rows)["all"]["median_s"] == 0.0
