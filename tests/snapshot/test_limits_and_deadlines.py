"""Caps and deadlines are runtime behaviour, not documentation.

Every value here is also published in the governing specification section 4.
The tests assert the *behaviour*, and one test asserts the constants match the
spec, so the two cannot drift apart again.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

import pytest

from property_core.snapshot.archive import ExtractionLimits
from property_core.snapshot.errors import (
    BundleVerificationError,
    DownloadDeadlineExceeded,
    InsufficientDiskSpaceError,
)
from property_core.snapshot.fetch import (
    DEFAULT_MAX_BUNDLE_BYTES,
    DEFAULT_STALL_SECONDS,
    DEFAULT_TOTAL_DEADLINE_SECONDS,
    DISK_HEADROOM_MULTIPLIER,
    download_verified,
    preflight_disk_space,
)
from property_core.snapshot.models import SnapshotManifest
from property_core.snapshot.source import DEFAULT_TIMEOUT


class Stream:
    """A controllable byte stream: per-read delay, optional early stop."""

    def __init__(self, blob: bytes, *, delay: float = 0.0, chunk: int = 8):
        self.blob, self.delay, self.chunk = blob, delay, chunk
        self.pos = 0
        self.declared_length = len(blob)

    def read(self, n):
        if self.delay:
            time.sleep(self.delay)
        size = min(n, self.chunk)
        out = self.blob[self.pos:self.pos + size]
        self.pos += len(out)
        return out

    def __enter__(self):
        return self

    def __exit__(self, *e):
        return False


class Source:
    def __init__(self, blob: bytes, **kw):
        self.blob, self.kw = blob, kw

    def read_bytes(self, name, *, max_bytes=None):
        return self.blob

    def open_stream(self, name):
        return Stream(self.blob, **self.kw)


def _manifest(blob: bytes, **over) -> SnapshotManifest:
    payload = {"snapshot_version": "v1", "bundle_object": "b.tar",
               "bundle_sha256": hashlib.sha256(blob).hexdigest(),
               "bundle_bytes": len(blob), "parquet_files": 1, "rows": 1}
    payload.update(over)
    return SnapshotManifest(**payload)


# --- the published constants ----------------------------------------------

SPEC = Path(__file__).resolve().parents[2] / "docs" / "design" / "ppd-source-routing.md"


def _spec_text() -> str:
    """Section 4 of the governing specification, whitespace-normalised."""
    body = SPEC.read_text()
    start = body.index("## 4. Runtime design")
    end = body.index("## 5. Packaging")
    return " ".join(body[start:end].split())


@pytest.mark.parametrize(
    "published, value, code_value",
    [
        ("`MAX_BUNDLE_BYTES` **2 GiB**", 2 * 1024 ** 3, DEFAULT_MAX_BUNDLE_BYTES),
        ("total download deadline **300 s**", 300.0, DEFAULT_TOTAL_DEADLINE_SECONDS),
        ("stall detection **60 s**", 60.0, DEFAULT_STALL_SECONDS),
        ("socket\n  timeout **10 s**".replace("\n  ", " "), 10.0, DEFAULT_TIMEOUT),
        ("`MAX_MEMBERS` (**5,000**", 5_000, ExtractionLimits().max_members),
        ("`MAX_TOTAL_BYTES` (**4 GiB**", 4 * 1024 ** 3,
         ExtractionLimits().max_total_bytes),
        ("`bundle_bytes * 2.5`", 2.5, DISK_HEADROOM_MULTIPLIER),
    ],
)
def test_each_constant_matches_the_text_published_in_the_specification(
        published, value, code_value):
    """Reads the SPECIFICATION, not a literal restated in this file.

    The previous version compared code against hardcoded test literals and
    comments, so code and test could drift together while the document said
    something else -- which is exactly the drift this reconciliation fixed.
    """
    assert published in _spec_text(), (
        f"the specification no longer publishes {published!r}; if the value "
        f"changed, change it in both places deliberately"
    )
    assert code_value == value


# --- disk preflight --------------------------------------------------------

def test_preflight_refuses_a_bundle_that_cannot_fit(tmp_path, monkeypatch):
    import shutil as shutil_mod

    from property_core.snapshot import fetch as fetch_mod

    monkeypatch.setattr(
        fetch_mod.shutil, "disk_usage",
        lambda p: shutil_mod._ntuple_diskusage(total=100, used=99, free=1))
    with pytest.raises(InsufficientDiskSpaceError) as ei:
        preflight_disk_space(tmp_path / "b.tar", bundle_bytes=1000)
    payload = ei.value.to_dict()
    assert payload["error"] == "snapshot_insufficient_disk"
    assert payload["required_bytes"] == 2500          # 1000 * 2.5
    assert payload["available_bytes"] == 1


def test_preflight_allows_a_bundle_that_fits(tmp_path):
    preflight_disk_space(tmp_path / "b.tar", bundle_bytes=1)  # must not raise


def test_the_transfer_does_not_start_when_disk_is_short(tmp_path, monkeypatch):
    """Checked BEFORE any bytes move: a full filesystem takes the live path down."""
    import shutil as shutil_mod

    from property_core.snapshot import fetch as fetch_mod

    blob = b"x" * 64
    source = Source(blob)
    monkeypatch.setattr(
        fetch_mod.shutil, "disk_usage",
        lambda p: shutil_mod._ntuple_diskusage(total=100, used=100, free=0))
    dest = tmp_path / "b.tar"
    with pytest.raises(InsufficientDiskSpaceError):
        download_verified(source, _manifest(blob), dest)
    assert not dest.exists(), "no partial file may be written"


def test_preflight_can_be_disabled_for_tests_only(tmp_path):
    blob = b"y" * 32
    result = download_verified(Source(blob), _manifest(blob), tmp_path / "b.tar",
                               check_disk=False)
    assert result.bytes_written == 32


# --- deadlines -------------------------------------------------------------

def test_a_stalled_read_is_aborted(tmp_path):
    """A read that returns nothing for longer than the stall budget."""
    blob = b"z" * 64
    with pytest.raises(DownloadDeadlineExceeded) as ei:
        download_verified(Source(blob, delay=0.15, chunk=8), _manifest(blob),
                          tmp_path / "b.tar", stall_seconds=0.02, check_disk=False)
    assert "stall" in str(ei.value).lower()
    assert not (tmp_path / "b.tar").exists()


def test_a_transfer_exceeding_its_total_budget_is_aborted(tmp_path):
    """Slow but progressing still has to finish inside the whole-transfer budget."""
    blob = b"w" * 400
    with pytest.raises(DownloadDeadlineExceeded) as ei:
        download_verified(Source(blob, delay=0.01, chunk=8), _manifest(blob),
                          tmp_path / "b.tar", total_deadline=0.05,
                          stall_seconds=5.0, check_disk=False)
    assert "budget" in str(ei.value).lower()
    assert not (tmp_path / "b.tar").exists()


def test_a_prompt_transfer_is_unaffected_by_the_deadlines(tmp_path):
    blob = b"q" * 128
    result = download_verified(Source(blob), _manifest(blob), tmp_path / "b.tar",
                               total_deadline=30.0, stall_seconds=5.0,
                               check_disk=False)
    assert result.bytes_written == 128


def test_the_deadline_error_is_typed_and_retryable():
    err = DownloadDeadlineExceeded("stalled")
    payload = err.to_dict()
    assert payload["error"] == "snapshot_download_deadline"
    assert payload["retryable"] is True


# --- the bundle cap --------------------------------------------------------

def test_a_manifest_above_the_bundle_cap_is_refused_before_transfer(tmp_path):
    blob = b"a" * 16
    with pytest.raises(BundleVerificationError) as ei:
        download_verified(Source(blob), _manifest(blob, bundle_bytes=DEFAULT_MAX_BUNDLE_BYTES + 1),
                          tmp_path / "b.tar", check_disk=False)
    assert "maximum" in str(ei.value).lower()
    assert not (tmp_path / "b.tar").exists()


# --- the record PR 4 will route from --------------------------------------

def test_the_record_persists_the_validated_manifest_metadata(tmp_path):
    """Routing must be able to answer coverage questions offline, from the
    materialized snapshot alone -- not by re-fetching a manifest that may have
    rotated since."""
    import io
    import json
    import tarfile

    from property_core.snapshot.runtime import SnapshotRuntime
    from property_core.snapshot.store import SnapshotStore

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        ti = tarfile.TarInfo("data.parquet"); ti.size = 4
        tar.addfile(ti, io.BytesIO(b"PAR1"))
    blob = buf.getvalue()

    manifest = {
        "snapshot_version": "v1", "bundle_object": "s.tar",
        "bundle_sha256": hashlib.sha256(blob).hexdigest(),
        "bundle_bytes": len(blob), "parquet_files": 1, "rows": 42,
        "coverage_from": "2016-01-01", "coverage_to": "2026-06-30",
        "provisional_from": "2026-04-01", "layout": "year",
        "duckdb_version": "v1.5.5",
    }
    objects = {
        "current.json": json.dumps({"current_manifest": "m.json"}).encode(),
        "m.json": json.dumps(manifest).encode(),
        "s.tar": blob,
    }

    class Src:
        def read_bytes(self, name, *, max_bytes=None):
            return objects[name]

        def open_stream(self, name):
            return Stream(objects[name], chunk=1024)

    SnapshotRuntime(source=Src(), store=SnapshotStore(tmp_path)).boot()
    record = SnapshotStore(tmp_path).verified_record("v1")

    assert record is not None
    assert record.coverage_from == "2016-01-01"
    assert record.coverage_to == "2026-06-30"
    assert record.provisional_from == "2026-04-01"
    assert record.layout == "year"
    assert record.duckdb_version == "v1.5.5"
    assert record.rows == 42
    assert record.bundle_object == "s.tar"
    # And it says what was actually established.
    assert record.verification == "structural"


def test_readiness_is_structural_not_queryable():
    """PR 3 must not claim the snapshot opens; PR 4 establishes that."""
    import inspect

    from property_core.snapshot import runtime as mod

    doc = (mod.__doc__ or "").lower()
    assert "structurally verified" in doc
    assert "not queryable" in doc or "not a claim" in doc or "weaker claim" in doc
    src = inspect.getsource(mod)
    for banned in ("duckdb.connect", "read_parquet", "SELECT "):
        assert banned not in src


@pytest.mark.parametrize("bad", ["../m.json", "a/m.json", "", "  ", ".", ".."])
def test_the_current_manifest_pointer_is_validated(tmp_path, bad):
    """current.json names an object we then fetch, so it gets the same
    single-component treatment as every other externally supplied name."""
    import json

    from property_core.snapshot.models import Readiness
    from property_core.snapshot.runtime import SnapshotRuntime
    from property_core.snapshot.store import SnapshotStore

    class Src:
        def read_bytes(self, name, *, max_bytes=None):
            if name == "current.json":
                return json.dumps({"current_manifest": bad}).encode()
            raise AssertionError(f"fetched {name!r} despite an invalid pointer")

        def open_stream(self, name):
            raise AssertionError("streamed despite an invalid pointer")

    report = SnapshotRuntime(source=Src(), store=SnapshotStore(tmp_path)).boot()
    assert report.readiness is Readiness.UNREADY
    assert report.fallback_to_live is True


# --- review follow-ups -----------------------------------------------------

class EOFBlocker:
    """Returns the whole body at once, then blocks before signalling EOF."""

    def __init__(self, blob: bytes, eof_delay: float):
        self.blob, self.eof_delay = blob, eof_delay
        self.declared_length = len(blob)
        self.sent = False

    def read(self, n):
        if not self.sent:
            self.sent = True
            return self.blob
        time.sleep(self.eof_delay)
        return b""

    def __enter__(self):
        return self

    def __exit__(self, *e):
        return False


def test_the_total_deadline_is_enforced_on_the_read_that_returns_eof(tmp_path):
    """`if not chunk: break` ran before the deadline check, so a transfer that
    blocked past its budget and then returned EOF completed successfully."""
    blob = b"X"

    class Src:
        def read_bytes(self, name, *, max_bytes=None):
            return blob

        def open_stream(self, name):
            return EOFBlocker(blob, eof_delay=0.08)

    with pytest.raises(DownloadDeadlineExceeded) as ei:
        download_verified(Src(), _manifest(blob), tmp_path / "b.tar",
                          total_deadline=0.05, stall_seconds=1.0, check_disk=False)
    assert "budget" in str(ei.value).lower()
    assert not (tmp_path / "b.tar").exists()


def test_stall_detection_detects_late_it_does_not_interrupt(tmp_path):
    """Pins the ACTUAL guarantee, so the docs and the test agree.

    A stopwatch around a blocking call is not a timeout: the read completes,
    and only then is the overrun noticed. This test asserts that honestly --
    the error is raised AFTER the blocking read, not at the limit.
    """
    blob = b"ABCD"
    blocked_for = 0.15

    class Src:
        def read_bytes(self, name, *, max_bytes=None):
            return blob

        def open_stream(self, name):
            return Stream(blob, delay=blocked_for, chunk=1)

    started = time.monotonic()
    with pytest.raises(DownloadDeadlineExceeded):
        download_verified(Src(), _manifest(blob), tmp_path / "b.tar",
                          stall_seconds=0.02, check_disk=False)
    elapsed = time.monotonic() - started
    assert elapsed >= blocked_for, (
        "the read was somehow interrupted; if that is now true, the "
        "documented guarantee in spec 4.1 should be strengthened"
    )


def test_one_socket_timeout_is_used_for_both_control_and_bundle_requests(monkeypatch):
    """urlopen takes ONE timeout covering connect and every socket operation.

    Advertising separate connect and read timeouts was a fiction: the second
    value simply changed the bundle connection's timeout too.
    """
    from property_core.snapshot import source as source_mod

    seen = []

    class FakeResponse:
        headers = {"Content-Length": "4"}

        def read(self, n=-1):
            return b"data"

        read1 = read

        def close(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *e):
            return False

    def fake_urlopen(request, timeout=None):
        seen.append(timeout)
        return FakeResponse()

    monkeypatch.setattr(source_mod.urllib.request, "urlopen", fake_urlopen)
    src = source_mod.HttpObjectSource("https://example.invalid", socket_timeout=7.5)
    src.read_bytes("current.json")
    src.open_stream("b.tar")
    assert seen == [7.5, 7.5], seen


def test_the_socket_timeout_defaults_to_the_published_value():
    from property_core.snapshot import source as source_mod

    assert source_mod.HttpObjectSource("https://x.invalid").socket_timeout == DEFAULT_TIMEOUT


def test_there_is_no_separate_read_timeout_setting():
    """Two settings would imply independent enforcement urllib cannot provide."""
    import inspect

    from property_core.snapshot.source import HttpObjectSource

    params = inspect.signature(HttpObjectSource.__init__).parameters
    assert "read_timeout" not in params
    assert "socket_timeout" in params


def test_the_bundle_stream_uses_a_bounded_read_primitive(monkeypatch):
    """`HTTPResponse.read(n)` loops internally until it has n bytes, so a
    dribbling server can keep one call active past the total budget. `read1`
    returns after one underlying socket read, so the budget is evaluated at a
    real interval."""
    from property_core.snapshot import source as source_mod

    calls = []

    class FakeResponse:
        headers = {"Content-Length": "4"}

        def read(self, n=-1):
            calls.append("read")
            return b"data"

        def read1(self, n=-1):
            calls.append("read1")
            return b"data"

        def close(self):
            pass

    monkeypatch.setattr(source_mod.urllib.request, "urlopen",
                        lambda request, timeout=None: FakeResponse())
    stream = source_mod.HttpObjectSource("https://x.invalid").open_stream("b.tar")
    stream.read(1024)
    assert calls == ["read1"], calls


# --- verification record constraints ---------------------------------------

def test_verification_is_constrained_to_structural():
    from pydantic import ValidationError

    from property_core.snapshot.models import VerificationRecord

    base = dict(version="v1", bundle_sha256="a" * 64, bundle_bytes=10,
                bundle_object="s.tar", parquet_files=1, rows=1,
                verified_at="x", inventory={"a.parquet": 4})
    assert VerificationRecord(**base).verification == "structural"
    for claim in ("queryable", "schema", "full", ""):
        with pytest.raises(ValidationError):
            VerificationRecord(**base, verification=claim)


def test_bundle_object_is_required_and_validated():
    from pydantic import ValidationError

    from property_core.snapshot.models import VerificationRecord

    base = dict(version="v1", bundle_sha256="a" * 64, bundle_bytes=10,
                parquet_files=1, rows=1, verified_at="x",
                inventory={"a.parquet": 4})
    with pytest.raises(ValidationError):
        VerificationRecord(**base)                       # missing
    for bad in ("a/b.tar", "../x.tar", "", "  "):
        with pytest.raises(ValidationError):
            VerificationRecord(**base, bundle_object=bad)
    assert VerificationRecord(**base, bundle_object="s.tar").bundle_object == "s.tar"


@pytest.mark.parametrize(
    "mutate",
    [
        # ordinary mutator calls
        lambda inv: inv.__setitem__("a.parquet", 999),
        lambda inv: inv.update({"b.parquet": 1}),
        lambda inv: inv.pop("a.parquet"),
        lambda inv: inv.clear(),
        lambda inv: inv.setdefault("c.parquet", 1),
        lambda inv: inv.__delitem__("a.parquet"),
        lambda inv: inv.popitem(),
        # base-class descriptors -- a dict SUBCLASS cannot block these, which is
        # why the evidence is a read-only mapping and not a subclass.
        lambda inv: dict.__setitem__(inv, "a.parquet", 999),
        lambda inv: dict.update(inv, {"b.parquet": 2}),
        lambda inv: dict.pop(inv, "a.parquet"),
        lambda inv: dict.clear(inv),
        lambda inv: dict.__delitem__(inv, "a.parquet"),
        lambda inv: dict.setdefault(inv, "c.parquet", 1),
    ],
    ids=["setitem", "update", "pop", "clear", "setdefault", "delitem", "popitem",
         "dict.__setitem__", "dict.update", "dict.pop", "dict.clear",
         "dict.__delitem__", "dict.setdefault"],
)
def test_the_inventory_cannot_be_mutated_in_place(mutate):
    """The inventory IS the evidence is_verified compares against.

    frozen=True only stopped rebinding the attribute, and a dict subclass only
    stopped ordinary calls -- `dict.__setitem__(inv, ...)` went straight through
    the base-class descriptor. A read-only mapping has no mutators to reach.
    """
    from property_core.snapshot.models import VerificationRecord

    record = VerificationRecord(
        version="v1", bundle_sha256="a" * 64, bundle_bytes=10,
        bundle_object="s.tar", parquet_files=1, rows=1, verified_at="x",
        inventory={"a.parquet": 4})
    before = record.model_dump_json()
    with pytest.raises((TypeError, AttributeError)):
        mutate(record.inventory)
    assert record.model_dump_json() == before


def test_the_inventory_still_serialises_and_compares_as_a_mapping():
    """Immutability must not change the on-disk shape or equality."""
    import json

    from property_core.snapshot.models import VerificationRecord

    record = VerificationRecord(
        version="v1", bundle_sha256="a" * 64, bundle_bytes=10,
        bundle_object="s.tar", parquet_files=1, rows=1, verified_at="x",
        inventory={"a.parquet": 4})
    assert record.inventory == {"a.parquet": 4}
    assert json.loads(record.model_dump_json())["inventory"] == {"a.parquet": 4}
    assert VerificationRecord(**json.loads(record.model_dump_json())) == record


# --- exports ---------------------------------------------------------------

def test_the_typed_failures_callers_must_handle_are_exported():
    import property_core.snapshot as snapshot

    for name in ("DownloadDeadlineExceeded", "InsufficientDiskSpaceError",
                 "BundleVerificationError", "ArchiveRejected",
                 "SnapshotExtraMissingError", "VerificationRecord"):
        assert name in snapshot.__all__, f"{name} missing from __all__"
        assert hasattr(snapshot, name)
