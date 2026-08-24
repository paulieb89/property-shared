"""record_status filtering on SPARQL search was a guaranteed crash.

PricePaidDataClient.sparql_search() builds PPDTransaction objects, then filtered
them with `t.record_status`. PPDTransaction has no such field — it belongs to
PPDTransactionRecord, the Linked Data detail model built by
get_transaction_record(). So any caller passing record_status hit AttributeError
as soon as the query returned a single row.

It now fails fast with a specific, actionable error instead.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import ppd as ppd_router
from property_core.ppd_client import (
    PricePaidDataClient,
    UnsupportedRecordStatusFilterError,
)
from property_core.ppd_service import PPDService

# One realistic SPARQL binding — enough for the old code to reach the filter.
_BINDINGS = {
    "results": {
        "bindings": [
            {
                "transactionId": {"value": "abc-123"},
                "pricePaid": {"value": "450000"},
                "transactionDate": {"value": "2024-03-01"},
                "postcode": {"value": "SW1A 1AA"},
                "propertyType": {
                    "value": "http://landregistry.data.gov.uk/def/common/flat-maisonette"
                },
                "estateType": {"value": "http://landregistry.data.gov.uk/def/common/leasehold"},
                "transactionCategory": {
                    "value": "http://landregistry.data.gov.uk/def/ppi/standardPricePaidTransaction"
                },
                "newBuild": {"value": "false"},
                "paon": {"value": "10"},
                "street": {"value": "DOWNING STREET"},
            }
        ]
    }
}


class TestClientLevel:
    def test_record_status_raises_specific_error_not_attributeerror(self):
        client = PricePaidDataClient()
        with patch.object(client, "_fetch_sparql", return_value=_BINDINGS) as mock_fetch:
            with pytest.raises(UnsupportedRecordStatusFilterError) as excinfo:
                client.sparql_search(postcode="SW1A 1AA", record_status="A")
        # Fails before building or issuing the query at all.
        mock_fetch.assert_not_called()
        assert "get_transaction_record" in str(excinfo.value)

    def test_error_is_a_valueerror_for_callers_catching_invalid_input(self):
        assert issubclass(UnsupportedRecordStatusFilterError, ValueError)

    def test_search_without_record_status_still_works(self):
        client = PricePaidDataClient()
        with patch.object(client, "_fetch_sparql", return_value=_BINDINGS):
            results = client.sparql_search(postcode="SW1A 1AA")
        assert len(results) == 1
        assert results[0].price == 450000

    def test_other_client_side_filters_are_unaffected(self):
        client = PricePaidDataClient()
        with patch.object(client, "_fetch_sparql", return_value=_BINDINGS):
            flats = client.sparql_search(postcode="SW1A 1AA", property_type="F")
            houses = client.sparql_search(postcode="SW1A 1AA", property_type="D")
        assert len(flats) == 1
        assert houses == []


class TestServiceLevel:
    def test_service_propagates_the_specific_error(self):
        service = PPDService()
        with patch.object(service.client, "_fetch_sparql", return_value=_BINDINGS):
            with pytest.raises(UnsupportedRecordStatusFilterError):
                service.search_transactions(postcode="SW1A 1AA", postcode_prefix=None, record_status="A")


class TestApiLayer:
    @pytest.fixture()
    def client(self):
        app = FastAPI()
        app.include_router(ppd_router.router, prefix="/v1")
        return TestClient(app)

    def test_record_status_returns_422_not_502(self, client):
        """Invalid input is a caller error, not 'upstream unavailable'."""
        with patch.object(ppd_router.service.client, "_fetch_sparql", return_value=_BINDINGS):
            resp = client.get(
                "/v1/ppd/transactions", params={"postcode": "SW1A 1AA", "record_status": "A"}
            )
        assert resp.status_code == 422, resp.text
        assert "get_transaction_record" in resp.json()["detail"]

    def test_unrelated_failures_still_map_to_502(self, client):
        """Narrowing the except clause must not reclassify genuine upstream errors."""
        with patch.object(
            ppd_router.service, "search_transactions", side_effect=RuntimeError("upstream down")
        ):
            resp = client.get("/v1/ppd/transactions", params={"postcode": "SW1A 1AA"})
        assert resp.status_code == 502, resp.text

    def test_unrelated_valueerror_is_not_swallowed_as_422(self, client):
        """Only the record_status error maps to 422 — not every ValueError.

        A ValueError from elsewhere usually signals an internal bug, and
        reporting it as a caller error would hide it.
        """
        with patch.object(
            ppd_router.service, "search_transactions", side_effect=ValueError("internal parse bug")
        ):
            resp = client.get("/v1/ppd/transactions", params={"postcode": "SW1A 1AA"})
        assert resp.status_code == 502, resp.text

    def test_search_without_record_status_still_succeeds(self, client):
        with patch.object(ppd_router.service.client, "_fetch_sparql", return_value=_BINDINGS):
            resp = client.get("/v1/ppd/transactions", params={"postcode": "SW1A 1AA"})
        assert resp.status_code == 200
        assert resp.json()["count"] == 1
