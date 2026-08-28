"""HM Land Registry attribution -- the one place the required text lives.

Price Paid Data is published under the Open Government Licence v3.0, which
requires the statement below wherever the data is used. Responses carry a
compact `attribution_ref` pointing here rather than the prose itself: a
paragraph of licence text repeated on every transaction would be noise in an
LLM's context and adds nothing a reference does not.

**The year is part of the prescribed statement, not a copyright notice we
render for the current year.** HM Land Registry publishes this exact sentence,
2021 included, on the Price Paid Data downloads page
(https://www.gov.uk/government/statistical-data-sets/price-paid-data-downloads,
checked 2026-08-28), and the frozen specification quotes it verbatim in section
6. An earlier version of this module substituted `date.today().year` and emitted
"2021" as "2026", which is not the statement the licence asks for. Nothing here
may consult the calendar.
"""

from __future__ import annotations

HMLR_LICENCE_URL = (
    "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
)

#: Verbatim, character for character. Changing it means HM Land Registry changed
#: the prescribed wording -- check the source above and update the frozen
#: specification's section 6 in the same commit.
HMLR_ATTRIBUTION = (
    "Contains HM Land Registry data © Crown copyright and database right 2021. "
    "This data is licensed under the Open Government Licence v3.0."
)


def hmlr_attribution() -> str:
    """The exact required statement.

    Takes no arguments on purpose: there is no per-year variant to select, and a
    year parameter would invite the same substitution this replaced.
    """
    return HMLR_ATTRIBUTION
