"""Codebook failure accounting under concurrency.

Four waiters shared ONE failed HTTP request, but each waiter incremented the
failure counter — so a single upstream attempt recorded four failures and
tripped the breaker. Fetch, cache write and failure accounting now live in the
shared loader task; waiters only consume its result.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from property_core.epc.codebook import EPCCodebook

CERT = {"data": {
    "current_energy_efficiency_band": "D", "energy_rating_current": 62,
    "schema_type": "RdSAP-Schema-20.0.0", "built_form": 4,
    "property_type": 2, "tenure": 3,
}}
SCHEMA = "RdSAP-Schema-20.0.0"


def _run(c):
    return asyncio.run(c)


def _book(handler, **kw):
    return EPCCodebook(transport=httpx.MockTransport(handler), **kw)


class TestOneAttemptIsOneFailure:
    def test_four_waiters_one_503_counts_a_single_failure(self):
        requests = []

        async def handler(request):
            requests.append(request.url.params.get("code"))
            await asyncio.sleep(0.05)
            return httpx.Response(503, text="down")

        book = _book(handler)

        async def main():
            return await asyncio.gather(
                *(book.label("built_form", 4, SCHEMA) for _ in range(4))
            )

        results = _run(main())
        assert results == [None] * 4
        assert len(requests) == 1, f"expected one shared request, saw {len(requests)}"
        assert book._failures == 1, f"one attempt must be one failure, got {book._failures}"
        assert book.degraded is False, "a single failed attempt must not trip the breaker"

    def test_three_distinct_failed_attempts_trip_the_breaker(self):
        requests = []

        async def handler(request):
            requests.append(request.url.params.get("code"))
            return httpx.Response(503, text="down")

        book = _book(handler)

        async def main():
            # Three separate attempts, each awaited to completion so they do
            # not share an in-flight task.
            for code in ("built_form", "property_type", "tenure"):
                await book.label(code, 1, SCHEMA)

        _run(main())
        assert len(requests) == 3
        assert book._failures == 3
        assert book.degraded is True, "three distinct failures must trip the breaker"

    def test_breaker_prevents_further_requests(self):
        requests = []

        async def handler(request):
            requests.append(1)
            return httpx.Response(503, text="down")

        book = _book(handler)

        async def main():
            for code in ("built_form", "property_type", "tenure"):
                await book.label(code, 1, SCHEMA)
            before = len(requests)
            await book.label("built_form", 1, "SAP-Schema-13.0")
            return before, len(requests)

        before, after = _run(main())
        assert after == before, "no request may be issued once the breaker has tripped"

    def test_success_resets_the_failure_count(self):
        state = {"fail": True}

        async def handler(request):
            if state["fail"]:
                return httpx.Response(503, text="down")
            return httpx.Response(200, json={"data": [
                {"key": "4", "values": [{"value": "Mid-Terrace", "schemaVersion": SCHEMA}]}]})

        book = _book(handler)

        async def main():
            await book.label("built_form", 4, SCHEMA)
            assert book._failures == 1
            state["fail"] = False
            return await book.label("property_type", 4, SCHEMA)

        _run(main())
        assert book._failures == 0, "a success must clear the failure count"


class TestCancellationSafety:
    def test_timed_out_waiter_cannot_cancel_the_shared_fetch(self):
        requests = []

        async def handler(request):
            requests.append(request.url.params.get("code"))
            await asyncio.sleep(0.25)
            return httpx.Response(200, json={"data": [
                {"key": "4", "values": [{"value": "Mid-Terrace", "schemaVersion": SCHEMA}]}]})

        book = _book(handler)

        async def main():
            impatient = asyncio.create_task(book.label("built_form", 4, SCHEMA))
            await asyncio.sleep(0.05)
            impatient.cancel()
            with pytest.raises(asyncio.CancelledError):
                await impatient
            # The shared loader should have survived and populated the cache.
            await asyncio.sleep(0.35)
            return await book.label("built_form", 4, SCHEMA)

        assert _run(main()) == "Mid-Terrace"
        assert len(requests) == 1, f"the fetch was re-issued: {len(requests)} requests"
        assert book._failures == 0, "a cancelled waiter must not record a failure"

    def test_timed_out_waiter_does_not_double_count_a_failure(self):
        async def handler(request):
            await asyncio.sleep(0.2)
            return httpx.Response(503, text="down")

        book = _book(handler)

        async def main():
            impatient = asyncio.create_task(book.label("built_form", 4, SCHEMA))
            await asyncio.sleep(0.05)
            impatient.cancel()
            with pytest.raises(asyncio.CancelledError):
                await impatient
            await asyncio.sleep(0.3)   # let the shared loader finish and fail

        _run(main())
        assert book._failures == 1, f"one attempt, one failure — got {book._failures}"
        assert book.degraded is False

    def test_background_failure_leaves_no_unobserved_task_exception(self):
        """A loader failing after every waiter has gone must not warn."""
        seen: list[str] = []

        async def handler(request):
            await asyncio.sleep(0.2)
            return httpx.Response(503, text="down")

        book = _book(handler)

        async def main():
            loop = asyncio.get_running_loop()
            previous = loop.get_exception_handler()
            loop.set_exception_handler(
                lambda _loop, ctx: seen.append(ctx.get("message", "")))
            try:
                waiter = asyncio.create_task(book.label("built_form", 4, SCHEMA))
                await asyncio.sleep(0.05)
                waiter.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await waiter
                await asyncio.sleep(0.35)   # loader fails with nobody awaiting
            finally:
                loop.set_exception_handler(previous)

        _run(main())
        unobserved = [m for m in seen if "never retrieved" in m.lower()]
        assert unobserved == [], f"unobserved task exception(s): {unobserved}"


class TestSharedLoaderStillCaches:
    def test_concurrent_success_issues_one_request_per_table(self):
        from collections import Counter

        requests: list[str] = []

        async def handler(request):
            requests.append(request.url.params.get("code"))
            await asyncio.sleep(0.05)
            return httpx.Response(200, json={"data": []})

        book = _book(handler)

        async def main():
            await asyncio.gather(*(
                book.label(code, 1, SCHEMA)
                for code in ("built_form", "property_type", "tenure")
                for _ in range(4)
            ))

        _run(main())
        counts = Counter(requests)
        assert set(counts.values()) == {1}, f"duplicate fetches: {dict(counts)}"
        assert len(requests) == 3
