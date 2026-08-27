"""Single-flight: two workers must not download or activate simultaneously."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import time

import pytest

from property_core.snapshot.lock import LockTimeout, single_flight


def test_lock_is_exclusive_within_a_process(tmp_path):
    path = tmp_path / ".boot.lock"
    with single_flight(path, timeout=0.2):
        with pytest.raises(LockTimeout):
            with single_flight(path, timeout=0.2):
                pass  # pragma: no cover


def test_lock_is_exclusive_across_processes(tmp_path):
    """flock is per-host and advisory -- the deployment shape is many workers,
    one machine, so cross-process exclusion is the property that matters."""
    path = tmp_path / ".boot.lock"
    script = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {os.getcwd()!r})
        from property_core.snapshot.lock import single_flight, LockTimeout
        try:
            with single_flight({str(path)!r}, timeout=0.2):
                print("ACQUIRED")
        except LockTimeout:
            print("BLOCKED")
    """)
    with single_flight(path, timeout=0.2):
        out = subprocess.run([sys.executable, "-c", script], capture_output=True,
                             text=True, timeout=60)
    assert "BLOCKED" in out.stdout, out.stdout + out.stderr


def test_lock_is_released_after_the_block(tmp_path):
    path = tmp_path / ".boot.lock"
    with single_flight(path, timeout=0.2):
        pass
    with single_flight(path, timeout=0.2):
        pass  # must not raise


def test_lock_is_released_when_the_holder_raises(tmp_path):
    """A lock-holder failure must not wedge every later start."""
    path = tmp_path / ".boot.lock"
    with pytest.raises(RuntimeError):
        with single_flight(path, timeout=0.2):
            raise RuntimeError("holder died mid-boot")
    with single_flight(path, timeout=0.2):
        pass


def test_a_waiter_blocks_then_acquires_when_released(tmp_path):
    """The second starter waits rather than racing or duplicating the work."""
    path = tmp_path / ".boot.lock"
    marker = tmp_path / "child-started"
    script = textwrap.dedent(f"""
        import sys, time, pathlib
        sys.path.insert(0, {os.getcwd()!r})
        from property_core.snapshot.lock import single_flight
        pathlib.Path({str(marker)!r}).write_text("ready")
        t0 = time.perf_counter()
        with single_flight({str(path)!r}, timeout=30):
            print("ACQUIRED", round(time.perf_counter() - t0, 2))
    """)
    with single_flight(path, timeout=5):
        proc = subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)
        # Only start timing the hold once the child is actually contending,
        # so interpreter start-up is not counted as waiting.
        deadline = time.monotonic() + 30
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert marker.exists(), "child never started"
        time.sleep(0.6)
    out, err = proc.communicate(timeout=60)
    assert "ACQUIRED" in out, out + err
    waited = float(out.split()[1])
    assert waited >= 0.4, f"waiter did not actually block (waited {waited}s)"


def test_a_stale_lock_file_from_a_dead_process_does_not_wedge_boot(tmp_path):
    """A leftover lock FILE is not a held lock: flock dies with the process."""
    path = tmp_path / ".boot.lock"
    path.write_text("99999")  # a pid that is not us and holds nothing
    with single_flight(path, timeout=1.0):
        pass
