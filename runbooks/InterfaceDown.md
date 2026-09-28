# InterfaceDown

**Fires when:** a site router reports an Ethernet interface that is not up
(`netpulse_intf_oper_status{interface_name=~"Ethernet.*"} == 0`).
**Impact:** Ethernet2 down = one transit path lost (its BGPSessionDown fires at the same moment,
because the session drops with the interface). Ethernet1 down = the site's internal link is lost, OSPF drops, and the site's iBGP
session follows.

## Check
1. On the site router: `docker exec -it clab-netpulse-<source> Cli`, then `show interfaces <interface>`
   (line protocol status, last change, carrier transitions).
2. Find the far end from the description: `show interfaces description`.
3. On the transit side: `docker exec clab-netpulse-<transit> ip link show <iface>`: is it `state DOWN`?
4. `show ip bgp summary` on the site router: confirm which BGP session went with it.

## Likely causes
| What you see | Cause | Fix (lab) |
| --- | --- | --- |
| Far end `state DOWN` / admin down | Port shut on the far side | `docker exec clab-netpulse-<transit> ip link set <iface> up` |
| Both ends up, but alert still firing | Telemetry lag or stale series | Wait a few seconds for the next update; if it persists, check [TelemetryDown](TelemetryDown.md) |
| Container gone | Node crashed | `sudo containerlab inspect -t netpulse.clab.yml`; redeploy the node |

## What I saw when I broke it by hand
Fire drill, 2026-09-28: `docker exec clab-netpulse-t1 ip link set eth1 down` (t1's side of link 4).

- Both alerts arrived within 3 ms of each other, for a1 only:
  `InterfaceDown` (a1 Ethernet2) and `BGPSessionDown` (a1 -> 10.0.4.1).
- `show interfaces Ethernet2` on a1: `Ethernet2 is down, line protocol is down (notconnect)`.
  a1 sees the far end disappear even though only t1's side was shut.
- `show ip bgp summary` on a1: t1-transit (10.0.4.1) in `Idle(NoIf)`; the a2 iBGP session stayed
  `Estab`, so site A kept its path to transit through a2.
- After `ip link set eth1 up`, both alerts resolved together. Total outage: 66 s (05:39:21 to 05:40:27 UTC).

## Verify
- `show interfaces <interface>` is up/up, the matching BGP session is Estab again,
  and both alerts resolve.

## Escalate
- In production: open a ticket with the circuit provider with the interface, the far-end device,
  and the time the carrier dropped.
