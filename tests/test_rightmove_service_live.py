import os
import time

import pytest

from app.services.rightmove_service import RightmoveService


@pytest.mark.anyio
async def test_rightmove_service_live() -> None:
    if os.getenv("RUN_LIVE_TESTS") != "1":
        pytest.skip("Set RUN_LIVE_TESTS=1 to run live network tests")

    service = RightmoveService()
    postcode = os.getenv("RIGHTMOVE_TEST_POSTCODE", "SW1A 1AA")
    property_type = os.getenv("RIGHTMOVE_TEST_TYPE", "sale")
    max_pages = int(os.getenv("RIGHTMOVE_TEST_MAX_PAGES", "1"))

    start = time.perf_counter()
    url = await service.build_search_url(postcode=postcode, property_type=property_type)
    listings = await service.listings(search_url=url, max_pages=max_pages)
    elapsed = time.perf_counter() - start

    print(f"Rightmove live fetch took {elapsed:.2f}s")
    print(f"Search URL: {url}")
    print(f"Listings: {len(listings)}")
    for idx, item in enumerate(listings[:3], start=1):
        print(f"{idx}. {item.price} {item.address} {item.url}")

    assert url.startswith("https://www.rightmove.co.uk/")
