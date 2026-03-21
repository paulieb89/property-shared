import os

import pytest

from property_core.interpret import classify_data_quality, classify_yield
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
    print(f"Thin market: {result.thin_market}")

    # Core no longer populates assessment/quality — consumers use interpret helpers
    assert result.yield_assessment is None
    assert result.data_quality is None

    assert result.postcode == postcode
    assert result.sale_count >= 0

    # If we got enough data, yield should be calculated
    quality = classify_data_quality(result.sale_count, result.rental_count)
    if quality != "insufficient":
        assert result.gross_yield_pct is not None
        assert result.gross_yield_pct > 0
        assert classify_yield(result.gross_yield_pct) in ("strong", "average", "weak")
        assert result.median_sale_price is not None
        assert result.median_monthly_rent is not None


def test_classify_yield() -> None:
    """Test interpret helpers work standalone."""
    assert classify_yield(7.0) == "strong"
    assert classify_yield(5.0) == "average"
    assert classify_yield(3.0) == "weak"
    assert classify_yield(6.0) == "strong"
    assert classify_yield(4.0) == "average"
    # Custom thresholds
    assert classify_yield(5.0, strong_pct=5.0) == "strong"
    assert classify_yield(5.0, average_pct=6.0) == "weak"


def test_classify_data_quality() -> None:
    """Test data quality classification."""
    assert classify_data_quality(10, 10) == "good"
    assert classify_data_quality(3, 3) == "low"
    assert classify_data_quality(1, 0) == "insufficient"
    assert classify_data_quality(5, 5) == "good"
    assert classify_data_quality(2, 2) == "low"
    # Custom threshold
    assert classify_data_quality(5, 5, min_good=10) == "low"
