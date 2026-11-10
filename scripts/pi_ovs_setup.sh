#!/usr/bin/env bash
# Turn a Raspberry Pi into an OpenFlow 1.3 switch managed by OpenDaylight.
# Usage: sudo ./scripts/pi_ovs_setup.sh <ODL_IP> <iface> [iface ...]
# Env overrides: BRIDGE=br0 OF_PORT=6653 DPID=00000000000000a1
set -euo pipefail

BRIDGE="${BRIDGE:-br0}"
OF_PORT="${OF_PORT:-6653}"
DPID="${DPID:-00000000000000a1}"   # appears in ODL as openflow:161

if [[ $EUID -ne 0 ]]; then echo "Run as root (sudo)." >&2; exit 1; fi
if [[ $# -lt 2 ]]; then
  echo "Usage: sudo $0 <ODL_IP> <iface> [iface ...]" >&2; exit 1
fi
ODL_IP="$1"; shift

if ! command -v ovs-vsctl >/dev/null 2>&1; then
  apt-get update && apt-get install -y openvswitch-switch
fi
systemctl enable --now openvswitch-switch

# Don't bridge the interface carrying this SSH session
if [[ -n "${SSH_CONNECTION:-}" ]]; then
  ssh_ip=$(awk '{print $3}' <<<"$SSH_CONNECTION")
  ssh_if=$(ip -o -4 addr show | awk -v ip="$ssh_ip" 'index($4, ip"/")==1 {print $2}')
  for i in "$@"; do
    if [[ "$i" == "$ssh_if" ]]; then
      echo "Refusing to add $i: your SSH session runs over it." >&2; exit 1
    fi
  done
fi

ovs-vsctl --may-exist add-br "$BRIDGE"
ovs-vsctl set bridge "$BRIDGE" protocols=OpenFlow13 other-config:datapath-id="$DPID"
ovs-vsctl set-fail-mode "$BRIDGE" secure

for i in "$@"; do
  ip link show "$i" >/dev/null 2>&1 || { echo "No such interface: $i" >&2; exit 1; }
  ip addr flush dev "$i"
  ip link set "$i" up
  ovs-vsctl --may-exist add-port "$BRIDGE" "$i"
done
ip link set "$BRIDGE" up
ovs-vsctl set-controller "$BRIDGE" "tcp:${ODL_IP}:${OF_PORT}"

echo "Waiting for controller connection..."
for _ in $(seq 1 15); do
  if ovs-vsctl get controller "$BRIDGE" is_connected 2>/dev/null | grep -q true; then
    echo "Connected. $BRIDGE should appear in ODL as openflow:$((16#$DPID))"
    ovs-vsctl show
    exit 0
  fi
  sleep 1
done

echo "Not connected yet. Check that ODL listens on ${ODL_IP}:${OF_PORT} and no firewall blocks it." >&2
ovs-vsctl show
exit 1
