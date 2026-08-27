"""Typed snapshot-runtime errors.

Protocol-neutral like the rest of `property_core`: typed data, no HTTP status
codes. Consumers map them.
"""

from __future__ import annotations

from typing import Any

from property_core.exceptions import PPDError


class SnapshotExtraMissingError(PPDError):
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


class BundleVerificationError(PPDError):
    """A bundle failed size or digest verification, or the transfer was short."""

    code = "snapshot_bundle_verification_failed"
    retryable = True


class ArchiveRejected(PPDError):
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
