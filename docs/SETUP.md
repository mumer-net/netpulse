# Setup and build checklist (run inside the `clab` machine unless noted)

## 1. Machine (on the Mac)
    orb create ubuntu clab
    ssh clab@orb

## 2. containerlab, Docker, tools (inside clab)
    curl -sL https://containerlab.dev/setup | sudo -E bash -s "all"
    sudo usermod -aG docker $USER && exit      # then: ssh clab@orb
    containerlab version                       # expect 0.79.x
    sudo apt-get update && sudo apt-get install -y python3-venv jq git make unzip

## 3. Arista image (file is in the Mac's Downloads)
    sudo docker import /mnt/mac/Users/umer/Downloads/cEOSarm-lab-4.36.2F.tar.xz ceos:4.36.2F
    docker image inspect ceos:4.36.2F -f '{{.Architecture}}'    # expect arm64

## 4. Other images + gnmic CLI
    for img in quay.io/frrouting/frr:10.7.1 ghcr.io/openconfig/gnmic:0.49.0 \
      prom/prometheus:v3.14.0 prom/alertmanager:v0.34.1 grafana/grafana:13.2.2 python:3.13-slim; do
      docker pull "$img"
    done
    bash -c "$(curl -sL https://get-gnmic.openconfig.net)"

## 5. Repo
    cd ~ && unzip /mnt/mac/Users/umer/Downloads/netpulse.zip && cd ~/netpulse
    python3 -m venv .venv && . .venv/bin/activate && pip install pytest ruff pyyaml jsonschema
    make test
    git init && git add -A && git commit -m "chore: NetPulse lab as code"

## Checkpoints
1. Routers: `make deploy`; after ~2 min, in `docker exec -it clab-netpulse-a1 Cli`:
   `show ip ospf neighbor` (FULL), `show ip bgp summary` (2 Estab), `ping 10.255.2.1 source Loopback0`.
2. Telemetry: `curl -s http://172.20.20.101:9804/metrics | grep ^netpulse_` shows labels
   `source`, `neighbor_neighbor_address`, `interface_name`; Prometheus `sum(netpulse_bgp_session_state)` = 8.
3. Fire drill: `docker exec clab-netpulse-t1 ip link set eth1 down`, watch Grafana + `tail -f results/alerts.jsonl`, then `... up`.
4. Chaos: `make chaos-dry`, `make chaos-smoke` (2 x "ok"), then `caffeinate -dims` on the Mac and `make chaos`.
5. Handoff: `make handoff`, copy one report to `docs/sample-handoff.md`.
6. Publish: `make set-user GH=<username>`, push, CI green, fill README numbers from `results/summary.json`.
