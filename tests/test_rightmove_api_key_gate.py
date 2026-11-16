"""The Rightmove surface is key-gated on both REST and MCP-over-HTTP.

Both surfaces expose the same listings, so a gate on one alone just moves a
scraper to the other. The MCP cases go through the real HTTP app with a bare
`tools/call` and no initialize, because that is what the scraper that prompted
this gate actually sends.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.api_keys import CONTACT_EMAIL, CONTACT_URL, presented_key

KEY = "test-key-123"


@pytest.fixture()
def keyed(monkeypatch):
    monkeypatch.setenv("RIGHTMOVE_API_KEYS", f"other-key, {KEY}")


@pytest.fixture()
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


def _mcp_call(client, tool: str, args: dict, headers: dict | None = None):
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": tool, "arguments": args}}
    resp = client.post(
        "/mcp", json=body,
        headers={"Accept": "application/json, text/event-stream",
                 "User-Agent": "Mozilla/5.0", **(headers or {})},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["result"]


# --- REST ---


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong"}, {"Authorization": "Bearer wrong"}])
def test_rest_refuses_without_a_valid_key(keyed, client, headers):
    with patch("app.api.v1.rightmove.fetch_listing") as fetch:
        resp = client.get("/v1/rightmove/listing/123456", headers=headers)
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"].startswith("Bearer")
    detail = resp.json()["detail"]
    assert detail["error"] == "api_key_required"
    assert CONTACT_EMAIL in detail["message"] and CONTACT_URL in detail["message"]
    fetch.assert_not_called()


@pytest.mark.parametrize("headers", [{"X-API-Key": KEY}, {"Authorization": f"Bearer {KEY}"}])
def test_rest_admits_a_valid_key(keyed, client, headers):
    with patch("app.api.v1.rightmove.fetch_listing", side_effect=RuntimeError("stub")) as fetch:
        resp = client.get("/v1/rightmove/listing/123456", headers=headers)
    assert resp.status_code == 502  # past the gate, into the stubbed fetch
    fetch.assert_called_once_with("123456")


def test_rest_fails_closed_when_no_keys_are_configured(monkeypatch, client):
    monkeypatch.delenv("RIGHTMOVE_API_KEYS", raising=False)
    with patch("app.api.v1.rightmove.fetch_listing") as fetch:
        resp = client.get("/v1/rightmove/listing/123456", headers={"X-API-Key": ""})
    assert resp.status_code == 401
    fetch.assert_not_called()


def test_other_rest_routes_stay_open(keyed, client):
    resp = client.get("/v1/stamp-duty", params={"price": 300000})
    assert resp.status_code != 401


# --- MCP over HTTP ---


@pytest.mark.parametrize("tool,args", [
    ("rightmove_listing", {"property_id": "123456"}),
    ("rightmove_search", {"postcode": "NG1 1AA"}),
])
def test_mcp_refuses_a_bare_tools_call_without_a_key(keyed, client, tool, args):
    with patch("property_core.fetch_listing") as fl, patch("property_core.fetch_listings") as fls:
        result = _mcp_call(client, tool, args)
    assert result["isError"] is True
    payload = json.loads(result["content"][0]["text"])
    assert payload["error_category"] == "auth_required"
    assert payload["attempted"] == tool
    assert CONTACT_EMAIL in payload["description"] and CONTACT_URL in payload["description"]
    fl.assert_not_called()
    fls.assert_not_called()


def test_mcp_admits_a_valid_key(keyed, client):
    with patch("property_core.fetch_listing", side_effect=RuntimeError("stub")) as fl:
        result = _mcp_call(client, "rightmove_listing", {"property_id": "123456"},
                           headers={"Authorization": f"Bearer {KEY}"})
    assert result["isError"] is True
    assert "auth_required" not in result["content"][0]["text"]
    fl.assert_called_once_with("123456")


def test_mcp_other_tools_stay_open(keyed, client):
    result = _mcp_call(client, "stamp_duty", {"price": 300000})
    assert result.get("isError") is not True


def test_mcp_tool_list_still_advertises_the_gated_tools(keyed, client):
    resp = client.post(
        "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        headers={"Accept": "application/json, text/event-stream"},
    )
    names = {t["name"] for t in resp.json()["result"]["tools"]}
    assert {"rightmove_listing", "rightmove_search"} <= names


# --- key extraction ---


@pytest.mark.parametrize("headers,expected", [
    ({"x-api-key": " k "}, "k"),
    ({"authorization": "Bearer k"}, "k"),
    ({"authorization": "bearer k"}, "k"),
    ({"authorization": "Basic k"}, None),
    ({"authorization": "Bearer "}, None),
    ({}, None),
])
def test_presented_key(headers, expected):
    assert presented_key(headers) == expected
