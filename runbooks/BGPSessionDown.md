# BGPSessionDown

**Fires when:** a site router reports a BGP session that is not Established
(`netpulse_bgp_session_state == 0`).
**Impact:** the site loses one of its two paths to transit and traffic shifts to the other
site router. If both of a site's transit sessions are down, the site is cut off.

## Check (on the router in the alert's `source` label)
1. `docker exec -it clab-netpulse-<source> Cli`
2. `show ip bgp summary`: which peer, and what state (Idle, Active, Connect)?
3. `show interfaces Ethernet2`: if the link is down, switch to the [InterfaceDown](InterfaceDown.md) runbook.
4. `show ip bgp neighbors <peer>`: read the last notification and the BFD state (last line).

## Likely causes
| What you see | Cause | Fix (lab) |
| --- | --- | --- |
| Interface down | Link failure | [InterfaceDown](InterfaceDown.md) runbook |
| Notification: Cease / administrative shutdown | Peer shut the session | On the transit router: `docker exec clab-netpulse-<transit> vtysh -c "conf t" -c "router bgp 65000" -c "no neighbor <site-ip> shutdown"` |
| `BFD is enabled and state is Down`, or notification `Cease/BFD down`, interface up | Silent packet loss (BFD caught it in ~300 ms) | `sudo containerlab tools netem show -n clab-netpulse-<transit>`, then `sudo containerlab tools netem reset -n clab-netpulse-<transit> -i <iface>` |

## What I saw when I broke it by hand
Fire drill, 2026-09-28: `neighbor 10.0.6.0 shutdown` on t1 (t1's session to b1).

- `show ip bgp summary` on b1: t1-transit (10.0.6.1) in `Active` (b1 keeps retrying, t1 refuses);
  the b2 iBGP session stayed `Estab`, so site B kept its path to transit through b2.
- `show ip bgp neighbors 10.0.6.1` on b1:
  - `Last rcvd notification: Cease/administrative shutdown`: the peer shut it on purpose.
  - `BFD is enabled and state is Up`: the link is healthy, so this is configuration, not a cable.
  - `Last sent notification: Cease/BFD down` (left over from the silent-loss chaos runs): what a
    real silent failure looks like from this side.
- The shift-handoff report generated during the incident listed it under "Still open" with this
  runbook ([docs/sample-handoff.md](../docs/sample-handoff.md)).
- `no neighbor 10.0.6.0 shutdown` on t1 restored it; the alert resolved within seconds.

**How to tell the three causes apart from the site router alone:** interface down = link failure;
interface up + BFD Down = silent loss on the path; interface up + BFD Up + `Cease/administrative
shutdown` = the peer disabled the session.

## Verify
- `show ip bgp summary` shows Estab, `BFD ... state is Up`, the alert resolves within a few seconds, and the Grafana row turns green.

## Escalate
- In production the transit side is the provider's. Send them the reset reason, both timestamps
  (fired and resolved), and your side's interface state.
