import os

import pytest

from property_core.yield_service import calculate_yield


@pytest.mark.anyio
async def test_calculate_yield_live() -> None:
    if os.getenv("RUN_LIVE_TESTS") != "1":
        pytest.skip("Set RUN_LIVE_TESTS=1 to run live network tests")

    postcode = os.getenv("RIGHTMOVE_TEST_POSTCODE", "LE12 8RQ")
    result = await calculate_yield(postcode, months=24)

    print(f"Postcode: {result.postcode}")
    print(f"Median sale price: {result.median_sale_price}")
    print(f"Sale count: {result.sale_count}")
    print(f"Median monthly rent: {result.median_monthly_rent}")
    print(f"Rental count: {result.rental_count}")
    print(f"Gross yield: {result.gross_yield_pct}%")
    print(f"Assessment: {result.yield_assessment}")
    print(f"Data quality: {result.data_quality}")
    print(f"Thin market: {result.thin_market}")

    assert result.postcode == postcode
    assert result.sale_count >= 0

    # If we got enough data, yield should be calculated
    if result.data_quality != "insufficient":
        assert result.gross_yield_pct is not None
        assert result.gross_yield_pct > 0
        assert result.yield_assessment in ("strong", "average", "weak")
        assert result.median_sale_price is not None
        assert result.median_monthly_rent is not None
