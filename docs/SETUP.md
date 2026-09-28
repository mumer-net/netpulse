# Setup

How I run NetPulse on an Apple silicon Mac. Everything after step 1 runs inside the Linux VM.

## 1. Linux VM (on the Mac)
    brew install orbstack
    orb create ubuntu clab
    orb -m clab

## 2. containerlab and Docker
    curl -sL https://containerlab.dev/setup | sudo -E bash -s "all"
    containerlab version                       # 0.79.x
    # On Ubuntu 26.04 the setup script skipped Docker; Ubuntu's package works:
    sudo apt-get install -y docker.io python3-venv jq git make
    sudo usermod -aG docker,clab_admins $USER  # then log out and back in

## 3. Arista cEOS (free account at arista.com, Software Downloads -> cEOS-lab)
Download the ARM build (`cEOSarm-lab-...tar.xz`, not `cEOS64-lab`), then:

    docker import /Users/<you>/Downloads/cEOSarm-lab-4.36.2F.tar.xz ceos:4.36.2F   # Mac files appear under /Users
    docker image inspect ceos:4.36.2F -f '{{.Architecture}}'           # arm64

## 4. Other images and the gnmic CLI
    for img in quay.io/frrouting/frr:10.7.1 ghcr.io/openconfig/gnmic:0.49.0 \
      prom/prometheus:v3.14.0 prom/alertmanager:v0.34.1 grafana/grafana:13.2.2 python:3.13-slim; do
      docker pull "$img"
    done
    bash -c "$(curl -sL https://get-gnmic.openconfig.net)"

## 5. Clone, test, deploy
    git clone https://github.com/mumer-net/netpulse.git && cd netpulse
    python3 -m venv .venv && . .venv/bin/activate && pip install pytest ruff pyyaml jsonschema
    make test
    make deploy          # cEOS needs ~2-3 minutes to boot

## Checks, bottom layer up
1. Routing: `docker exec -it clab-netpulse-a1 Cli -c "show ip bgp summary"` shows 2 peers Estab;
   `docker exec -it clab-netpulse-a1 Cli -p 15 -c "ping 10.255.2.1 source Loopback0"` crosses transit.
2. BFD: `docker exec -it clab-netpulse-a1 Cli -c "show bfd peers"` shows the transit peer Up.
3. Telemetry: `curl -s http://172.20.20.101:9804/metrics | grep ^netpulse_`; in Prometheus,
   `sum(netpulse_bgp_session_state)` is 8.
4. Grafana: http://localhost:3000/d/netpulse (no login).
5. Measure: `make chaos-dry`, `make chaos-smoke`, then `make chaos` with nothing heavy running on the Mac
   (`caffeinate -dims` keeps it awake).
