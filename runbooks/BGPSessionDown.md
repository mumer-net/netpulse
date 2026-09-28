# BGPSessionDown

**Fires when:** a site router reports a BGP session that is not Established
(`netpulse_bgp_session_state == 0`).
**Impact:** the site loses one of its two paths to transit and traffic shifts to the other
site router. If both of a site's transit sessions are down, the site is cut off.

## Check (on the router in the alert's `source` label)
1. `docker exec -it clab-netpulse-<source> Cli`
2. `show ip bgp summary`: which peer, and what state (Idle, Active, Connect)?
3. `show interfaces Ethernet2`: if the link is down, switch to the [InterfaceDown](InterfaceDown.md) runbook.
4. `show ip bgp neighbors <peer>`: read the last reset reason and notification.

## Likely causes
| What you see | Cause | Fix (lab) |
| --- | --- | --- |
| Interface down | Link failure | [InterfaceDown](InterfaceDown.md) runbook |
| Notification: Cease / administrative shutdown | Peer shut the session | On the transit router: `docker exec clab-netpulse-<transit> vtysh -c "conf t" -c "router bgp 65000" -c "no neighbor <site-ip> shutdown"` |
| Hold timer expired, interface up | Silent packet loss | `sudo containerlab tools netem show -n clab-netpulse-<transit>`, then `sudo containerlab tools netem reset -n clab-netpulse-<transit> -i <iface>` |

## What I saw when I broke it by hand
<!-- Fill in after the Phase 4 fire drill: the exact output of `show ip bgp summary`
     and the reset reason from `show ip bgp neighbors`. -->

## Verify
- `show ip bgp summary` shows Estab, the alert resolves within about 6 s, and the Grafana row turns green.

## Escalate
- In production the transit side is the provider's. Send them the reset reason, both timestamps
  (fired and resolved), and your side's interface state.
