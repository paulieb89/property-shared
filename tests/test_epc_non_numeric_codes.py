"""The coded fields are keyed by STRING upstream, not by integer.

`built_form`, `property_type` and `tenure` were modelled as `Optional[int]`.
Observed at the live boundary on 2026-09-05 across 133 certificates drawn from
twelve postcodes, **8 (6.0%) carry a non-numeric code** and were therefore
unfetchable — the whole certificate failed pydantic validation:

    tenure     'ND'   3 certificates   SAP-Schema-16.1, SAP-Schema-19.1.0
    built_form 'NR'   5 certificates   RdSAP-Schema-21.0.1

These are not junk and they are not absences. `/api/codes/info` lists them as
first-class keys in the same tables as the numeric ones, in every schema
version checked:

    tenure     ND -> "unknown"       (RdSAP 20.0.0 / 21.0.1, SAP 19.1.0, 16.1)
    built_form NR -> "Not Recorded"  (RdSAP 20.0.0 / 21.0.1, SAP 16.1)

So the fix is not to discard them. Dropping 'ND' to None would conflate "the
upstream states the tenure is unknown" with "the upstream said nothing about
tenure" — the same conflation this package already refuses for pagination
completeness and for stated-vs-inferred currency — and would throw away a label
the upstream is willing to supply.

The codebook made the mirror-image mistake: `_fetch_table` did `int(key)` inside
a try/except that `continue`d, so 'ND' and 'NR' were silently dropped from every
table. Even had the model accepted them, they could never have resolved.

Both sides now use the upstream key space: string.
"""

from __future__ import annotations

import asyncio
import os

import httpx
import pytest

from property_core.epc.codebook import EPCCodebook
from property_core.epc.compat import to_epcdata
from property_core.epc.source_models import EPCCertificateDoc

from tests.test_epc_source_models import CERT_DOC

SCHEMA = "RdSAP-Schema-20.0.0"

# Shape returned by /api/codes/info, including the non-numeric keys.
TENURE_TABLE = {"data": [
    {"key": "1", "values": [{"value": "owner-occupied", "schemaVersion": SCHEMA}]},
    {"key": "2", "values": [{"value": "rented (social)", "schemaVersion": SCHEMA}]},
    {"key": "3", "values": [{"value": "rented (private)", "schemaVersion": SCHEMA}]},
    {"key": "ND", "values": [{"value": "unknown", "schemaVersion": SCHEMA}]},
]}
BUILT_FORM_TABLE = {"data": [
    {"key": "4", "values": [{"value": "Mid-Terrace", "schemaVersion": SCHEMA}]},
    {"key": "NR", "values": [{"value": "Not Recorded", "schemaVersion": SCHEMA}]},
]}


def _doc(**overrides) -> EPCCertificateDoc:
    return EPCCertificateDoc.from_source(
        {**CERT_DOC, **overrides}, certificate_number="1111-2222-3333-4444-5555")


class TestTheCertificateParsesAtAll:
    """The reported bug: one non-numeric code made the whole certificate unfetchable."""

    def test_tenure_nd_does_not_fail_validation(self):
        assert _doc(tenure="ND").tenure_code == "ND"

    def test_built_form_nr_does_not_fail_validation(self):
        assert _doc(built_form="NR").built_form_code == "NR"

    def test_every_coded_field_tolerates_a_non_numeric_key(self):
        doc = _doc(built_form="NR", property_type="ND", tenure="ND")
        assert (doc.built_form_code, doc.property_type_code, doc.tenure_code) == (
            "NR", "ND", "ND")


class TestNumericCodesStillJoinTheCodebook:
    """Certificates send `4`; the code table sends `"4"`. They must still meet."""

    def test_an_integer_code_is_carried_in_the_upstream_key_space(self):
        doc = _doc()
        assert (doc.built_form_code, doc.property_type_code, doc.tenure_code) == (
            "4", "2", "3")

    def test_a_code_of_zero_is_preserved_and_not_read_as_absent(self):
        assert _doc(built_form=0).built_form_code == "0"


class TestUnknownIsNotAbsent:
    """'the upstream says unknown' and 'the upstream said nothing' stay distinct."""

    def test_an_absent_code_is_none(self):
        raw = {k: v for k, v in CERT_DOC.items() if k != "tenure"}
        assert EPCCertificateDoc.from_source(raw, certificate_number="1").tenure_code is None

    def test_a_stated_unknown_is_not_none(self):
        assert _doc(tenure="ND").tenure_code is not None

    def test_an_empty_string_is_absence_not_a_code(self):
        assert _doc(tenure="").tenure_code is None


class TestTheCodebookKeepsNonNumericKeys:
    def _book(self, body):
        async def handler(request):
            return httpx.Response(200, json=body)
        return EPCCodebook(transport=httpx.MockTransport(handler))

    def test_nd_resolves_to_its_label_rather_than_being_skipped(self):
        book = self._book(TENURE_TABLE)
        assert asyncio.run(book.label("tenure", "ND", SCHEMA)) == "unknown"

    def test_nr_resolves_to_its_label(self):
        book = self._book(BUILT_FORM_TABLE)
        assert asyncio.run(book.label("built_form", "NR", SCHEMA)) == "Not Recorded"

    def test_numeric_keys_are_unaffected(self):
        book = self._book(TENURE_TABLE)
        assert asyncio.run(book.label("tenure", "3", SCHEMA)) == "rented (private)"

    def test_a_key_absent_from_the_table_is_still_none(self):
        book = self._book(TENURE_TABLE)
        assert asyncio.run(book.label("tenure", "ZZ", SCHEMA)) is None

    def test_a_table_entry_with_no_key_is_still_skipped(self):
        book = self._book({"data": [{"key": None, "values": [{"value": "x"}]}]})
        assert asyncio.run(book.label("tenure", "1", SCHEMA)) is None


class TestEndToEndLabelling:
    class _Book:
        def label_sync(self, code, key, schema_version):
            return {("tenure", "ND"): "unknown",
                    ("built_form", "NR"): "Not Recorded",
                    ("built_form", "4"): "Mid-Terrace",
                    ("property_type", "2"): "Flat",
                    ("tenure", "3"): "rented (private)"}.get((code, key))

    def test_unknown_tenure_reaches_the_legacy_field_as_a_label(self):
        d = to_epcdata(_doc(tenure="ND"), codebook=self._Book())
        assert d.tenure == "unknown"

    def test_not_recorded_built_form_reaches_the_legacy_field_as_a_label(self):
        d = to_epcdata(_doc(built_form="NR"), codebook=self._Book())
        assert d.built_form == "Not Recorded"

    def test_the_ordinary_case_is_unchanged(self):
        d = to_epcdata(_doc(), codebook=self._Book())
        assert (d.built_form, d.property_type, d.tenure) == (
            "Mid-Terrace", "Flat", "rented (private)")

    def test_a_resolved_label_emits_no_unresolved_warning(self):
        _, warnings = to_epcdata(_doc(tenure="ND"), codebook=self._Book(), return_warnings=True)
        assert not any("tenure code" in w for w in warnings)


@pytest.mark.skipif(os.getenv("RUN_LIVE_TESTS") != "1", reason="Set RUN_LIVE_TESTS=1")
@pytest.mark.skipif(not os.getenv("EPC_API_TOKEN"), reason="EPC credentials not set")
class TestAgainstTheLiveCertificatesThatFailed:
    """The two certificates observed failing on 2026-09-05."""

    @pytest.mark.parametrize("number,field,code", [
        ("0070-3068-7679-2402-8091", "tenure_code", "ND"),
        ("9075-3062-2205-6806-4204", "built_form_code", "NR"),
    ])
    def test_the_certificate_is_retrievable(self, number, field, code):
        from property_core.epc_client import EPCClient

        async def go():
            return await EPCClient().get_certificate_doc(number)

        try:
            doc = asyncio.run(go())
        except httpx.HTTPError as exc:
            pytest.skip(f"EPC API unavailable: {exc}")
        if doc is None:
            pytest.skip(f"certificate {number} no longer published")
        assert getattr(doc, field) == code
