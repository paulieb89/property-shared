"""Rev 7-8 — the rollout premises and status, pinned so they cannot drift back.

Specification rev 7 corrected a sizing baseline that had been wrong since rev 1:
§1.1 sized eleven partitions at 214 MiB, which was a **year+area** measurement
applied to the **year-only** layout §1.2 mandates. PR 5 built the real artifact
and measured it. Every figure the rollout depends on moved with it.

Two groups of assertions, and the split matters:

* **Group A — arithmetic is recomputed, never restated.** The derived figures
  (transfer time, simultaneous payload footprint, preflight threshold, bundle
  limit margin) are computed here from the recorded byte counts and compared
  against what the documents print. A future edit that changes a printed number
  without changing the bytes fails; one that changes the bytes must move all of
  them together. Restating "22.3" as a literal in both places would let the
  document and the test drift together while the measurement said otherwise --
  which is the exact failure rev 7 exists to correct.

* **Group B — the premises themselves**, asserted against the document text.

**On 214 MiB.** The figure is not banned: recording that it was wrong is how the
correction stays legible. What is banned is *asserting* it as a current
eleven-partition year-only size. So the permitted occurrences are enumerated by
their anchor -- a named table cell, a named sentence -- and any occurrence that
is not one of them fails. A loose textual window around each hit would be
brittle across table reflows and would quietly accept a new live claim that
happened to sit near an explanatory word.

**Rev 8** added a third group. It is a *status* round, not an architecture one:
it accepts the shadow corpus, records the owner's scoped artifact-distribution
determination, and corrects status text that had gone stale as PRs merged
beneath it -- a Basis paragraph denying the adapter the same document describes,
a changelog requiring an ordering PR 4 made impossible, a runbook citing two
different revisions of its own governing spec. Status text is exactly where a
requirement gets softened by accident, because none of it looks like a
requirement, so `test_revision_8_relaxed_no_requirement` guards the same
invariants for rev 8 that this file already guards for rev 7.

Nothing here relaxes a requirement. The 30 s readiness target, the
`bundle_bytes * 2.5` headroom rule and every Stage 1 exit criterion are
unchanged by rev 7 and by rev 8, and several assertions below exist to keep
them that way.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from property_core.snapshot.fetch import (
    DEFAULT_MAX_BUNDLE_BYTES,
    DISK_HEADROOM_MULTIPLIER,
)

REPO = Path(__file__).resolve().parents[2]
SPEC = REPO / "docs" / "design" / "ppd-source-routing.md"
RUNBOOK = REPO / "docs" / "ops" / "ppd-snapshot-build.md"
CHANGELOG = REPO / "CHANGELOG.md"
DECISION = REPO / "docs" / "design" / "ppd-artifact-distribution-decision.md"

MiB = 1024 ** 2

#: The measurement, from two independent local builds on 2026-08-28 that
#: produced a byte-identical bundle (docs/ops/ppd-snapshot-build.md).
BUNDLE_BYTES = 279_109_872
EXTRACTED_BYTES = 280_925_271

#: Nominal link rate for the transfer calculation. Not a measured rate: no real
#: transfer has been timed on either Fly Machine. That is G1a/G1b.
NOMINAL_BITS_PER_SECOND = 100_000_000


def _text(path: Path) -> str:
    return path.read_text()


def _normalised(path: Path) -> str:
    return " ".join(path.read_text().split())


def _section(path: Path, heading: str) -> str:
    """The body of one heading, up to the next heading at the same level."""
    body = path.read_text()
    start = body.index(heading)
    level = len(heading) - len(heading.lstrip("#"))
    rest = body[start + len(heading):]
    nxt = re.search(rf"^#{{1,{level}}} ", rest, re.MULTILINE)
    return rest[: nxt.start()] if nxt else rest


def _paragraph(path: Path, opener: str) -> str:
    """One paragraph, from `opener` to the next blank line.

    `_section` above only understands `#` headings. A status list that opens
    with bold text needs its own scope, and it has to be a tight one: widening
    it to the rest of the document would let any later mention of the corpus
    satisfy an assertion about what this paragraph claims is outstanding.
    """
    body = path.read_text()
    start = body.index(opener)
    end = body.find("\n\n", start)
    return " ".join(body[start: end if end != -1 else len(body)].split())


def _rounded(value: float, places: int = 1) -> str:
    return f"{value:.{places}f}"


# ---------------------------------------------------------------------------
# Group A -- every derived figure recomputed from the recorded bytes
# ---------------------------------------------------------------------------

def test_the_recorded_byte_counts_are_the_ones_everything_derives_from():
    """The measurement is the anchor. If it moves, every figure below moves."""
    runbook = _normalised(RUNBOOK)
    assert f"{BUNDLE_BYTES:,}" in runbook, "the measured bundle byte count is gone"
    assert f"{EXTRACTED_BYTES:,}" in runbook, "the measured extracted byte count is gone"


#: Where each corrected figure has to appear. "Somewhere in one of the two
#: documents" was too weak to back the claim this file makes: a figure could
#: vanish from the gate that depends on it and still pass because the other
#: document happened to mention it. Each figure is required in the section that
#: actually relies on it, and a failure names that section.
SPEC_WINDOW = "### 1.1 Window — 11 year-partitions"
SPEC_ROLLOUT = "## 7. TDD and rollout"
RUNBOOK_G1 = "### What this means for G1a and G1b"

#: (figure, value recomputed from the recorded bytes, required locations).
#: The preflight threshold derives from the SHIPPED multiplier, so changing
#: DISK_HEADROOM_MULTIPLIER without republishing the figure fails here.
DERIVED_FIGURES = [
    ("bundle size", BUNDLE_BYTES / MiB,
     [(SPEC, SPEC_WINDOW), (RUNBOOK, RUNBOOK_G1)]),
    ("extracted size", EXTRACTED_BYTES / MiB,
     [(SPEC, SPEC_ROLLOUT), (RUNBOOK, RUNBOOK_G1)]),
    ("transfer time", BUNDLE_BYTES * 8 / NOMINAL_BITS_PER_SECOND,
     [(SPEC, SPEC_WINDOW), (SPEC, SPEC_ROLLOUT), (RUNBOOK, RUNBOOK_G1)]),
    ("simultaneous payload", (BUNDLE_BYTES + EXTRACTED_BYTES) / MiB,
     [(SPEC, SPEC_ROLLOUT), (RUNBOOK, RUNBOOK_G1)]),
    ("preflight threshold", BUNDLE_BYTES * DISK_HEADROOM_MULTIPLIER / MiB,
     [(SPEC, SPEC_ROLLOUT), (RUNBOOK, RUNBOOK_G1)]),
]

_FIGURE_CASES = [(label, value, path, heading)
                 for label, value, locations in DERIVED_FIGURES
                 for path, heading in locations]


@pytest.mark.parametrize(
    "label, computed, path, heading",
    _FIGURE_CASES,
    ids=[f"{label}:{path.name}:{heading.lstrip('# ').split(chr(8212))[0].strip()}"
         for label, _v, path, heading in _FIGURE_CASES],
)
def test_each_derived_figure_is_published_where_its_gate_relies_on_it(
        label, computed, path, heading):
    """Recomputed here, not restated, and required in the section that uses it."""
    printed = _rounded(computed)
    section = " ".join(_section(path, heading).split())
    assert printed in section, (
        f"{label}: {path.name} section {heading!r} no longer publishes "
        f"{printed}, which is what the recorded bytes produce. Change the "
        f"measurement, not the label."
    )


@pytest.mark.parametrize("path", [SPEC, RUNBOOK], ids=lambda p: p.name)
def test_the_preflight_figure_is_tied_to_the_shipped_headroom_multiplier(path):
    """The 2.5 is a policy constant, so the threshold is policy x measurement.

    The value is computed from the imported constant above; this pins the
    EXPRESSION alongside it, so a reader can see where the figure came from and
    a changed multiplier cannot leave a stale number looking authoritative.
    """
    assert "`bundle_bytes * 2.5`" in _normalised(path), (
        f"{path.name} publishes a preflight threshold without citing the "
        f"bundle_bytes x {DISK_HEADROOM_MULTIPLIER} rule it derives from"
    )


def test_the_bundle_limit_margin_is_stated_against_the_measured_bundle():
    """§4.1's margin was ~4.8x against 214 MiB; against the real bundle it is less."""
    margin = _rounded(DEFAULT_MAX_BUNDLE_BYTES / BUNDLE_BYTES)
    section = " ".join(_section(SPEC, "## 4. Runtime design").split())
    assert f"{margin}x" in section, (
        f"§4.1 no longer states the {margin}x margin the 1 GiB ceiling actually "
        f"has over the measured bundle"
    )
    assert "4.8x" not in section, "the superseded margin is still published"


# ---------------------------------------------------------------------------
# Group B -- 214 MiB: permitted only at enumerated historical anchors
# ---------------------------------------------------------------------------

def _occurrences(path: Path) -> list[tuple[int, str]]:
    return [(n, line) for n, line in enumerate(path.read_text().splitlines(), 1)
            if "214 MiB" in line]


def test_the_specification_states_214_MiB_only_as_a_superseded_figure():
    """Exactly one occurrence, and it is the sentence that supersedes it."""
    found = _occurrences(SPEC)
    assert len(found) == 1, (
        f"expected one historical reference to 214 MiB in the specification, "
        f"found {len(found)}: {[n for n, _ in found]}"
    )
    line = found[0][1]
    assert line.strip().startswith("An earlier revision published 214 MiB here"), (
        f"the surviving 214 MiB reference is not the supersession sentence: {line!r}"
    )


def test_the_runbook_states_214_MiB_only_in_the_superseded_baseline_column():
    """Two anchors: the comparison table's baseline cell, and the prose beneath it."""
    found = _occurrences(RUNBOOK)
    assert len(found) == 2, (
        f"expected two historical references to 214 MiB in the runbook, found "
        f"{len(found)}: {[n for n, _ in found]}"
    )

    rows = {line.split("|")[1].strip(): line
            for _, line in found if line.lstrip().startswith("|")}
    assert "Bundle size" in rows, (
        "214 MiB no longer appears in the comparison table's Bundle size row"
    )
    cells = [c.strip() for c in rows["Bundle size"].split("|")]
    assert "214 MiB" in cells[2], "214 MiB has moved out of the baseline column"
    assert "266.2 MiB" in cells[3], "the Bundle size row no longer carries the measurement"

    prose = [line for _, line in found if not line.lstrip().startswith("|")]
    assert len(prose) == 1 and "superseded" in prose[0].lower(), (
        f"the prose reference does not mark 214 MiB as superseded: {prose!r}"
    )


def test_the_comparison_table_labels_its_baseline_column_as_superseded():
    """A table that prints 214 MiB under a column headed 'Measured' is the defect."""
    table = _section(RUNBOOK, "### What this means for G1a and G1b")
    header = next(line for line in table.splitlines() if line.strip().startswith("|"))
    cells = [c.strip().lower() for c in header.split("|")]
    assert "superseded" in cells[2], f"baseline column is not marked superseded: {header!r}"
    assert "measured" not in cells[2], (
        "the superseded baseline column is headed 'Measured'; three of its rows "
        "are arithmetic, which is the mislabelling rev 7 corrects"
    )


def test_no_stale_eleven_partition_size_survives_in_production_code():
    """The same failure class as the docs: a superseded premise outside the prose."""
    stale = [p for p in (REPO / "property_core").rglob("*.py")
             if "214 MiB" in p.read_text()]
    assert not stale, f"superseded sizing figure still in code: {stale}"


# ---------------------------------------------------------------------------
# Group B -- the corrected premises
# ---------------------------------------------------------------------------

def test_the_eleven_partition_row_publishes_the_measurement():
    """The guard that matters: the current claim is the measured one."""
    window = _section(SPEC, "### 1.1 Window — 11 year-partitions")
    row = next((line for line in window.splitlines()
                if line.strip().startswith("|") and "2016–2026" in line), None)
    assert row is not None, "the eleven-partition row is gone from §1.1"
    assert "266.2 MiB" in row and "measured" in row.lower(), (
        f"the eleven-partition row does not publish the measurement: {row!r}"
    )
    assert "214" not in row, "the eleven-partition row still claims the superseded size"


def test_the_estimated_rows_label_both_their_size_and_their_transfer():
    """10 and 12 partitions are year+area estimates; their times are doubly derived."""
    window = _section(SPEC, "### 1.1 Window — 11 year-partitions")
    for years in ("2017–2026", "2015–2026"):
        row = next(line for line in window.splitlines()
                   if line.strip().startswith("|") and years in line)
        assert "estimated" in row.lower(), f"{years} row does not label its size: {row!r}"
        assert "calculated from that estimate" in row.lower(), (
            f"{years} row does not label its transfer time as derived from an "
            f"estimate rather than from a measurement: {row!r}"
        )


@pytest.mark.parametrize("phrase", [
    "G1a",
    "G1b",
    "Passing G1a authorises neither",
    "ephemeral rootfs",
])
def test_the_split_gate_is_recorded(phrase):
    assert phrase in _normalised(SPEC), f"§7.2 no longer states: {phrase!r}"


def test_each_split_gate_names_its_own_target():
    stage2 = _section(SPEC, "## 7. TDD and rollout")
    normalised = " ".join(stage2.split())
    g1a = normalised.index("G1a")
    g1b = normalised.index("G1b")
    assert "property-shared" in normalised[g1a:g1b], "G1a does not name its target"
    assert "2 GB" in normalised[g1a:g1b], "G1a does not state the 2 GB target"
    assert "propertydata" in normalised[g1b:g1b + 900], "G1b does not name its target"
    assert "512 MB" in normalised[g1b:g1b + 900], "G1b does not state the 512 MB target"


def test_the_rollout_section_does_not_claim_a_volume_that_does_not_exist():
    """Neither app declares one (§4.5). Naming its absence is fine; claiming it is not."""
    rollout = _section(SPEC, "## 7. TDD and rollout")
    flattened = " ".join(rollout.split()).replace("’", "'").lower()
    assert "machine's volume" not in flattened, (
        "§7.2 still requires the payload to fit within the machine's volume; "
        "both Machines run Fly's default ephemeral rootfs with no [mounts]"
    )
    assert "ephemeral rootfs" in flattened, (
        "§7.2 does not name the storage that actually constrains G1a/G1b"
    )


def test_the_calculated_g1_inputs_are_not_presented_as_measurements():
    rollout = " ".join(_section(SPEC, "## 7. TDD and rollout").split())
    marker = "Calculated inputs"
    assert marker in rollout, "§7.2 does not separate G1's calculated inputs from its result"
    block = rollout[rollout.index(marker):rollout.index(marker) + 700]
    for figure in ("534.1", "665.4", "22.3"):
        assert figure in block, f"{figure} is not inside the calculated-inputs block"


def test_g3_states_the_deploy_and_observe_invariant_instead_of_the_impossible_order():
    """Routing merged in PR 4, so 'before routing is introduced' can never hold."""
    # Same rule as 214 MiB: the phrase may be QUOTED as superseded, never
    # required. Anchored to the supersession sentence, not a textual window.
    found = [line for line in _text(SPEC).splitlines()
             if "before routing is introduced" in line]
    assert len(found) == 1, (
        f"expected one historical reference to the superseded ordering, found "
        f"{len(found)}"
    )
    assert "revision required this" in found[0], (
        f"G3 still requires an ordering that PR 4 made unsatisfiable: {found[0]!r}"
    )
    assert ("must land, deploy and be observed with `PPD_SNAPSHOT_ENABLED` off "
            "before any snapshot enablement") in _normalised(SPEC), (
        "G3 no longer carries the replacement safety invariant"
    )


def test_nothing_in_the_correction_relaxed_a_requirement():
    normalised = _normalised(SPEC)
    assert "30 s readiness target" in normalised, "the readiness target was dropped"
    assert "`bundle_bytes * 2.5`" in normalised, "the headroom rule was dropped"
    for criterion in ("Zero unexplained false empties", "Zero geography contamination",
                      "100% field equality on shared transaction IDs",
                      "Every divergence classified", "Zero snapshot errors",
                      "p95 < 1 second"):
        assert criterion in normalised, f"Stage 1 exit criterion dropped: {criterion!r}"


def test_a_local_rehearsal_is_not_recorded_as_a_stage_1_result():
    normalised = _normalised(SPEC)
    assert "A local rehearsal is not Stage 1" in normalised
    assert "cannot satisfy" in normalised and "p95" in normalised


def test_the_implementation_status_records_pr_5_as_merged():
    normalised = _normalised(SPEC)
    assert "By **PR 5**" in normalised, "the build pipeline is still listed as unimplemented"
    for outstanding in ("artifact distribution", "G1a", "G1b", "G2", "G3",
                        "v1.15"):
        assert outstanding in normalised, f"outstanding work no longer listed: {outstanding}"


def test_the_flag_is_still_recorded_as_off_everywhere():
    assert "remains off in all checked-in configuration" in _normalised(SPEC)


# ---------------------------------------------------------------------------
# Group B -- two premises the shipped implementation already contradicted
# ---------------------------------------------------------------------------

def test_the_retention_rule_agrees_with_the_runtime_that_implements_it():
    """§7.1 item 36 said 'current + previous'; §4.7, store.py and its test say one."""
    normalised = _normalised(SPEC)
    assert "retains exactly current + previous" not in normalised, (
        "§7.1 still requires a retention policy §4.7 and SnapshotStore reject"
    )
    assert "retains exactly the active version" in normalised


def test_the_lock_wait_bound_names_a_constant_that_exists():
    """`LOCK_WAIT_SECONDS` was never an identifier; the value 420 s is unchanged."""
    from property_core.snapshot.lock import DEFAULT_TIMEOUT

    assert DEFAULT_TIMEOUT == 420.0
    assert "LOCK_WAIT_SECONDS" not in _text(SPEC), (
        "the specification still names an identifier that does not exist"
    )
    assert "LOCK_WAIT_SECONDS" not in _text(REPO / "property_core" / "snapshot" / "bootstrap.py")


# ---------------------------------------------------------------------------
# Scope -- this correction changes documents and tests, nothing operational
# ---------------------------------------------------------------------------

def test_the_changelog_describes_pr_groups_rather_than_a_total():
    """A bare total is a counter that has to be right forever.

    It was wrong twice already -- "four", then "Five" against eight merged PRs.
    The groups are what a reader actually needs: five PRs that built the thing
    (#24-#28) and three that prepared its rollout without touching production
    (#29-#31). A ninth PR extends a range, which is a one-line edit; it does
    not force a recount, and a recount is what kept going stale.
    """
    normalised = _normalised(CHANGELOG)
    assert "Five** PRs" not in normalised, (
        "the changelog still states a bare PR total; totals go stale silently"
    )
    for phrase in ("implementation PRs", "rollout-preparation PRs",
                   "#24-#28", "#29-#31"):
        assert phrase in normalised, (
            f"the changelog no longer describes its PR groups: {phrase!r} is gone"
        )


def test_the_changelog_still_records_the_sizing_correction():
    """Rev 8 must not erase rev 7's provenance.

    The surviving half of the assertion this replaced: the sizing correction was
    made by rev 7, and saying so stays true no matter how many revisions follow.
    """
    assert "specification rev 7" in _normalised(CHANGELOG), (
        "the changelog no longer records which revision corrected the sizing"
    )


# ---------------------------------------------------------------------------
# Rev 8 -- the corpus-acceptance and artifact-distribution decision round
# ---------------------------------------------------------------------------

def test_the_specification_declares_revision_8_and_a_revision_note():
    """History is appended, never overwritten.

    A revision that replaced its predecessor's note would make the document's
    own account of itself unfalsifiable: nobody could tell which decision round
    settled what.
    """
    body = _text(SPEC)
    head = body.splitlines()[0]
    assert "rev 8" in head and "FROZEN" in head, head
    normalised = _normalised(SPEC)
    assert "**Revision 8**" in normalised, "rev 8 landed without a revision note"
    for earlier in ("**Revision 7**", "**Revision 6**"):
        assert earlier in normalised, (
            f"{earlier} was overwritten; revision notes accumulate, they do not "
            f"replace each other"
        )


def test_revision_8_relaxed_no_requirement():
    """Sibling of the rev 7 assertion below, for the same reason.

    A status-reconciliation round is exactly where a requirement gets softened
    by accident, because nothing in it looks like a requirement change.
    """
    normalised = _normalised(SPEC)
    for requirement in (
        "30 s readiness target",
        "bundle_bytes * 2.5",
        "Zero unexplained false empties",
        "Zero geography contamination",
        "100% field equality on shared transaction IDs",
        "Every divergence classified",
        "Zero snapshot errors",
        "p95 < 1 second",
        "Passing G1a authorises neither `propertydata` nor Stage 3",
        "blocking G2 if the deployed count exceeds one",
    ):
        assert requirement in normalised, (
            f"rev 8 relaxed a requirement it had no authority to touch: "
            f"{requirement!r}"
        )


def test_the_specification_records_the_corpus_and_rehearsal_as_merged():
    """PRs #30 and #31 merged; the status list said they had not."""
    unimplemented = _paragraph(SPEC, "**Still unimplemented or unperformed:**")
    for merged in ("shadow corpus", "rehearsal"):
        assert merged not in unimplemented, (
            f"the status list still calls {merged!r} unimplemented, but it "
            f"merged and its guard tests run in this suite"
        )
    normalised = _normalised(SPEC)
    assert "ppd-shadow-corpus.md" in normalised, (
        "the specification never names the corpus document it governs"
    )


def test_the_specification_no_longer_denies_the_adapter_it_documents():
    """The sharpest self-contradiction in the repository, until rev 8.

    The Basis paragraph said no production adapter or boot lifecycle existed
    while the implementation-status paragraph, thirty lines above, described
    both -- and `test_the_lifespan_rule_is_wired_in_both_deployments` asserts
    they boot.
    """
    normalised = _normalised(SPEC)
    assert "no production adapter or boot lifecycle exists" not in normalised, (
        "the specification still denies the adapter and lifespan that PR 3 and "
        "PR 4 shipped and that this suite asserts are wired"
    )


def test_the_changelog_no_longer_carries_the_impossible_ordering():
    """Replaced in the spec by rev 7; the changelog kept the dead phrase.

    The spec's *quotation* of it must survive: recording what was replaced, and
    why it can no longer be satisfied, is how the correction stays legible.
    """
    assert "*before* routing is introduced" not in _normalised(CHANGELOG), (
        "the changelog still requires an ordering that routing made impossible "
        "when PR 4 merged"
    )
    assert "before routing is introduced" in _normalised(SPEC), (
        "the specification stopped recording which ordering rev 7 replaced"
    )


def test_the_runbook_cites_the_current_specification_revision():
    """It cited rev 6 in its header and rev 7 in its body -- both, at once."""
    normalised = _normalised(RUNBOOK)
    assert "rev 6" not in normalised, (
        "the runbook still says it is governed by a superseded revision"
    )


# ---------------------------------------------------------------------------
# The artifact-distribution decision record
# ---------------------------------------------------------------------------

def test_the_distribution_decision_record_exists_and_states_its_limits():
    """Three merged documents said distribution was undecided.

    Without a record, the next session reads them and re-litigates a settled
    decision -- which is the failure this whole reconciliation exists to stop.
    A record that states the permission without stating its edges is worse than
    none: it reads as blanket approval.
    """
    assert DECISION.exists(), (
        "the scoped distribution determination is not written down anywhere"
    )
    normalised = _normalised(DECISION)
    assert "Paul Boucherat" in normalised, "the record names no owner"
    assert "2026-08-29" in normalised, "the record carries no date"
    for exclusion in (
        "No public bundle download",
        "bulk rows",
        "address validation",
        "attribution",
    ):
        assert exclusion in normalised, (
            f"the record states the permission without its {exclusion!r} limit"
        )
    for trigger in ("re-review", "public hosting", "new consumer"):
        assert trigger in normalised.lower(), (
            f"the record states no re-review trigger for {trigger!r}; a "
            f"determination with no reopening condition is a permanent one"
        )
    assert "no mutation authority" in normalised.lower(), (
        "the record does not say that permission to distribute is not "
        "permission to create a bucket, upload anything, or configure Fly"
    )


def test_the_distribution_record_is_a_determination_not_legal_advice():
    """It records what the owner decided, not what a lawyer concluded.

    It also settles exactly one of section 6's four Royal Mail triggers. Reading
    it as clearing the other three is the mistake it must make impossible.
    """
    normalised = _normalised(DECISION)
    assert "not legal advice" in normalised.lower(), (
        "the record does not disclaim independent legal advice"
    )
    assert "determination" in normalised.lower(), (
        "the record does not present itself as the owner's determination"
    )
    for still_gated in ("autocomplete", "geocoding", "PAF-like"):
        assert still_gated in normalised, (
            f"the record does not restate that {still_gated!r} remains gated by "
            f"section 6"
        )


def test_the_specification_points_at_the_decision_record():
    """The places that said "separately approved" must now resolve somewhere."""
    for document, name in ((SPEC, "specification"), (RUNBOOK, "runbook")):
        assert "ppd-artifact-distribution-decision" in _normalised(document), (
            f"the {name} still describes distribution as an open decision "
            f"without pointing at the record that settled its scope"
        )


def test_the_lock_wait_versus_grace_period_question_is_recorded_not_resolved():
    """C11: recorded against G2 by rev 7, deliberately left open.

    Reconciling a 420 s lock wait against 60 s / 30 s health-check grace periods
    needs deployment evidence or a new operational policy. A documentation
    correction may record the question; it may not invent the answer.
    """
    normalised = _normalised(SPEC)
    assert "blocking G2 if the deployed count exceeds one" in normalised, (
        "the lock-wait versus grace-period question is no longer recorded as a "
        "G2 blocker; it would be lost between sessions"
    )
    assert "deliberately does not resolve it" in normalised
    for number in ("420 s", "60 s (`property-shared`)", "30 s (`propertydata`)"):
        assert number in normalised, f"G2's open question no longer cites {number}"
