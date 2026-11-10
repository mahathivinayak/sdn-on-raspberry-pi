#!/usr/bin/env bash
# Dump the real OpenFlow tables from OVS (all bridges, or the ones named).
# Usage: ./scripts/dump_flows.sh [bridge ...]
set -euo pipefail

SUDO=""
[[ $EUID -ne 0 ]] && SUDO="sudo"

if [[ $# -gt 0 ]]; then
  bridges=("$@")
else
  mapfile -t bridges < <($SUDO ovs-vsctl list-br)
fi

if [[ ${#bridges[@]} -eq 0 ]]; then
  echo "No OVS bridges found. Is Mininet running?" >&2
  exit 1
fi

for br in "${bridges[@]}"; do
  echo "===== $br ====="
  $SUDO ovs-ofctl -O OpenFlow13 dump-flows "$br"
  echo
done
