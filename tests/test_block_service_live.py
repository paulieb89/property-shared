"""Live tests for block analysis — requires real network calls."""

import os

# Credentials are loaded ONLY when live tests are explicitly enabled.
#
# This used to run at import time, so merely HAVING a .env on disk leaked
# credentials into os.environ for the whole pytest session — and unit tests
# asserting unconfigured behaviour then saw a configured client and failed.
# Collection must never configure an integration as a side effect: a .env is a
# convenience for the developer, not an instruction to talk to live services.
if os.getenv("RUN_LIVE_TESTS") == "1":  # pragma: no cover - live-only path
    try:
        from dotenv import load_dotenv
    except ImportError:  # optional local dev dependency
        pass
    else:
        load_dotenv()

import pytest

from property_core.block_service import analyze_blocks


@pytest.fixture(autouse=True)
def _skip_unless_live():
    if os.getenv("RUN_LIVE_TESTS") != "1":
        pytest.skip("RUN_LIVE_TESTS not set")


def test_analyze_blocks_birmingham():
    """Birmingham city centre has many flat blocks."""
    result = analyze_blocks("B1 1AA", months=24, min_transactions=2)
    assert result.postcode == "B1 1AA"
    assert result.blocks_found >= 0

    for block in result.blocks:
        assert block.transaction_count >= 2
        assert block.building_name is not None
        assert block.transactions  # at least one transaction


def test_analyze_blocks_no_results():
    """Rural postcode unlikely to have flat blocks."""
    result = analyze_blocks("SY25 6AA", months=12, min_transactions=3)
    assert result.blocks_found >= 0  # may be 0, that's fine
