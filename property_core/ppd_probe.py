"""The bounded existence probe -- spec section 2.4, decision O1.

`ppd_transactions` and CLI `ppd search` take no date, so each currently means
"latest ever". Against a snapshot the same call means "latest within coverage",
and a postcode last sold in 2009 comes back empty -- which an LLM reads as
"never sold". That is a confident false claim produced by a tool that was only
ever asked a narrower question.

The probe answers exactly one question, against the **live** source (the
snapshot cannot answer it: by construction it holds nothing before
`coverage_from`): does any record exist at this geography before coverage
begins?

The constraints are all about not letting the probe become a second data path:

* `LIMIT 1` existence, never `COUNT` -- we need one bit, not a number;
* a **3-second** timeout;
* **no retries**;
* any failure yields `None`, never `False`. `False` is a positive assertion that
  nothing older exists, and only a probe that actually completed may make it.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from property_core.ppd_client import PricePaidDataClient

#: One query, bounded. Long enough for a healthy endpoint, short enough that an
#: unhealthy one costs an empty result its warning rather than the whole request.
PROBE_TIMEOUT_SECONDS = 3.0
#: One attempt. A retried probe is no longer bounded.
PROBE_RETRY_ATTEMPTS = 1


def build_probe_client() -> PricePaidDataClient:
    """A client configured for one bounded attempt and nothing else."""
    return PricePaidDataClient(timeout=PROBE_TIMEOUT_SECONDS,
                               retry_attempts=PROBE_RETRY_ATTEMPTS)


def day_before(iso_date: str) -> str:
    """The last day outside coverage. `coverage_from` itself is inside it."""
    return (date.fromisoformat(iso_date) - timedelta(days=1)).isoformat()


class ExistenceProbe:
    """Answers 'do older records exist?' as `True` / `False` / `None`."""

    def __init__(self, client: Optional[PricePaidDataClient] = None):
        self.client = client or build_probe_client()

    def older_records_exist(
        self,
        *,
        postcode: Optional[str],
        postcode_prefix: Optional[str],
        coverage_from: str,
    ) -> Optional[bool]:
        """`True` / `False` / `None` (probe did not complete).

        Every failure path returns `None`. There is deliberately no branch that
        turns an exception into `False`: the difference between "nothing older
        exists" and "we could not find out" is the whole point of this function.
        """
        try:
            page = self.client.search_with_evidence(
                postcode=postcode,
                postcode_prefix=postcode_prefix,
                to_date=day_before(coverage_from),
                limit=1,
                order_desc=True,
            )
        except Exception:  # noqa: BLE001 -- any failure is "unknown", never "no"
            return None
        return bool(page.transactions)
