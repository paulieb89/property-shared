"""Cached codebook for the coded integers the certificate returns.

The upstream returns `built_form: 4`, not "Mid-Terrace". Keys are STRINGS: the
tables carry `ND` ("unknown") and `NR` ("Not Recorded") beside the numeric keys,
and certificates do return them. Coercing keys with int() silently dropped both
from every table, so they could never resolve. Resolution goes through
/api/codes/info, which — verified by probe — returns a whole table when given
(code, schemaVersion) without a key. So the cache unit is a table, not a key.

schemaVersion is sent verbatim: the certificate's own `schema_type` value was
accepted 11/11 across both RdSAP and SAP families, with the exact value echoed
back. No normalisation rule is applied, because none is needed.

A codebook outage must never fail certificate retrieval. It trips a breaker so
an outage cannot generate a lookup per certificate.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

_log = logging.getLogger(__name__)

BASE_URL = "https://api.get-energy-performance-data.communities.gov.uk"

# Only the three labels v1 semantics require. Other raw codes are preserved
# untouched; enriching them belongs to uk-property-mcp.
SUPPORTED_CODES = ("built_form", "property_type", "tenure")

_BREAKER_THRESHOLD = 3

# warm() resolves a throwaway key purely to force the table load. Any key does;
# it is in the string key space so the signature stays honest.
_WARM_KEY = "0"


class EPCCodebook:
    """Table-per-(code, schemaVersion) cache with a failure breaker."""

    def __init__(
        self,
        token: str | None = None,
        transport=None,
        timeout: float = 15.0,
        warm_budget: float = 8.0,
    ):
        self._token = token
        self._transport = transport
        self._timeout = timeout
        # One budget for the whole warm, not per table: three sequential
        # per-request timeouts would exceed the 30s MCP tool timeout on their own.
        self._warm_budget = warm_budget
        self._tables: dict[tuple[str, str | None], dict[str, str]] = {}
        # Single-flight: concurrent callers awaiting the same (code,
        # schemaVersion) share one in-flight fetch instead of each issuing a
        # request. Without this, four concurrent cold certificates produced
        # twelve requests for three tables.
        self._inflight: dict[tuple[str, str | None], "asyncio.Task[None]"] = {}
        self._failures = 0
        self._tripped = False

    @property
    def degraded(self) -> bool:
        return self._tripped

    def _headers(self) -> dict:
        h = {"Accept": "application/json"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    async def _fetch_table(self, code: str, schema_version: Optional[str]) -> dict[str, str]:
        params = {"code": code}
        if schema_version:
            params["schemaVersion"] = schema_version  # verbatim — proven 11/11
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as c:
            resp = await c.get(f"{BASE_URL}/api/codes/info", params=params, headers=self._headers())
        if resp.status_code != 200:
            raise RuntimeError(f"codebook HTTP {resp.status_code}")
        body = resp.json()
        entries = body.get("data") if isinstance(body, dict) else body
        table: dict[str, str] = {}
        for entry in entries or []:
            key = entry.get("key")
            values = entry.get("values") or []
            if key is None or not values:
                continue
            key = str(key).strip()
            if not key:
                continue
            table[key] = values[0].get("value")
        return table

    async def label(self, code: str, key: Optional[str], schema_version: Optional[str]) -> Optional[str]:
        """Resolve one code to its label, or None. Never raises.

        Async because the certificate path is async: a synchronous request here
        would block the event loop for every uncached lookup.
        """
        if key is None or code not in SUPPORTED_CODES:
            return None
        cache_key = (code, schema_version)
        if cache_key not in self._tables:
            if self._tripped:
                return None
            try:
                # shield: if THIS caller is cancelled (e.g. the warm budget
                # expires), the shared loader keeps running for everyone else
                # rather than being torn down mid-flight.
                await asyncio.shield(self._loader(cache_key))
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - the loader already accounted for it
                return None
        return self._tables.get(cache_key, {}).get(key)

    def _loader(self, cache_key: tuple[str, str | None]) -> "asyncio.Task[None]":
        """The single shared task that fetches, caches and accounts for one table.

        Fetch, cache write and failure accounting all live HERE rather than in
        each waiter. Previously every waiter incremented the failure counter, so
        four waiters sharing ONE failed request recorded four failures and
        tripped the breaker on a single upstream attempt. One attempt is now one
        failure, however many callers were waiting on it.
        """
        task = self._inflight.get(cache_key)
        if task is not None:
            return task

        code, schema_version = cache_key

        async def _load() -> None:
            try:
                table = await self._fetch_table(code, schema_version)
            except Exception as exc:  # noqa: BLE001 - degradation is the contract
                # Exactly one failure per upstream attempt.
                self._failures += 1
                if self._failures >= _BREAKER_THRESHOLD:
                    self._tripped = True
                    _log.warning("EPC codebook unavailable; breaker tripped (%s)", exc)
                raise
            # Cache nothing on failure, so a later recovery can still populate.
            self._tables[cache_key] = table
            self._failures = 0

        task = asyncio.ensure_future(_load())

        def _done(t: "asyncio.Task[None]") -> None:
            self._inflight.pop(cache_key, None)
            # Consume any exception even when every waiter has already gone
            # away, so a background failure cannot surface as an unretrieved
            # task exception.
            if not t.cancelled():
                t.exception()

        task.add_done_callback(_done)
        self._inflight[cache_key] = task
        return task

    async def warm(self, schema_version: Optional[str]) -> list[str]:
        """Pre-fetch the tables v1 semantics need, so projection stays sync.

        Concurrent, under ONE overall budget. Sequentially these three fetches
        can reach three times the per-request timeout, which by itself exceeds
        the MCP tool timeout — failing an entire certificate call for a purely
        cosmetic label. Exceeding the budget degrades to labels=None.

        Without a schema_version the codebook cannot be queried safely: an
        unscoped lookup returns one value per schema version, and taking the
        first would be a guess. Labels are left unresolved and the caller warned.

        Returns any warnings to surface; never raises.
        """
        if not schema_version:
            return [
                "certificate has no schema_type, so code labels cannot be resolved "
                "safely (an unscoped codebook lookup returns one value per schema "
                "version); built_form, property_type and tenure are reported as missing"
            ]

        pending = [c for c in SUPPORTED_CODES if (c, schema_version) not in self._tables]
        if not pending or self._tripped:
            return []

        try:
            await asyncio.wait_for(
                asyncio.gather(*(self.label(c, _WARM_KEY, schema_version) for c in pending)),
                timeout=self._warm_budget,
            )
        except asyncio.TimeoutError:
            return [
                f"EPC codebook lookup exceeded its {self._warm_budget:.0f}s budget; "
                "built_form, property_type and tenure are reported as missing"
            ]
        return []

    def label_sync(self, code: str, key: Optional[str], schema_version: Optional[str]) -> Optional[str]:
        """Cache-only lookup for synchronous callers. Never issues a request."""
        if key is None or code not in SUPPORTED_CODES:
            return None
        return self._tables.get((code, schema_version), {}).get(key)
