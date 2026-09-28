"""Cross-check the router configs against the design plan, so a typo fails CI instead of a deploy."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIGS = ROOT / "configs"

SITE = {  # router: (AS, loopback, mgmt IP, Ethernet1, Ethernet2, eBGP peer, iBGP peer)
    "a1": (65001, "10.255.1.1", "172.20.20.11", "10.0.1.0", "10.0.4.0", "10.0.4.1", "10.255.1.2"),
    "a2": (65001, "10.255.1.2", "172.20.20.12", "10.0.1.1", "10.0.5.0", "10.0.5.1", "10.255.1.1"),
    "b1": (65002, "10.255.2.1", "172.20.20.21", "10.0.2.0", "10.0.6.0", "10.0.6.1", "10.255.2.2"),
    "b2": (65002, "10.255.2.2", "172.20.20.22", "10.0.2.1", "10.0.7.0", "10.0.7.1", "10.255.2.1"),
}


def test_site_configs_match_design_plan():
    for name, (asn, lo, mgmt, e1, e2, ebgp, ibgp) in SITE.items():
        cfg = (CONFIGS / f"{name}.cfg").read_text()
        assert f"hostname {name}" in cfg
        assert "ip routing" in cfg
        assert f"router bgp {asn}" in cfg
        assert f"ip address {lo}/32" in cfg
        assert f"ip address {mgmt}/24" in cfg
        assert f"ip address {e1}/31" in cfg and f"ip address {e2}/31" in cfg
        assert f"neighbor {ebgp} remote-as 65000" in cfg
        assert f"neighbor {ibgp} next-hop-self" in cfg
        assert cfg.count("timers 1 3") == 2


def test_every_ebgp_peer_points_back():
    """Each site router's transit peer must have that router configured as its neighbor on FRR."""
    frr = {n: (CONFIGS / f"{n}.conf").read_text() for n in ("t1", "t2")}
    for asn, _lo, _mgmt, _e1, e2, ebgp, _ibgp in SITE.values():
        owners = [t for t, cfg in frr.items() if f"ip address {ebgp}/31" in cfg]
        assert len(owners) == 1, f"{ebgp} should live on exactly one transit router"
        assert f"neighbor {e2} remote-as {asn}" in frr[owners[0]]


def test_topology_mgmt_ips_match_configs():
    topo = yaml.safe_load((ROOT / "netpulse.clab.yml").read_text())
    for name, (_asn, _lo, mgmt, *_rest) in SITE.items():
        assert topo["topology"]["nodes"][name]["mgmt-ipv4"] == mgmt


def test_eight_bgp_sessions_from_the_site_side():
    sessions = sum(len(re.findall(r"remote-as \d+\n", (CONFIGS / f"{n}.cfg").read_text())) for n in SITE)
    assert sessions == 8  # chaos.EXPECTED_SESSIONS and the dashboard assume this
