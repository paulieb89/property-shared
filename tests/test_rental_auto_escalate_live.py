"""Live tests for rental auto-escalation.

Run with: RUN_LIVE_TESTS=1 pytest tests/test_rental_auto_escalate_live.py -v
"""
from __future__ import annotations

import os

import pytest

from property_core.rental_service import analyze_rentals


@pytest.mark.anyio
async def test_rental_auto_escalate_widens_on_thin_market() -> None:
    if os.getenv("RUN_LIVE_TESTS") != "1":
        pytest.skip("Set RUN_LIVE_TESTS=1 to run live network tests")

    # Use a known-good postcode with an absurdly high threshold to guarantee
    # thin_market=True and force escalation regardless of actual listing count.
    postcode = os.getenv("RENTAL_TEST_POSTCODE_BUSY", "E1 6RF")

    result = await analyze_rentals(
        postcode,
        radius=0.5,
        auto_escalate=True,
        thin_market_threshold=10_000,
    )

    # With threshold=10000, escalation must have been attempted
    assert result.escalated_from is not None, "Expected escalation to trigger with threshold=10000"
    assert result.escalated_to is not None
    assert result.escalated_to > result.escalated_from
    assert result.search_postcode == postcode
    assert isinstance(result.thin_market, bool)


@pytest.mark.anyio
async def test_rental_no_escalate_when_sufficient_listings() -> None:
    if os.getenv("RUN_LIVE_TESTS") != "1":
        pytest.skip("Set RUN_LIVE_TESTS=1 to run live network tests")

    # Use a busy urban postcode
    postcode = os.getenv("RENTAL_TEST_POSTCODE_BUSY", "E1 6RF")

    result = await analyze_rentals(
        postcode,
        radius=0.5,
        auto_escalate=True,
        thin_market_threshold=3,
    )

    # Should not have escalated if listings were sufficient
    if result.rental_listings_count >= 3:
        assert result.escalated_from is None


@pytest.mark.anyio
async def test_rental_auto_escalate_disabled_no_escalation() -> None:
    if os.getenv("RUN_LIVE_TESTS") != "1":
        pytest.skip("Set RUN_LIVE_TESTS=1 to run live network tests")

    postcode = os.getenv("RENTAL_TEST_POSTCODE_BUSY", "E1 6RF")

    result = await analyze_rentals(
        postcode,
        radius=0.5,
        auto_escalate=False,
    )

    # Should never escalate when disabled
    assert result.escalated_from is None
    assert result.escalated_to is None
