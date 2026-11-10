import pytest

from sdnlab.flow_builder import (BASELINE_FLOW_ID, ICMP_ECHO_REQUEST,
                                 icmp_block_flow, normal_forwarding_flow)


def test_block_flow_match():
    f = icmp_block_flow("block-1", src="10.0.0.1", dst="10.0.0.3")
    m = f["match"]
    assert m["ethernet-match"]["ethernet-type"]["type"] == 0x0800
    assert m["ip-match"]["ip-protocol"] == 1
    assert m["ipv4-source"] == "10.0.0.1/32"
    assert m["ipv4-destination"] == "10.0.0.3/32"
    assert "icmpv4-match" not in m
    assert f["priority"] == 500


def test_block_flow_is_drop():
    f = icmp_block_flow("block-1", dst="10.0.0.3")
    action = f["instructions"]["instruction"][0]["apply-actions"]["action"][0]
    assert "drop-action" in action


def test_echo_only():
    f = icmp_block_flow("b", src="10.0.0.1", icmp_type=ICMP_ECHO_REQUEST)
    assert f["match"]["icmpv4-match"]["icmpv4-type"] == 8


def test_subnet_prefix_kept():
    f = icmp_block_flow("b", src="10.0.0.0/24")
    assert f["match"]["ipv4-source"] == "10.0.0.0/24"


@pytest.mark.parametrize("bad", ["10.0.0.999", "not-an-ip", "10.0.0.1/40"])
def test_bad_ip_rejected(bad):
    with pytest.raises(ValueError):
        icmp_block_flow("b", src=bad)


@pytest.mark.parametrize("bad_id", ["", "has space", "a/b"])
def test_bad_flow_id_rejected(bad_id):
    with pytest.raises(ValueError):
        icmp_block_flow(bad_id, src="10.0.0.1")


def test_baseline_flow():
    f = normal_forwarding_flow()
    assert f["id"] == BASELINE_FLOW_ID
    assert f["priority"] == 1
    assert f["match"] == {}
    out = f["instructions"]["instruction"][0]["apply-actions"]["action"][0]["output-action"]
    assert out["output-node-connector"] == "NORMAL"
