"""Red-first tests for the HMLR release check (specification section 4.9).

The check is a `HEAD`, never a download: comparing validators against the ones
recorded for the current build is the whole mechanism, and reading 5.5 GB to
learn a release has not changed would defeat it.

**No request leaves this machine.** One test drives a loopback HTTP server so
the method and the absence of a body are observed at a real HTTP boundary; the
rest inject a recording opener.
"""

from __future__ import annotations

import json
import threading
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from tools.ppd_snapshot.release_check import (
    UNINGESTED_ALERT_DAYS,
    ReleaseObservation,
    check_release,
    record_ingested,
)

URL = "http://example.invalid/pp-complete.csv"
NOW = datetime(2026, 8, 28, 9, 0, tzinfo=timezone.utc)

HEADERS = {"ETag": '"333695120b2f0a82265a499df7682980-655"',
           "Last-Modified": "Tue, 28 Jul 2026 05:16:16 GMT",
           "Content-Length": "5494145759"}


class _Opener:
    """Stands in for `urlopen`, recording what it was asked to do."""

    def __init__(self, headers=None, status=200):
        self.headers = dict(HEADERS if headers is None else headers)
        self.status = status
        self.requests = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        opener = self

        class _Response:
            status = opener.status
            headers = opener.headers

            def read(self, *_args):  # pragma: no cover - must never be called
                raise AssertionError("the release check must not read a body")

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        return _Response()


# -- the boundary -----------------------------------------------------------

def test_the_check_issues_a_head_request_and_downloads_nothing(tmp_path: Path):
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_HEAD(self):  # noqa: N802 - stdlib naming
            seen.append(("HEAD", self.path))
            self.send_response(200)
            for key, value in HEADERS.items():
                self.send_header(key, value)
            self.end_headers()

        def do_GET(self):  # noqa: N802 - stdlib naming
            seen.append(("GET", self.path))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"body")

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/pp-complete.csv"
        result = check_release(url, tmp_path / "state.json", now=NOW)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert seen == [("HEAD", "/pp-complete.csv")]
    assert result.bytes_read == 0
    assert result.observation.etag == HEADERS["ETag"]


def test_the_check_never_issues_a_get(tmp_path: Path):
    opener = _Opener()
    check_release(URL, tmp_path / "state.json", opener=opener, now=NOW)
    assert [r.get_method() for r in opener.requests] == ["HEAD"]


# -- observation and change detection ---------------------------------------

def test_a_first_observation_is_recorded_as_changed(tmp_path: Path):
    result = check_release(URL, tmp_path / "state.json", opener=_Opener(), now=NOW)
    assert result.changed is True
    assert result.first_observed == NOW
    assert result.previous is None


def test_an_unchanged_release_is_reported_unchanged(tmp_path: Path):
    state = tmp_path / "state.json"
    check_release(URL, state, opener=_Opener(), now=NOW)
    later = check_release(URL, state, opener=_Opener(),
                          now=NOW + timedelta(days=1))
    assert later.changed is False
    # The clock runs from first observation, not from the latest check.
    assert later.first_observed == NOW


def test_a_new_etag_is_reported_changed_and_restarts_the_clock(tmp_path: Path):
    state = tmp_path / "state.json"
    check_release(URL, state, opener=_Opener(), now=NOW)
    moved = check_release(
        URL, state, now=NOW + timedelta(days=30),
        opener=_Opener({**HEADERS, "ETag": '"a-different-etag"'}))
    assert moved.changed is True
    assert moved.first_observed == NOW + timedelta(days=30)
    assert moved.previous.etag == HEADERS["ETag"]


def test_a_response_with_no_validators_is_treated_as_changed(tmp_path: Path):
    # Nothing to compare means the check cannot prove the release is the same
    # one. Reporting "unchanged" would let a rebuild be skipped on no evidence.
    result = check_release(URL, tmp_path / "state.json", opener=_Opener({}),
                           now=NOW)
    assert result.changed is True
    assert "no validators" in result.reason


# -- the uningested alert ---------------------------------------------------

def test_an_uningested_release_alerts_after_seven_days(tmp_path: Path):
    state = tmp_path / "state.json"
    check_release(URL, state, opener=_Opener(), now=NOW)
    result = check_release(URL, state, opener=_Opener(),
                           now=NOW + timedelta(days=UNINGESTED_ALERT_DAYS))
    assert result.uningested_days == UNINGESTED_ALERT_DAYS
    assert result.alert is True


def test_a_release_observed_yesterday_does_not_alert(tmp_path: Path):
    state = tmp_path / "state.json"
    check_release(URL, state, opener=_Opener(), now=NOW)
    result = check_release(URL, state, opener=_Opener(),
                           now=NOW + timedelta(days=1))
    assert result.alert is False


def test_recording_an_ingest_clears_the_alert(tmp_path: Path):
    state = tmp_path / "state.json"
    check_release(URL, state, opener=_Opener(), now=NOW)
    record_ingested(state, version="v20260828T101500Z", etag=HEADERS["ETag"],
                    now=NOW + timedelta(hours=2))
    result = check_release(URL, state, opener=_Opener(),
                           now=NOW + timedelta(days=30))
    assert result.alert is False
    assert result.ingested is True
    assert result.uningested_days is None


def test_an_ingest_of_a_different_release_does_not_clear_the_alert(tmp_path: Path):
    state = tmp_path / "state.json"
    check_release(URL, state, opener=_Opener(), now=NOW)
    record_ingested(state, version="v20260101T000000Z", etag='"an-older-etag"',
                    now=NOW)
    result = check_release(URL, state, opener=_Opener(),
                           now=NOW + timedelta(days=8))
    assert result.ingested is False
    assert result.alert is True


# -- state ------------------------------------------------------------------

def test_the_state_file_is_the_only_thing_written(tmp_path: Path):
    state = tmp_path / "state.json"
    check_release(URL, state, opener=_Opener(), now=NOW)
    assert [p.name for p in tmp_path.iterdir()] == ["state.json"]
    assert json.loads(state.read_text())["etag"] == HEADERS["ETag"]


def test_a_corrupt_state_file_is_treated_as_no_observation(tmp_path: Path):
    state = tmp_path / "state.json"
    state.write_text("{not json")
    result = check_release(URL, state, opener=_Opener(), now=NOW)
    assert result.changed is True
    assert result.previous is None


def test_an_observation_round_trips_through_the_state_file(tmp_path: Path):
    state = tmp_path / "state.json"
    check_release(URL, state, opener=_Opener(), now=NOW)
    stored = ReleaseObservation(**{
        k: v for k, v in json.loads(state.read_text()).items()
        if k in {"etag", "last_modified", "content_length"}})
    assert stored.content_length == 5494145759


# -- the release's declared coverage end ------------------------------------

def test_the_declared_coverage_end_is_the_month_before_publication():
    from tools.ppd_snapshot.release_check import declared_coverage_end

    # The July 2026 publication carries data to the end of June 2026 -- which is
    # exactly the maximum transfer date observed in that release.
    assert declared_coverage_end("Tue, 28 Jul 2026 05:16:16 GMT") == date(2026, 6, 30)


def test_the_declared_coverage_end_wraps_at_the_year_boundary():
    from tools.ppd_snapshot.release_check import declared_coverage_end

    assert declared_coverage_end("Thu, 15 Jan 2026 00:00:00 GMT") == date(2025, 12, 31)


def test_an_unparseable_publication_date_yields_no_declared_end():
    from tools.ppd_snapshot.release_check import declared_coverage_end

    assert declared_coverage_end("not a date") is None
    assert declared_coverage_end(None) is None


# -- the observation clock must survive a failed write ----------------------

def test_a_failed_state_write_preserves_the_previous_observation(tmp_path,
                                                                 monkeypatch):
    """`write_text` truncates first, so an interrupted check would erase the
    first-observed timestamp the seven-day alert is measured from."""
    from tools.ppd_snapshot import atomic

    state = tmp_path / "state.json"
    check_release(URL, state, opener=_Opener(), now=NOW)
    before = state.read_bytes()

    monkeypatch.setattr(atomic.os, "replace",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("boom")))
    with pytest.raises(OSError):
        check_release(URL, state, opener=_Opener(),
                      now=NOW + timedelta(days=1))

    assert state.read_bytes() == before
    assert json.loads(state.read_text())["first_observed_utc"] == NOW.isoformat()


def test_a_failed_ingest_record_preserves_the_previous_state(tmp_path,
                                                             monkeypatch):
    from tools.ppd_snapshot import atomic

    state = tmp_path / "state.json"
    check_release(URL, state, opener=_Opener(), now=NOW)
    before = state.read_bytes()

    monkeypatch.setattr(atomic.os, "replace",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("boom")))
    with pytest.raises(OSError):
        record_ingested(state, version="v20260828T101500Z", etag=HEADERS["ETag"],
                        now=NOW)
    assert state.read_bytes() == before


def test_a_state_write_leaves_no_temporary_files(tmp_path):
    state = tmp_path / "state.json"
    check_release(URL, state, opener=_Opener(), now=NOW)
    record_ingested(state, version="v1", etag=HEADERS["ETag"], now=NOW)
    assert [p.name for p in tmp_path.iterdir()] == ["state.json"]
