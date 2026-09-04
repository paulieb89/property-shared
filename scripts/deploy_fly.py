#!/usr/bin/env python3
"""Deploy one Fly app, retrying past a transient builder failure.

On the v1.15.1 release, `publish` and the `propertydata` deploy both succeeded
while the `property-shared` deploy failed twice, five minutes apart:

    Waiting for depot builder...
    error releasing builder: deadline_exceeded: context deadline exceeded
    Error: failed to fetch an image or build from source: error building:
      timed out connecting to machine: failed to list workers:
      Unavailable: ... authentication handshake failed: EOF

Fly reported no incident, the same token had built the app five hours earlier,
and `propertydata` obtained a builder on the same run. It was treated as
transient Depot unavailability. Recovery was a manual `fly deploy` with
`--depot=false`, which is the one causally relevant difference from CI.

So: attempt with Depot (the default, and the faster path -- one intermittent
incident is not a reason to discard it permanently), then fall back to
`--depot=false`.

**The per-attempt timeout is load-bearing.** Both observed failures were
timeouts. Without a bound, one hung attempt consumes the whole job budget and
the fallback never runs, which would make this retry decorative.

Why a script and not YAML: retry logic in a workflow cannot be tested, and the
`if: failure()` two-step form needs `continue-on-error` (so a failed first
attempt renders as a misleading green) and writes the flyctl arguments twice --
and two copies drifting apart is the failure class this change exists to close.

Duplicate-release hazard, stated rather than assumed: if an attempt released the
app and then timed out waiting, the next attempt releases again. Both apps are
stateless, run `--ha=false`, and have no migration step, so a duplicate release
is benign here. That is a property of these two apps, not of `fly deploy`.

Stdlib only: the deploy job installs flyctl, not the project.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from typing import Callable, Sequence

#: Depot first, then two non-Depot attempts.
ATTEMPTS: tuple[tuple[str, ...], ...] = ((), ("--depot=false",), ("--depot=false",))

ATTEMPT_TIMEOUT_SECONDS = 900.0
SLEEP_BETWEEN_ATTEMPTS = 30.0


def build_argv(app: str, config: str, extra: Sequence[str] = ()) -> list[str]:
    """The deploy command for one attempt.

    `--app` and `--config` are always explicit. CI previously relied on cwd
    discovery of `fly.toml` for property-shared, so the command that ran was not
    the command anyone had written down; the successful manual recovery named
    both.
    """
    return [
        "flyctl", "deploy",
        "--app", app,
        "--config", config,
        "--remote-only",
        "--ha=false",
        *extra,
    ]


def deploy(
    app: str,
    config: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    sleep: Callable[[float], None] = time.sleep,
    attempts: Sequence[Sequence[str]] = ATTEMPTS,
    timeout: float = ATTEMPT_TIMEOUT_SECONDS,
) -> int:
    """Run the attempt ladder. Returns a process exit code."""
    failures: list[str] = []

    for index, extra in enumerate(attempts, start=1):
        argv = build_argv(app, config, extra)
        label = "depot" if not extra else "depot=false"
        print(f"::group::deploy attempt {index}/{len(attempts)} ({label})", flush=True)
        print(f"$ {' '.join(argv)}", flush=True)
        try:
            completed = runner(argv, timeout=timeout)
            code = completed.returncode
        except subprocess.TimeoutExpired:
            code = None
            failures.append(f"attempt {index} ({label}): timed out after {timeout:.0f}s")
            print(f"attempt {index} timed out after {timeout:.0f}s", flush=True)
        except FileNotFoundError as exc:
            print("::endgroup::", flush=True)
            print(f"::error::flyctl is not installed: {exc}", flush=True)
            return 1
        else:
            if code == 0:
                print("::endgroup::", flush=True)
                print(f"deployed {app} on attempt {index} ({label})", flush=True)
                return 0
            failures.append(f"attempt {index} ({label}): exit {code}")
            print(f"attempt {index} failed with exit {code}", flush=True)
        print("::endgroup::", flush=True)

        if index < len(attempts):
            sleep(SLEEP_BETWEEN_ATTEMPTS)

    print(f"::error::every deploy attempt for {app} failed", flush=True)
    for line in failures:
        print(f"  {line}", flush=True)
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", required=True)
    parser.add_argument("--config", required=True)
    args = parser.parse_args(argv)
    return deploy(args.app, args.config)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
