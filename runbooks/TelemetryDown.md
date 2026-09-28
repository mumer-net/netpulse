# TelemetryDown

**Fires when:** Prometheus can't scrape gNMIc, or fewer than 4 routers are reporting
interface data, for 10 s.
**Impact:** blind spot. Metrics expire after 30 s, so `BGPSessionDown` and `InterfaceDown` go
silent instead of firing. No data is not good data: treat the network as unverified until this clears.

## Check
1. `docker logs clab-netpulse-gnmic --tail 50`: connection refused, auth errors, or a crash?
2. Prometheus targets page, http://localhost:9090/targets: is the `gnmic` job up?
3. Which routers are missing: `count by (source) (netpulse_intf_oper_status)` in Prometheus.
4. Test a router directly: `gnmic -a <router-mgmt-ip>:6030 -u admin -p admin --insecure capabilities`.

## Likely causes
| What you see | Cause | Fix (lab) |
| --- | --- | --- |
| `up{job="gnmic"} == 0` | gNMIc container down | `docker start clab-netpulse-gnmic` |
| One router missing, "connection refused" | Router rebooting, or `management api gnmi` missing | Wait for boot; check `show management api gnmi` on that router |
| All routers missing, gNMIc up | Wrong credentials or port in `gnmic.yml` | Fix `telemetry/gnmic.yml`, then `docker restart clab-netpulse-gnmic` |

## What I saw when I broke it by hand
First deploy, 2026-09-28: TelemetryDown fired at 05:31:15 UTC while the four cEOS routers were still
booting (fewer than 4 reporting) and resolved on its own at 05:31:55 once all four streamed data.
Expected after every fresh deploy; if it lasts more than ~3 minutes, work through the checks above.

## Verify
- `sum(netpulse_bgp_session_state)` is back to 8 and the alert resolves.

## Escalate
- In production: page whoever owns the monitoring stack. A telemetry gap during an incident
  means nobody can confirm recovery.
