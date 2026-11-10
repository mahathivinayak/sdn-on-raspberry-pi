"""Small OpenDaylight RESTCONF client for OpenFlow inventory flows.

Supports both URL styles:
  rfc8040 (Fluorine+):  /rests/data/opendaylight-inventory:nodes/node=openflow:1/...
  legacy  (draft-02):   /restconf/config/opendaylight-inventory:nodes/node/openflow:1/...
"""
from __future__ import annotations

import logging
from urllib.parse import quote

import requests

log = logging.getLogger(__name__)

INV = "opendaylight-inventory:nodes"
TABLE = "flow-node-inventory:table"


class ODLError(RuntimeError):
    """The controller could not be reached or rejected a request."""


def _enc(value) -> str:
    return quote(str(value), safe=":")


def _node_sort_key(node_id: str):
    tail = node_id.rsplit(":", 1)[-1]
    return (0, int(tail)) if tail.isdigit() else (1, node_id)


class ODLClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 8181,
                 user: str = "admin", password: str = "admin",
                 api: str = "rfc8040", timeout: float = 10.0):
        if api not in ("rfc8040", "legacy"):
            raise ValueError("api must be 'rfc8040' or 'legacy'")
        self.base = f"http://{host}:{port}"
        self.api = api
        self.timeout = timeout
        self.session = requests.Session()
        self.session.auth = (user, password)
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
        })

    # ---------- URL building ----------
    def _url(self, node: str | None = None, table: int | None = None,
             flow_id: str | None = None, operational: bool = False) -> str:
        if self.api == "rfc8040":
            url = f"{self.base}/rests/data/{INV}"
            if node is not None:
                url += f"/node={_enc(node)}"
                if table is not None:
                    url += f"/{TABLE}={table}"
                    if flow_id is not None:
                        url += f"/flow={_enc(flow_id)}"
            return url

        ds = "operational" if operational else "config"
        url = f"{self.base}/restconf/{ds}/{INV}"
        if node is not None:
            url += f"/node/{_enc(node)}"
            if table is not None:
                url += f"/{TABLE}/{table}"
                if flow_id is not None:
                    url += f"/flow/{_enc(flow_id)}"
        return url

    def _read_params(self, operational: bool) -> dict | None:
        if self.api == "rfc8040":
            return {"content": "nonconfig" if operational else "config"}
        return None

    # ---------- HTTP ----------
    @staticmethod
    def _is_missing(resp: requests.Response) -> bool:
        # ODL returns 404, or 409 with error-tag "data-missing", for absent data
        return resp.status_code == 404 or (
            resp.status_code == 409 and "data-missing" in resp.text)

    def _request(self, method: str, url: str, *, params=None, body=None,
                 allow_missing: bool = False) -> requests.Response | None:
        log.debug("%s %s", method, url)
        try:
            resp = self.session.request(method, url, params=params, json=body,
                                        timeout=self.timeout)
        except requests.RequestException as exc:
            raise ODLError(f"Cannot reach OpenDaylight at {self.base}: {exc}") from exc

        if allow_missing and self._is_missing(resp):
            return None
        if resp.status_code == 401:
            raise ODLError("401 Unauthorized: check --user/--password")
        if resp.status_code >= 400:
            text = resp.text.strip().replace("\n", " ")
            raise ODLError(f"{method} {url} -> HTTP {resp.status_code}: {text[:300]}")
        return resp

    # ---------- public API ----------
    def list_nodes(self) -> list[str]:
        """OpenFlow switches currently connected (operational datastore)."""
        resp = self._request("GET", self._url(operational=True),
                             params=self._read_params(True), allow_missing=True)
        if resp is None or not resp.content:
            return []
        data = resp.json()
        container = data.get(INV) or data.get("nodes") or {}
        ids = [n["id"] for n in container.get("node", [])
               if str(n.get("id", "")).startswith("openflow:")]
        return sorted(ids, key=_node_sort_key)

    def put_flow(self, node: str, flow: dict) -> None:
        """Create or replace a flow in the config datastore."""
        table = flow.get("table_id", 0)
        url = self._url(node, table, flow["id"])
        self._request("PUT", url, body={"flow-node-inventory:flow": [flow]})
        log.info("PUT flow %s on %s (table %s)", flow["id"], node, table)

    def delete_flow(self, node: str, flow_id: str, table: int = 0) -> bool:
        """Remove a flow. Returns False if it was already gone."""
        resp = self._request("DELETE", self._url(node, table, flow_id), allow_missing=True)
        if resp is None:
            log.info("Flow %s not present on %s", flow_id, node)
            return False
        log.info("Deleted flow %s on %s", flow_id, node)
        return True

    def get_flows(self, node: str, table: int = 0, operational: bool = False) -> dict:
        """Table contents from config (what you asked for) or operational (what's on the switch)."""
        resp = self._request("GET", self._url(node, table, operational=operational),
                             params=self._read_params(operational), allow_missing=True)
        if resp is None or not resp.content:
            return {}
        return resp.json()
