import os
import urllib.error

import pytest

from property_core.ppd_service import PPDService


@pytest.mark.skipif(os.getenv("RUN_LIVE_TESTS") != "1", reason="Set RUN_LIVE_TESTS=1 to run live tests")
def test_ppd_address_search_live() -> None:
    service = PPDService()
    limit = 5
    # Birmingham city centre Broad Street has frequent transactions.
    try:
        res = service.address_search(
            postcode_prefix="B1",
            street="Broad Street",
            paon=None,
            saon=None,
            town=None,
            county=None,
            postcode=None,
            limit=limit,
        )
    except urllib.error.HTTPError as exc:
        # Upstream SPARQL endpoint can return 503 under load; skip instead of failing CI.
        pytest.skip(f"PPD endpoint unavailable: {exc}")

    assert res["count"] > 0
    assert res["count"] <= limit
    assert all(tx.postcode and tx.postcode.startswith("B1") for tx in res["results"] if tx.postcode)
