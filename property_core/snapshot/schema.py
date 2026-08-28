"""The Parquet column contract a routable snapshot must satisfy.

This is the interface between the build pipeline and the routing layer, and it
is checked before a single request is served from a snapshot: a missing column
is not a query returning nothing, it is a query that cannot be asked, and
finding that out at request time would surface as an empty result -- the one
thing an empty result must never mean.

Two design points worth stating.

**Geography is stored derived, not derived at query time.** `outcode` and
`sector` are materialized columns, so an outcode search is `outcode = 'B5'`.
There is no text-prefix comparison anywhere in the query path, which is why the
`STRSTARTS("B5")` class of bug -- matching `B50`, twenty miles away -- cannot be
expressed against this schema at all.

**Types are checked, not just names.** `transfer_date` stored as VARCHAR would
still answer a range filter, lexically, and return the wrong rows silently.

The contract is "at least these columns, with these types". Extra columns are
tolerated: a later build that adds one must not take the snapshot path down.
"""

from __future__ import annotations

from typing import Mapping

#: Column -> the DuckDB type names accepted for it. A set rather than one name
#: because more than one width is genuinely equivalent for our use (`price` as
#: INTEGER or BIGINT), while VARCHAR for a date is not.
REQUIRED_COLUMNS: Mapping[str, frozenset[str]] = {
    "transaction_id": frozenset({"VARCHAR"}),
    "price": frozenset({"BIGINT", "INTEGER", "HUGEINT"}),
    "transfer_date": frozenset({"DATE"}),
    "postcode": frozenset({"VARCHAR"}),
    #: Derived geography. The reason outcode/sector membership is exact.
    "outcode": frozenset({"VARCHAR"}),
    "sector": frozenset({"VARCHAR"}),
    "property_type": frozenset({"VARCHAR"}),
    #: PPD's `duration` column; the API calls it `estate_type` (F/L).
    "duration": frozenset({"VARCHAR"}),
    #: PPD's `ppd_category` column; the API calls it `transaction_category` (A/B).
    "ppd_category": frozenset({"VARCHAR"}),
    "new_build": frozenset({"BOOLEAN"}),
    "paon": frozenset({"VARCHAR"}),
    "saon": frozenset({"VARCHAR"}),
    "street": frozenset({"VARCHAR"}),
    "locality": frozenset({"VARCHAR"}),
    "town": frozenset({"VARCHAR"}),
    "district": frozenset({"VARCHAR"}),
    "county": frozenset({"VARCHAR"}),
}

#: Columns the adapter projects, in the order the row mapper reads them.
PROJECTION: tuple[str, ...] = (
    "transaction_id", "price", "transfer_date", "postcode", "property_type",
    "duration", "ppd_category", "new_build", "paon", "saon", "street",
    "locality", "town", "district", "county",
)


def normalise_type(duckdb_type: str) -> str:
    """DuckDB reports e.g. `DECIMAL(18,3)`; compare on the base name."""
    return duckdb_type.strip().upper().split("(", 1)[0]
