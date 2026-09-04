"""One property certified twice is not two properties.

Reproduced live against the real EPC API on 2026-09-04:

    EPCClient().search_by_postcode('NG11 9HD', address='27 Havenwood Rise')
    -> EPCAmbiguousMatchError: 2 certificates share the address text
       '27 Havenwood Rise'; cannot select one

Both candidates carry UPRN 100031555077. It is one house, certified twice, whose
address text differs only by a comma. Properties are re-certified on sale and on
let, so this is the normal case rather than an edge one, and every affected
property was unreachable by address — including through `enrich_comps_with_epc`,
where it silently left comps un-enriched.

The module this fixes has been repaired four times, each round finding a new way
for partial evidence to look sufficient. So the rule here is deliberately
narrower than "same UPRN wins":

    same UPRN  AND  same canonical address  AND  a strict latest date

A shared UPRN with *different* address text is contradictory upstream data, not
one property, and still refuses. Equal dates still refuse, because "most recent"
does not exist. A missing date still refuses. Every existing guard therefore
passes unmodified — which is the check that this fix is not a fifth gap.
"""

from __future__ import annotations

import pytest

from property_core.epc.errors import EPCAmbiguousMatchError
from property_core.epc.selection import select_candidate
from property_core.epc.source_models import EPCSearchRow

UPRN = "100031555077"


def _row(cert: str, address: str, *, uprn: str | None = None,
         registered: str | None = "2023-01-01") -> EPCSearchRow:
    return EPCSearchRow.from_source({
        "certificateNumber": cert, "addressLine1": address, "addressLine2": None,
        "uprn": uprn, "postcode": "NG11 9HD", "currentEnergyEfficiencyBand": "D",
        "registrationDate": registered, "schemaType": "RdSAP-Schema-20.0.0",
    })


# --- the reproduced defect, both entry points -------------------------------


def test_the_live_repro_selects_the_most_recent_certificate():
    """The exact shape observed at NG11 9HD, comma and all."""
    older = _row("6234-2126-73", "27 Havenwood Rise", uprn=UPRN, registered="2011-06-02")
    newer = _row("8694-7123-28", "27, Havenwood Rise", uprn=UPRN, registered="2021-09-14")

    result = select_candidate([older, newer], address="27 Havenwood Rise")

    assert result.row.certificate_number == "8694-7123-28"
    assert result.method == "uprn_latest_certificate"


def test_the_caller_supplied_uprn_path_is_fixed_too():
    """`select_candidate(uprn=...)` refused this identically before.

    A fix touching only the address path would leave `epc_lookup(uprn=...)`
    broken for exactly the same properties.
    """
    older = _row("A", "27 Havenwood Rise", uprn=UPRN, registered="2011-06-02")
    newer = _row("B", "27 Havenwood Rise", uprn=UPRN, registered="2021-09-14")

    assert select_candidate([older, newer], uprn=UPRN).row.certificate_number == "B"


def test_order_of_the_candidate_rows_does_not_decide():
    """Upstream row order resolving a tie is a defect this module already names."""
    older = _row("A", "27 Havenwood Rise", uprn=UPRN, registered="2011-06-02")
    newer = _row("B", "27 Havenwood Rise", uprn=UPRN, registered="2021-09-14")

    for rows in ([older, newer], [newer, older]):
        assert select_candidate(rows, address="27 Havenwood Rise").row.certificate_number == "B"


def test_three_certificates_for_one_property_select_the_newest():
    rows = [
        _row("A", "27 Havenwood Rise", uprn=UPRN, registered="2011-06-02"),
        _row("C", "27, Havenwood Rise", uprn=UPRN, registered="2024-02-29"),
        _row("B", "27 Havenwood Rise", uprn=UPRN, registered="2021-09-14"),
    ]
    assert select_candidate(rows, address="27 Havenwood Rise").row.certificate_number == "C"


def test_the_designator_canonicalized_collision_is_also_resolved():
    """`Flat 2` / `Apartment 2` collapse to one address; same UPRN makes it one flat."""
    rows = [
        _row("A", "Flat 2, 24 Alexandra Road", uprn=UPRN, registered="2012-01-01"),
        _row("B", "Apartment 2, 24 Alexandra Road", uprn=UPRN, registered="2022-01-01"),
    ]
    assert select_candidate(rows, address="Flat 2, 24 Alexandra Road").row.certificate_number == "B"


# --- every reason to keep refusing ------------------------------------------


def test_a_shared_uprn_with_different_addresses_still_refuses():
    """Contradictory upstream data, not one property.

    Selecting here would be the exact failure this module exists to prevent:
    attaching another property's certificate, and with it a wrong floor area and
    every price-per-sqft derived from it.
    """
    rows = [
        _row("A", "12 Elm Road", uprn=UPRN, registered="2011-01-01"),
        _row("B", "14 Elm Road", uprn=UPRN, registered="2022-01-01"),
    ]
    with pytest.raises(EPCAmbiguousMatchError):
        select_candidate(rows, uprn=UPRN)


def test_equal_registration_dates_still_refuse():
    """There is no "most recent" between two certificates lodged the same day."""
    rows = [
        _row("A", "27 Havenwood Rise", uprn=UPRN, registered="2021-09-14"),
        _row("B", "27 Havenwood Rise", uprn=UPRN, registered="2021-09-14"),
    ]
    with pytest.raises(EPCAmbiguousMatchError):
        select_candidate(rows, address="27 Havenwood Rise")


@pytest.mark.parametrize("bad", [None, "", "not-a-date", "2021-13-01", "14/09/2021"])
def test_an_unusable_date_on_any_candidate_still_refuses(bad):
    """No ordering exists, so there is nothing to be latest."""
    rows = [
        _row("A", "27 Havenwood Rise", uprn=UPRN, registered="2011-06-02"),
        _row("B", "27 Havenwood Rise", uprn=UPRN, registered=bad),
    ]
    with pytest.raises(EPCAmbiguousMatchError):
        select_candidate(rows, address="27 Havenwood Rise")


def test_a_missing_uprn_on_any_candidate_still_refuses():
    """UPRN is optional upstream and often absent; absence proves nothing."""
    rows = [
        _row("A", "27 Havenwood Rise", uprn=UPRN, registered="2011-06-02"),
        _row("B", "27 Havenwood Rise", uprn=None, registered="2021-09-14"),
    ]
    with pytest.raises(EPCAmbiguousMatchError):
        select_candidate(rows, address="27 Havenwood Rise")


def test_two_blank_uprns_do_not_count_as_agreement():
    rows = [
        _row("A", "27 Havenwood Rise", uprn=None, registered="2011-06-02"),
        _row("B", "27 Havenwood Rise", uprn=None, registered="2021-09-14"),
    ]
    with pytest.raises(EPCAmbiguousMatchError):
        select_candidate(rows, address="27 Havenwood Rise")


def test_different_uprns_on_a_colliding_address_still_refuse():
    """Two genuinely different properties whose address text happens to collide."""
    rows = [
        _row("A", "27 Havenwood Rise", uprn="100000000001", registered="2011-06-02"),
        _row("B", "27 Havenwood Rise", uprn="100000000002", registered="2021-09-14"),
    ]
    with pytest.raises(EPCAmbiguousMatchError):
        select_candidate(rows, address="27 Havenwood Rise")


# --- the single-candidate paths are untouched -------------------------------


def test_a_single_exact_match_is_still_exact_address():
    row = _row("A", "27 Havenwood Rise", uprn=UPRN)
    result = select_candidate([row], address="27 Havenwood Rise")
    assert result.method == "exact_address"
    assert result.confidence == 100


def test_a_single_uprn_hit_is_still_uprn():
    row = _row("A", "27 Havenwood Rise", uprn=UPRN)
    assert select_candidate([row], uprn=UPRN).method == "uprn"


def test_a_uprn_that_matches_nothing_still_does_not_fall_back():
    row = _row("A", "27 Havenwood Rise", uprn=UPRN)
    with pytest.raises(EPCAmbiguousMatchError, match="refusing to fall back"):
        select_candidate([row], uprn="999999999999")
