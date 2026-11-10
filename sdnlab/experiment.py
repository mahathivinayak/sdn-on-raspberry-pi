"""End-to-end experiment: measure ICMP reachability before/after pushing a
filter rule through OpenDaylight, and capture traffic for Wireshark.

    sudo python3 -m sdnlab.experiment --controller-ip 127.0.0.1 --src h1 --dst h3
"""
from __future__ import annotations

import argparse
import os
import re
import time

from mininet.cli import CLI
from mininet.log import info, setLogLevel

from .flow_builder import ICMP_ECHO_REQUEST, icmp_block_flow, normal_forwarding_flow
from .odl_client import ODLClient, ODLError
from .topology import build_net

LOSS_RE = re.compile(r"(\d+(?:\.\d+)?)% packet loss")


def node_id(switch) -> str:
    return f"openflow:{int(switch.dpid, 16)}"


def wait_for_nodes(client: ODLClient, expected: set[str], timeout: float = 60) -> None:
    deadline = time.time() + timeout
    seen: set[str] = set()
    while time.time() < deadline:
        try:
            seen = set(client.list_nodes())
        except ODLError:
            seen = set()
        if expected <= seen:
            info(f"*** Controller sees: {sorted(seen)}\n")
            return
        time.sleep(2)
    raise TimeoutError(f"Switches not connected to ODL: {sorted(expected - seen)}")


def wait_for_drop_rule(switches, timeout: float = 15) -> None:
    """Confirm the rule reached the data plane, not just ODL's datastore."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        dumps = [sw.cmd(f"ovs-ofctl -O OpenFlow13 dump-flows {sw.name}") for sw in switches]
        if all("icmp" in d and "actions=drop" in d for d in dumps):
            return
        time.sleep(1)
    raise TimeoutError("Drop rule did not appear on all switches")


def ping_matrix(net, count: int = 2) -> dict:
    results = {}
    for src in net.hosts:
        for dst in net.hosts:
            if src is dst:
                continue
            out = src.cmd(f"ping -c {count} -W 1 {dst.IP()}")
            m = LOSS_RE.search(out)
            results[(src.name, dst.name)] = float(m.group(1)) if m else 100.0
    return results


def format_matrix(title: str, hosts, results: dict) -> str:
    names = [h.name for h in hosts]
    lines = [title, "src\\dst " + "".join(f"{n:>6}" for n in names)]
    for s in names:
        cells = []
        for d in names:
            if s == d:
                cells.append("-")
            else:
                loss = results[(s, d)]
                cells.append("OK" if loss == 0 else "DROP" if loss == 100 else f"{loss:.0f}%")
        lines.append(f"{s:>7} " + "".join(f"{c:>6}" for c in cells))
    return "\n".join(lines)


def start_capture(host, path: str):
    # -Z root: tcpdump otherwise drops privileges and may fail to write the file
    return host.popen(["tcpdump", "-i", host.defaultIntf().name, "-n", "-U",
                       "-Z", "root", "-w", path, "icmp"])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--controller-ip", default="127.0.0.1")
    p.add_argument("--of-port", type=int, default=6653)
    p.add_argument("--rest-port", type=int, default=8181)
    p.add_argument("--api", choices=["rfc8040", "legacy"], default="rfc8040")
    p.add_argument("--src", default="h1")
    p.add_argument("--dst", default="h3")
    p.add_argument("--echo-only", action="store_true")
    p.add_argument("--capture-dir", default="captures")
    p.add_argument("--cli", action="store_true", help="open Mininet CLI before cleanup")
    args = p.parse_args()

    setLogLevel("info")
    client = ODLClient(args.controller_ip, args.rest_port, api=args.api)
    net = build_net(args.controller_ip, args.of_port)
    nodes = {node_id(sw) for sw in net.switches}
    rule_id = f"block-icmp-{args.src}-{args.dst}"

    net.start()
    capture = None
    try:
        wait_for_nodes(client, nodes)
        for n in nodes:
            client.put_flow(n, normal_forwarding_flow())
        time.sleep(2)

        src, dst = net.get(args.src), net.get(args.dst)
        os.makedirs(args.capture_dir, exist_ok=True)
        pcap = os.path.abspath(os.path.join(args.capture_dir, f"{dst.name}_icmp.pcap"))
        capture = start_capture(dst, pcap)
        time.sleep(1)

        before = ping_matrix(net)

        flow = icmp_block_flow(rule_id, src=src.IP(), dst=dst.IP(),
                               icmp_type=ICMP_ECHO_REQUEST if args.echo_only else None)
        t0 = time.time()
        for n in nodes:
            client.put_flow(n, flow)
        wait_for_drop_rule(net.switches)
        info(f"*** Rule active on data plane after {time.time() - t0:.2f}s\n")

        after = ping_matrix(net)

        print("\n" + format_matrix("BEFORE rule", net.hosts, before))
        print("\n" + format_matrix("AFTER rule", net.hosts, after))
        print(f"\nOVS flows on {net.switches[1].name}:")
        print(net.switches[1].cmd(f"ovs-ofctl -O OpenFlow13 dump-flows {net.switches[1].name}"))

        if args.cli:
            CLI(net)
    finally:
        if capture:
            capture.terminate()
            capture.wait()
            info(f"*** Capture saved to {args.capture_dir}/\n")
        for n in nodes:
            try:
                client.delete_flow(n, rule_id)
                client.delete_flow(n, "baseline-normal")
            except ODLError as exc:
                info(f"*** Cleanup warning: {exc}\n")
        net.stop()


if __name__ == "__main__":
    main()
