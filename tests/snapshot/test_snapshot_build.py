"""Red-first tests for the snapshot build window, layout and derived columns.

Everything here runs on a handful of synthetic CSV rows. The real 5.5 GB
`pp-complete.csv` is never touched by the test suite: a build gate that can only
be exercised at full scale is a gate nobody runs.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb", reason="needs the optional 'snapshot' extra")

from tools.ppd_snapshot.build import (  # noqa: E402
    PARTITION_YEARS,
    PROVISIONAL_MONTHS,
    BuildRequest,
    build_snapshot,
    coverage_start,
    expected_years,
    provisional_boundary,
)
from tests.snapshot.build_fixtures import csv_row, write_source_csv  # noqa: E402


# -- window arithmetic -------------------------------------------------------

def test_coverage_starts_at_the_first_year_of_ppd():
    # 32 partitions ending 2026 opens the window on 1995-01-01, the first year
    # of Price Paid Data. Full history is what lets the subject-property lookup
    # -- the one unbounded query -- route to the snapshot at all.
    #
    # This pins the arithmetic that PARTITION_YEARS has to track: when the
    # release year rolls to 2027, 32 would start the window at 1996 and quietly
    # drop a year, so the constant must be incremented and this test is what
    # says so.
    assert coverage_start(date(2026, 6, 30)) == date(1995, 1, 1)


def test_expected_years_span_ppd_history():
    assert expected_years(date(2026, 6, 30)) == tuple(range(1995, 2027))
    assert len(expected_years(date(2026, 6, 30))) == PARTITION_YEARS


def test_provisional_boundary_is_first_day_of_the_month_three_before_the_end():
    assert PROVISIONAL_MONTHS == 3
    assert provisional_boundary(date(2026, 6, 30)) == date(2026, 3, 1)


def test_provisional_boundary_wraps_across_the_year_end():
    assert provisional_boundary(date(2026, 1, 31)) == date(2025, 10, 1)


# -- the build ---------------------------------------------------------------

@pytest.fixture
def built(tmp_path: Path):
    csv_path = write_source_csv(tmp_path / "pp.csv", [
        csv_row("{AAA}", "B5 7AA", "2016-01-01 00:00", 200_000),
        csv_row("{BBB}", "B5 7AB", "2024-03-01 00:00", 210_000),
        csv_row("{CCC}", "B50 4AA", "2024-03-01 00:00", 400_000),
        csv_row("{DDD}", "M3 7AA", "2026-06-30 00:00", 250_000),
        # Outside the window on both sides -- must not reach the snapshot.
        csv_row("{OLD}", "B5 7AC", "1994-12-31 00:00", 100_000),
        csv_row("{NEW}", "B5 7AD", "2026-07-01 00:00", 500_000),
    ])
    result = build_snapshot(BuildRequest(
        csv_path=csv_path,
        out_dir=tmp_path / "snapshot",
        coverage_to=date(2026, 6, 30),
        temp_dir=tmp_path / "tmp",
    ))
    return result


def test_build_writes_one_parquet_file_per_expected_year(built):
    written = sorted(p.relative_to(built.snapshot_dir).as_posix()
                     for p in built.snapshot_dir.rglob("*.parquet"))
    assert written == [f"year={y}/data.parquet" for y in range(1995, 2027)]
    assert built.parquet_files == PARTITION_YEARS


def test_build_writes_nothing_but_parquet_partitions(built):
    stray = [p.relative_to(built.snapshot_dir).as_posix()
             for p in built.snapshot_dir.rglob("*")
             if p.is_file() and p.suffix != ".parquet"]
    assert stray == []


def test_build_excludes_rows_outside_the_declared_window(built):
    con = duckdb.connect()
    ids = [r[0] for r in con.execute(
        f"SELECT transaction_id FROM read_parquet("
        f"'{built.snapshot_dir}/**/*.parquet') ORDER BY transaction_id").fetchall()]
    assert ids == ["AAA", "BBB", "CCC", "DDD"]
    assert built.rows == 4


def test_build_derives_exact_outcode_and_sector_columns(built):
    con = duckdb.connect()
    rows = con.execute(
        f"SELECT transaction_id, outcode, sector FROM read_parquet("
        f"'{built.snapshot_dir}/**/*.parquet') ORDER BY transaction_id").fetchall()
    assert rows == [
        ("AAA", "B5", "B5 7"),
        ("BBB", "B5", "B5 7"),
        ("CCC", "B50", "B50 4"),
        ("DDD", "M3", "M3 7"),
    ]


def test_build_reports_the_window_it_was_given(built):
    assert built.coverage_from == date(1995, 1, 1)
    assert built.coverage_to == date(2026, 6, 30)
    assert built.provisional_from == date(2026, 3, 1)


def test_build_records_the_duckdb_version_that_wrote_the_files(built):
    assert built.duckdb_version.startswith("v1.5.")


# -- malformed required source values fail the build ------------------------

def build_from(tmp_path: Path, rows, name: str = "s"):
    csv_path = write_source_csv(tmp_path / f"pp-{name}.csv", rows)
    return build_snapshot(BuildRequest(
        csv_path=csv_path, out_dir=tmp_path / name, coverage_to=date(2026, 6, 30),
        temp_dir=tmp_path / f"tmp-{name}"))


def test_an_unparseable_date_anywhere_in_the_source_fails_the_build(tmp_path):
    from tools.ppd_snapshot.build import MalformedSourceRows

    with pytest.raises(MalformedSourceRows, match="transfer_date"):
        build_from(tmp_path, [
            csv_row("{OK}", "B5 7AA", "2024-03-01 00:00", 200_000),
            # Unplaceable: it may or may not belong in the window, and dropping
            # it would silently decide that it does not.
            csv_row("{BAD}", "B5 7AB", "not-a-date", 210_000),
        ])


def test_an_unparseable_price_inside_the_window_fails_the_build(tmp_path):
    from tools.ppd_snapshot.build import MalformedSourceRows

    rows = [csv_row("{OK}", "B5 7AA", "2024-03-01 00:00", 200_000)]
    bad = list(csv_row("{BAD}", "B5 7AB", "2024-04-01 00:00", 0))
    bad[1] = "not-a-price"
    with pytest.raises(MalformedSourceRows, match="price"):
        build_from(tmp_path, rows + [tuple(bad)])


def test_a_blank_transaction_id_inside_the_window_fails_the_build(tmp_path):
    from tools.ppd_snapshot.build import MalformedSourceRows

    with pytest.raises(MalformedSourceRows, match="transaction_id"):
        build_from(tmp_path, [
            csv_row("{OK}", "B5 7AA", "2024-03-01 00:00", 200_000),
            csv_row("  ", "B5 7AB", "2024-04-01 00:00", 210_000),
        ])


def test_a_malformed_price_outside_the_window_does_not_fail_the_build(tmp_path):
    # Rows the snapshot never serves are not its problem.
    bad = list(csv_row("{OLD}", "B5 7AB", "1994-04-01 00:00", 0))
    bad[1] = "not-a-price"
    built = build_from(tmp_path, [
        csv_row("{OK}", "B5 7AA", "2024-03-01 00:00", 200_000), tuple(bad)])
    assert built.rows == 1


def test_the_build_counts_eligible_source_rows_independently_of_what_it_wrote(
        tmp_path):
    built = build_from(tmp_path, [
        csv_row("{A}", "B5 7AA", "2024-03-01 00:00", 200_000),
        csv_row("{B}", "B5 7AB", "2016-03-01 00:00", 210_000),
        csv_row("{OLD}", "B5 7AC", "1994-03-01 00:00", 100_000),
    ])
    assert built.eligible_source_rows == 2
    assert built.rows == 2


# -- prices must be canonical integers, not merely castable ------------------

def _with_price(text: str):
    row = list(csv_row("{BAD}", "B5 7AB", "2024-04-01 00:00", 0))
    row[1] = text
    return tuple(row)


@pytest.mark.parametrize("text,cast_to", [
    ("1.5", "2"),        # rounded, not rejected
    ("2.5", "3"),
    (".5", "1"),
    ("100.", "100"),
    ("1e3", "1000"),     # scientific notation
    ("0x10", "16"),      # hexadecimal
    ("1_000", "1000"),   # digit separators
    ("+100", "100"),     # signed forms
    ("-100", "-100"),
])
def test_a_non_canonical_price_fails_the_build(tmp_path, text, cast_to):
    """`TRY_CAST` accepts far more than an integer and silently changes it.

    A price of "1.5" becomes 2 and a price of "0x10" becomes 16, with nothing
    downstream able to tell: the artifact holds a plausible integer, so every
    gate that reads the snapshot agrees with itself.
    """
    from tools.ppd_snapshot.build import MalformedSourceRows

    with pytest.raises(MalformedSourceRows, match="price"):
        build_from(tmp_path, [
            csv_row("{OK}", "B5 7AA", "2024-03-01 00:00", 200_000),
            _with_price(text),
        ], name=f"p{abs(hash(text))}")


def test_a_canonical_price_is_accepted(tmp_path):
    built = build_from(tmp_path, [_with_price("100")])
    assert built.rows == 1


def test_surrounding_whitespace_does_not_make_a_price_non_canonical(tmp_path):
    built = build_from(tmp_path, [_with_price(" 100 ")], name="ws")
    assert built.rows == 1
