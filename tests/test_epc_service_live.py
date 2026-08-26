import os
import time

import pytest

from property_core.epc_client import EPCClient

# Credentials are loaded ONLY when live tests are explicitly enabled.
#
# This used to run at import time, so merely HAVING a .env on disk leaked
# EPC_API_TOKEN into os.environ for the whole pytest session — and unit tests
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


@pytest.mark.anyio
async def test_epc_service_live_search() -> None:
    if os.getenv("RUN_LIVE_TESTS") != "1":
        pytest.skip("Set RUN_LIVE_TESTS=1 to run live network tests")

    client = EPCClient()
    if not client.is_configured():
        pytest.skip("EPC credentials not configured")

    postcode = os.getenv("EPC_TEST_POSTCODE") or "NG7 1FN"
    address = os.getenv("EPC_TEST_ADDRESS") or None

    if address is None:
        # A bare postcode with many candidates must NOT resolve to an arbitrary
        # certificate — take a real address from the summary page instead.
        page = await client.search_summaries(postcode)
        if not page.results:
            pytest.skip(f"No EPC certificates at {postcode}")
        address = page.results[0].address

    start = time.perf_counter()
    result = await client.search_by_postcode(postcode, address=address)
    elapsed = time.perf_counter() - start

    print(f"EPC live search took {elapsed:.2f}s")
    if result is None:
        raise AssertionError(
            "No EPC result for test postcode. Set EPC_TEST_POSTCODE to a known-good "
            "postcode (and EPC_TEST_ADDRESS if needed)."
        )
    print(f"EPC rating={result.rating} score={result.score} address={result.address}")
    assert result.rating


@pytest.mark.anyio
async def test_epc_service_live_area_search() -> None:
    """Live test: summary search returns candidate rows for a residential postcode."""
    if os.getenv("RUN_LIVE_TESTS") != "1":
        pytest.skip("Set RUN_LIVE_TESTS=1 to run live network tests")

    client = EPCClient()
    if not client.is_configured():
        pytest.skip("EPC credentials not configured")

    postcode = os.getenv("EPC_TEST_POSTCODE") or "NG11 9HD"

    start = time.perf_counter()
    page = await client.search_summaries(postcode)
    certs = page.results
    elapsed = time.perf_counter() - start

    print(f"EPC area search for {postcode} took {elapsed:.2f}s -> {len(certs)} certs")
    if not certs:
        pytest.skip(f"No EPC certs for {postcode}. Try a different EPC_TEST_POSTCODE.")

    assert len(certs) >= 1
    # Sanity check — at least some certs should have ratings
    assert any(c.current_energy_efficiency_band for c in certs), \
        "expected at least one summary row with an energy band"
    assert all(c.certificate_number for c in certs), "every usable row must be chainable"


@pytest.mark.anyio
async def test_epc_live_bare_postcode_does_not_resolve_arbitrarily() -> None:
    """A postcode with many certificates must refuse, not pick one."""
    if os.getenv("RUN_LIVE_TESTS") != "1":
        pytest.skip("Set RUN_LIVE_TESTS=1 to run live network tests")

    from property_core.epc.errors import EPCAmbiguousMatchError

    client = EPCClient()
    if not client.is_configured():
        pytest.skip("EPC credentials not configured")

    postcode = os.getenv("EPC_TEST_POSTCODE") or "NG7 1FN"
    page = await client.search_summaries(postcode)
    if len(page.results) < 2:
        pytest.skip(f"{postcode} has fewer than 2 certificates")

    with pytest.raises(EPCAmbiguousMatchError):
        await client.search_by_postcode(postcode)
