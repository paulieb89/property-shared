"""In-memory politeness helpers (no Redis/Postgres required)."""

from __future__ import annotations

import asyncio
import time


class PoliteLimiter:
    """A simple per-process limiter: max concurrency + min delay between starts."""

    def __init__(self, *, max_concurrency: int = 1, min_delay_seconds: float = 0.6):
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be >= 1")
        if min_delay_seconds < 0:
            raise ValueError("min_delay_seconds must be >= 0")
        self._sem = asyncio.Semaphore(max_concurrency)
        self._min_delay = float(min_delay_seconds)
        self._lock = asyncio.Lock()
        self._last_started_at: float = 0.0

    async def __aenter__(self) -> "PoliteLimiter":
        await self._sem.acquire()
        async with self._lock:
            now = time.monotonic()
            wait_for = (self._last_started_at + self._min_delay) - now
            if wait_for > 0:
                await asyncio.sleep(wait_for)
            self._last_started_at = time.monotonic()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self._sem.release()

