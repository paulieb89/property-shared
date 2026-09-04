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


class TestCallerErrorMapping:
    """Caller mistakes must not be reported as our failure.

    A sector returned 502 Bad Gateway -- the API blaming itself for input that
    Rightmove can never resolve. Both endpoints build their own search URL, so
    both need the mapping; fixing only /search-url would leave identical input
    answered 422 on one route and 502 on the other.
    """

    SECTOR = "B5 7"
    UNKNOWN = "XX99 9XX"

    @pytest.mark.parametrize("path", ["/v1/rightmove/search-url", "/v1/rightmove/listings"])
    def test_a_sector_is_422_not_502(self, client, path):
        with patch.object(rightmove_router, "fetch_listings") as fetch:
            resp = client.get(path, params={"postcode": self.SECTOR})
        assert resp.status_code == 422, resp.text
        body = resp.json()["detail"]
        assert body["error"] == "invalid_postcode"
        assert body["retryable"] is False
        # The remedy must survive into the response, not just the log.
        assert "'B5'" in body["expected"]
        assert fetch.call_count == 0, "a refused input must not reach the scraper"

    @pytest.mark.parametrize("path", ["/v1/rightmove/search-url", "/v1/rightmove/listings"])
    def test_a_wellformed_unknown_postcode_is_404_not_502(self, client, path):
        with patch.object(rightmove_router, "fetch_listings") as fetch, patch(
            "property_core.rightmove_location.requests.get"
        ) as get:
            get.return_value.json.return_value = {"matches": []}
            get.return_value.raise_for_status.return_value = None
            resp = client.get(path, params={"postcode": self.UNKNOWN})
        assert resp.status_code == 404, resp.text
        assert resp.json()["detail"]["error"] == "rightmove_location_not_found"
        assert fetch.call_count == 0, "an absent location must not reach the scraper"

    @pytest.mark.parametrize("path", ["/v1/rightmove/search-url", "/v1/rightmove/listings"])
    def test_a_transport_failure_is_still_502_with_a_typed_body(self, client, path):
        import requests as _requests

        with patch(
            "property_core.rightmove_location.requests.get",
            side_effect=_requests.RequestException("upstream down"),
        ):
            resp = client.get(path, params={"postcode": "B5 4BX"})
        assert resp.status_code == 502, resp.text
        body = resp.json()["detail"]
        assert body["error"] == "rightmove_location_unavailable"
        assert body["retryable"] is True, "an outage is worth retrying; caller error is not"

    def test_listing_detail_mapping_is_unchanged(self, client):
        """Guard the fix from over-reaching.

        /listing/{id} takes a numeric id, not a postcode, and already maps
        correctly. It also carries a deliberate warning against catching
        ValueError there, since pydantic's ValidationError subclasses it and an
        upstream shape change would then be misreported as caller error.
        """
        with patch.object(rightmove_router, "fetch_listing") as fetch:
            assert client.get("/v1/rightmove/listing/abc").status_code == 422
            assert fetch.call_count == 0
            fetch.side_effect = ValueError("upstream shape changed")
            assert client.get("/v1/rightmove/listing/123").status_code == 502
