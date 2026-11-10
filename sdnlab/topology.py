"""Mininet topology: one core switch, two edge switches, two hosts per edge.

    h1  h2        h3  h4
     \\  /          \\  /
      s2 ---- s1 ---- s3

Run standalone:  sudo python3 -m sdnlab.topology --controller-ip 127.0.0.1
Or with mn:      sudo mn --custom sdnlab/topology.py --topo testbed \\
                     --controller remote,ip=127.0.0.1,port=6653 \\
                     --switch ovs,protocols=OpenFlow13
"""
from __future__ import annotations

import argparse
from functools import partial

from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import setLogLevel
from mininet.net import Mininet
from mininet.node import OVSSwitch, RemoteController
from mininet.topo import Topo


class TestbedTopo(Topo):
    def build(self, edges: int = 2, hosts_per_edge: int = 2, bw: int = 10):
        core = self.addSwitch("s1", protocols="OpenFlow13")
        n = 1
        for e in range(edges):
            edge = self.addSwitch(f"s{e + 2}", protocols="OpenFlow13")
            self.addLink(core, edge, bw=bw * 10, delay="1ms")
            for _ in range(hosts_per_edge):
                host = self.addHost(f"h{n}", ip=f"10.0.0.{n}/24",
                                    mac=f"00:00:00:00:00:{n:02x}")
                self.addLink(host, edge, bw=bw)
                n += 1


topos = {"testbed": lambda: TestbedTopo()}


def build_net(controller_ip: str, of_port: int = 6653) -> Mininet:
    return Mininet(
        topo=TestbedTopo(),
        switch=OVSSwitch,
        link=TCLink,
        controller=partial(RemoteController, ip=controller_ip, port=of_port),
        autoSetMacs=False,
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--controller-ip", default="127.0.0.1")
    p.add_argument("--of-port", type=int, default=6653)
    args = p.parse_args()

    setLogLevel("info")
    net = build_net(args.controller_ip, args.of_port)
    net.start()
    try:
        CLI(net)
    finally:
        net.stop()


if __name__ == "__main__":
    main()
