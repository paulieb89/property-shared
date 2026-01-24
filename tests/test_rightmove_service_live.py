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


@pytest.mark.anyio
async def test_rightmove_rental_listings_live() -> None:
    """Test that rental-specific fields are populated correctly."""
    if os.getenv("RUN_LIVE_TESTS") != "1":
        pytest.skip("Set RUN_LIVE_TESTS=1 to run live network tests")

    service = RightmoveService()
    postcode = os.getenv("RIGHTMOVE_TEST_POSTCODE", "SW1A 1AA")

    start = time.perf_counter()
    url = await service.build_search_url(postcode=postcode, property_type="rent")
    listings = await service.listings(search_url=url, max_pages=1)
    elapsed = time.perf_counter() - start

    print(f"Rightmove rental fetch took {elapsed:.2f}s")
    print(f"Search URL: {url}")
    print(f"Rental Listings: {len(listings)}")

    assert url.startswith("https://www.rightmove.co.uk/property-to-rent/")
    assert len(listings) > 0, "Expected at least one rental listing"

    # Verify rental-specific fields are populated
    listing = listings[0]
    print(f"First listing: £{listing.price} {listing.price_frequency}")
    print(f"  let_available_date: {listing.let_available_date}")
    print(f"  transaction_type: {listing.transaction_type}")

    assert listing.transaction_type == "rent", "Expected transaction_type='rent'"
    assert listing.price_frequency in ("monthly", "weekly"), f"Unexpected frequency: {listing.price_frequency}"
    assert listing.price is not None, "Expected rental price"


@pytest.mark.anyio
async def test_rightmove_listing_detail_live() -> None:
    """Test fetching full property detail from an individual listing page."""
    if os.getenv("RUN_LIVE_TESTS") != "1":
        pytest.skip("Set RUN_LIVE_TESTS=1 to run live network tests")

    service = RightmoveService()

    # First find a leasehold listing from search results
    url = await service.build_search_url(postcode="SW1A 1AA", property_type="sale")
    listings = await service.listings(search_url=url, max_pages=1, include_raw=True)
    assert len(listings) > 0, "Expected at least one listing"

    # Pick first listing with a leasehold tenure if possible
    target_id = None
    for item in listings:
        raw_tenure = (item.raw or {}).get("tenure", {})
        if raw_tenure.get("tenureType") == "LEASEHOLD":
            target_id = item.id
            break
    if target_id is None:
        target_id = listings[0].id

    start = time.perf_counter()
    detail = await service.listing_detail(property_url_or_id=str(target_id), include_raw=False)
    elapsed = time.perf_counter() - start

    print(f"Listing detail fetch took {elapsed:.2f}s")
    print(f"  Address: {detail.address}")
    print(f"  Price: £{detail.price:,}" if detail.price else "  Price: —")
    print(f"  Tenure: {detail.tenure_type}")
    print(f"  Lease remaining: {detail.years_remaining_on_lease} years" if detail.years_remaining_on_lease else "  Lease remaining: —")
    print(f"  Service charge: £{detail.annual_service_charge:,}/yr" if detail.annual_service_charge else "  Service charge: —")
    print(f"  Ground rent: £{detail.annual_ground_rent:,}/yr" if detail.annual_ground_rent else "  Ground rent: —")
    print(f"  Council tax: {detail.council_tax_band}")
    print(f"  Key features: {detail.key_features[:3]}")
    print(f"  Floorplans: {len(detail.floorplans)}")
    print(f"  Lat/Lon: {detail.latitude}, {detail.longitude}")

    assert detail.id is not None
    assert detail.url.startswith("https://www.rightmove.co.uk/properties/")
    assert detail.address is not None
    assert detail.tenure_type in ("FREEHOLD", "LEASEHOLD", None)
