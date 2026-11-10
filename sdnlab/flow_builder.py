"""Build flow JSON in the OpenDaylight `opendaylight-inventory` / `flow-node-inventory` model.

The OpenFlow plugin translates these into OFPT_FLOW_MOD messages, e.g.:
    priority=500,icmp,nw_src=10.0.0.1,nw_dst=10.0.0.3 actions=drop
"""
from __future__ import annotations

import ipaddress
import re

ETH_TYPE_IPV4 = 0x0800
IP_PROTO_ICMP = 1
ICMP_ECHO_REPLY = 0
ICMP_ECHO_REQUEST = 8

BASELINE_FLOW_ID = "baseline-normal"
DEFAULT_TABLE = 0

_FLOW_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _check_flow_id(flow_id: str) -> str:
    if not flow_id or not _FLOW_ID_RE.match(flow_id):
        raise ValueError(f"Invalid flow id {flow_id!r}: use letters, digits, '.', '_' or '-'")
    return flow_id


def _to_prefix(addr: str) -> str:
    """'10.0.0.1' -> '10.0.0.1/32'; '10.0.0.0/24' stays as is. Raises ValueError if bad."""
    try:
        net = ipaddress.IPv4Network(addr, strict=False)
    except ValueError as exc:
        raise ValueError(f"Invalid IPv4 address or prefix: {addr!r}") from exc
    return str(net)


def _instructions(actions: list[dict]) -> dict:
    for i, action in enumerate(actions):
        action["order"] = i
    return {"instruction": [{"order": 0, "apply-actions": {"action": actions}}]}


def icmp_block_flow(
    flow_id: str,
    src: str | None = None,
    dst: str | None = None,
    icmp_type: int | None = None,
    priority: int = 500,
    table: int = DEFAULT_TABLE,
    hard_timeout: int = 0,
    idle_timeout: int = 0,
) -> dict:
    """Drop ICMP matching src/dst (and optionally a single ICMP type)."""
    _check_flow_id(flow_id)
    if not (0 <= priority <= 65535):
        raise ValueError("priority must be between 0 and 65535")
    if icmp_type is not None and not (0 <= icmp_type <= 255):
        raise ValueError("icmp_type must be between 0 and 255")

    # OpenFlow prerequisites: eth_type=IPv4 before ip_proto, ip_proto=ICMP before icmp_type.
    match: dict = {
        "ethernet-match": {"ethernet-type": {"type": ETH_TYPE_IPV4}},
        "ip-match": {"ip-protocol": IP_PROTO_ICMP},
    }
    if src:
        match["ipv4-source"] = _to_prefix(src)
    if dst:
        match["ipv4-destination"] = _to_prefix(dst)
    if icmp_type is not None:
        match["icmpv4-match"] = {"icmpv4-type": icmp_type}

    desc = f"drop icmp{'' if icmp_type is None else f' type={icmp_type}'} {src or '*'} -> {dst or '*'}"
    return {
        "id": flow_id,
        "table_id": table,
        "priority": priority,
        "flow-name": desc,
        "hard-timeout": hard_timeout,
        "idle-timeout": idle_timeout,
        "match": match,
        "instructions": _instructions([{"drop-action": {}}]),
    }


def normal_forwarding_flow(priority: int = 1, table: int = DEFAULT_TABLE) -> dict:
    """Low-priority catch-all that hands packets to OVS's normal L2 pipeline."""
    return {
        "id": BASELINE_FLOW_ID,
        "table_id": table,
        "priority": priority,
        "flow-name": "baseline normal forwarding",
        "hard-timeout": 0,
        "idle-timeout": 0,
        "match": {},
        "instructions": _instructions([
            {"output-action": {"output-node-connector": "NORMAL", "max-length": 65535}}
        ]),
    }
