#!/usr/bin/env python3
"""Assert every app actually serves the released version.

`release.yml` fans out to two independent leaf deploy jobs. One failing while
the other succeeds is a *normal terminal state* of that graph, which is exactly
what happened on v1.15.1: PyPI and `propertydata` succeeded, `property-shared`
failed twice, and nothing noticed. The two apps ran different versions for
roughly an hour, with the app that needed a critical hotfix still on the broken
build. This script is the job that would have noticed.

Both apps expose the same version field (verified live 2026-09-04):

    property-shared  /.well-known/mcp/server-card.json -> serverInfo.version
    propertydata     /.well-known/mcp/server-card.json -> serverInfo.version

`serverInfo.name` differs (`property-data` vs `property-app`) but `version`
comes from the same installed `property-shared` distribution in both, so the
comparison is meaningful rather than coincidental. `propertydata`'s `/health`
carries no version and cannot be used for this.

Two distinct failures, deliberately reported differently:

  * **tag/pyproject mismatch** -- the version is baked into the image at build
    time, so tagging v1.18.3 without bumping pyproject.toml deploys two apps
    that both honestly report 1.18.2. No amount of polling fixes that, so it is
    caught up front and reported as its own thing rather than as drift.
  * **release drift** -- an app is not serving the released version.

Polling, not a single request: a completed deploy does not mean the new version
is instantly serving. And `--require-consecutive` rounds, because Fly's proxy
may front more than one Machine; a single 200 cannot distinguish "propagated"
from "you happened to hit the updated Machine". At the time of writing each app
runs exactly one Machine, which is a point-in-time observation and not a
guarantee, so the defence stays.

Stdlib only, so the reconcile job needs no project install.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import tomllib
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Sequence

CARD_PATH = "/.well-known/mcp/server-card.json"
REQUEST_TIMEOUT_SECONDS = 10.0


def normalise_tag(tag: str) -> str:
    """Strip a single leading v.

    Deliberately not `lstrip("v")`, which strips every leading v and turns the
    nonsense tag `vv1.0.0` into a plausible `1.0.0`.
    """
    tag = tag.strip()
    return tag[1:] if tag[:1] in ("v", "V") else tag


def project_version(pyproject: Path) -> str:
    with pyproject.open("rb") as handle:
        return tomllib.load(handle)["project"]["version"]


def _fetch(url: str) -> str:
    with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return response.read().decode("utf-8")


def observed_version(base_url: str, fetch: Callable[[str], str]) -> tuple[str | None, str | None]:
    """Return (version, error). Exactly one is None."""
    try:
        body = fetch(f"{base_url.rstrip('/')}{CARD_PATH}")
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    try:
        return json.loads(body)["serverInfo"]["version"], None
    except (ValueError, KeyError, TypeError) as exc:
        return None, f"unreadable server card: {type(exc).__name__}: {exc}"


def verify(
    expected: str,
    targets: dict[str, str],
    *,
    attempts: int = 20,
    interval: float = 15.0,
    require_consecutive: int = 2,
    fetch: Callable[[str], str] = _fetch,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    consecutive = 0
    last: dict[str, str] = {}

    for attempt in range(1, attempts + 1):
        round_state: dict[str, str] = {}
        for name, base_url in targets.items():
            version, error = observed_version(base_url, fetch)
            # An unreachable target is a failure, not an unknown. Treating it as
            # "not yet" would let a permanently dead app pass by timing out.
            round_state[name] = version if version is not None else f"<{error}>"
        last = round_state

        agreed = all(value == expected for value in round_state.values())
        consecutive = consecutive + 1 if agreed else 0
        summary = "  ".join(f"{name}={value}" for name, value in sorted(round_state.items()))
        print(
            f"attempt {attempt}/{attempts}: {summary}"
            f"  (agreed {consecutive}/{require_consecutive})",
            flush=True,
        )

        if consecutive >= require_consecutive:
            print(f"all targets serve {expected}", flush=True)
            return 0
        if attempt < attempts:
            sleep(interval)

    print(f"::error::RELEASE DRIFT: expected {expected} — " + "  ".join(
        f"{name}={value}" for name, value in sorted(last.items())
    ), flush=True)
    for name, value in sorted(last.items()):
        print(f"  {name:20} {value}", flush=True)
    return 1


def parse_target(raw: str) -> tuple[str, str]:
    name, _, url = raw.partition("=")
    if not name or not url:
        raise argparse.ArgumentTypeError(f"expected name=url, got {raw!r}")
    return name, url


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expect", required=True, help="release tag, e.g. v1.18.2")
    parser.add_argument("--target", action="append", required=True, type=parse_target)
    parser.add_argument("--attempts", type=int, default=20)
    parser.add_argument("--interval", type=float, default=15.0)
    parser.add_argument("--require-consecutive", type=int, default=2)
    parser.add_argument("--pyproject", default=str(Path(__file__).resolve().parents[1] / "pyproject.toml"))
    args = parser.parse_args(argv)

    expected = normalise_tag(args.expect)

    declared = project_version(Path(args.pyproject))
    if declared != expected:
        print(
            f"::error::tag/pyproject mismatch: tag {args.expect!r} normalises to "
            f"{expected!r} but pyproject.toml declares {declared!r}. The version is "
            f"baked into the image at build time, so both apps would report "
            f"{declared!r} however many times they are polled. This is a release "
            f"preparation error, not a partial deploy.",
            flush=True,
        )
        return 1

    return verify(
        expected,
        dict(args.target),
        attempts=args.attempts,
        interval=args.interval,
        require_consecutive=args.require_consecutive,
    )


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
