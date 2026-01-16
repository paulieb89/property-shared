import time

from app.services.ppd_service import PPDService
from property_core.ppd_client import PricePaidDataClient


def test_ppd_service_live_search() -> None:
    client = PricePaidDataClient(timeout=30)
    service = PPDService(client=client)

    start = time.perf_counter()
    response = service.search_transactions(
        postcode=None,
        postcode_prefix="PL6 8",
        from_date=None,
        to_date=None,
        min_price=None,
        max_price=None,
        property_type=None,
        estate_type=None,
        transaction_category=None,
        record_status=None,
        new_build=None,
        limit=10,
        offset=0,
        order_desc=True,
    )
    elapsed = time.perf_counter() - start

    print(f"PPD live search took {elapsed:.2f}s")
    print(f"PPD live search returned {response.count} results (limit={response.limit})")
    for idx, item in enumerate(response.results[:3], start=1):
        print(
            f"{idx}. {item.postcode} {item.price} {item.date} "
            f"{item.property_type} {item.town or ''} {item.street or ''}".strip()
        )

    assert response.count > 0
    assert response.results
