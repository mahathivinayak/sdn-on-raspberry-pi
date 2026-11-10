"""Command-line tool for managing ICMP filter rules on OpenDaylight."""
from __future__ import annotations

import argparse
import json
import logging
import sys

from .flow_builder import ICMP_ECHO_REQUEST, icmp_block_flow, normal_forwarding_flow
from .odl_client import ODLClient, ODLError


def _targets(client: ODLClient, nodes: list[str] | None) -> list[str]:
    targets = nodes or client.list_nodes()
    if not targets:
        raise ODLError("No OpenFlow switches connected to the controller.")
    return targets


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8181)
    p.add_argument("--user", default="admin")
    p.add_argument("--password", default="admin")
    p.add_argument("--api", choices=["rfc8040", "legacy"], default="rfc8040")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("nodes", help="list connected switches")

    b = sub.add_parser("baseline", help="install NORMAL forwarding flow")
    b.add_argument("--node", action="append", help="repeatable; default = all switches")

    blk = sub.add_parser("block-icmp", help="install an ICMP drop rule")
    blk.add_argument("--id", required=True)
    blk.add_argument("--src")
    blk.add_argument("--dst")
    blk.add_argument("--echo-only", action="store_true",
                     help="match only echo-request (type 8), i.e. one-directional")
    blk.add_argument("--priority", type=int, default=500)
    blk.add_argument("--node", action="append")

    ub = sub.add_parser("unblock", help="remove a rule by id")
    ub.add_argument("--id", required=True)
    ub.add_argument("--node", action="append")

    ls = sub.add_parser("list", help="show flows on a switch")
    ls.add_argument("--node", required=True)
    ls.add_argument("--operational", action="store_true",
                    help="show what's actually on the switch, not just config")

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(message)s")
    client = ODLClient(args.host, args.port, args.user, args.password, args.api)

    try:
        if args.cmd == "nodes":
            for n in client.list_nodes():
                print(n)
        elif args.cmd == "baseline":
            for n in _targets(client, args.node):
                client.put_flow(n, normal_forwarding_flow())
        elif args.cmd == "block-icmp":
            if not (args.src or args.dst):
                p.error("give at least --src or --dst")
            flow = icmp_block_flow(args.id, args.src, args.dst,
                                   ICMP_ECHO_REQUEST if args.echo_only else None,
                                   args.priority)
            for n in _targets(client, args.node):
                client.put_flow(n, flow)
        elif args.cmd == "unblock":
            for n in _targets(client, args.node):
                client.delete_flow(n, args.id)
        elif args.cmd == "list":
            print(json.dumps(client.get_flows(args.node, operational=args.operational),
                             indent=2))
    except (ODLError, ValueError) as exc:
        logging.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
