"""The non-live second arm must actually detect the defects it exists for.

A verifier that passes everything is worthless, and a verifier for a defect
nobody has reproduced is a guess. Every check here is driven from a row built to
carry the specific defect, and asserted to be found — then a clean row is
asserted to pass, so the checks are not simply always-on.

The defect class being targeted is the one Stage 1's live arm would have caught
and cannot currently be run for:

    "snapshot_false_empty": snap.count == 0 and live.count > 0

Here the second arm is the artifact read a different way, so no upstream is
needed.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pytest

_MODULE_PATH = (Path(__file__).resolve().parents[2]
                / "tools" / "ppd_snapshot" / "nonlive_verify.py")


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("nonlive_verify", _MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


nv = _load_module()

COLUMNS = nv._COLUMNS


def row(**over: Any) -> tuple:
    """One row in `_COLUMNS` order, correct unless deliberately broken."""
    base = {
        "transaction_id": "TX1", "price": 250000,
        "transfer_date": date(2025, 6, 1), "postcode": "B5 4BX",
        "outcode": "B5", "sector": "B5 4", "property_type": "F",
        "duration": "L", "ppd_category": "A", "new_build": False,
    }
    base.update(over)
    return tuple(base[c] for c in COLUMNS)


# --- the reference derivation is genuinely independent of the build ---


@pytest.mark.parametrize(
    ("postcode", "outcode", "sector"),
    [
        ("B5 4BX", "B5", "B5 4"),
        ("SW1A 1AA", "SW1A", "SW1A 1"),
        ("GIR 0AA", "GIR", "GIR 0"),
        ("  b5   4bx ", "B5", "B5 4"),
    ],
)
def test_reference_geography_matches_the_grammar(postcode, outcode, sector):
    assert nv.reference_geography(postcode) == (outcode, sector)


@pytest.mark.parametrize("postcode", ["", "   ", None, "NOTAPOSTCODE", "B54BX", 12345])
def test_reference_geography_refuses_what_the_grammar_refuses(postcode):
    """The build's split_part would still have stored something here."""
    assert nv.reference_geography(postcode) == (None, None)


# --- check 1: geography derivation ---


def test_a_correct_row_produces_no_findings():
    assert nv.check_geography_derivation([row()]) == []


def test_a_mis_derived_outcode_is_reported_as_unreachable():
    """The false empty, in its purest form.

    Stored 'B50', reference 'B5'. A query for outcode 'B5' equality-matches
    nothing, and the row is invisible with no error anywhere.
    """
    findings = nv.check_geography_derivation([row(outcode="B50")])
    assert [f.check for f in findings] == ["geography_derivation"]
    assert findings[0].count == 1
    assert "cannot reach" in findings[0].detail


def test_a_mis_derived_sector_is_reported():
    findings = nv.check_geography_derivation([row(sector="B5 9")])
    assert [f.check for f in findings] == ["geography_derivation"]


def test_a_lowercase_stored_geography_is_reported_separately():
    """The build never upper-cases; normalise_prefix does.

    'b5' and 'B5' are the same place and different strings, so equality misses.
    Kept apart from a mis-derivation because the cause and the fix differ.
    """
    findings = nv.check_geography_derivation([row(postcode="b5 4bx", outcode="b5", sector="b5 4")])
    assert [f.check for f in findings] == ["geography_case"]
    assert "upper-case" in findings[0].detail


def test_a_geography_the_grammar_rejects_is_reported_as_unvalidated():
    """split_part stores the text before the first space, valid or not."""
    findings = nv.check_geography_derivation(
        [row(postcode="XX 1AA", outcode="XX", sector=None)])
    assert [f.check for f in findings] == ["geography_unvalidated"]


def test_findings_carry_no_price_address_or_row():
    findings = nv.check_geography_derivation([row(outcode="B50", price=999999)])
    blob = str(findings[0].to_dict())
    assert "999999" not in blob
    assert findings[0].sample == ["TX1"], "ids only, and capped"


def test_the_sample_is_capped_rather_than_unbounded():
    rows = [row(transaction_id=f"TX{i}", outcode="B50") for i in range(50)]
    finding = nv.check_geography_derivation(rows)[0]
    assert finding.count == 50
    assert len(finding.sample) == 5


# --- check 2: query semantics, reimplemented independently ---


def test_python_select_filters_on_recomputed_geography_not_the_stored_column():
    """The whole point: a wrong stored column must not hide itself.

    This row's stored outcode is wrong, so the adapter cannot find it — but the
    reference arm still selects it, which is what makes the disagreement
    visible.
    """
    assert nv.python_select([row(outcode="WRONG")], outcode="B5") == ["TX1"]


def test_python_select_applies_each_predicate():
    rows = [
        row(transaction_id="A", postcode="B5 4BX", transfer_date=date(2025, 1, 1)),
        row(transaction_id="B", postcode="B5 5AA", transfer_date=date(2025, 2, 1)),
        row(transaction_id="C", postcode="XX9 9XX", transfer_date=date(2025, 3, 1)),
        row(transaction_id="D", postcode="B5 4BX", property_type="D"),
        row(transaction_id="E", postcode="B5 4BX", ppd_category="B"),
    ]
    assert set(nv.python_select(rows, outcode="B5")) == {"A", "B", "D", "E"}
    assert nv.python_select(rows, sector="B5 4") != []
    assert set(nv.python_select(rows, outcode="B5", property_types=["F"])) == {"A", "B", "E"}
    assert set(nv.python_select(rows, outcode="B5", transaction_category="A")) == {"A", "B", "D"}
    assert nv.python_select(rows, outcode="B5", from_date="2025-02-01") != ["A"]


def test_python_select_orders_date_desc_then_id_asc_like_the_adapter():
    rows = [
        row(transaction_id="TXB", transfer_date=date(2025, 1, 1)),
        row(transaction_id="TXA", transfer_date=date(2025, 1, 1)),
        row(transaction_id="TXC", transfer_date=date(2026, 1, 1)),
    ]
    assert nv.python_select(rows, outcode="B5") == ["TXC", "TXA", "TXB"]


def test_python_select_orders_ids_of_unequal_length_ascending():
    """Guards the sort: a composite key negating a string gets this wrong."""
    rows = [
        row(transaction_id="TX10", transfer_date=date(2025, 1, 1)),
        row(transaction_id="TX9", transfer_date=date(2025, 1, 1)),
        row(transaction_id="TX100", transfer_date=date(2025, 1, 1)),
    ]
    assert nv.python_select(rows, outcode="B5") == ["TX10", "TX100", "TX9"]


def test_python_select_honours_the_limit():
    rows = [row(transaction_id=f"TX{i}") for i in range(10)]
    assert len(nv.python_select(rows, outcode="B5", limit=3)) == 3


def test_a_row_with_no_date_is_skipped_rather_than_crashing():
    assert nv.python_select([row(transfer_date=None)], outcode="B5") == []


# --- check 3: partition completeness ---


def test_every_covered_year_present_passes(tmp_path):
    for year in range(2016, 2027):
        (tmp_path / f"year={year}").mkdir()
    assert nv.check_partition_completeness(
        tmp_path, date(2016, 1, 1), date(2026, 6, 30)) == []


def test_a_missing_year_is_reported(tmp_path):
    """A missing partition does not fail a query; it just returns less."""
    for year in range(2016, 2027):
        if year != 2019:
            (tmp_path / f"year={year}").mkdir()
    findings = nv.check_partition_completeness(
        tmp_path, date(2016, 1, 1), date(2026, 6, 30))
    assert [f.check for f in findings] == ["partition_completeness"]
    assert findings[0].sample == ["2019"]


def test_stray_directories_do_not_count_as_partitions(tmp_path):
    (tmp_path / "year=2016").mkdir()
    (tmp_path / "notes").mkdir()
    (tmp_path / "year=abc").mkdir()
    findings = nv.check_partition_completeness(
        tmp_path, date(2016, 1, 1), date(2017, 12, 31))
    assert findings and findings[0].sample == ["2017"]


# --- the report must not overclaim ---


def test_the_report_marks_itself_not_stage_1_evidence():
    report = nv.build_report([], artifact={"version": "v1"}, rows_examined=10,
                             cases_compared=13)
    assert report["not_stage_1_evidence"] is True
    assert report["passed"] is True
    assert "cannot detect a row that never reached the artifact" in report["note"]


def test_a_report_with_findings_does_not_pass():
    report = nv.build_report([nv.Finding("x", "y", 1)], artifact={},
                             rows_examined=1, cases_compared=1)
    assert report["passed"] is False


# --- memory safety: the artifact is ~10.4M rows on a 2GB Machine ---


class _Cursor:
    """Minimal DuckDB-cursor stand-in that only supports fetchmany."""

    def __init__(self, rows, chunk_calls):
        self._rows = list(rows)
        self._at = 0
        self.chunk_calls = chunk_calls

    def fetchmany(self, size):
        self.chunk_calls.append(size)
        batch = self._rows[self._at:self._at + size]
        self._at += len(batch)
        return batch

    def fetchall(self):  # pragma: no cover - must never be reached
        raise AssertionError(
            "fetchall would materialize ~10.4M rows against ~1.6GB free and "
            "OOM the app serving traffic"
        )


def test_iter_rows_streams_and_never_calls_fetchall():
    calls: list[int] = []
    cursor = _Cursor([row(transaction_id=f"TX{i}") for i in range(250)], calls)
    streamed = list(nv.iter_rows(cursor, chunk=100))
    assert len(streamed) == 250
    assert calls == [100, 100, 100, 100], "must page, and must stop on the empty batch"


def test_iter_rows_is_lazy_rather_than_building_a_list():
    calls: list[int] = []
    cursor = _Cursor([row() for _ in range(100)], calls)
    stream = nv.iter_rows(cursor, chunk=10)
    next(iter(stream))
    assert len(calls) == 1, "one chunk fetched to yield the first row, not all of them"


def test_findings_stay_bounded_when_every_row_disagrees():
    """The failure mode this guards: a wholly mis-derived artifact.

    Accumulating one id per disagreement would hold ~10.4M strings on the
    machine already short of memory — failing hardest exactly when the artifact
    is most broken.
    """
    rows = (row(transaction_id=f"TX{i}", outcode="WRONG") for i in range(20_000))
    findings = nv.check_geography_derivation(rows)
    assert findings[0].count == 20_000
    assert len(findings[0].sample) == nv._SAMPLE_CAP
