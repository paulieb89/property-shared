"""The MCP registry manifest must state the version this repository builds.

`server.json` is what the MCP registry publishes about this server: the version
a registry client believes it is installing, and the PyPI version `uvx` resolves.
Nothing generated it and nothing checked it, so both of its version fields were
hand-edited at each release and silently drifted whenever one was missed.

This is the same defect class as the v1.14.2 server-card fix: a manifest that
misreports what is published defeats the purpose of publishing it. That one was
caught by dogfooding in production; this one would be caught by a user whose
registry install resolved the wrong release.

Asserted as agreement with `pyproject.toml` — the single source the build reads —
never as a literal, so it holds across releases without edits.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = json.loads((ROOT / "server.json").read_text())
BUILD_VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]


def test_the_manifest_declares_the_version_this_repository_builds():
    assert MANIFEST["version"] == BUILD_VERSION, (
        f"server.json declares {MANIFEST['version']!r}, but pyproject.toml "
        f"builds {BUILD_VERSION!r}"
    )


def test_every_pypi_package_entry_resolves_to_that_same_version():
    """The `uvx` install path carries its own version field, edited separately."""
    pypi = [p for p in MANIFEST["packages"] if p["registryType"] == "pypi"]
    assert pypi, "no PyPI package entry in server.json"
    for package in pypi:
        assert package["version"] == BUILD_VERSION, (
            f"server.json PyPI entry {package['identifier']!r} pins "
            f"{package['version']!r}, but pyproject.toml builds {BUILD_VERSION!r}"
        )


def test_the_manifest_names_the_distribution_actually_published():
    """A version match is worthless if the identifier points somewhere else."""
    name = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["name"]
    identifiers = {p["identifier"] for p in MANIFEST["packages"] if p["registryType"] == "pypi"}
    assert identifiers == {name}, f"manifest publishes {identifiers}, build publishes {name!r}"


def test_the_changelog_heads_with_the_version_being_built():
    """The other hand-edited version field in a release.

    Bumping `pyproject.toml` without dating the changelog section ships a
    release whose notes still say "Unreleased", and bumping the changelog
    without `pyproject.toml` publishes the previous version under the new
    notes. Both are one forgotten edit away, and neither fails anything today.
    """
    headings = [
        line for line in (ROOT / "CHANGELOG.md").read_text().splitlines()
        if line.startswith("## ")
    ]
    assert headings, "no release headings in CHANGELOG.md"
    assert headings[0].startswith(f"## v{BUILD_VERSION} "), (
        f"the changelog heads with {headings[0]!r}, but pyproject.toml builds "
        f"{BUILD_VERSION!r}"
    )
