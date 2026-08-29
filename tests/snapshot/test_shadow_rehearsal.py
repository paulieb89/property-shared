"""Local shadow-corpus rehearsal (`tools.ppd_snapshot rehearse`).

The rehearsal exercises the corpus Definition's cases against an already-built
local artifact, through the snapshot adapter only. It is a correctness exercise:
it has no live arm, so it can satisfy neither the p95 criterion nor any
divergence criterion, and its report is never Stage 1 evidence.

Two properties are worth more than the rest, and both are tested first:

* **An instance is refused before an artifact is opened.** The instance names
  the artifact and supplies the concrete geographies the Definition leaves as
  placeholders. An instance that is malformed, incomplete, or bound to a
  different artifact must stop the run at argument-validation time -- before
  ~534 MiB is materialized, and before any snapshot is opened. Refusing after
  materialization would still be correct, but it would burn the disk and the
  wall time first, and it would leave a cache directory whose provenance nobody
  can explain.

* **No live path is constructed.** A rehearsal that quietly fell back to live
  SPARQL would produce a report that looks like a rehearsal and is not one. The
  socket blocker is armed with a self-check, and every case asserts its answer
  came from the snapshot.

Exit codes follow the tool's existing convention: 2 for a refused instance,
1 for a rehearsal that ran but failed an invariant, 0 only when every case
passed.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

pytest.importorskip("duckdb")
pytest.importorskip("zstandard")

from tools.ppd_snapshot import __main__ as cli  # noqa: E402
from tools.ppd_snapshot.build import BuildRequest, build_snapshot  # noqa: E402
from tools.ppd_snapshot.package import (  # noqa: E402
    package_release,
    promote_release,
    snapshot_version,
)
from tests.snapshot.build_fixtures import csv_row, write_source_csv  # noqa: E402

COVERAGE_TO = date(2026, 6, 30)


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    """A real published dist: bundle, manifest and current.json.

    Built through the shipped pipeline rather than hand-assembled, so the
    rehearsal is exercised against the artifact shape it will actually meet.
    """
    # Dates sit inside a 24-month window measured from "today", and inside the
    # provisional tail, so the geography and provisional cases are not vacuous.
    # An out-of-window B5 row would make the B5/B50 contamination check pass by
    # returning nothing at all, which proves less than nothing.
    csv_path = write_source_csv(tmp_path / "pp.csv", [
        csv_row("{T-B57-A}", "B5 7AA", "2026-05-01 00:00", 210_000),
        csv_row("{T-B50-A}", "B50 4AA", "2026-05-02 00:00", 400_000),
        csv_row("{T-M37-A}", "M3 7AA", "2026-06-30 00:00", 250_000),
    ])
    built = build_snapshot(BuildRequest(
        csv_path=csv_path, out_dir=tmp_path / "snapshot",
        coverage_to=COVERAGE_TO, temp_dir=tmp_path / "tmp"))
    release = package_release(
        built, dist_dir=tmp_path / "dist", candidate_root=tmp_path / "work",
        version=snapshot_version(datetime(2026, 8, 28, 10, 15, tzinfo=timezone.utc)),
        source={"file": "pp.csv", "sha256": "a" * 64, "etag": '"abc"'},
        facts={"rows_per_year": {"2024": 2, "2026": 1}},
    )
    promote_release(release)
    return tmp_path / "dist"


def _manifest(dist_dir: Path) -> dict:
    current = json.loads((dist_dir / "current.json").read_text())
    return json.loads((dist_dir / current["current_manifest"]).read_text())


def valid_instance(dist_dir: Path) -> dict:
    """An instance bound to `dist_dir`, with every placeholder supplied."""
    m = _manifest(dist_dir)
    return {
        "instance_kind": "rehearsal",
        "snapshot_version": m["snapshot_version"],
        "bundle_sha256": m["bundle_sha256"],
        "geographies": {
            "S4_thin": "B5 6",
            "S5_dense": "B5 7",
            "S6_unit": "B5 7AA",
            "S7_type_weak": "M3 7",
            "S8_type_strong": "B5 7",
            "S11_provisional_empty": "B5 6",
            "S13_empty_unit": "B5 7AA",
        },
        # Definition section 10: containment is qualified from FULL aggregate
        # counts, which a paged rehearsal cannot show. Declaring them here makes
        # the qualification evidence explicit instead of merely described.
        "aggregate_baselines": {
            "S1_full": 2, "S3_full": 1, "S9_full": 2,
        },
    }


def write_instance(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, indent=2))
    return path


def run(tmp_path: Path, dist_dir: Path, instance: Path) -> tuple[int, Path, Path]:
    cache = tmp_path / "rehearsal-cache"
    report = tmp_path / "report.json"
    code = cli.main([
        "rehearse",
        "--instance", str(instance),
        "--dist", str(dist_dir),
        "--cache-dir", str(cache),
        "--report", str(report),
    ])
    return code, cache, report


# ---------------------------------------------------------------------------
# 1. The instance is refused before an artifact is opened
# ---------------------------------------------------------------------------

def _mutations(dist_dir: Path):
    """Each returns (label, instance payload) that must be refused."""
    base = valid_instance(dist_dir)

    missing = dict(base)
    missing.pop("bundle_sha256")

    unknown = dict(base, extra_key="not in the schema")

    wrong_kind = dict(base, instance_kind="stage1")

    wrong_digest = dict(base, bundle_sha256="f" * 64)

    wrong_version = dict(base, snapshot_version="v20200101T000000Z")

    incomplete_geo = dict(base)
    incomplete_geo["geographies"] = {
        k: v for k, v in base["geographies"].items() if k != "S4_thin"}

    unknown_geo = dict(base)
    unknown_geo["geographies"] = dict(base["geographies"], S99_nonsense="B5 7")

    malformed_geo = dict(base)
    malformed_geo["geographies"] = dict(base["geographies"], S4_thin="not a postcode!")

    return [
        ("missing required key", missing),
        ("unknown top-level key", unknown),
        ("instance_kind is not rehearsal", wrong_kind),
        ("bundle_sha256 does not bind to the artifact", wrong_digest),
        ("snapshot_version does not bind to the artifact", wrong_version),
        ("a placeholder is unsupplied", incomplete_geo),
        ("an unknown placeholder is supplied", unknown_geo),
        ("a placeholder is not a postcode or sector", malformed_geo),
    ]


def test_every_invalid_instance_is_refused_with_exit_2(tmp_path, dist):
    for label, payload in _mutations(dist):
        instance = write_instance(tmp_path / f"inst-{abs(hash(label))}.json", payload)
        code, cache, report = run(tmp_path, dist, instance)
        assert code == 2, f"{label!r} was not refused with exit 2 (got {code})"
        assert not report.exists(), f"{label!r} wrote a report despite being refused"


def test_a_refused_instance_materializes_nothing(tmp_path, dist):
    """The refusal must happen before ~534 MiB is written, not after."""
    for label, payload in _mutations(dist):
        instance = write_instance(tmp_path / f"nomat-{abs(hash(label))}.json", payload)
        code, cache, _report = run(tmp_path, dist, instance)
        assert code == 2, label
        materialized = list(cache.rglob("*.parquet")) if cache.exists() else []
        assert not materialized, (
            f"{label!r} materialized a snapshot before refusing the instance: "
            f"{materialized[:3]}"
        )


def test_unparseable_json_is_refused_with_exit_2(tmp_path, dist):
    instance = tmp_path / "broken.json"
    instance.write_text("{not json")
    code, _cache, report = run(tmp_path, dist, instance)
    assert code == 2
    assert not report.exists()


def test_a_missing_instance_file_is_refused_with_exit_2(tmp_path, dist):
    code, _cache, report = run(tmp_path, dist, tmp_path / "absent.json")
    assert code == 2
    assert not report.exists()


def test_the_valid_instance_is_accepted(tmp_path, dist):
    """Control: the refusals above must be refusing the mutation, not the shape."""
    from tools.ppd_snapshot.rehearse import load_instance

    instance = write_instance(tmp_path / "ok.json", valid_instance(dist))
    loaded = load_instance(instance, dist)
    assert loaded.instance_kind == "rehearsal"
    assert loaded.geographies["S4_thin"] == "B5 6"


# ---------------------------------------------------------------------------
# 2. A fixture artifact runs adapter-only, isolated, and reports as a rehearsal
# ---------------------------------------------------------------------------

#: Shared with the dependency-free summary guards in
#: `test_shadow_rehearsal_summary.py`, which must not inherit this module's
#: `importorskip`.
from tests.snapshot.rehearsal_fixtures import FORBIDDEN_IN_REPORT  # noqa: E402


@pytest.fixture
def rehearsed(tmp_path, dist):
    instance = write_instance(tmp_path / "ok.json", valid_instance(dist))
    code, cache, report = run(tmp_path, dist, instance)
    assert report.exists(), f"no report written (exit {code})"
    return code, json.loads(report.read_text()), report


def test_the_report_is_labelled_a_rehearsal_and_not_stage_1_evidence(rehearsed):
    _code, report, _path = rehearsed
    assert report["kind"] == "rehearsal"
    assert report["not_stage_1_evidence"] is True
    assert "no live arm" in report["disclaimer"].lower()


def test_the_socket_blocker_was_armed_and_self_checked(rehearsed):
    """Isolation is recorded as an observed fact, not an assumption."""
    _code, report, _path = rehearsed
    assert report["isolation"]["socket_blocker_armed"] is True
    assert report["isolation"]["self_check_passed"] is True


def test_every_case_was_answered_by_the_snapshot(rehearsed):
    """Proof no live path answered, independent of the socket blocker."""
    _code, report, _path = rehearsed
    for case in report["cases"]:
        assert case["provenance"]["source"] == "snapshot", (
            f"{case['shape']} was not answered by the snapshot"
        )


def test_the_report_binds_to_the_artifact_it_ran_against(rehearsed, dist):
    _code, report, _path = rehearsed
    m = _manifest(dist)
    assert report["artifact"]["snapshot_version"] == m["snapshot_version"]
    assert report["artifact"]["bundle_sha256"] == m["bundle_sha256"]


def test_the_report_records_the_reconstructed_window_per_case(rehearsed):
    _code, report, _path = rehearsed
    for case in report["cases"]:
        assert case["observed_at_before"] == case["observed_at_after"], (
            "a midnight-crossing observation was kept instead of excluded"
        )
        assert case["derived_from_date"], "the reconstructed window is missing"
        assert case["resolved_to_date"], "the resolved upper bound is missing"


def test_the_report_separates_wire_parameters_from_effective_semantics(rehearsed):
    _code, report, _path = rehearsed
    for case in report["cases"]:
        wire = case["request"]["wire"]
        effective = case["request"]["effective"]
        assert wire["address"] == "<omitted>"
        assert effective["address"] is None
        if wire["property_type"] == "<omitted>":
            assert effective["property_type"] == "residential_default (F/D/S/T)"


def test_the_report_carries_no_ids_prices_or_addresses(rehearsed):
    """Aggregates only. The subset checks run in memory and discard their sets."""
    _code, _report, path = rehearsed
    body = path.read_text()
    for forbidden in FORBIDDEN_IN_REPORT:
        assert forbidden not in body, (
            f"the rehearsal report leaked {forbidden!r}; reports carry counts, "
            f"geography membership and outcomes only"
        )


def test_geography_isolation_is_actually_evaluated(rehearsed):
    """The fixture holds B5 and B50, so S1 must exclude B50 for real."""
    _code, report, _path = rehearsed
    s1 = next(c for c in report["cases"] if c["shape"] == "S1")
    assert s1["outcodes_returned"] == ["B5"], (
        f"S1 returned outcodes {s1['outcodes_returned']}; B50 is a different "
        f"place and must never appear in a B5 district search"
    )
    assert s1["invariants"]["geography_isolation"] is True


def test_the_universal_invariants_are_evaluated_on_every_case(rehearsed):
    _code, report, _path = rehearsed
    for case in report["cases"]:
        inv = case["invariants"]
        assert inv["coverage_clamp_warning_present"] is True, case["shape"]
        assert inv["sample_complete_is_false"] is True, case["shape"]
        assert inv["completeness_basis_is_null"] is True, case["shape"]


# ---------------------------------------------------------------------------
# 3. Exit codes and isolation, proven rather than assumed
# ---------------------------------------------------------------------------

def test_the_socket_blocker_actually_refuses_a_socket():
    """Directly exercised. An unarmed blocker would let a live call through
    while the report still claimed isolation."""
    from tools.ppd_snapshot.rehearse import LivePathAttempted, SocketBlocker
    import socket as socket_mod

    blocker = SocketBlocker()
    blocker.arm()
    try:
        with pytest.raises(LivePathAttempted):
            socket_mod.socket(socket_mod.AF_INET, socket_mod.SOCK_STREAM)
    finally:
        blocker.disarm()
    # Restored, so the blocker cannot leak into the rest of the suite.
    sock = socket_mod.socket(socket_mod.AF_INET, socket_mod.SOCK_STREAM)
    sock.close()


def test_a_three_row_fixture_cannot_satisfy_the_dense_cases_and_exits_1(rehearsed):
    """Exit 1 means "ran, and an invariant failed" -- and is correct here.

    A fixture holding three rows cannot be a dense market, so S5 and S12 must
    fail their truncation invariant. If this ever exits 0, the invariants are
    not being evaluated.
    """
    code, report, _path = rehearsed
    assert code == 1, f"expected exit 1 on a fixture that cannot be dense, got {code}"
    assert report["passed"] is False
    dense = [c for c in report["cases"] if c["shape"] in {"S5", "S12"}]
    assert dense, "the dense cases are missing from the report"
    for case in dense:
        assert case["invariants"]["truncated_at_limit"] is False


def test_the_universal_invariants_hold_even_where_a_case_fails(rehearsed):
    """A failing shape must not take the universal invariants down with it."""
    _code, report, _path = rehearsed
    for case in report["cases"]:
        assert case["invariants"]["answered_by_snapshot"] is True, case["shape"]


# ---------------------------------------------------------------------------
# 4. Saturated comparisons are not_evaluable, never failures
# ---------------------------------------------------------------------------

@pytest.fixture
def dense_dist(tmp_path: Path) -> Path:
    """An artifact where S1, S3 and S9 all saturate at limit=50.

    Page-set containment is meaningless once either side is truncated: S1's
    fifty most recent rows across the district need not contain S3's fifty most
    recent within one sector. The rehearsal must say so rather than report a
    failure the artifact did not cause.
    """
    rows = []
    for i in range(60):                       # B5 4 -- S3's sector, saturates
        rows.append(csv_row("{T-B54-%03d}" % i, "B5 4AA", f"2026-05-{i % 28 + 1:02d} 00:00",
                            200_000 + i))
    for i in range(60):                       # B5 7 -- widens B5 beyond B5 4
        rows.append(csv_row("{T-B57-%03d}" % i, "B5 7AA", f"2026-06-{i % 28 + 1:02d} 00:00",
                            300_000 + i))
    for i in range(20):                       # category B, so S9 differs from S3
        rows.append(csv_row("{T-B54B-%03d}" % i, "B5 4AB", f"2026-06-{i % 28 + 1:02d} 00:00",
                            900_000 + i, ppd_category="B"))
    csv_path = write_source_csv(tmp_path / "pp.csv", rows)
    built = build_snapshot(BuildRequest(
        csv_path=csv_path, out_dir=tmp_path / "snapshot",
        coverage_to=COVERAGE_TO, temp_dir=tmp_path / "tmp"))
    release = package_release(
        built, dist_dir=tmp_path / "dist", candidate_root=tmp_path / "work",
        version=snapshot_version(datetime(2026, 8, 28, 11, 0, tzinfo=timezone.utc)),
        source={"file": "pp.csv", "sha256": "b" * 64, "etag": '"dense"'},
        facts={"rows_per_year": {"2026": len(rows)}},
    )
    promote_release(release)
    return tmp_path / "dist"


def _dense_instance(dist_dir: Path) -> dict:
    payload = valid_instance(dist_dir)
    payload["geographies"].update({
        "S4_thin": "B5 6", "S5_dense": "B5 4", "S6_unit": "B5 4AA",
        "S7_type_weak": "B5 7", "S8_type_strong": "B5 7",
        "S11_provisional_empty": "B5 6", "S13_empty_unit": "B5 4AA",
    })
    return payload


@pytest.fixture
def dense_report(tmp_path, dense_dist):
    instance = write_instance(tmp_path / "dense.json", _dense_instance(dense_dist))
    code, _cache, report = run(tmp_path, dense_dist, instance)
    assert report.exists(), f"no report written (exit {code})"
    return code, json.loads(report.read_text())


def test_saturated_subset_comparisons_are_not_evaluable(dense_report):
    _code, report = dense_report
    by = {c["shape"]: c for c in report["cases"]}
    assert by["S3"]["count"] == 50 and by["S1"]["count"] == 50, "fixture is not saturated"

    not_eval = by["S3"]["not_evaluable"]
    assert "subset_of_S1" in not_eval, (
        "a saturated page-set comparison was evaluated instead of being "
        "reported as not_evaluable"
    )
    assert "saturat" in not_eval["subset_of_S1"].lower(), (
        f"the reason does not name saturation: {not_eval['subset_of_S1']!r}"
    )
    assert "subset_of_S1" not in by["S3"]["invariants"], (
        "a not_evaluable assertion must not also appear as an invariant outcome"
    )


def test_saturated_category_comparison_is_not_evaluable(dense_report):
    _code, report = dense_report
    by = {c["shape"]: c for c in report["cases"]}
    assert "category_all_is_superset_of_default" in by["S9"]["not_evaluable"]


def test_not_evaluable_is_never_counted_as_a_pass(dense_report):
    _code, report = dense_report
    assert report["assertions_not_evaluable"] > 0, "the fixture should saturate"
    counted = (report["assertions_passed"] + report["assertions_failed"]
               + report["assertions_not_evaluable"])
    assert counted == report["assertions_total"]
    for case in report["cases"]:
        overlap = set(case["invariants"]) & set(case["not_evaluable"])
        assert not overlap, f"{case['shape']} counts {overlap} twice"


def test_geography_containment_is_checked_even_when_sets_are_not(dense_report):
    """Truncation does not excuse geography: it is meaningful on any page."""
    _code, report = dense_report
    by = {c["shape"]: c for c in report["cases"]}
    assert by["S3"]["invariants"]["geography_isolation"] is True
    assert by["S3"]["invariants"]["within_S1_geography"] is True


# ---------------------------------------------------------------------------
# 5. The rehearsal is a guest: it restores what it found
# ---------------------------------------------------------------------------

def test_pre_existing_snapshot_environment_is_restored(tmp_path, dist, monkeypatch):
    """Unsetting a caller's variable would leave their process quietly changed."""
    monkeypatch.setenv("PPD_SNAPSHOT_ENABLED", "0")
    monkeypatch.setenv("PPD_SNAPSHOT_DIR", "/somewhere/else")
    monkeypatch.delenv("PPD_SNAPSHOT_CACHE_DIR", raising=False)

    instance = write_instance(tmp_path / "ok.json", valid_instance(dist))
    run(tmp_path, dist, instance)

    import os
    assert os.environ["PPD_SNAPSHOT_ENABLED"] == "0", "a caller's flag was not restored"
    assert os.environ["PPD_SNAPSHOT_DIR"] == "/somewhere/else"
    assert "PPD_SNAPSHOT_CACHE_DIR" not in os.environ, (
        "a variable the caller did not set was left behind"
    )


def test_a_pre_existing_installed_adapter_is_restored(tmp_path, dist):
    """The rehearsal installs its own adapter; it must hand back the caller's."""
    from property_core.snapshot import state

    sentinel = object()
    state.install(sentinel, "caller-boot-report")
    try:
        instance = write_instance(tmp_path / "ok.json", valid_instance(dist))
        run(tmp_path, dist, instance)
        assert state.installed_adapter() is sentinel, (
            "the rehearsal dropped an adapter the caller had installed"
        )
        assert state.boot_report() == "caller-boot-report"
    finally:
        state.install(None, None)


# ---------------------------------------------------------------------------
# 6. Latency, date bounds, and midnight accounting
# ---------------------------------------------------------------------------

def test_each_case_records_latency_and_returned_date_bounds(rehearsed):
    _code, report, _path = rehearsed
    for case in report["cases"]:
        assert isinstance(case["latency_ms"], (int, float)), case["shape"]
        assert case["latency_ms"] >= 0
        assert "returned_date_from" in case and "returned_date_to" in case, case["shape"]


def test_midnight_accounting_is_reported(rehearsed):
    _code, report, _path = rehearsed
    assert report["midnight"]["exclusions"] == 0
    assert report["midnight"]["retries"] == 0
    assert report["midnight"]["unrecoverable"] is False


# ---------------------------------------------------------------------------
# 7. The universal invariants really are universal
# ---------------------------------------------------------------------------

def test_provisional_is_asserted_on_every_case_not_just_one(rehearsed):
    """Definition section 3 makes it universal, so the harness must check it
    everywhere. Asserting it on one shape while the contract claims all of them
    is a gap nothing else would catch: the field would still read `true`."""
    _code, report, _path = rehearsed
    for case in report["cases"]:
        assert "provisional_flagged" in case["invariants"], (
            f"{case['shape']} does not assert recent_period_provisional, which "
            f"section 3 makes a universal snapshot-side invariant"
        )
        assert case["invariants"]["provisional_flagged"] is True, case["shape"]


# ---------------------------------------------------------------------------
# 8. Aggregate baselines are part of the instance, and validated
# ---------------------------------------------------------------------------

def test_the_instance_carries_the_declared_aggregate_baselines(tmp_path, dist):
    from tools.ppd_snapshot.rehearse import load_instance

    instance = write_instance(tmp_path / "ok.json", valid_instance(dist))
    loaded = load_instance(instance, dist)
    assert loaded.aggregate_baselines["S1_full"] == 2
    assert loaded.aggregate_baselines["S3_full"] == 1


def test_missing_aggregate_baselines_are_refused(tmp_path, dist):
    payload = valid_instance(dist)
    payload.pop("aggregate_baselines")
    instance = write_instance(tmp_path / "nobase.json", payload)
    code, _cache, report = run(tmp_path, dist, instance)
    assert code == 2
    assert not report.exists()


@pytest.mark.parametrize("baselines, why", [
    ({"S1_full": 1, "S3_full": 2, "S9_full": 3}, "S3 is larger than S1"),
    # Equality contradicts the contract just as surely: section 4 requires a
    # STRICT subset, and S3_full == S1_full says the sector is the whole
    # district. It would have passed a `>` check.
    ({"S1_full": 5, "S3_full": 5, "S9_full": 6}, "S3 equals S1, so is not strict"),
    ({"S1_full": 5, "S3_full": 3, "S9_full": 3}, "S9 does not exceed S3"),
    ({"S1_full": 5, "S3_full": 3}, "a required baseline is missing"),
    ({"S1_full": 5, "S3_full": 3, "S9_full": 4, "extra": 1}, "an unknown baseline"),
    ({"S1_full": "many", "S3_full": 3, "S9_full": 4}, "a baseline is not an integer"),
])
def test_inconsistent_aggregate_baselines_are_refused(tmp_path, dist, baselines, why):
    """The baselines ARE the qualification evidence. A set that contradicts the
    relation it is supposed to establish would qualify nothing."""
    payload = valid_instance(dist)
    payload["aggregate_baselines"] = baselines
    instance = write_instance(tmp_path / f"bad-{abs(hash(why))}.json", payload)
    code, _cache, report = run(tmp_path, dist, instance)
    assert code == 2, f"{why} was not refused"
    assert not report.exists()


def test_the_report_records_the_declared_qualification_evidence(rehearsed):
    """Recorded as DECLARED, not measured: the rehearsal reads pages, so it
    cannot re-derive a full aggregate count and must not imply it did."""
    _code, report, _path = rehearsed
    qual = report["qualification"]
    assert qual["source"] == "declared in the instance, not measured by this rehearsal"
    assert qual["baselines"]["S1_full"] == 2


# ---------------------------------------------------------------------------
# 9. An unrecoverable midnight crossing is reported, not just raised
# ---------------------------------------------------------------------------

def test_an_unrecoverable_midnight_crossing_writes_a_failed_report(
        tmp_path, dist, monkeypatch):
    """The Definition says the failure is recorded. Re-raising before the report
    is written meant the recorded state could never actually occur."""
    from datetime import date as real_date
    import tools.ppd_snapshot.rehearse as reh

    ticker = {"n": 0}

    class AlternatingDate(real_date):
        @classmethod
        def today(cls):
            ticker["n"] += 1
            # Every observation straddles a boundary: before != after, always.
            return real_date(2026, 8, 29) if ticker["n"] % 2 else real_date(2026, 8, 30)

    monkeypatch.setattr(reh, "date", AlternatingDate)

    instance = write_instance(tmp_path / "ok.json", valid_instance(dist))
    code, _cache, report = run(tmp_path, dist, instance)

    assert code == 1, f"an unrecoverable crossing must exit 1, got {code}"
    assert report.exists(), "no report was written for an unrecoverable crossing"
    body = json.loads(report.read_text())
    assert body["passed"] is False
    assert body["midnight"]["unrecoverable"] is True
    assert body["midnight"]["retries"] > 0
    assert body["failure"], "the report does not say what went wrong"
    assert "midnight" in body["failure"].lower()
    assert body["kind"] == "rehearsal" and body["not_stage_1_evidence"] is True

