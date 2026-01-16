import os

import pytest

from app.services.ppd_service import PPDService


@pytest.mark.skipif(os.getenv("RUN_LIVE_TESTS") != "1", reason="Set RUN_LIVE_TESTS=1 to run live tests")
def test_ppd_form_search_live() -> None:
    service = PPDService()
    limit = 5
    # Birmingham city centre Broad Street has frequent transactions.
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

    assert res.count > 0
    assert res.count <= limit
    assert all(tx.postcode and tx.postcode.startswith("B1") for tx in res.results if tx.postcode)
