"""The one definition of a lookback window, shared by every surface.

Three things about a date window have to agree, and until now nothing made them:
the **words** a caller reads, the **schema defaults** a client validates
against, and the **runtime behaviour** that answers. They disagreed in ways that
were invisible from any single surface:

* the MCP input schema for `months` was literally `{"default": 24, "type":
  "integer"}` — no description, no minimum, nothing about what happens past
  coverage. A model choosing a value had the type and nothing else.
* `/v1/ppd/transactions` takes `from_date`/`to_date` and has no `months` at all,
  while the MCP tool of the same name takes `months`. A caller who assumed one
  vocabulary got the other.
* `PPDService.comps` bounds `months` nowhere; `le=120` existed only on one REST
  route. So the "cap" applied to direct HTTP callers and not to models.

This module is the single structured definition those surfaces derive from, so
they cannot drift apart again. It deliberately exports *data* rather than prose:
`MONTHS_DESCRIPTION` is the text, `MONTHS_PARAM` is the annotated type that
produces the MCP input schema, and `resolve_window` is the behaviour. A test
asserts the published schema matches this contract, so changing the words
without changing the schema, or either without the other, fails.

**No maximum is declared, deliberately.** Coverage is the real ceiling and it
moves when the artifact is rebuilt, so a second number here would be a second
thing to keep in sync — and it would be wrong for most of its life. A window
reaching past coverage is answered over the overlap and *said so*, which is
what `resolve_window` returns and what the provenance block publishes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Annotated, Optional

from pydantic import Field

#: Months in the default lookback.
#:
#: 24 because that is what this server has always answered when `months` is
#: omitted. The contract exists to stop the words, the schema and the behaviour
#: disagreeing -- it is not a licence to change the behaviour while documenting
#: it. Halving the default would move every median computed by a caller who
#: never passed `months`, which is a product decision and needs to be taken as
#: one, not arrive inside a documentation fix.
DEFAULT_MONTHS = 24

#: A window has to contain at least one month. There is no maximum: see the
#: module docstring.
MIN_MONTHS = 1

#: Days per month used to turn `months` into a date. Approximate on purpose and
#: stated so, because the alternative is a calendar-accurate figure that differs
#: from what every existing caller has been getting.
DAYS_PER_MONTH = 30

#: The words a caller reads. Published in the MCP input schema, in the REST
#: parameter description and in the generated documentation, from here.
MONTHS_DESCRIPTION = (
    "Number of calendar months ending today; default "
    f"{DEFAULT_MONTHS}. Results are limited to available coverage."
)

#: The annotated type every MCP tool uses for `months`. This is what produces
#: `{"default": 24, "description": ..., "minimum": 1, "type": "integer"}` in the
#: tool's input schema — the thing a model actually reads.
MonthsParam = Annotated[int, Field(description=MONTHS_DESCRIPTION, ge=MIN_MONTHS)]

#: REST keeps `from_date`/`to_date`: dates are the natural HTTP interface and
#: an absolute range is what a cache key or a log line wants. These are the
#: descriptions for those, kept here so both surfaces are documented from one
#: place even though they are spelled differently.
FROM_DATE_DESCRIPTION = (
    "Inclusive start of the window, YYYY-MM-DD. Omit to start at the earliest "
    "available coverage. Results are limited to available coverage."
)
TO_DATE_DESCRIPTION = (
    "Inclusive end of the window, YYYY-MM-DD. Omit to end today. Results are "
    "limited to available coverage."
)


@dataclass(frozen=True)
class ResolvedWindow:
    """What was asked for, what could be answered, and whether they differ.

    Both windows are published so an answer is auditable on its own: a reader
    seeing only `effective` cannot tell whether it was the request or a clamp,
    and a model that has dropped the earlier turn from its context cannot either.
    """

    requested_from: Optional[str]
    requested_to: Optional[str]
    effective_from: Optional[str]
    effective_to: Optional[str]

    @property
    def truncated(self) -> bool:
        """Whether coverage answered less than was asked for."""
        return (self.requested_from, self.requested_to) != (
            self.effective_from, self.effective_to)

    @property
    def truncation_warning(self) -> Optional[str]:
        """One sentence naming both windows, or None when nothing was clamped.

        Names the figures rather than saying "truncated", because a caller
        deciding whether the answer supports a claim needs the bounds, not an
        adjective.
        """
        if not self.truncated:
            return None
        return (
            f"requested {self.requested_from or 'earliest'}"
            f"..{self.requested_to or 'today'} but answered "
            f"{self.effective_from or 'earliest'}..{self.effective_to or 'today'}; "
            f"the window was limited to available coverage"
        )


def window_from_months(months: int, *, today: Optional[date] = None) -> tuple[str, str]:
    """The (from_date, to_date) a `months` lookback means, as ISO strings.

    Kept here rather than in each caller because `date.today() -
    timedelta(days=months * 30)` was written out separately in the service and
    implied differently in three docstrings.
    """
    if months < MIN_MONTHS:
        raise ValueError(f"months must be >= {MIN_MONTHS}, got {months}")
    end = today or date.today()
    return (end - timedelta(days=months * DAYS_PER_MONTH)).isoformat(), end.isoformat()


def resolve_window(
    *,
    requested_from: Optional[str],
    requested_to: Optional[str],
    coverage_from: Optional[str],
    coverage_to: Optional[str],
) -> ResolvedWindow:
    """Clamp a requested window to coverage, keeping both for the record.

    ISO strings compare correctly as text, which is the only reason this is a
    string comparison — callers must have validated them first
    (`ppd_source.validate_date_range`). Passing `None` coverage means the source
    states no bounds, in which case nothing is clamped.
    """
    effective_from, effective_to = requested_from, requested_to

    if coverage_from and (effective_from is None or effective_from < coverage_from):
        effective_from = coverage_from
    if coverage_to and (effective_to is None or effective_to > coverage_to):
        effective_to = coverage_to

    return ResolvedWindow(
        requested_from=requested_from,
        requested_to=requested_to,
        effective_from=effective_from,
        effective_to=effective_to,
    )
