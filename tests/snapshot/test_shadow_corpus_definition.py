"""Guards for the shadow-corpus DEFINITION.

`docs/design/ppd-shadow-corpus.md` defines the Stage 1 shadow corpus as a
*contract*: request shapes, frozen parameters, semantic assertions, a divergence
taxonomy, and machine-checkable warning classes. It deliberately contains no
artifact, no execution date and no aggregate counts -- those belong to a corpus
INSTANCE, which is written when the Stage 1 artifact is selected. A monthly
rebuild then produces a new instance and restarts Stage 1, instead of quietly
rewriting the evidence for a run already in progress.

Two things in that document are load-bearing enough to break silently, so they
are pinned here:

1. **The warning-class predicates.** The Definition says to compare warning
   *classes*, never warning *text*, because snapshot and live warnings are
   deliberately worded differently by source. A class is matched by a narrow
   substring, and each substring is quoted from the call site that emits it.
   Reword that call site and the Definition starts silently matching nothing --
   a corpus that reports "no warnings diverged" because it can no longer see any
   warning at all. Each substring is therefore asserted against BOTH the
   emitting module and the document, so the two cannot drift apart.

2. **The `months` -> `from_date` arithmetic.** `comps` accepts no absolute
   window, so a harness that wants to record the window it queried has to
   reconstruct it. The Definition publishes that reconstruction. It is exercised
   here against the real service through the `_fetch_comps` seam, so the pin is
   behavioural rather than a copy of the source line: if the derivation changes,
   every recorded window in every observation is wrong, and this fails.

Neither test asserts anything about a snapshot artifact, and neither touches the
network.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DEFINITION = REPO / "docs" / "design" / "ppd-shadow-corpus.md"
SERVICE = REPO / "property_core" / "ppd_service.py"
SOURCE = REPO / "property_core" / "ppd_source.py"


def _normalised(path: Path) -> str:
    return " ".join(path.read_text().split())


# ---------------------------------------------------------------------------
# 1. Warning classes: the Definition and the emitting call site agree
# ---------------------------------------------------------------------------

#: (class name, substring the predicate matches, module that emits it).
#: Every substring is quoted from merged main. A class backed by a STRUCTURED
#: field is not listed here -- see the separate test below, which is the
#: stronger guarantee: no string matching at all.
WARNING_CLASSES = [
    ("coverage clamp", "beyond snapshot coverage", SOURCE),
    ("coverage clamp", "are not included", SOURCE),
    ("coverage-floor narrowing", "narrowed to", SOURCE),
    ("freshness", "days behind its coverage end", SOURCE),
    ("escalation containment", "auto-escalation not applied:", SERVICE),
    ("live incompleteness", "the upstream window was not exhausted", SERVICE),
    ("geography containment", "removed by geography containment", SERVICE),
]


@pytest.mark.parametrize(
    "klass, substring, module",
    WARNING_CLASSES,
    ids=[f"{k}:{sub[:28]}" for k, sub, _mod in WARNING_CLASSES],
)
def test_each_warning_class_substring_is_still_emitted_by_its_call_site(
        klass, substring, module):
    """The predicate must match something the code actually says.

    A reworded warning does not fail any existing test -- warnings are prose --
    so without this pin the corpus would keep passing while silently observing
    an empty set of warnings.
    """
    assert substring in module.read_text(), (
        f"warning class {klass!r}: {module.name} no longer emits {substring!r}. "
        f"Either restore the wording or update the class predicate in "
        f"{DEFINITION.name} deliberately -- the corpus matches on this substring."
    )


@pytest.mark.parametrize(
    "klass, substring, module",
    WARNING_CLASSES,
    ids=[f"{k}:{sub[:28]}" for k, sub, _mod in WARNING_CLASSES],
)
def test_each_warning_class_substring_is_published_in_the_definition(
        klass, substring, module):
    """And the document must publish the same substring the code emits."""
    assert substring in DEFINITION.read_text(), (
        f"warning class {klass!r}: the corpus definition does not publish the "
        f"predicate substring {substring!r} emitted by {module.name}"
    )


def test_the_structured_classes_are_fields_not_string_matches():
    """Two classes need no string matching, and the Definition must say so.

    `recent_period_provisional` and `thin_market` are typed fields. Matching
    them by warning text would be strictly worse: the field is the contract and
    the warning is its human rendering.
    """
    body = _normalised(DEFINITION)
    assert "provenance.recent_period_provisional is True" in body, (
        "the provisional class is not defined against the structured field"
    )
    assert "response.thin_market is True" in body, (
        "the thin-market class is not defined against the structured field"
    )

    from property_core.models.ppd import PPDCompsResponse
    from property_core.provenance import PPDProvenance

    assert "thin_market" in PPDCompsResponse.model_fields
    assert "recent_period_provisional" in PPDProvenance.model_fields


def test_the_definition_forbids_comparing_warning_text():
    body = _normalised(DEFINITION)
    assert "never" in body and "text" in body
    assert "auto-escalation not applied:" in body, (
        "the one class whose marker is shared and whose tail is deliberately "
        "source-specific must be published with its prefix"
    )


# ---------------------------------------------------------------------------
# 2. The months -> from_date derivation, exercised against the real service
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("months", [1, 6, 24, 60, 120])
def test_comps_derives_from_date_as_today_minus_months_times_thirty_days(
        months, monkeypatch):
    """Behavioural pin, not a copy of the source line.

    A harness recording which window it queried cannot read that window back:
    `comps` takes no absolute date and the provenance block carries coverage
    bounds, not the resolved request. It has to reconstruct it. If this
    derivation changes, every window recorded by every observation is wrong.
    """
    from property_core.ppd_service import PPDService

    seen: dict[str, str] = {}

    def _capture(_self, *, from_date, **_kwargs):
        seen["from_date"] = from_date
        # `_fetch_comps` returns (transactions, provenance_factory, from_snapshot);
        # the factory is called later with the final counts and warnings, once
        # the block can be built atomically (spec section 3.1.2).
        return [], lambda _count, _warnings: None, False

    monkeypatch.setattr(PPDService, "_fetch_comps", _capture)

    before = date.today()
    PPDService().comps(postcode="B5 4", search_level="sector", months=months)
    after = date.today()

    expected_before = (before - timedelta(days=months * 30)).isoformat()
    expected_after = (after - timedelta(days=months * 30)).isoformat()
    # Tolerates a midnight crossing inside the call itself -- which is exactly
    # the hazard the Definition's midnight guard exists to catch at run time.
    assert seen["from_date"] in {expected_before, expected_after}, (
        f"months={months}: comps derived from_date {seen['from_date']!r}, not "
        f"today - {months} * 30 days"
    )


def test_the_definition_publishes_that_derivation():
    body = _normalised(DEFINITION)
    assert "months × 30 days" in body or "months * 30 days" in body, (
        "the corpus definition does not publish the from_date reconstruction "
        "a harness must perform"
    )
    assert "reconstruction" in body, (
        "the definition must record that the window is reconstructed rather "
        "than observed -- provenance does not carry the resolved request window"
    )


def test_the_definition_requires_the_midnight_guard():
    """Two sequential adapter calls can straddle midnight and compare windows
    that differ by a day. The guard must be in the contract, not folklore."""
    body = _normalised(DEFINITION)
    assert "observed_at_before" in body and "observed_at_after" in body
    assert "excluded" in body, (
        "the definition does not say what happens when the dates differ"
    )


# ---------------------------------------------------------------------------
# 3. The Definition / Instance split
# ---------------------------------------------------------------------------

def test_the_definition_carries_no_instance_data():
    """No artifact, no execution date, no counts.

    This is the whole point of the split: a monthly rebuild changes counts and
    moves `provisional_from`, and must produce a NEW instance rather than
    silently rewriting the evidence for a Stage 1 run already under way.
    """
    body = DEFINITION.read_text()
    assert "50f802b2" not in body, "a bundle digest belongs to an instance"
    assert "v20260828T194003Z" not in body, "an artifact version belongs to an instance"
    assert "10,394,935" not in body, "an aggregate count belongs to an instance"
    for stale in ("EXEC =", "EXEC="):
        assert stale not in body, "a frozen execution date belongs to an instance"


def test_the_definition_states_the_lifecycle():
    body = _normalised(DEFINITION)
    assert "restarts Stage 1" in body, (
        "the definition does not state that a new artifact restarts Stage 1"
    )
    assert "Instance" in body and "Definition" in body


def test_the_universal_invariants_are_recorded():
    """`comps` never sends to_date, so no case can ever be coverage-contained."""
    body = _normalised(DEFINITION)
    assert "sample_complete" in body and "false" in body
    assert "completeness_basis" in body


def test_stage_1_exit_criteria_are_carried_forward_unchanged():
    body = _normalised(DEFINITION)
    for criterion in ("Zero unexplained false empties", "Zero geography contamination",
                      "100% field equality on shared transaction IDs",
                      "Every divergence classified", "Zero snapshot errors",
                      "p95 < 1 second"):
        assert criterion in body, f"Stage 1 exit criterion missing: {criterion!r}"


def test_the_rehearsal_cannot_be_filed_as_stage_1():
    body = _normalised(DEFINITION)
    assert "never filed as Stage 1 evidence" in body


# ---------------------------------------------------------------------------
# 4. The freeze
# ---------------------------------------------------------------------------

def test_the_corpus_is_frozen_not_proposed():
    """Its own section 1 says it is frozen for Stage 1's duration.

    Carrying "Status: proposed" contradicted that, and left the next reader
    entitled to reopen shapes that a real rehearsal had already corrected.
    """
    body = _normalised(DEFINITION)
    assert "**Status:** proposed" not in body, (
        "the corpus still calls itself proposed while its own section 1 says it "
        "is agreed before Stage 1 and frozen for its duration"
    )
    assert "frozen" in body.lower(), "the corpus does not state that it is frozen"
    assert "2026-08-29" in body, "the freeze carries no date"
    assert "rev 8" in body, (
        "the corpus still cites a superseded revision of its governing spec"
    )


def test_the_freeze_does_not_claim_an_instance():
    """An absent Instance is the design, not an outstanding task.

    Section 0 says an Instance is written when the Stage 1 artifact is selected.
    Describing its absence as incompleteness would invite someone to write one
    against no artifact, which is exactly the coupling the split exists to
    prevent -- and it would make this document's status permanently unachievable.
    """
    body = _normalised(DEFINITION)
    assert "written when the Stage 1 artifact is selected" in body, (
        "the Definition no longer states when an Instance comes into being"
    )
    for overreach in ("Instance is outstanding", "Instance is missing",
                      "pending Instance", "awaiting an Instance"):
        assert overreach not in body, (
            f"the freeze describes the absent Instance as incomplete work "
            f"({overreach!r}); it is deferred by design, not missing"
        )


def test_the_definition_carries_the_rev_10_p95_qualification():
    """§8 must not keep the pre-rev-10 wording while §7.2 has moved on.

    The Definition says its criteria are carried forward from the governing
    spec. Two documents stating the same criterion differently is the failure
    mode that makes "which one governs?" an open question mid-run.
    """
    body = _normalised(DEFINITION)
    assert ("p95 < 1 second on the deployed production Machine and selected "
            "artifact, measured across the frozen corpus request mix") in body
    assert "on real traffic" not in body, (
        "the Definition still carries the pre-rev-10 'on real traffic' wording"
    )


def test_the_definition_excludes_non_machine_latency_from_the_percentile():
    """A rehearsal's latency must not be able to reach the gate percentile.

    Both tools record per-case latency in the same shape. Without an explicit
    exclusion rule, the cheap mistake is to pool them -- and a workstation run
    against a local artifact is faster than the Machine, so pooling would
    flatter the gate.
    """
    body = _normalised(DEFINITION)
    assert "controlled_synthetic" in body
    assert "excluded from this percentile" in body


def test_the_definition_decides_the_postcode_less_row_question():
    """§11 left it undecided; leaving it so in code would settle it silently.

    Skipping a returned row that carries no postcode means a source could
    return arbitrary rows with the geography blanked and every containment
    check would pass. The decision is recorded here, before Stage 1, rather
    than living only in an implementation.
    """
    body = _normalised(DEFINITION)
    assert "Decided before Stage 1 began" in body
    assert "containment failure" in body
    assert "rows_without_postcode" in body


def test_the_definition_forbids_weakening_the_neighbour_volume_rule():
    """The rule stays qualitative, and tooling refers rather than redefines."""
    body = _normalised(DEFINITION)
    assert "refers the judgement rather than deciding it" in body
    assert "is forbidden" in body
    assert "substitute with recorded justification" in body


def test_the_definition_keeps_the_substitution_route_and_links_the_three():
    body = _normalised(DEFINITION)
    assert "may substitute with recorded justification" in body
    assert "silently false" in body
