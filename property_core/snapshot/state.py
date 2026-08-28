"""Process-scoped snapshot state.

**Process-scoped, deliberately.** The materialization belongs to the process and
the Machine it runs on, not to any client. Holding it in MCP session state --
the obvious-looking alternative -- would re-boot for every client that connects,
leak one client's adapter into another's reconnect, and tie a filesystem
resource to a lifetime that has nothing to do with it. There is no session
anything in this module and there must never be.

The state is a module global because a process has exactly one of these, the
same way it has one working directory. Guarded by a lock because uvicorn serves
concurrently and boot happens while requests may already be arriving.

Nothing here decides *whether* to use a snapshot beyond the flag: installing is
the boot layer's job, and `active_adapter()` returning `None` is the normal,
expected state -- it means the caller uses the live source.
"""

from __future__ import annotations

import threading
from typing import Any, Optional

from property_core.config import ppd_snapshot_enabled

_lock = threading.Lock()
_adapter: Any = None
_boot_report: Any = None


def install(adapter: Any, report: Any = None) -> None:
    """Make a validated adapter the process's snapshot source.

    Only a validated adapter reaches here: `SnapshotAdapter.open` raises rather
    than returning an unusable one, so there is no half-installed state.
    """
    global _adapter, _boot_report
    with _lock:
        _adapter = adapter
        _boot_report = report


def active_adapter() -> Optional[Any]:
    """The adapter to route to, or `None` to use the live source.

    The flag is consulted on every call, not once at import. `PPD_SNAPSHOT_ENABLED=0`
    plus a restart is the documented rollback, and reading the flag here means an
    installed adapter cannot outlive the flag that authorised it.
    """
    if not ppd_snapshot_enabled():
        return None
    with _lock:
        return _adapter


def installed_adapter() -> Optional[Any]:
    """What is installed, regardless of the flag. For diagnostics and shutdown."""
    with _lock:
        return _adapter


def boot_report() -> Optional[Any]:
    with _lock:
        return _boot_report


def clear() -> None:
    """Drop the adapter and close it. Safe to call when nothing is installed."""
    global _adapter, _boot_report
    with _lock:
        adapter, _adapter, _boot_report = _adapter, None, None
    if adapter is not None:
        close = getattr(adapter, "close", None)
        if callable(close):
            try:
                close()
            except Exception:  # noqa: BLE001 -- shutdown must not raise
                pass
