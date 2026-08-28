"""Typed snapshot-runtime errors.

Protocol-neutral like the rest of `property_core`: typed data, no HTTP status
codes. Consumers map them.
"""

from __future__ import annotations

from typing import Any

from property_core.exceptions import PPDError, SnapshotFailure


class SnapshotExtraMissingError(SnapshotFailure):
    """A snapshot feature was used without the optional dependency installed.

    Actionable by construction: the message names the extra to install, because
    a bare ``ModuleNotFoundError: duckdb`` tells an operator nothing about which
    optional feature they enabled.
    """

    code = "snapshot_extra_missing"
    retryable = False

    def __init__(self, feature: str = "the PPD snapshot source",
                 package: str = "duckdb", extra: str = "snapshot"):
        self.feature, self.package, self.extra = feature, package, extra
        super().__init__(
            f"{feature} requires the optional '{extra}' extra "
            f"(missing package: {package}). Install it with "
            f"`pip install 'property-shared[{extra}]'` "
            f"(or `uv sync --extra {extra}`), or leave PPD_SNAPSHOT_ENABLED unset "
            f"to use the live source."
        )

    def to_dict(self) -> dict[str, Any]:
        return {**super().to_dict(), "extra": self.extra, "package": self.package}


class BundleVerificationError(SnapshotFailure):
    """A bundle failed size or digest verification, or the transfer was short."""

    code = "snapshot_bundle_verification_failed"
    retryable = True


class InsufficientDiskSpaceError(SnapshotFailure):
    """Not enough free space to download and unpack the bundle.

    Checked BEFORE the transfer starts: filling the filesystem is worse than not
    having the snapshot, because it takes the live path down with it.
    """

    code = "snapshot_insufficient_disk"
    retryable = True

    def __init__(self, required: int, available: int, path: str = ""):
        self.required, self.available, self.path = required, available, path
        super().__init__(
            f"need {required} bytes free to materialize the snapshot, "
            f"{available} available" + (f" at {path}" if path else "")
        )

    def to_dict(self) -> dict[str, Any]:
        return {**super().to_dict(), "required_bytes": self.required,
                "available_bytes": self.available}


class DownloadDeadlineExceeded(SnapshotFailure):
    """The transfer exceeded its total budget or stalled."""

    code = "snapshot_download_deadline"
    retryable = True


class ArchiveRejected(SnapshotFailure):
    """An archive member violated a safety rule. Fail closed.

    ``rule`` names the violated invariant so a caller can tell a hostile archive
    from a merely oversized one.
    """

    code = "snapshot_archive_rejected"
    retryable = False

    def __init__(self, rule: str, member: str = "", detail: str = ""):
        self.rule, self.member, self.detail = rule, member, detail
        super().__init__(
            f"archive rejected [{rule}]"
            + (f" member={member!r}" if member else "")
            + (f" {detail}" if detail else "")
        )

    def to_dict(self) -> dict[str, Any]:
        return {**super().to_dict(), "rule": self.rule, "member": self.member}


class SnapshotSchemaError(SnapshotFailure):
    """The materialized snapshot does not carry the columns routing needs.

    A missing or mistyped column is not a query that returns nothing -- it is a
    query that cannot be asked. Caught here so it becomes a live fallback rather
    than an empty result set that reads as "no sales here".
    """

    code = "snapshot_schema_invalid"
    retryable = False

    def __init__(self, detail: str, *, column: str = ""):
        self.column = column
        super().__init__(detail)

    def to_dict(self) -> dict[str, Any]:
        return {**super().to_dict(), "column": self.column}


class SnapshotRowCountError(SnapshotFailure):
    """The snapshot holds a different number of rows than its record declares.

    The verification record is written from the build's own count. A disagreement
    means the directory is not the snapshot that was verified, whatever the file
    inventory says.
    """

    code = "snapshot_row_count_mismatch"
    retryable = False

    def __init__(self, expected: int, found: int):
        self.expected, self.found = expected, found
        super().__init__(
            f"snapshot holds {found} row(s); the verification record declares "
            f"{expected}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {**super().to_dict(), "expected_rows": self.expected,
                "found_rows": self.found}


class SnapshotNotQueryableError(SnapshotFailure):
    """Structurally verified bytes that DuckDB cannot actually read.

    Boot proves the archive was safe and the inventory exact. Neither implies the
    Parquet files parse, so this is checked before the adapter is allowed to
    serve anything.
    """

    code = "snapshot_not_queryable"
    retryable = False


class SnapshotQueryError(SnapshotFailure):
    """A query against an already-validated snapshot failed at request time."""

    code = "snapshot_query_failed"
    retryable = True


class SnapshotMetadataError(SnapshotFailure):
    """Coverage metadata that routing cannot answer coverage questions from.

    Routing decides what to refuse, what to narrow, and what a warning must say
    entirely from `coverage_from`/`coverage_to`/`provisional_from`. Missing,
    unparseable or contradictory bounds do not degrade those decisions -- they
    silently remove them: a record with no bounds answered a 1995 request from an
    eleven-year snapshot, reported null coverage, and claimed the sample was
    complete. Rejected before routing, so the caller gets the live source.
    """

    code = "snapshot_metadata_invalid"
    retryable = False

    def __init__(self, detail: str, *, field: str = ""):
        self.field = field
        super().__init__(detail)

    def to_dict(self) -> dict[str, Any]:
        return {**super().to_dict(), "field": self.field}


class SnapshotCoverageGapError(SnapshotFailure):
    """The snapshot holds nothing in the window this surface must answer.

    Distinct from `PPDCoverageError`, and the distinction is who the answer is
    for. A caller who named dates outside coverage gets a refusal they can act
    on. A caller of a bounded-`months` surface named no dates at all -- the
    window was derived for them -- so refusing would blame them for a stale
    snapshot. This is a snapshot failure, and the live source answers.
    """

    code = "snapshot_coverage_gap"
    retryable = True
