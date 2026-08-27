"""PR 2 — descriptions must not overclaim, and offset paging must warn.

Three documentation/contract defects on the live path:

* Both `ppd_transactions` tool descriptions imply unbounded history. These
  strings are what an LLM routes on, so they are part of the contract.
* The `record_status` parameter documentation misdescribes what it does. The
  filter stays disabled; only the wording is corrected.
* `offset` is not a stable cursor -- the ordering is not guaranteed total across
  pages, so deep offsets can repeat or omit rows. Callers are not told.

Spec: docs/design/ppd-source-routing.md sections 2.7.5, 2.7.6 and 3.3.
"""

from __future__ import annotations

import inspect
from unittest.mock import patch

import pytest

from property_core.ppd_client import PricePaidDataClient
from property_core.ppd_service import PPDService

EMPTY = {"results": {"bindings": []}}


def _plain_tool():
    from app.mcp.server import ppd_transactions

    return getattr(ppd_transactions, "fn", ppd_transactions)


def _app_tool():
    from property_app.tools import ppd_transactions

    return getattr(ppd_transactions, "fn", ppd_transactions)


# --------------------------------------------------------------------------
# Tool descriptions
# --------------------------------------------------------------------------

@pytest.mark.parametrize("getter", [_plain_tool, _app_tool],
                         ids=["plain-server", "mcp-app"])
def test_ppd_transactions_does_not_claim_every_recorded_transaction(getter):
    doc = inspect.getdoc(getter()) or ""
    lowered = doc.lower()
    assert "every recorded transaction" not in lowered, doc
    assert "unbounded" not in lowered


@pytest.mark.parametrize("getter", [_plain_tool, _app_tool],
                         ids=["plain-server", "mcp-app"])
def test_ppd_transactions_states_it_returns_up_to_limit_most_recent(getter):
    doc = (inspect.getdoc(getter()) or "").lower()
    assert "most recent" in doc, doc
    assert "limit" in doc, doc


@pytest.mark.parametrize("getter", [_plain_tool, _app_tool],
                         ids=["plain-server", "mcp-app"])
def test_ppd_transactions_warns_it_is_not_a_complete_history(getter):
    doc = (inspect.getdoc(getter()) or "").lower()
    assert "not a complete" in doc or "not complete" in doc, doc


def test_plain_server_instructions_do_not_advertise_unbounded_history():
    from app.mcp.server import mcp

    instructions = (mcp.instructions or "").lower()
    assert "ppd_transactions for specific property history" not in instructions, (
        "server instructions still describe the tool as a history lookup"
    )


# --------------------------------------------------------------------------
# record_status documentation
# --------------------------------------------------------------------------

def test_record_status_filter_remains_disabled():
    """Only the wording changes -- behaviour must not."""
    from property_core.ppd_client import UnsupportedRecordStatusFilterError

    client = PricePaidDataClient()
    with pytest.raises(UnsupportedRecordStatusFilterError):
        client.sparql_search(postcode="B5 4BX", record_status="A", limit=5)


def test_record_status_docs_do_not_imply_the_filter_works():
    import app.api.v1.ppd as rest

    doc = inspect.getsource(rest.transactions).lower()
    assert "unsupported" in doc or "not supported" in doc
    for claim in ("filter by record status", "filters by record status"):
        assert claim not in doc, f"docs still claim the filter works: {claim!r}"


def test_rest_rejects_record_status_with_422():
    from fastapi.testclient import TestClient

    from app.main import app

    r = TestClient(app).get("/v1/ppd/transactions?postcode=B5%204BX&record_status=A")
    assert r.status_code == 422


# --------------------------------------------------------------------------
# Offset pagination instability
# --------------------------------------------------------------------------

def test_offset_zero_emits_no_pagination_warning():
    svc = PPDService()
    with patch.object(PricePaidDataClient, "_fetch_sparql", return_value=EMPTY):
        result = svc.search_transactions(postcode="B5 4BX", postcode_prefix=None,
                                         limit=10, offset=0)
    assert not any("offset" in w.lower() for w in result["warnings"])


@pytest.mark.parametrize("offset", [1, 10, 500])
def test_nonzero_offset_warns_that_paging_is_unstable(offset):
    svc = PPDService()
    with patch.object(PricePaidDataClient, "_fetch_sparql", return_value=EMPTY):
        result = svc.search_transactions(postcode="B5 4BX", postcode_prefix=None,
                                         limit=10, offset=offset)
    warns = " ".join(result["warnings"]).lower()
    assert "offset" in warns, result["warnings"]
    assert "repeat" in warns or "omit" in warns or "unstable" in warns, result["warnings"]


def test_rest_surfaces_the_offset_warning():
    from fastapi.testclient import TestClient

    from app.main import app

    with patch.object(PricePaidDataClient, "_fetch_sparql", return_value=EMPTY):
        r = TestClient(app).get("/v1/ppd/transactions?postcode=B5%204BX&limit=10&offset=20")
    assert r.status_code == 200
    assert any("offset" in w.lower() for w in r.json().get("warnings", []))


def test_offset_documentation_states_the_instability():
    import app.api.v1.ppd as rest

    src = inspect.getsource(rest.transactions).lower()
    assert "offset" in src
    assert "unstable" in src or "repeat" in src or "omit" in src, (
        "offset parameter is not documented as an unstable cursor"
    )
