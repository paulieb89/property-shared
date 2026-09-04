"""Tests for the Fly deploy retry ladder.

Loaded by path and driven through an injected runner, following
`tests/test_fly_observability_snapshot.py` -- the suite never shells out and
never needs a Fly token.

The point of putting this ladder in a script rather than in workflow YAML is
that it can be tested at all. The `if: failure()` two-step form these tests
would not have caught is the one that reports success as failure.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "deploy_fly.py"


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("deploy_fly", _MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


df = _load_module()

FAKE_TOKEN = "fm2_lJPECAAAAAAAtesttokenvalue0000000000000xyz"


class Runner:
    """Records argv per call and returns queued exit codes (or raises)."""

    def __init__(self, outcomes: list[object]):
        self.outcomes = list(outcomes)
        self.calls: list[list[str]] = []

    def __call__(self, argv, timeout=None, **kwargs):
        self.calls.append(list(argv))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return subprocess.CompletedProcess(argv, outcome)


@pytest.fixture
def sleeps() -> list[float]:
    return []


@pytest.fixture
def sleep(sleeps):
    return sleeps.append


def test_first_attempt_uses_depot_and_no_fallback_runs_on_success(sleep, sleeps):
    runner = Runner([0])
    assert df.deploy("property-shared", "fly.toml", runner=runner, sleep=sleep) == 0
    assert len(runner.calls) == 1, "a successful deploy must not be repeated"
    assert "--depot=false" not in runner.calls[0], "Depot is the default and faster path"
    assert sleeps == [], "no backoff when nothing failed"


def test_depot_failure_falls_back_to_depot_false(sleep):
    runner = Runner([1, 0])
    assert df.deploy("property-shared", "fly.toml", runner=runner, sleep=sleep) == 0
    assert "--depot=false" not in runner.calls[0]
    assert "--depot=false" in runner.calls[1], "the flag that made manual recovery work"


def test_exit_status_is_zero_when_the_fallback_succeeds(sleep):
    """The defect an `if: failure()` two-step form would have.

    A failed first step fails the job even when a later step succeeds, so that
    shape needs continue-on-error and then reports a misleading green.
    """
    runner = Runner([1, 0])
    assert df.deploy("propertydata", "fly.app.toml", runner=runner, sleep=sleep) == 0


def test_exit_status_is_one_when_every_attempt_fails(sleep):
    runner = Runner([1, 1, 1])
    assert df.deploy("property-shared", "fly.toml", runner=runner, sleep=sleep) == 1
    assert len(runner.calls) == 3


def test_a_hung_attempt_is_bounded_and_the_fallback_still_runs(sleep):
    """Both observed failures were timeouts.

    Without a per-attempt bound the first hang eats the job budget and the
    fallback never runs, which makes the whole ladder decorative.
    """
    runner = Runner([subprocess.TimeoutExpired(cmd="flyctl", timeout=900), 0])
    assert df.deploy("property-shared", "fly.toml", runner=runner, sleep=sleep) == 0
    assert len(runner.calls) == 2
    assert "--depot=false" in runner.calls[1]


def test_every_attempt_is_given_a_timeout(sleep):
    seen: list[float | None] = []

    def runner(argv, timeout=None, **kwargs):
        seen.append(timeout)
        return subprocess.CompletedProcess(argv, 1)

    df.deploy("property-shared", "fly.toml", runner=runner, sleep=sleep)
    assert seen and all(t is not None and t > 0 for t in seen), (
        "an attempt with no timeout can hang forever"
    )


@pytest.mark.parametrize(
    ("app", "config"),
    [("property-shared", "fly.toml"), ("propertydata", "fly.app.toml")],
)
def test_app_and_config_are_always_explicit_in_argv(app, config, sleep):
    """CI relied on cwd discovery of fly.toml; the command that ran was not the
    command anyone had written down."""
    runner = Runner([0])
    df.deploy(app, config, runner=runner, sleep=sleep)
    argv = runner.calls[0]
    assert argv[:2] == ["flyctl", "deploy"]
    assert argv[argv.index("--app") + 1] == app
    assert argv[argv.index("--config") + 1] == config
    assert "--remote-only" in argv and "--ha=false" in argv


def test_a_missing_flyctl_fails_immediately_without_retrying(sleep):
    runner = Runner([FileNotFoundError("flyctl")])
    assert df.deploy("property-shared", "fly.toml", runner=runner, sleep=sleep) == 1
    assert len(runner.calls) == 1, "retrying a missing binary cannot help"


def test_it_backs_off_between_attempts_but_not_after_the_last(sleep, sleeps):
    runner = Runner([1, 1, 1])
    df.deploy("property-shared", "fly.toml", runner=runner, sleep=sleep)
    assert len(sleeps) == 2, "three attempts means two gaps"


def test_the_token_never_appears_in_output(capsys, sleep, monkeypatch):
    monkeypatch.setenv("FLY_API_TOKEN", FAKE_TOKEN)
    runner = Runner([1, 1, 1])
    df.deploy("property-shared", "fly.toml", runner=runner, sleep=sleep)
    captured = capsys.readouterr()
    assert FAKE_TOKEN not in captured.out + captured.err
