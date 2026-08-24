"""Endpoint-level tests for app/api/v1/rightmove.py.

This router previously had no test coverage at all, while exposing two of the
three confirmed SSRF entry points:
  * GET /rightmove/listings?search_url=<anything>  -> fetched server-side
  * GET /rightmove/listing/{property_id}           -> URLs passed straight through
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import rightmove as rightmove_router


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(rightmove_router.router, prefix="/v1")
    return TestClient(app)


class TestListingDetailPathValidation:
    @pytest.mark.parametrize(
        "raw",
        [
            "https:%2F%2Fevil.example%2Fx",
            "..%2F..%2Fetc%2Fpasswd",
            "abc123",
            "12a",
            "9" * 13,
            "-1",
        ],
    )
    def test_non_numeric_ids_rejected_at_routing_layer(self, client, raw):
        with patch.object(rightmove_router, "fetch_listing") as mock_fetch:
            resp = client.get(f"/v1/rightmove/listing/{raw}")
        assert resp.status_code in (404, 422), resp.status_code
        mock_fetch.assert_not_called()

    def test_listing_url_is_rejected_by_the_public_rest_surface(self, client):
        """The library accepts a canonical URL; this public surface does not."""
        with patch.object(rightmove_router, "fetch_listing") as mock_fetch:
            resp = client.get(
                "/v1/rightmove/listing/https%3A%2F%2Fwww.rightmove.co.uk%2Fproperties%2F123456"
            )
        assert resp.status_code in (404, 422)
        mock_fetch.assert_not_called()

    def test_numeric_id_reaches_the_service(self, client):
        with patch.object(rightmove_router, "fetch_listing") as mock_fetch:
            mock_fetch.return_value = _stub_detail()
            resp = client.get("/v1/rightmove/listing/123456")
        assert resp.status_code == 200
        mock_fetch.assert_called_once_with("123456")


class TestListingsStructuredFilters:
    def test_raw_search_url_is_no_longer_accepted(self, client):
        """The old contract must be gone: search_url alone can't drive a fetch."""
        with patch.object(rightmove_router, "fetch_listings") as mock_fetch:
            resp = client.get(
                "/v1/rightmove/listings",
                params={"search_url": "https://evil.example/x"},
            )
        assert resp.status_code == 422, "postcode is now required"
        mock_fetch.assert_not_called()

    def test_postcode_builds_url_server_side(self, client):
        built = "https://www.rightmove.co.uk/property-for-sale/find.html?locationIdentifier=X"
        with patch.object(rightmove_router, "RightmoveLocationAPI") as mock_api, patch.object(
            rightmove_router, "fetch_listings"
        ) as mock_fetch:
            mock_api.return_value.build_search_url.return_value = built
            mock_fetch.return_value = []
            resp = client.get("/v1/rightmove/listings", params={"postcode": "NG1 1AA"})

        assert resp.status_code == 200
        # The URL handed to the scraper came from the builder, not from the caller.
        assert mock_fetch.call_args.args[0] == built
        assert mock_api.return_value.build_search_url.call_args.args[0] == "NG1 1AA"

    def test_caller_cannot_smuggle_a_host_through_filters(self, client):
        """Even with an injected search_url param, the fetched URL is the built one."""
        built = "https://www.rightmove.co.uk/property-for-sale/find.html?locationIdentifier=X"
        with patch.object(rightmove_router, "RightmoveLocationAPI") as mock_api, patch.object(
            rightmove_router, "fetch_listings"
        ) as mock_fetch:
            mock_api.return_value.build_search_url.return_value = built
            mock_fetch.return_value = []
            resp = client.get(
                "/v1/rightmove/listings",
                params={"postcode": "NG1 1AA", "search_url": "https://evil.example/x"},
            )

        assert resp.status_code == 200
        assert mock_fetch.call_args.args[0] == built
        assert "evil.example" not in str(mock_fetch.call_args)


def _stub_detail():
    from property_core.models.rightmove import RightmoveListingDetail

    return RightmoveListingDetail(
        id=123456, url="https://www.rightmove.co.uk/properties/123456"
    )
