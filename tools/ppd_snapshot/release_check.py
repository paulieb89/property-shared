"""Daily check for a new HM Land Registry release (specification section 4.9).

Cadence follows the observed release, not the calendar: rebuild monthly *after*
HMLR publishes. Detecting that cheaply is the whole job here -- a `HEAD` against
`pp-complete.csv`, comparing `ETag` / `Last-Modified` / `Content-Length` with the
values recorded when the current snapshot was built. **Nothing is downloaded.**

The state file also carries *when a release was first observed*, because the
seven-day alert is a statement about the pipeline, not about HMLR: it means an
available release has not been ingested, and it has to be measured from
observation rather than from build time to mean that.

**No request is issued by this module during PR 5.** It is exercised against a
loopback server and a recording opener; pointing it at the real host is an
operator action, documented in the runbook.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

#: The official HTTPS endpoint published by HM Land Registry on the GOV.UK
#: "Price Paid Data single file" page. Public open data: no credentials, and
#: nothing is created or mutated.
#:
#: HTTPS on purpose. The S3 *website* endpoint the lab used
#: (`http://prod.publicdata.landregistry.gov.uk.s3-website-eu-west-1...`) is
#: plaintext, so both the validators this pipeline trusts and the 5.5 GB body
#: itself are open to tampering in transit -- and the receipt would then bind
#: the build to whatever arrived.
DEFAULT_URL = "https://price-paid-data.publicdata.landregistry.gov.uk/pp-complete.csv"

#: Section 4.9: an observed release still uningested after this many days is an
#: operational alert -- the pipeline is failing, which is a different fact from
#: the snapshot merely being old.
UNINGESTED_ALERT_DAYS = 7

DEFAULT_TIMEOUT = 30.0
USER_AGENT = "property-shared-snapshot-build/1"


def declared_coverage_end(last_modified: Optional[str]) -> Optional[date]:
    """The coverage end a release publication implies.

    HMLR publishes `pp-complete.csv` after a month closes, so a file published
    in July covers to the end of June. Deriving the window end this way keeps it
    a statement about the *release*: taking `max(transfer_date)` instead would
    let a truncated download declare whatever window its rows happened to reach,
    which is the one thing coverage must not be able to do.

    Returns None when the publication date cannot be read, so the caller has to
    supply the end explicitly rather than proceed on a guess.
    """
    from email.utils import parsedate_to_datetime

    if not last_modified:
        return None
    try:
        published = parsedate_to_datetime(last_modified)
    except (TypeError, ValueError):
        return None
    if published is None:
        return None
    return date(published.year, published.month, 1) - timedelta(days=1)


@dataclass(frozen=True)
class ReleaseObservation:
    """The validators that identify one published release."""

    etag: Optional[str] = None
    last_modified: Optional[str] = None
    content_length: Optional[int] = None

    @property
    def has_validators(self) -> bool:
        return any((self.etag, self.last_modified, self.content_length))


@dataclass(frozen=True)
class ReleaseCheck:
    url: str
    observation: ReleaseObservation
    previous: Optional[ReleaseObservation]
    changed: bool
    reason: str
    first_observed: datetime
    #: None once the observed release has been ingested; otherwise how long it
    #: has been sitting there.
    uningested_days: Optional[float]
    ingested: bool
    alert: bool
    #: Always zero. Asserted by test rather than promised in a comment.
    bytes_read: int = 0


def _parse_length(value: Any) -> Optional[int]:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _read_state(path: Path) -> dict[str, Any]:
    """The recorded state, or an empty one.

    A corrupt state file means "nothing observed", never an exception: this runs
    unattended, and a check that crashes reports nothing at all.
    """
    try:
        state = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}
    return state if isinstance(state, dict) else {}


def _observation_from(state: dict[str, Any]) -> Optional[ReleaseObservation]:
    if not state or "first_observed_utc" not in state:
        return None
    return ReleaseObservation(
        etag=state.get("etag"),
        last_modified=state.get("last_modified"),
        content_length=_parse_length(state.get("content_length")))


def _head(url: str, opener: Callable[..., Any], timeout: float
          ) -> ReleaseObservation:
    import urllib.request

    request = urllib.request.Request(
        url, method="HEAD", headers={"User-Agent": USER_AGENT})
    with opener(request, timeout=timeout) as response:
        headers = response.headers
        return ReleaseObservation(
            etag=headers.get("ETag"),
            last_modified=headers.get("Last-Modified"),
            content_length=_parse_length(headers.get("Content-Length")))


def check_release(url: str = DEFAULT_URL, state_path: Path | str = "release.json",
                  *, opener: Optional[Callable[..., Any]] = None,
                  now: Optional[datetime] = None,
                  timeout: float = DEFAULT_TIMEOUT) -> ReleaseCheck:
    """Compare the published release with the recorded one. HEAD only."""
    import urllib.request

    state_path = Path(state_path)
    now = now or datetime.now(timezone.utc)
    observation = _head(url, opener or urllib.request.urlopen, timeout)
    previous = _observation_from(_read_state(state_path))
    state = _read_state(state_path)

    if not observation.has_validators:
        # Fail towards doing the work: an unverifiable response must not be the
        # reason a real release is skipped.
        changed, reason = True, ("the response carried no validators, so the "
                                 "release cannot be shown to be unchanged")
    elif previous is None:
        changed, reason = True, "no release has been observed before"
    elif observation != previous:
        changed, reason = True, "the published validators have moved"
    else:
        changed, reason = False, "the published validators are unchanged"

    first_observed = now
    if not changed:
        recorded = state.get("first_observed_utc")
        if recorded:
            try:
                first_observed = datetime.fromisoformat(recorded)
            except ValueError:
                first_observed = now

    ingested = bool(observation.etag) and (
        state.get("last_ingested", {}).get("etag") == observation.etag)
    uningested_days = None if ingested else round(
        (now - first_observed).total_seconds() / 86400.0, 4)
    alert = uningested_days is not None and uningested_days >= UNINGESTED_ALERT_DAYS

    state.update({
        "url": url,
        "etag": observation.etag,
        "last_modified": observation.last_modified,
        "content_length": observation.content_length,
        "first_observed_utc": first_observed.isoformat(),
        "last_checked_utc": now.isoformat(),
    })
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2) + "\n")

    return ReleaseCheck(
        url=url, observation=observation, previous=previous, changed=changed,
        reason=reason, first_observed=first_observed,
        uningested_days=uningested_days, ingested=ingested, alert=alert)


def record_ingested(state_path: Path | str, *, version: str, etag: Optional[str],
                    now: Optional[datetime] = None) -> None:
    """Record which observed release a build consumed, stopping its alert clock."""
    state_path = Path(state_path)
    state = _read_state(state_path)
    state["last_ingested"] = {
        "version": version,
        "etag": etag,
        "at_utc": (now or datetime.now(timezone.utc)).isoformat(),
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2) + "\n")


def describe(check: ReleaseCheck) -> str:  # pragma: no cover - operator output
    lines = [
        f"url:            {check.url}",
        f"etag:           {check.observation.etag}",
        f"last-modified:  {check.observation.last_modified}",
        f"content-length: {check.observation.content_length}",
        f"changed:        {check.changed} ({check.reason})",
        f"first observed: {check.first_observed.isoformat()}",
        f"ingested:       {check.ingested}",
    ]
    if check.uningested_days is not None:
        lines.append(f"uningested for: {check.uningested_days} day(s)")
    if check.alert:
        lines.append(f"ALERT: an observed release has been uningested for "
                     f"{UNINGESTED_ALERT_DAYS}+ days; the pipeline is failing")
    return "\n".join(lines)
