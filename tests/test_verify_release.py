"""Tests for the post-deploy release reconciliation.

This job exists because of one concrete incident: on v1.15.1 the two Fly deploys
are independent leaf jobs, one failed and one succeeded, and that combination is
a normal terminal state of the workflow graph. The two apps ran different
versions with the broken build still live on the app that needed the fix.

`test_one_target_behind_fails_and_names_both_versions` replays that exactly.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_release.py"


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("verify_release", _MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


vr = _load_module()

TARGETS = {
    "property-shared": "https://property-shared.fly.dev",
    "propertydata": "https://propertydata.fly.dev",
}


def card(version: str, name: str = "property-data") -> str:
    return json.dumps({"serverInfo": {"name": name, "version": version}})


class Fetcher:
    """Serves a queue of per-round responses keyed by host substring."""

    def __init__(self, rounds: list[dict[str, object]]):
        self.rounds = list(rounds)
        self.calls: list[str] = []
        self._served = 0

    def __call__(self, url: str) -> str:
        self.calls.append(url)
        # One round is consumed per full sweep of the targets.
        index = min(self._served // len(TARGETS), len(self.rounds) - 1)
        self._served += 1
        for key, value in self.rounds[index].items():
            if key in url:
                if isinstance(value, BaseException):
                    raise value
                return str(value)
        raise AssertionError(f"unexpected url {url}")


@pytest.fixture
def sleeps() -> list[float]:
    return []


@pytest.fixture
def sleep(sleeps):
    return sleeps.append


# --- tag normalisation ---


@pytest.mark.parametrize(
    ("tag", "expected"),
    [("v1.18.2", "1.18.2"), ("1.18.2", "1.18.2"), ("V1.18.2", "1.18.2"), ("vv1.0.0", "v1.0.0")],
)
def test_v_prefix_is_stripped_exactly_once(tag, expected):
    """`lstrip("v")` would turn the nonsense tag vv1.0.0 into a plausible 1.0.0."""
    assert vr.normalise_tag(tag) == expected


# --- the happy path, and the incident ---


def test_both_targets_on_the_released_version_passes(sleep):
    fetch = Fetcher([{"property-shared": card("1.18.2"), "propertydata": card("1.18.2")}])
    assert vr.verify("1.18.2", TARGETS, fetch=fetch, sleep=sleep, require_consecutive=2) == 0


def test_one_target_behind_fails_and_names_both_versions(capsys, sleep):
    """The v1.15.1 incident, replayed."""
    fetch = Fetcher([{"property-shared": card("1.15.0"), "propertydata": card("1.15.1")}])
    assert vr.verify("1.15.1", TARGETS, attempts=2, fetch=fetch, sleep=sleep) == 1
    out = capsys.readouterr().out
    assert "RELEASE DRIFT" in out
    assert "1.15.0" in out and "1.15.1" in out, "the operator must see both sides"


def test_an_unreachable_target_is_a_failure_not_a_pass(capsys, sleep):
    fetch = Fetcher([
        {"property-shared": ConnectionError("refused"), "propertydata": card("1.18.2")}
    ])
    assert vr.verify("1.18.2", TARGETS, attempts=2, fetch=fetch, sleep=sleep) == 1
    assert "RELEASE DRIFT" in capsys.readouterr().out


def test_an_unreadable_card_is_a_failure_not_a_pass(sleep):
    fetch = Fetcher([{"property-shared": "not json", "propertydata": card("1.18.2")}])
    assert vr.verify("1.18.2", TARGETS, attempts=2, fetch=fetch, sleep=sleep) == 1


# --- propagation ---


def test_it_waits_for_a_late_target_rather_than_failing_on_the_first_round(sleep):
    """A completed deploy does not mean the new version is instantly serving."""
    fetch = Fetcher([
        {"property-shared": card("1.18.1"), "propertydata": card("1.18.2")},
        {"property-shared": card("1.18.2"), "propertydata": card("1.18.2")},
        {"property-shared": card("1.18.2"), "propertydata": card("1.18.2")},
    ])
    assert vr.verify("1.18.2", TARGETS, attempts=5, fetch=fetch, sleep=sleep) == 0


def test_a_version_that_flaps_between_rounds_does_not_pass(sleep):
    """Defends against a multi-Machine app round-robining old and new.

    A single 200 cannot distinguish "propagated" from "you happened to hit the
    updated Machine".
    """
    fetch = Fetcher([
        {"property-shared": card("1.18.2"), "propertydata": card("1.18.2")},
        {"property-shared": card("1.18.1"), "propertydata": card("1.18.2")},
        {"property-shared": card("1.18.2"), "propertydata": card("1.18.2")},
    ])
    assert vr.verify("1.18.2", TARGETS, attempts=3, fetch=fetch, sleep=sleep,
                     require_consecutive=3) == 1


def test_it_stops_polling_as_soon_as_the_targets_agree(sleeps, sleep):
    fetch = Fetcher([{"property-shared": card("1.18.2"), "propertydata": card("1.18.2")}])
    vr.verify("1.18.2", TARGETS, attempts=20, fetch=fetch, sleep=sleep, require_consecutive=1)
    assert sleeps == [], "no reason to keep polling once the answer is in"


# --- the two failures must stay distinguishable ---


def test_a_pyproject_tag_mismatch_fails_immediately_without_polling(tmp_path, capsys):
    """No amount of polling can fix a version that was never built.

    Distinct from drift, and reported as such -- otherwise an operator chases a
    partial deploy that did not happen.
    """
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "property-shared"\nversion = "1.18.2"\n')

    called: list[str] = []
    original = vr._fetch
    vr._fetch = lambda url: called.append(url) or ""  # type: ignore[assignment]
    try:
        code = vr.main([
            "--expect", "v1.18.3",
            "--target", "property-shared=https://example.invalid",
            "--pyproject", str(pyproject),
        ])
    finally:
        vr._fetch = original  # type: ignore[assignment]

    assert code == 1
    assert called == [], "a mismatch must not spend twenty polling rounds"
    out = capsys.readouterr().out
    assert "tag/pyproject mismatch" in out
    assert "RELEASE DRIFT" not in out, "two different failures must read differently"


def test_the_real_pyproject_version_is_readable():
    """Pins the field path this depends on."""
    root = Path(__file__).resolve().parents[1]
    assert vr.project_version(root / "pyproject.toml").count(".") >= 2


@pytest.mark.parametrize("raw", ["noequals", "=https://x", "name="])
def test_a_malformed_target_is_rejected(raw):
    import argparse

    with pytest.raises(argparse.ArgumentTypeError):
        vr.parse_target(raw)
