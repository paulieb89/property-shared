"""Deterministic harness for the PR 1 inertness gate.

Drives the four PPD consumer surfaces against a FIXED in-memory fixture with the
transport patched out, so the output depends only on our own code. No network
request is made, and no live SPARQL response is ever compared byte-for-byte --
those are not stable and the test would be measuring the upstream.

Kept importable and self-contained so the identical harness can be run against
an older checkout to prove a change is inert.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from unittest.mock import patch

def _lit(v):
    return {"type": "literal", "value": str(v)}


def _uri(v):
    return {"type": "uri", "value": v}


_PT = "http://landregistry.data.gov.uk/def/common/"
_TC = "http://landregistry.data.gov.uk/def/ppi/"

FIXTURE_ROWS = [
    {
        "transaction_id": "{AAAAAAAA-0000-0000-0000-000000000001}",
        "price": 250000, "date": "2025-06-01", "postcode": "B5 4BX",
        "property_type": "F", "estate_type": "L", "transaction_category": "A",
        "new_build": False, "paon": "33", "saon": "APARTMENT 1",
        "street": "ESSEX STREET", "town": "BIRMINGHAM",
        "county": "WEST MIDLANDS", "district": "BIRMINGHAM", "locality": None,
    },
    {
        "transaction_id": "{AAAAAAAA-0000-0000-0000-000000000002}",
        "price": 310000, "date": "2025-03-14", "postcode": "B5 4BX",
        "property_type": "T", "estate_type": "F", "transaction_category": "A",
        "new_build": False, "paon": "35", "saon": None,
        "street": "ESSEX STREET", "town": "BIRMINGHAM",
        "county": "WEST MIDLANDS", "district": "BIRMINGHAM", "locality": None,
    },
    {
        "transaction_id": "{AAAAAAAA-0000-0000-0000-000000000003}",
        "price": 190000, "date": "2024-11-02", "postcode": "B5 4BY",
        "property_type": "F", "estate_type": "L", "transaction_category": "A",
        "new_build": True, "paon": "12", "saon": None,
        "street": "GOOCH STREET", "town": "BIRMINGHAM",
        "county": "WEST MIDLANDS", "district": "BIRMINGHAM", "locality": None,
    },
]


def _bindings():
    """The fixture as raw SPARQL bindings.

    Patching `_fetch_sparql` -- the real transport boundary -- rather than a
    service-level method means the golden exercises the actual parsing,
    filtering and containment path, and does not silently stop covering it when
    an internal call site is refactored.
    """
    type_uri = {"F": "flat-maisonette", "D": "detached", "S": "semi-detached",
                "T": "terraced", "O": "otherPropertyType"}
    estate_uri = {"F": "freehold", "L": "leasehold"}
    cat_uri = {"A": "standardPricePaidTransaction", "B": "additionalPricePaidTransaction"}
    out = []
    for r in FIXTURE_ROWS:
        out.append({
            "transactionId": _lit(r["transaction_id"]),
            "pricePaid": _lit(r["price"]),
            "transactionDate": _lit(r["date"]),
            "postcode": _lit(r["postcode"]),
            "propertyType": _uri(_PT + type_uri[r["property_type"]]),
            "estateType": _uri(_PT + estate_uri[r["estate_type"]]),
            "transactionCategory": _uri(_TC + cat_uri[r["transaction_category"]]),
            "newBuild": _lit("true" if r["new_build"] else "false"),
            "paon": _lit(r["paon"]), "saon": _lit(r["saon"] or ""),
            "street": _lit(r["street"]), "town": _lit(r["town"]),
            "county": _lit(r["county"]), "locality": _lit(r["locality"] or ""),
            "district": _lit(r["district"]),
        })
    return {"results": {"bindings": out}}


#: Credentials that would otherwise make a captured response depend on the
#: developer's shell or .env. `/v1/meta/integrations` reports EPC as configured
#: purely from `os.getenv("EPC_API_TOKEN")`, so without this the golden differs
#: between a developer machine and CI -- and between an isolated run and the full
#: suite, where other tests clear these vars.
AMBIENT_CREDENTIAL_VARS = ("EPC_API_TOKEN", "EPC_API_EMAIL", "EPC_API_KEY")


@contextmanager
def deterministic_ppd():
    """Patch the transport seam, neutralise ambient credentials, block sockets."""
    import os
    import socket

    def _no_network(*a, **k):  # pragma: no cover - only fires on regression
        raise AssertionError("golden inertness test attempted a network connection")

    payload = _bindings()
    # patch.dict with no overrides snapshots os.environ and restores it on exit;
    # the vars are then removed inside the block. (Passing {var: None} does not
    # work -- os.environ values must be strings.)
    with patch.dict(os.environ), patch(
        "property_core.ppd_client.PricePaidDataClient._fetch_sparql",
        return_value=payload,
    ), patch.object(socket.socket, "connect", _no_network):
        for var in AMBIENT_CREDENTIAL_VARS:
            os.environ.pop(var, None)
        yield


def _sortable(obj):
    """Stable JSON for comparison."""
    return json.loads(json.dumps(obj, sort_keys=True, default=str))


def capture() -> dict:
    """Run every PPD surface in PR 1 scope and return a comparable structure."""
    out: dict = {}
    with deterministic_ppd():
        from property_core import PPDService

        svc = PPDService()

        comps = svc.comps(postcode="B5 4BX", months=24, limit=50, auto_escalate=False)
        out["core.comps"] = _sortable(comps.model_dump(mode="json"))

        search = svc.search_transactions(postcode="B5 4BX", postcode_prefix=None, limit=10)
        out["core.search_transactions"] = _sortable(
            {
                **{k: v for k, v in search.items() if k != "results"},
                "results": [t.model_dump(mode="json", exclude_none=True)
                            for t in search["results"]],
            }
        )

        from app.mcp.server import ppd_transactions as plain_tool
        # FastMCP may return either the function or a Tool wrapping it.
        plain_fn = getattr(plain_tool, "fn", plain_tool)
        out["mcp.plain.ppd_transactions"] = _sortable(
            plain_fn(postcode="B5 4BX", limit=10)
        )

        from property_app.tools import search_ppd_transactions as app_tool
        out["mcp.app.ppd_transactions"] = _sortable(
            app_tool(postcode="B5 4BX", limit=10)
        )

        # REST surfaces, driven through the real app with the same patched seam.
        from fastapi.testclient import TestClient

        from app.main import app as fastapi_app

        client = TestClient(fastapi_app)
        for key, url in (
            ("rest.comps", "/v1/ppd/comps?postcode=B5%204BX&months=24&limit=50"),
            ("rest.transactions", "/v1/ppd/transactions?postcode=B5%204BX&limit=10"),
            ("rest.meta_integrations", "/v1/meta/integrations"),
        ):
            resp = client.get(url)
            out[key] = _sortable({"status": resp.status_code, "body": resp.json()})

        # CLI, in core mode (no --api-url), through the real Typer app.
        from typer.testing import CliRunner

        from property_cli.main import app as cli_app

        result = CliRunner().invoke(
            cli_app, ["ppd", "comps", "B5 4BX", "--months", "24", "--limit", "50"]
        )
        out["cli.ppd_comps"] = _sortable(
            {"exit_code": result.exit_code, "stdout": result.stdout}
        )
    return out


if __name__ == "__main__":  # generate a golden file
    import sys

    print(json.dumps(capture(), indent=2, sort_keys=True))
    sys.exit(0)
