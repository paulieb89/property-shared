"""PR 1 — provenance and transport-evidence models.

These encode two invariants the design got wrong earlier and must never regress:

* Completeness is NEVER inferred from counts. `sample_count < sample_limit` is
  not evidence of anything, because on the live path the upstream window is
  bounded before client-side filtering runs.
* `source_exhausted` is tri-state and DERIVED. Unknown stays unknown: only
  ``True`` may authorise escalation or support ``sample_complete=True``.

Spec: docs/design/ppd-source-routing.md sections 2.7.3 and 3.1.1.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from property_core.provenance import (
    CompletenessBasis,
    PPDProvenance,
    SourceKind,
    TransportEvidence,
)


# --------------------------------------------------------------------------
# TransportEvidence.source_exhausted — tri-state, derived, not settable
# --------------------------------------------------------------------------

def test_source_exhausted_true_when_upstream_returned_fewer_than_asked():
    ev = TransportEvidence(raw_bindings_returned=17, fetch_limit=50)
    assert ev.source_exhausted is True


def test_source_exhausted_false_when_upstream_window_was_full():
    ev = TransportEvidence(raw_bindings_returned=50, fetch_limit=50)
    assert ev.source_exhausted is False


@pytest.mark.parametrize(
    "raw, limit",
    [(None, 50), (50, None), (None, None)],
    ids=["no-raw-count", "no-fetch-limit", "neither"],
)
def test_source_exhausted_is_none_when_either_input_is_absent(raw, limit):
    """Unknown must stay unknown — never collapse to False."""
    ev = TransportEvidence(raw_bindings_returned=raw, fetch_limit=limit)
    assert ev.source_exhausted is None


def test_source_exhausted_cannot_be_set_through_the_constructor():
    """It is derived, and the attempt must RAISE rather than be dropped.

    Silently ignoring the argument would leave a caller believing they had
    asserted exhaustion when they had not -- the quiet version of the bug this
    model exists to prevent.
    """
    with pytest.raises(ValidationError):
        TransportEvidence(
            raw_bindings_returned=50, fetch_limit=50, source_exhausted=True
        )


def test_transport_evidence_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        TransportEvidence(raw_bindings_returned=1, fetch_limit=2, exhausted=True)


def test_fetch_limit_must_be_positive_when_present():
    """A limit of 0 makes `raw < limit` unsatisfiable: caller error, not a page size."""
    with pytest.raises(ValidationError):
        TransportEvidence(raw_bindings_returned=0, fetch_limit=0)


def test_raw_bindings_returned_cannot_be_negative():
    with pytest.raises(ValidationError):
        TransportEvidence(raw_bindings_returned=-1, fetch_limit=10)


def test_source_exhausted_cannot_be_assigned_after_construction():
    ev = TransportEvidence(raw_bindings_returned=50, fetch_limit=50)
    with pytest.raises((AttributeError, ValidationError)):
        ev.source_exhausted = True  # type: ignore[misc]


def test_unknown_exhaustion_does_not_authorise_escalation():
    assert TransportEvidence().authorises_escalation() is False


def test_full_window_does_not_authorise_escalation():
    ev = TransportEvidence(raw_bindings_returned=50, fetch_limit=50)
    assert ev.authorises_escalation() is False


def test_only_true_exhaustion_authorises_escalation():
    ev = TransportEvidence(raw_bindings_returned=3, fetch_limit=50)
    assert ev.authorises_escalation() is True


# --------------------------------------------------------------------------
# PPDProvenance — completeness needs explicit evidence
# --------------------------------------------------------------------------

def test_source_accepts_only_the_three_known_kinds():
    for kind in ("snapshot", "linked_data", "sparql"):
        assert PPDProvenance(source=kind).source == kind
    with pytest.raises(ValidationError):
        PPDProvenance(source="guess")


def test_sample_complete_defaults_false_and_basis_defaults_none():
    p = PPDProvenance(source=SourceKind.SPARQL)
    assert p.sample_complete is False
    assert p.completeness_basis is None


def test_short_result_is_not_evidence_of_completeness():
    """The deleted inference rule: 3 of 5 does NOT mean complete."""
    p = PPDProvenance(source=SourceKind.SPARQL, sample_count=3, sample_limit=5)
    assert p.sample_complete is False


def test_sample_complete_true_without_a_basis_is_rejected():
    with pytest.raises(ValidationError):
        PPDProvenance(
            source=SourceKind.SNAPSHOT, sample_complete=True, completeness_basis=None
        )


def test_sample_complete_false_permits_a_null_basis():
    p = PPDProvenance(
        source=SourceKind.SPARQL, sample_complete=False, completeness_basis=None
    )
    assert p.sample_complete is False


@pytest.mark.parametrize(
    "basis",
    [
        CompletenessBasis.SOURCE_EXHAUSTED,
        CompletenessBasis.LIMIT_PLUS_ONE,
        CompletenessBasis.EXPLICIT_ADAPTER_EXHAUSTION,
    ],
)
def test_sample_complete_true_is_allowed_with_each_valid_basis(basis):
    p = PPDProvenance(
        source=SourceKind.SNAPSHOT, sample_complete=True, completeness_basis=basis
    )
    assert p.sample_complete is True and p.completeness_basis is basis


def test_older_records_exist_is_tristate_and_defaults_unknown():
    assert PPDProvenance(source=SourceKind.SNAPSHOT).older_records_exist is None
    assert (
        PPDProvenance(source=SourceKind.SNAPSHOT, older_records_exist=True)
        .older_records_exist is True
    )
    assert (
        PPDProvenance(source=SourceKind.SNAPSHOT, older_records_exist=False)
        .older_records_exist is False
    )


def test_older_records_unknown_never_coerces_to_false():
    """A failed probe must not read as 'nothing older exists'."""
    p = PPDProvenance(source=SourceKind.SNAPSHOT, older_records_exist=None)
    assert p.older_records_exist is not False
    assert p.model_dump()["older_records_exist"] is None


def test_provenance_rejects_unknown_or_misspelled_fields():
    """Provenance that silently drops a field still looks authoritative."""
    with pytest.raises(ValidationError):
        PPDProvenance(source=SourceKind.SNAPSHOT, coverage_form="2016-01-01")
    with pytest.raises(ValidationError):
        PPDProvenance(source=SourceKind.SNAPSHOT, sample_compleat=True)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"sample_count": -1},
        {"sample_limit": -1},
        {"freshness_days": -1},
    ],
    ids=["negative-count", "negative-limit", "negative-freshness"],
)
def test_provenance_counters_cannot_be_negative(kwargs):
    with pytest.raises(ValidationError):
        PPDProvenance(source=SourceKind.SNAPSHOT, **kwargs)


# --------------------------------------------------------------------------
# Frozen: the completeness invariant is a CONSTRUCTION check, so the block must
# not be mutable afterwards. validate_assignment is deliberately not used --
# under Pydantic 2.12.5 an after-validator can raise during assignment while the
# object keeps the invalid mutated value.
# --------------------------------------------------------------------------

def test_assigning_sample_complete_raises_and_leaves_the_block_unchanged():
    p = PPDProvenance(source=SourceKind.SNAPSHOT, sample_count=3, sample_limit=5)
    with pytest.raises(ValidationError):
        p.sample_complete = True  # type: ignore[misc]
    assert p.sample_complete is False
    assert p.completeness_basis is None
    assert p.model_dump()["sample_complete"] is False


def test_stripping_the_basis_from_a_complete_block_raises_and_leaves_it_unchanged():
    p = PPDProvenance(
        source=SourceKind.SNAPSHOT,
        sample_complete=True,
        completeness_basis=CompletenessBasis.LIMIT_PLUS_ONE,
    )
    with pytest.raises(ValidationError):
        p.completeness_basis = None  # type: ignore[misc]
    assert p.sample_complete is True
    assert p.completeness_basis is CompletenessBasis.LIMIT_PLUS_ONE
    dumped = p.model_dump()
    assert dumped["completeness_basis"] == CompletenessBasis.LIMIT_PLUS_ONE.value


@pytest.mark.parametrize(
    "field, value",
    [
        ("sample_count", 99),
        ("sample_limit", 99),
        ("source", SourceKind.SPARQL),
        ("older_records_exist", True),
        ("coverage_from", "1995-01-01"),
        ("warnings", ["injected"]),
    ],
)
def test_ordinary_fields_cannot_be_mutated(field, value):
    p = PPDProvenance(source=SourceKind.SNAPSHOT, sample_count=3, sample_limit=5)
    before = p.model_dump()
    with pytest.raises(ValidationError):
        setattr(p, field, value)
    assert p.model_dump() == before


def test_warnings_accept_a_list_and_normalise_to_a_tuple():
    p = PPDProvenance(source=SourceKind.SNAPSHOT, warnings=["a", "b"])
    assert isinstance(p.warnings, tuple)
    assert p.warnings == ("a", "b")


def test_warnings_default_is_an_empty_tuple():
    p = PPDProvenance(source=SourceKind.SNAPSHOT)
    assert p.warnings == ()
    assert isinstance(p.warnings, tuple)


def test_warnings_cannot_be_mutated_in_place():
    """Freezing is shallow: a list field would still be appendable."""
    p = PPDProvenance(source=SourceKind.SNAPSHOT, warnings=["original"])
    with pytest.raises(AttributeError):
        p.warnings.append("injected")  # type: ignore[attr-defined]
    assert p.warnings == ("original",)
    # python-mode dump preserves the tuple; only mode="json" converts to a list.
    assert p.model_dump()["warnings"] == ("original",)
    assert p.model_dump(mode="json")["warnings"] == ["original"]


def test_warnings_cannot_be_reassigned():
    p = PPDProvenance(source=SourceKind.SNAPSHOT, warnings=["original"])
    with pytest.raises(ValidationError):
        p.warnings = ("replaced",)  # type: ignore[misc]
    assert p.warnings == ("original",)


def test_warnings_serialise_as_a_json_array():
    p = PPDProvenance(source=SourceKind.SNAPSHOT, warnings=["one", "two"])
    assert p.model_dump(mode="json")["warnings"] == ["one", "two"]
    assert json.loads(p.model_dump_json())["warnings"] == ["one", "two"]


def test_block_with_warnings_round_trips():
    p = PPDProvenance(
        source=SourceKind.SNAPSHOT, sample_count=2, sample_limit=50,
        warnings=["upstream window not exhausted"],
    )
    revived = PPDProvenance.model_validate(json.loads(p.model_dump_json()))
    assert revived == p
    assert revived.warnings == ("upstream window not exhausted",)


def test_valid_incomplete_block_still_serialises():
    p = PPDProvenance(
        source=SourceKind.SPARQL, sample_count=3, sample_limit=5,
        coverage_from=None, warnings=["upstream window not exhausted"],
    )
    d = p.model_dump()
    assert d["sample_complete"] is False
    assert d["completeness_basis"] is None
    assert d["sample_count"] == 3 and d["sample_limit"] == 5
    assert d["warnings"] == ("upstream window not exhausted",)
    assert p.model_dump(mode="json")["warnings"] == ["upstream window not exhausted"]


def test_valid_complete_block_still_serialises():
    p = PPDProvenance(
        source=SourceKind.SNAPSHOT, sample_count=4, sample_limit=50,
        sample_complete=True,
        completeness_basis=CompletenessBasis.LIMIT_PLUS_ONE,
        coverage_from="2016-01-01", coverage_to="2026-06-30", freshness_days=58,
    )
    d = p.model_dump()
    assert d["sample_complete"] is True
    assert d["completeness_basis"] == CompletenessBasis.LIMIT_PLUS_ONE.value
    assert d["coverage_from"] == "2016-01-01" and d["freshness_days"] == 58
    assert PPDProvenance(**{**d, "source": SourceKind.SNAPSHOT}) == p


def test_atomic_construction_is_the_supported_update_path():
    """A refined block is a NEW validated block, not a mutated one."""
    base = PPDProvenance(source=SourceKind.SNAPSHOT, sample_count=4, sample_limit=50)
    refined = PPDProvenance(
        **{**base.model_dump(), "source": SourceKind.SNAPSHOT,
           "sample_complete": True,
           "completeness_basis": CompletenessBasis.LIMIT_PLUS_ONE}
    )
    assert refined.sample_complete is True
    assert base.sample_complete is False, "the original block must be untouched"


def test_model_copy_update_is_an_unvalidated_escape_hatch():
    """Documents a Pydantic behaviour we accept rather than defend against.

    ``model_copy(update=...)`` bypasses validation by design: it CAN produce and
    serialise a block that ``__init__`` would reject. We deliberately do not
    override ``model_copy`` -- adding a custom BaseModel override solely to
    protect trusted internal code is not worth the surface area. The
    specification prohibits copy-and-patch instead, and the guard below shows
    that explicit revalidation is what catches it.
    """
    p = PPDProvenance(source=SourceKind.SNAPSHOT)
    escaped = p.model_copy(update={"sample_complete": True})

    # The escape hatch really does produce an invalid, serialisable state.
    assert escaped.sample_complete is True
    assert escaped.completeness_basis is None
    assert escaped.model_dump()["sample_complete"] is True

    # Only explicit revalidation rejects it -- hence the spec prohibition and
    # the supported path of fresh validated construction.
    with pytest.raises(ValidationError):
        PPDProvenance.model_validate(escaped.model_dump())


def test_provenance_carries_a_compact_attribution_ref_not_licence_prose():
    p = PPDProvenance(source=SourceKind.SNAPSHOT)
    assert p.attribution_ref
    assert len(p.attribution_ref) < 64
    assert "Crown copyright" not in p.model_dump_json()
