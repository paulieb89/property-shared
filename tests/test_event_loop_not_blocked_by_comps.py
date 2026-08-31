"""Slow PPD comps must not block the event loop.

Production incident, 2026-08-30 22:00-22:15Z. `property-shared` stopped
answering: TLS completed at Fly's edge, then no HTTP response arrived. The
Machine was healthy throughout -- no OOM, no restart, 1.74 GB of 2 GB free --
and the load average was **0.00**. Zero CPU while serving nothing is the
signature of a blocked event loop, not of saturation: the loop thread was
parked in a synchronous socket read and could not run any other task.

`PPDService.comps` is synchronous, and both `GET /v1/ppd/comps` and the MCP
`property_comps` tool called it directly from inside `async def`. For the whole
of an upstream SPARQL round trip, one comps request stopped the single uvicorn
worker from serving anything at all -- including `/v1/health`, which is a
constant-returning coroutine that does no I/O. Fly's health check then timed
out against its 5 s limit, the Machine was dropped from the proxy's candidate
set, and every request queued behind "could not find a good candidate".

`app/api/v1/rightmove.py` already offloads its synchronous calls with
`anyio.to_thread.run_sync`; the PPD router never did.

These tests use a slow *stub* in place of the upstream call -- no Land Registry
traffic -- and assert responsiveness, never the wall-clock of the slow call
itself, so they measure the property that broke rather than a timing artefact.
"""

from __future__ import annotations

import asyncio
import socket
import threading
import time

import pytest

from property_core.models.ppd import PPDCompsQuery, PPDCompsResponse

# Long enough that a blocked loop is unmistakable, short enough to keep the
# suite fast. Health is asserted against a far smaller budget, so the two can
# never be confused for one another.
SLOW_SECONDS = 3.0
HEALTH_BUDGET_SECONDS = 1.0

pytestmark = pytest.mark.anyio


def _stub_response(postcode: str) -> PPDCompsResponse:
    return PPDCompsResponse(
        query=PPDCompsQuery(postcode=postcode, months=24, search_level="sector"),
        count=0,
        thin_market=False,
    )


def _slow_comps(*args, **kwargs) -> PPDCompsResponse:
    """Stands in for a slow upstream.

    `time.sleep` is the honest stand-in for a blocking socket read: it holds the
    calling thread without consuming CPU, which is what the incident showed.
    """
    time.sleep(SLOW_SECONDS)
    return _stub_response(kwargs.get("postcode", "B5 7"))


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Server:
    """A real uvicorn server on a real port.

    Deliberately not `TestClient`/ASGITransport: the incident was about the
    server's own loop being unable to accept and answer a second connection, and
    an in-process transport that shares the caller's loop cannot demonstrate
    that. This is the closest reproduction of the deployed process -- one
    uvicorn worker, one event loop -- that a test can be.
    """

    def __init__(self, app, port: int):
        import uvicorn

        self._server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
        )
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self.base = f"http://127.0.0.1:{port}"

    def __enter__(self):
        self._thread.start()
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if self._server.started:
                return self
            time.sleep(0.02)
        raise RuntimeError("uvicorn did not start")

    def __exit__(self, *exc):
        self._server.should_exit = True
        self._thread.join(timeout=30)


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def test_health_answers_while_a_slow_comps_request_is_in_flight(monkeypatch):
    """The reproduction: one slow comps must not take the whole worker down."""
    import httpx

    from app.main import create_app
    from property_core.ppd_service import PPDService

    monkeypatch.setattr(PPDService, "comps", _slow_comps)

    with _Server(create_app(), _free_port()) as server:
        async with httpx.AsyncClient(base_url=server.base) as client:
            comps = asyncio.ensure_future(
                client.get("/v1/ppd/comps", params={"postcode": "B5 7"}, timeout=30.0)
            )
            # Let the slow request reach the handler and start blocking.
            await asyncio.sleep(0.5)

            started = time.monotonic()
            health = await client.get("/v1/health", timeout=HEALTH_BUDGET_SECONDS + 4)
            elapsed = time.monotonic() - started

            assert health.status_code == 200, health.text
            assert elapsed < HEALTH_BUDGET_SECONDS, (
                f"/v1/health took {elapsed:.2f}s while one comps request was in "
                f"flight; the event loop is blocked by a synchronous call. Fly's "
                f"health check allows 5s before removing the Machine."
            )

            assert (await comps).status_code == 200


async def test_the_mcp_tool_does_not_stall_the_loop_it_shares(monkeypatch):
    """The same defect on the other consumer.

    Measured as a heartbeat rather than through a server: what harmed production
    was the loop being unable to run *any* other task, and a heartbeat observes
    that directly. A coroutine that yields every 50 ms cannot show a gap much
    larger than that unless something ran synchronously to completion inside the
    loop thread.
    """
    from app.mcp.server import property_comps
    from property_core.ppd_service import PPDService

    monkeypatch.setattr(PPDService, "comps", _slow_comps)

    gaps: list[float] = []

    async def heartbeat() -> None:
        last = time.monotonic()
        while True:
            await asyncio.sleep(0.05)
            now = time.monotonic()
            gaps.append(now - last)
            last = now

    beat = asyncio.ensure_future(heartbeat())
    # Let the heartbeat establish itself BEFORE the blocking call starts.
    # Without this the loop never runs it, `gaps` stays empty, and an
    # `if gaps else 0.0` fallback would report a perfect score for the very
    # stall the test exists to catch.
    await asyncio.sleep(0.3)
    beats_before = len(gaps)
    try:
        await property_comps(postcode="B5 7")
        # A stall is only *recorded* on the heartbeat's next wake, which cannot
        # happen until the loop is free again. Cancelling straight after the
        # call would discard the one gap that matters and report a clean run.
        await asyncio.sleep(0.1)
    finally:
        beat.cancel()

    assert beats_before >= 2, (
        f"heartbeat only ran {beats_before}x before the call; it was not "
        f"established, so this test could not have observed a stall"
    )
    worst = max(gaps)
    assert worst < HEALTH_BUDGET_SECONDS, (
        f"the event loop stalled for {worst:.2f}s during one property_comps "
        f"call; every other MCP session and /v1/health waits that long"
    )


# ---------------------------------------------------------------------------
# The siblings: synchronous handlers, which both dispatchers already offload.
#
# A synchronous *call* is not the defect. The defect is a synchronous call made
# from an `async def` handler, because only then does it run on the loop
# thread. `comps` was the only `async def` in the PPD router; every sibling is
# a plain `def`, which Starlette runs in its threadpool, and FastMCP does the
# same for a synchronous tool.
#
# These tests exist because that distinction is easy to assert and easy to get
# wrong -- it was got wrong once already, when the siblings were listed as
# defective on the strength of the call alone. They drive the real route and
# the real tool dispatcher, so they would fail if a sibling were ever converted
# to `async def` without an offload.
# ---------------------------------------------------------------------------


def _slow_search(*args, **kwargs) -> dict:
    time.sleep(SLOW_SECONDS)
    return {"count": 0, "limit": 5, "offset": 0, "results": [], "warnings": []}


async def test_a_synchronous_rest_handler_does_not_block_the_loop(monkeypatch):
    """`GET /v1/ppd/transactions` is `def`; Starlette offloads it for us."""
    import httpx

    from app.main import create_app
    from property_core.ppd_service import PPDService

    monkeypatch.setattr(PPDService, "search_transactions", _slow_search)

    with _Server(create_app(), _free_port()) as server:
        async with httpx.AsyncClient(base_url=server.base) as client:
            slow = asyncio.ensure_future(
                client.get(
                    "/v1/ppd/transactions",
                    params={"postcode_prefix": "B5", "limit": 5},
                    timeout=30.0,
                )
            )
            await asyncio.sleep(0.5)

            started = time.monotonic()
            health = await client.get("/v1/health", timeout=HEALTH_BUDGET_SECONDS + 4)
            elapsed = time.monotonic() - started

            assert health.status_code == 200, health.text
            assert elapsed < HEALTH_BUDGET_SECONDS, (
                f"/v1/health took {elapsed:.2f}s during a slow *synchronous* "
                f"handler; it is no longer being offloaded"
            )
            # Anti-vacuity: if the stub never ran -- a 422 on params, a route
            # that does not exist -- health would be fast for a reason that has
            # nothing to do with offloading, and this test would prove nothing.
            response = await slow
            assert response.status_code == 200, response.text
            assert time.monotonic() - started >= SLOW_SECONDS - 0.6, (
                "the slow stub did not actually run; this test is vacuous"
            )


async def test_a_synchronous_mcp_tool_does_not_block_the_loop(monkeypatch):
    """Driven through FastMCP's own dispatcher, not by calling the function."""
    from fastmcp import Client

    from app.mcp.server import mcp
    from property_core.ppd_service import PPDService

    monkeypatch.setattr(PPDService, "search_transactions", _slow_search)

    gaps: list[float] = []

    async def heartbeat() -> None:
        last = time.monotonic()
        while True:
            await asyncio.sleep(0.05)
            now = time.monotonic()
            gaps.append(now - last)
            last = now

    async with Client(mcp) as client:
        beat = asyncio.ensure_future(heartbeat())
        await asyncio.sleep(0.3)
        beats_before = len(gaps)
        call_started = time.monotonic()
        try:
            await client.call_tool("ppd_transactions", {"postcode": "B5 4BX"})
            elapsed = time.monotonic() - call_started
            await asyncio.sleep(0.1)
        finally:
            beat.cancel()

    assert beats_before >= 2, "heartbeat was not established; test proves nothing"
    # Anti-vacuity: the tool must actually have reached the slow stub, or a
    # quiet loop says nothing about offloading.
    assert elapsed >= SLOW_SECONDS - 0.6, (
        f"the tool returned in {elapsed:.2f}s; the slow stub did not run and "
        f"this test is vacuous"
    )
    worst = max(gaps)
    assert worst < HEALTH_BUDGET_SECONDS, (
        f"the loop stalled for {worst:.2f}s dispatching a synchronous MCP tool; "
        f"FastMCP is no longer offloading it"
    )
