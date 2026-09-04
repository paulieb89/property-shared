"""Protocol-neutral typed failures for `property_core`.

`property_core` has four consumers (REST API, two MCP servers, CLI) that map
failures differently, so these carry typed data and no transport concerns. The
REST layer chooses the response code; MCP surfaces them as tool errors; the CLI
exits non-zero.

`PPDError` is the base for every typed failure here, not only PPD ones -- the
name is historical. Non-PPD paths (Rightmove location lookup, below) subclass it
deliberately, because the REST mapping convention and `property_cli`'s
`_ppd_errors` decorator both key off this base, and a parallel hierarchy would
mean a second decorator and a second set of `except` clauses saying the same
thing. Nothing PPD-flavoured crosses a protocol boundary: a caller sees
`str(exc)` and `code`, and `code` names the actual failure.

The distinction these types exist to preserve: **a failure is not an absence**.
An empty result means "no matching rows within the stated coverage" and nothing
else.

See docs/design/ppd-source-routing.md section 3.2.
"""

from __future__ import annotations

from typing import Any, Optional


class PPDError(Exception):
    """Base for typed PPD failures. Never raised directly."""

    code = "ppd_error"
    retryable = False

    def to_dict(self) -> dict[str, Any]:
        return {"error": self.code, "detail": str(self), "retryable": self.retryable}


class PPDCoverageError(PPDError):
    """The requested date range falls outside the available data.

    Carries both ranges as structured data so a caller can reformulate the
    request without parsing prose. Never answer such a request partially: a
    truncated result is indistinguishable from a complete one.
    """

    code = "ppd_coverage_error"
    retryable = False

    def __init__(
        self,
        *,
        coverage_from: str,
        coverage_to: str,
        requested_from: Optional[str] = None,
        requested_to: Optional[str] = None,
        source_release: Optional[str] = None,
        detail: str = "requested range precedes available coverage",
        remedy: Optional[str] = None,
    ):
        if not coverage_from or not coverage_to:
            raise ValueError(
                "PPDCoverageError requires the available coverage range; an error "
                "that cannot state what IS available gives the caller no remedy"
            )
        self.coverage_from = coverage_from
        self.coverage_to = coverage_to
        self.requested_from = requested_from
        self.requested_to = requested_to
        self.source_release = source_release
        # The remedy differs by which boundary was crossed. Telling a caller who
        # asked for next month to "set from_date >= 2016-01-01" is advice that
        # cannot work, and advice that cannot work is worse than none.
        self.remedy = remedy or (
            f"set from_date >= {coverage_from}, or look up a known transaction "
            f"by its id"
        )
        super().__init__(detail)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": self.code,
            "detail": str(self),
            "requested": {"from_date": self.requested_from, "to_date": self.requested_to},
            "available": {
                "coverage_from": self.coverage_from,
                "coverage_to": self.coverage_to,
            },
            "source_release": self.source_release,
            "retryable": self.retryable,
            "remedy": self.remedy,
        }


class InvalidPostcodeError(PPDError):
    """Caller supplied a postcode or prefix outside the allowlisted grammar.

    ``field`` distinguishes an exact postcode from a prefix. They share this
    type, but a consumer must be able to tell which input was wrong -- and an
    internally derived prefix that fails validation is a bug in our own
    derivation, not something to silently repair.
    """

    code = "invalid_postcode"
    retryable = False

    def __init__(self, value: str, *, field: str = "postcode", expected: str = ""):
        self.value = value
        self.field = field
        self.expected = expected
        detail = f"{field} {value!r} is not valid"
        if expected:
            detail += f"; expected {expected}"
        super().__init__(detail)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": self.code,
            "detail": str(self),
            "field": self.field,
            "value": self.value,
            "expected": self.expected,
            "retryable": self.retryable,
        }


class InvalidDateRangeError(PPDError):
    """Caller supplied a date, or a pair of dates, that cannot mean anything.

    Two distinct mistakes share this type because they share a remedy -- fix the
    input -- but ``field`` says which one:

    * an unparseable date. Coverage decisions compare ISO strings lexically,
      which is only meaningful for well-formed ones: ``"nonsense"`` sorts after
      ``"2026-06-30"``, so a garbage ``to_date`` read as "beyond coverage" and
      was silently clamped to it.
    * ``from_date`` after ``to_date``. The window is empty by construction, so
      it passed both coverage-bound checks, matched nothing, and -- being
      nominally inside coverage -- was reported as a COMPLETE empty result.

    Raised **before either source is queried**, because it is the caller's
    input that is wrong and neither source can improve on that answer.
    """

    code = "invalid_date_range"
    retryable = False

    def __init__(
        self,
        detail: str,
        *,
        field: str = "",
        value: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ):
        self.field = field
        self.value = value
        self.from_date = from_date
        self.to_date = to_date
        super().__init__(detail)

    def to_dict(self) -> dict[str, Any]:
        return {
            **super().to_dict(),
            "field": self.field,
            "value": self.value,
            "requested": {"from_date": self.from_date, "to_date": self.to_date},
            "expected": "ISO dates (YYYY-MM-DD) with from_date <= to_date",
        }


class TransactionNotFoundError(PPDError):
    """No such transaction upstream. Distinct from a failed lookup."""

    code = "transaction_not_found"
    retryable = False

    def __init__(self, transaction_id: str, detail: str = ""):
        self.transaction_id = transaction_id
        super().__init__(detail or f"no transaction record for {transaction_id}")

    def to_dict(self) -> dict[str, Any]:
        return {**super().to_dict(), "transaction_id": self.transaction_id}


class SnapshotFailure(PPDError):
    """The snapshot path could not serve this request.

    **This type is the fallback contract.** A caller that sees it uses the live
    source and says so; it never returns empty data. Routing catches this base
    class rather than an enumeration of known subclasses, so a failure mode added
    later falls back correctly without anyone remembering to extend a tuple.

    Deliberately disjoint from `UpstreamUnavailableError`: the live source is
    what the fallback falls back *to*, so a live failure that also read as a
    snapshot failure would send routing round the loop again.

    Caller errors (`InvalidPostcodeError`) and coverage refusals
    (`PPDCoverageError`) are NOT snapshot failures. Retrying either against the
    live source would hide the very fact the caller needs.
    """

    code = "snapshot_failure"
    retryable = True


class SnapshotUnavailableError(SnapshotFailure):
    """No verified snapshot is open. Distinct from 'no rows matched'."""

    code = "snapshot_unavailable"
    retryable = True


class UpstreamUnavailableError(PPDError):
    """A live upstream failed. Distinct from both 'empty' and 'no snapshot'."""

    code = "upstream_unavailable"
    retryable = True


class UpstreamShapeError(UpstreamUnavailableError):
    """A successful upstream response whose shape we cannot use.

    Deliberately NOT ``TransactionNotFoundError``: a malformed envelope tells us
    nothing about whether the record exists, so reporting it as an absence would
    state a false fact about the world. Subclasses ``UpstreamUnavailableError``
    so existing upstream-failure handling catches it, while keeping its own code
    for diagnosis.
    """

    code = "upstream_shape_error"
    retryable = True


class LocationNotFoundError(PPDError):
    """A well-formed postcode or outcode that Rightmove holds no location for.

    Distinct from `InvalidPostcodeError`, and the distinction is the caller's
    next action. `XX99 9XX` satisfies the grammar, so telling that caller their
    input "is not valid" states a false fact and sends them hunting a typo that
    is not there. The upstream answered normally, with an empty match list, so
    this is not a failure either -- it is an absence, and consumers map it the
    same way they already map `TransactionNotFoundError`.
    """

    code = "rightmove_location_not_found"
    retryable = False

    def __init__(self, value: str, *, field: str = "postcode"):
        self.value = value
        self.field = field
        super().__init__(
            f"no Rightmove location matches {field} {value!r}; the input is "
            f"well-formed, so this is an absence rather than a bad input"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": self.code,
            "detail": str(self),
            "field": self.field,
            "value": self.value,
            "retryable": self.retryable,
        }


class LocationLookupError(UpstreamUnavailableError):
    """Rightmove's location service could not be consulted.

    Previously a bare `Exception` raised for BOTH a transport failure and a
    successful-but-empty lookup, which made the two indistinguishable to every
    consumer. It now covers only the former. Reparenting is what supplies
    `to_dict()`, `retryable` and `_ppd_errors` handling -- setting the
    attributes by hand would supply the data without the behaviour.
    """

    code = "rightmove_location_unavailable"
    retryable = True
