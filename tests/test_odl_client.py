import pytest

from sdnlab.odl_client import ODLClient


def test_rfc8040_flow_url():
    c = ODLClient("10.1.1.1", 8181, api="rfc8040")
    assert c._url("openflow:2", 0, "block-icmp") == (
        "http://10.1.1.1:8181/rests/data/opendaylight-inventory:nodes"
        "/node=openflow:2/flow-node-inventory:table=0/flow=block-icmp")


def test_legacy_flow_urls():
    c = ODLClient("10.1.1.1", 8181, api="legacy")
    assert c._url("openflow:2", 0, "x") == (
        "http://10.1.1.1:8181/restconf/config/opendaylight-inventory:nodes"
        "/node/openflow:2/flow-node-inventory:table/0/flow/x")
    assert "/restconf/operational/" in c._url(operational=True)


def test_read_params():
    assert ODLClient(api="rfc8040")._read_params(True) == {"content": "nonconfig"}
    assert ODLClient(api="legacy")._read_params(True) is None


def test_bad_api():
    with pytest.raises(ValueError):
        ODLClient(api="v3")
