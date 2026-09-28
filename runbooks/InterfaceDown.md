# InterfaceDown

**Fires when:** a site router reports an Ethernet interface that is not up
(`netpulse_intf_oper_status{interface_name=~"Ethernet.*"} == 0`).
**Impact:** Ethernet2 down = one transit path lost (its BGPSessionDown fires too, within the 3 s
hold timer). Ethernet1 down = the site's internal link is lost, OSPF drops, and the site's iBGP
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
| Both ends up, but alert still firing | Telemetry lag or stale series | Wait one sample (2 s); if it persists, check [TelemetryDown](TelemetryDown.md) |
| Container gone | Node crashed | `sudo containerlab inspect -t netpulse.clab.yml`; redeploy the node |

## What I saw when I broke it by hand
<!-- Fill in after the Phase 2 fire drill (`ip link set eth1 down` on t1). -->

## Verify
- `show interfaces <interface>` is up/up, the matching BGP session is Estab again,
  and both alerts resolve.

## Escalate
- In production: open a ticket with the circuit provider with the interface, the far-end device,
  and the time the carrier dropped.
