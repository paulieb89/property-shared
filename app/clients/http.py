"""HTTP client helpers."""

import httpx


def get_async_client(timeout: float = 15.0) -> httpx.AsyncClient:
    # Caller should manage closing (e.g., via lifespan)
    return httpx.AsyncClient(timeout=timeout)
