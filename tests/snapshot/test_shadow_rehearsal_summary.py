"""Guards for the reconstructed rehearsal summary. **No optional dependency.**

`docs/ops/ppd-shadow-rehearsal-summary.md` is the only durable record of the
real rehearsal run: the tool's `--report` JSON was not retained, and a search on
2026-08-29 across the repository, the home directory and `.ppd-lab/` found none.
The summary is therefore prose assembled from commit `6f969eb` and PR #31, and
the danger it carries is precisely that it will later be cited as though a file
had been verified.

These guards live in their own module, deliberately. `test_shadow_rehearsal.py`
runs the tool, so it `importorskip`s DuckDB and zstandard at module level; a
document guard that inherited that skip would vanish in exactly the runs where
nobody was watching for it. Nothing here imports anything optional.

Two failures are worth naming, because a looser test misses both:

* **A label bound to no value.** Asserting that "0" appears somewhere in the
  document is satisfied by a coverage date, a byte count, or a summary claiming
  nine failed assertions. Each figure is read out of its own table row and
  compared exactly.

* **Row data pasted in.** Checked against the fixture values this suite already
  forbids in a report, and against quoted JSON field names -- not against a
  pattern for what an id or a price looks like, which would match coverage dates
  and byte counts and would have to be loosened until it meant nothing.
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.snapshot.rehearsal_fixtures import FORBIDDEN_IN_REPORT

SUMMARY = (Path(__file__).resolve().parents[2]
           / "docs" / "ops" / "ppd-shadow-rehearsal-summary.md")

#: JSON field names that only appear if row data was pasted in. Quoted, so
#: ordinary prose about a district search or a town cannot trip them -- a real
#: leak is JSON-shaped, or is one of the fixture values above.
FORBIDDEN_KEYS_IN_SUMMARY = ['"transaction_id"', '"paon"', '"saon"', '"street"',
                             '"locality"', '"town"', '"district"', '"county"',
                             '"price"']

#: Exactly what commit 6f969eb and PR #31 record, bound label to value. Reading
#: these out of their own rows is what makes `failed` mean zero rather than
#: "the character 0 occurs somewhere in the document".
RECORDED_RESULTS = {
    "Exit code": "0",
    "Cases": "13 of 13",
    "Assertions passed": "85",
    "Assertions failed": "0",
    "Assertions not evaluable": "2",
}

#: Artifact identity, from the same two sources.
RECORDED_ARTIFACT = ("v20260828T194003Z", "50f802b2")


def _body() -> str:
    return " ".join(SUMMARY.read_text().split())


def _rows() -> dict[str, str]:
    """Every `| label | value |` row, with markdown emphasis stripped.

    A label missing from this mapping fails the lookup below, so deleting a row
    is as loud as changing its value.
    """
    rows: dict[str, str] = {}
    for line in SUMMARY.read_text().splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 2 and cells[0] and not set(cells[0]) <= {"-", ":"}:
            rows[cells[0]] = cells[1].replace("**", "").strip()
    return rows


def test_the_rehearsal_summary_is_labelled_reconstructed():
    """It must not read as the tool's own output.

    A document that looks like a report, but was assembled from a commit
    message, is evidence of the wrong kind: it would be cited later as though a
    file had been verified, when what was verified was prose about a file.
    """
    assert SUMMARY.exists(), "the real rehearsal result is recorded only in git"
    body = _body()
    assert "econstructed" in body, "the summary does not say it is reconstructed"
    for source in ("6f969eb", "#31"):
        assert source in body, f"the summary does not cite {source}"
    assert "not retained" in body, (
        "the summary does not record that the original report JSON is gone -- a "
        "later reader would assume it was consulted"
    )
    assert "never" in body and "Stage 1 evidence" in body, (
        "the summary is not labelled as something that can never be Stage 1 "
        "evidence, which its own subject matter requires"
    )


def test_the_rehearsal_summary_carries_no_row_data():
    """Same rule as the report it describes: aggregates only."""
    raw = SUMMARY.read_text()
    for forbidden in FORBIDDEN_IN_REPORT:
        assert forbidden not in raw, (
            f"the summary leaked the fixture value {forbidden!r}"
        )
    for key in FORBIDDEN_KEYS_IN_SUMMARY:
        assert key not in raw, (
            f"the summary carries the row field {key}; it records counts, "
            f"outcomes and artifact identity only"
        )


def test_each_recorded_result_is_bound_to_its_own_label():
    """The figures, read out of their own rows and compared exactly.

    Substring matching would have accepted `failed = 9` and
    `not_evaluable = 7`: the digits it was really matching live elsewhere in the
    document. A result table is a set of claims, and each one has to be checked
    against the claim it makes, not against the document as a bag of characters.
    """
    rows = _rows()
    for label, expected in RECORDED_RESULTS.items():
        assert label in rows, (
            f"the summary no longer reports {label!r}; commit 6f969eb records it"
        )
        assert rows[label] == expected, (
            f"the summary reports {label} = {rows[label]!r}, but commit 6f969eb "
            f"and PR #31 record {expected!r}"
        )


def test_the_summary_binds_to_the_artifact_the_run_used():
    """A result with no artifact identity describes nothing in particular."""
    rows = _rows()
    assert "Artifact" in rows, "the summary names no artifact"
    for token in RECORDED_ARTIFACT:
        assert token in rows["Artifact"], (
            f"the artifact row no longer carries {token!r}, so the result is "
            f"not bound to the bundle it was produced from"
        )


def test_the_summary_claims_no_outcome_neither_source_records():
    """It may say it HAS no p95; it may not report one.

    Banning the bare token would ban the disclaimer along with the claim, and
    the disclaimer is the reason this document is not Stage 1 evidence.
    """
    body = _body()
    assert "no p95 criterion" in body, (
        "the summary does not state that it satisfies no p95 criterion, which "
        "is the whole reason it is not Stage 1 evidence"
    )
    for claimed in ("p95 of", "p95:", "p95 =", "divergence rate",
                    "field equality"):
        assert claimed not in body, (
            f"the summary reports {claimed!r}; a rehearsal has no live arm and "
            f"neither source records it"
        )


def test_no_result_row_is_left_unchecked():
    """Every numeric outcome row is one this file pins.

    Without this, a new row -- "Divergences: 0", say -- could be added to the
    result table and no assertion would ever look at it.
    """
    numeric = {label: value for label, value in _rows().items()
               if re.fullmatch(r"[\d ,.]+(of [\d ,.]+)?", value)}
    unchecked = set(numeric) - set(RECORDED_RESULTS)
    assert not unchecked, (
        f"the summary states numeric outcomes nothing pins: {sorted(unchecked)}. "
        f"Add them to RECORDED_RESULTS with the value the sources record, or "
        f"remove them -- an unchecked figure is one nobody verified."
    )
