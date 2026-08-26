"""Source-model adapters for the GOV.UK Bearer EPC API.

Search summaries and full certificates are SEPARATE adapters with different
naming conventions (camelCase vs snake_case), proven by live probe. A single
shared mapping would silently yield all-None, which is the failure class this
whole migration exists to remove.

Requiredness note: the OAS declares certificate `data` as
`additionalProperties: true` with no field schema, and the search result schema
carries no `required:` block. So every field is Optional in the model;
"observed always present" is asserted here in tests, not encoded as
requiredness.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from property_core.epc.errors import EPCUpstreamShapeError
from property_core.epc.source_models import (
    EPCCertificateDoc,
    EPCMoney,
    EPCSearchPage,
    EPCSearchRow,
)

# --- fixtures: shapes taken from live probes, values synthetic ---------------

SEARCH_ROW = {
    "certificateNumber": "1111-2222-3333-4444-5555",
    "uprn": 100000000001,
    "addressLine1": "Flat 2",
    "addressLine2": "42 Example Boulevard",
    "addressLine3": None,
    "addressLine4": None,
    "postcode": "AA1 1AA",
    "postTown": "EXAMPLETOWN",
    "council": "Exampleshire",
    "constituency": "Exampleton East",
    "currentEnergyEfficiencyBand": "D",
    "registrationDate": "2023-03-05",
    "schemaType": "RdSAP-Schema-20.0.0",
}

PAGINATION = {
    "totalRecords": 29, "currentPage": 1, "totalPages": 1,
    "nextPage": None, "prevPage": None, "pageSize": 5000,
}

CERT_DOC = {
    "address_line_1": "Flat 2",
    "address_line_2": "42 Example Boulevard",
    "postcode": "AA1 1AA",
    "current_energy_efficiency_band": "D",
    "energy_rating_current": 62,
    "energy_rating_potential": 75,
    "potential_energy_efficiency_band": "C",
    "total_floor_area": 27,
    "built_form": 4,
    "property_type": 2,
    "tenure": 3,
    "habitable_room_count": 1,
    "inspection_date": "2023-02-27",
    "registration_date": "2023-03-05",
    "completion_date": "2023-03-05",
    "uprn": 100000000001,
    "schema_type": "RdSAP-Schema-20.0.0",
    "assessment_type": "RdSAP",
    "heating_cost_current": {"value": 785, "currency": "GBP"},
}


class TestSearchAdapter:
    def test_parses_camelcase_summary(self):
        row = EPCSearchRow.from_source(SEARCH_ROW)
        assert row.certificate_number == "1111-2222-3333-4444-5555"
        assert row.current_energy_efficiency_band == "D"
        assert row.schema_type == "RdSAP-Schema-20.0.0"
        assert row.uprn == "100000000001", "uprn is int upstream, str on the model"

    def test_address_is_composed_from_non_null_lines(self):
        """address_matching consumes this composition — it is load-bearing."""
        row = EPCSearchRow.from_source(SEARCH_ROW)
        assert row.address == "Flat 2, 42 Example Boulevard"

    def test_absent_uprn_is_none_not_empty_string(self):
        row = EPCSearchRow.from_source({**SEARCH_ROW, "uprn": None})
        assert row.uprn is None

    def test_certificate_payload_fed_to_search_adapter_raises(self):
        """Adapter confusion must be loud. Silent all-None is the bug we're fixing."""
        with pytest.raises(EPCUpstreamShapeError):
            EPCSearchRow.from_source(CERT_DOC)


class TestCertificateAdapter:
    def test_parses_snakecase_certificate(self):
        doc = EPCCertificateDoc.from_source(CERT_DOC, certificate_number="1111-2222-3333-4444-5555")
        assert doc.energy_rating_current == 62
        assert doc.total_floor_area == 27
        assert doc.assessment_type == "RdSAP"

    def test_certificate_number_comes_from_the_request_not_the_body(self):
        """Proven by probe: the certificate body does not echo its own number."""
        assert "certificate_number" not in CERT_DOC
        doc = EPCCertificateDoc.from_source(CERT_DOC, certificate_number="9999-8888-7777-6666-5555")
        assert doc.certificate_number == "9999-8888-7777-6666-5555"

    def test_schema_type_optional_and_context_suppliable(self):
        body = {k: v for k, v in CERT_DOC.items() if k != "schema_type"}
        doc = EPCCertificateDoc.from_source(body, certificate_number="1", schema_type="SAP-Schema-13.0")
        assert doc.schema_type == "SAP-Schema-13.0"
        doc2 = EPCCertificateDoc.from_source(body, certificate_number="1")
        assert doc2.schema_type is None, "absent schema_type must not be invented"

    def test_search_row_fed_to_certificate_adapter_raises(self):
        with pytest.raises(EPCUpstreamShapeError):
            EPCCertificateDoc.from_source(SEARCH_ROW, certificate_number="1")

    def test_raw_codes_preserved_alongside_labels(self):
        doc = EPCCertificateDoc.from_source(CERT_DOC, certificate_number="1")
        assert doc.built_form_code == 4 and doc.property_type_code == 2 and doc.tenure_code == 3

    def test_schema_variant_fields_absent_are_none_not_errors(self):
        """Older schemas legitimately omit fields (72 vs 83 observed)."""
        minimal = {"current_energy_efficiency_band": "E", "schema_type": "SAP-Schema-13.0"}
        doc = EPCCertificateDoc.from_source(minimal, certificate_number="1")
        assert doc.total_floor_area is None
        assert doc.photovoltaic_supply is None


class TestUnknownFieldsSurvive:
    """OAS declares additionalProperties: true — dropping silently is unacceptable."""

    def test_unmodelled_field_is_retained(self):
        doc = EPCCertificateDoc.from_source(
            {**CERT_DOC, "brand_new_upstream_field": "surprise"}, certificate_number="1")
        assert "brand_new_upstream_field" in doc.unmodelled_fields
        assert doc.unmodelled_fields["brand_new_upstream_field"] == "surprise"

    def test_unmodelled_fields_excluded_from_outward_dump(self):
        doc = EPCCertificateDoc.from_source(
            {**CERT_DOC, "brand_new_upstream_field": "surprise"}, certificate_number="1")
        assert "unmodelled_fields" not in doc.model_dump()
        assert "brand_new_upstream_field" not in doc.model_dump()


class TestMoney:
    def test_structured_money_uses_decimal(self):
        doc = EPCCertificateDoc.from_source(CERT_DOC, certificate_number="1")
        assert isinstance(doc.heating_cost_current, EPCMoney)
        assert doc.heating_cost_current.value == Decimal("785")
        assert doc.heating_cost_current.currency == "GBP"

    def test_malformed_money_raises_rather_than_becoming_none(self):
        # NB: a BARE NUMBER was in this list until v1.14.1. It was wrong — SAP
        # schemas 13.0/14.0/14.2/15.0 genuinely return scalars, and rejecting
        # them made every such certificate a production 503. It is now accepted
        # with no stated currency; see tests/test_epc_scalar_money.py.
        for bad in (True, False, "785", [785], {}, {"value": 785}, {"currency": "GBP"},
                    {"value": "x", "currency": "GBP"}, {"value": 785, "currency": ""}):
            with pytest.raises(EPCUpstreamShapeError):
                EPCCertificateDoc.from_source(
                    {**CERT_DOC, "heating_cost_current": bad}, certificate_number="1")

    def test_bare_scalar_is_accepted_without_a_currency(self):
        doc = EPCCertificateDoc.from_source(
            {**CERT_DOC, "heating_cost_current": 785}, certificate_number="1")
        assert doc.heating_cost_current.value == Decimal("785")
        assert doc.heating_cost_current.currency is None
        assert doc.heating_cost_current.currency_stated is False

    def test_non_gbp_currency_is_preserved_not_discarded(self):
        doc = EPCCertificateDoc.from_source(
            {**CERT_DOC, "heating_cost_current": {"value": 900, "currency": "EUR"}},
            certificate_number="1")
        assert doc.heating_cost_current.currency == "EUR"


class TestSearchPageInvariants:
    def _page(self, rows, pagination=None):
        return EPCSearchPage.from_source(
            {"data": rows, "pagination": pagination or PAGINATION})

    def test_row_without_certificate_number_is_quarantined_not_fatal(self):
        """Unchainable rows must never silently become valid results."""
        bad = {**SEARCH_ROW, "certificateNumber": None}
        page = self._page([SEARCH_ROW, bad])
        assert page.returned_distinct_count == 1
        assert page.unusable_rows == 1
        assert page.complete is False
        assert any("unusable" in w.lower() for w in page.warnings)

    def test_within_page_duplicates_removed_and_reported(self):
        page = self._page([SEARCH_ROW, dict(SEARCH_ROW)])
        assert page.returned_distinct_count == 1
        assert page.duplicates_removed == 1
        assert any("duplicate" in w.lower() for w in page.warnings)

    def test_complete_false_when_total_exceeds_returned(self):
        page = self._page([SEARCH_ROW], {**PAGINATION, "totalRecords": 500})
        assert page.complete is False
        assert any("not snapshot-stable" in w.lower() or "complete" in w.lower() for w in page.warnings)

    def test_complete_true_only_when_all_records_returned(self):
        page = self._page([SEARCH_ROW], {**PAGINATION, "totalRecords": 1})
        assert page.complete is True

    def test_missing_pagination_never_invents_completeness(self):
        with pytest.raises(EPCUpstreamShapeError):
            EPCSearchPage.from_source({"data": [SEARCH_ROW]})

    def test_unusable_pagination_does_not_claim_complete(self):
        page = EPCSearchPage.from_source(
            {"data": [SEARCH_ROW], "pagination": {"totalRecords": None, "currentPage": 1,
                                                  "totalPages": None, "pageSize": 5000,
                                                  "nextPage": None, "prevPage": None}})
        assert page.complete is False
