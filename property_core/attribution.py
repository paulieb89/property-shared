"""HM Land Registry attribution -- the one place the required text lives.

Price Paid Data is published under the Open Government Licence v3.0, which
requires the statement below wherever the data is used. Responses carry a
compact `attribution_ref` pointing here rather than the prose itself: a
paragraph of licence text repeated on every transaction would be noise in an
LLM's context and adds nothing a reference does not.

The year in the statement is the year of the data being used, so it is derived
from the current date rather than pinned -- a hardcoded 2024 in a 2026 response
misstates the copyright period.
"""

from __future__ import annotations

from datetime import date

HMLR_LICENCE_URL = (
    "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
)


def hmlr_attribution(year: int | None = None) -> str:
    """The exact required statement for `year` (default: the current year)."""
    return (
        f"Contains HM Land Registry data © Crown copyright and database right "
        f"{year or date.today().year}. This data is licensed under the Open "
        f"Government Licence v3.0."
    )

# Deliberately no module-level constant holding the rendered string: a
# long-running process that imported it in December would keep serving last
# year's statement in January. Call the function.
