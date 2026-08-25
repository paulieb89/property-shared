"""Absence of evidence must never compare equal to absence of evidence.

Reproduced on 0d3d60c: a query address of "   " or "---" is truthy, so the
`if not address` guard passed, but it normalizes to "". A candidate row carrying
no address normalizes to "" too — so the two compared equal and the row was
returned as `exact_address` at confidence 100.

Emptiness is therefore tested AFTER normalization, on both sides. A UPRN can
still select an addressless row, because that is independent identity evidence.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from property_core.epc.errors import EPCAmbiguousMatchError
from property_core.epc.selection import select_candidate
from property_core.epc.source_models import EPCSearchRow
from property_core.epc_client import EPCClient


def _row(cert_no: str, address: str | None, uprn: str | None = None) -> EPCSearchRow:
    return EPCSearchRow.from_source({
        "certificateNumber": cert_no, "addressLine1": address, "addressLine2": None,
        "uprn": uprn, "postcode": "AA1 1AA", "currentEnergyEfficiencyBand": "D",
        "registrationDate": "2023-01-01", "schemaType": "RdSAP-Schema-20.0.0",
    })


EMPTY_QUERIES = ["   ", "---", ".", ",,,", "\t\n", " , . - ", "()"]


class TestEmptyNormalizedQueryRefuses:
    @pytest.mark.parametrize("query", EMPTY_QUERIES)
    def test_addressless_candidate_is_not_selected(self, query):
        with pytest.raises(EPCAmbiguousMatchError):
            select_candidate([_row("X", None)], address=query)

    @pytest.mark.parametrize("query", EMPTY_QUERIES)
    def test_real_candidate_is_not_selected_either(self, query):
        """Even a lone well-formed row: the QUERY carries no evidence."""
        with pytest.raises(EPCAmbiguousMatchError):
            select_candidate([_row("X", "Flat 2, 24 Alexandra Road")], address=query)

    def test_message_names_the_absence_of_evidence(self):
        with pytest.raises(EPCAmbiguousMatchError) as exc:
            select_candidate([_row("X", "Flat 2, 24 Alexandra Road")], address="---")
        assert "no address text" in str(exc.value).lower()


class TestEmptyCandidateAddressNeverMatches:
    @pytest.mark.parametrize("candidate", [None, "", "   ", "---", "."])
    def test_candidate_without_address_text_cannot_match(self, candidate):
        with pytest.raises(EPCAmbiguousMatchError):
            select_candidate([_row("X", candidate)],
                             address="Flat 2, 24 Alexandra Road")

    def test_addressless_row_does_not_shadow_a_real_match(self):
        """The addressless row must drop out, not make the set ambiguous."""
        rows = [_row("EMPTY", None), _row("REAL", "Flat 2, 24 Alexandra Road")]
        got = select_candidate(rows, address="Flat 2, 24 Alexandra Road")
        assert got.row.certificate_number == "REAL"
        assert got.method == "exact_address"

    def test_two_addressless_rows_are_not_a_duplicate_match(self):
        rows = [_row("A", None), _row("B", "   ")]
        with pytest.raises(EPCAmbiguousMatchError):
            select_candidate(rows, address="Flat 2, 24 Alexandra Road")

    def test_addressless_row_still_matches_by_designator_path_never(self):
        with pytest.raises(EPCAmbiguousMatchError):
            select_candidate([_row("X", "  -- ")], address="Apartment 2, 24 High Street")


class TestUprnStillSelectsAddresslessRows:
    """Control: UPRN is independent identity evidence and must be unaffected."""

    def test_uprn_selects_a_row_with_no_address(self):
        got = select_candidate([_row("X", None, uprn="100000000001")],
                               uprn="100000000001")
        assert got.row.certificate_number == "X"
        assert got.method == "uprn" and got.confidence == 100

    def test_uprn_selects_a_row_with_punctuation_only_address(self):
        got = select_candidate([_row("X", "---", uprn="100000000001")],
                               uprn="100000000001")
        assert got.method == "uprn"

    def test_uprn_wins_even_alongside_an_empty_address_query(self):
        got = select_candidate([_row("X", None, uprn="100000000001")],
                               uprn="100000000001", address="   ")
        assert got.method == "uprn"


class TestNoCertificateFetchOnInvalidAddressEvidence:
    """Refusing must cost zero certificate-detail calls."""

    def test_enrichment_issues_no_certificate_request(self):
        from property_core.enrichment import enrich_comps_with_epc
        from property_core.models.ppd import PPDTransaction

        from tests.test_epc_honest_failure import CERT_BODY, SEARCH_BODY

        calls: list[str] = []

        # Every candidate row is addressless, so no address evidence can match.
        rows = {
            "data": [{**SEARCH_BODY["data"][0], "addressLine1": None,
                      "addressLine2": None, "addressLine3": None,
                      "addressLine4": None, "uprn": None}],
            "pagination": SEARCH_BODY["pagination"],
        }

        def handler(request):
            calls.append(request.url.path)
            if request.url.path.endswith("/certificate"):
                return httpx.Response(200, json=CERT_BODY)
            return httpx.Response(200, json=rows)

        client = EPCClient(token="t")
        client._transport = httpx.MockTransport(handler)

        comps = [PPDTransaction(transaction_id="1", price=1, postcode="AA1 1AA",
                                paon="10", street="GOOD STREET")]
        out = asyncio.run(enrich_comps_with_epc(comps, epc_client=client))

        assert out[0].epc_match is None, "an unmatched comp must stay un-enriched"
        cert_calls = [p for p in calls if p.endswith("/certificate")]
        assert cert_calls == [], f"certificate fetched despite no match: {cert_calls}"
