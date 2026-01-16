import os
import time

import pytest

from app.services.epc_service import EPCService

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional local dev dependency
    load_dotenv = None


if load_dotenv:
    load_dotenv()


@pytest.mark.anyio
async def test_epc_service_live_search() -> None:
    if os.getenv("RUN_LIVE_TESTS") != "1":
        pytest.skip("Set RUN_LIVE_TESTS=1 to run live network tests")

    service = EPCService()
    if not service.is_configured():
        pytest.skip("EPC credentials not configured")

    postcode = os.getenv("EPC_TEST_POSTCODE", "SW1A 1AA")
    address = os.getenv("EPC_TEST_ADDRESS")

    start = time.perf_counter()
    result = await service.search(postcode=postcode, address=address, include_raw=True)
    elapsed = time.perf_counter() - start

    print(f"EPC live search took {elapsed:.2f}s")
    if result is None:
        raise AssertionError(
            "No EPC result for test postcode. Set EPC_TEST_POSTCODE to a known-good "
            "postcode (and EPC_TEST_ADDRESS if needed)."
        )
    print(f"EPC rating={result.record.rating} score={result.record.score} address={result.record.address}")
    assert result.record.rating
