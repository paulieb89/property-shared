"""PR 1 — the governing specification ships with the code, and attribution is exact.

The attribution literal below is pinned IN THIS FILE on purpose. Importing it
from the same constant the docs and runtime use would make the test pass even if
that constant were corrupted -- it would assert only that a value equals itself.

Spec: docs/design/ppd-source-routing.md section 6.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SPEC = REPO / "docs" / "design" / "ppd-source-routing.md"

# Pinned literal. Do NOT replace with an import.
REQUIRED_ATTRIBUTION = (
    "Contains HM Land Registry data © Crown copyright and database right 2021. "
    "This data is licensed under the Open Government Licence v3.0."
)


def test_governing_specification_ships_with_the_code():
    assert SPEC.exists(), "PR 1 must land the specification that governs PRs 1-4"


def test_specification_is_version_stamped():
    """Rev 8 -- the corpus-acceptance and artifact-distribution decision round.

    The stamp moves only on a decision round, never on an edit in passing, so
    this assertion is what makes "frozen" mean something.
    """
    head = SPEC.read_text().splitlines()[0]
    assert "rev 8" in head and "FROZEN" in head, head


def _normalised(text: str) -> str:
    """Strip markdown blockquote markers and collapse wrapping.

    Presentation only -- the wording itself is never altered.
    """
    lines = [ln.lstrip().removeprefix("> ").removeprefix(">") for ln in text.splitlines()]
    return " ".join(" ".join(lines).split())


def test_specification_states_the_exact_attribution():
    assert _normalised(REQUIRED_ATTRIBUTION) in _normalised(SPEC.read_text())


def test_the_runtime_emits_the_exact_attribution():
    """The gap this file used to leave open.

    It pinned the literal against the SPECIFICATION only, so a runtime that
    computed the statement from the current year satisfied every assertion here
    while emitting the wrong sentence. The year is part of the prescribed
    wording, not a copyright notice rendered for today.
    """
    from property_core.attribution import hmlr_attribution

    assert hmlr_attribution() == REQUIRED_ATTRIBUTION


def test_runtime_attribution_ref_is_compact_and_carries_no_prose():
    from property_core.provenance import ATTRIBUTION_REF

    assert ATTRIBUTION_REF and len(ATTRIBUTION_REF) < 64
    assert "Crown copyright" not in ATTRIBUTION_REF
    assert "Open Government Licence" not in ATTRIBUTION_REF


def test_specification_records_the_snapshot_is_not_distributed():
    body = _normalised(SPEC.read_text())
    assert "private implementation data" in body
    assert "no bulk or address export" in body.lower()
