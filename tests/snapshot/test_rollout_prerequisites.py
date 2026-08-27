"""Repository-config lint for the snapshot-extra prerequisite.

**This is a lint over checked-in configuration, NOT enforcement of rollout gate
G3.** It reads the Dockerfiles and fly configs in this repository and nothing
else. The flag can be switched on by paths this file cannot see:

* `fly secrets set PPD_SNAPSHOT_ENABLED=1` — no checked-in change at all;
* machine or process environment set outside the repo;
* any orchestration that injects env at deploy time.

On any of those paths this lint stays green while the feature is on and the
dependencies are missing. Treat a pass as "the repo does not contradict the
prerequisite", never as "the prerequisite is satisfied".

The definitive gate is G3 in `docs/design/ppd-source-routing.md`, enforced by
built-image smoke tests and a fail-closed runtime check, both of which belong to
PR 4 / the rollout rather than here.

What this file is good for: catching the ordinary mistake of enabling the flag
in a Dockerfile or fly.toml without adding the extra alongside it. Cheap,
immediate, and covers the path a change to this repository would take.

`property_core.snapshot` needs `duckdb` and `zstandard`, both optional and both
in the `snapshot` extra. Neither production image installs that extra today,
which is correct while the flag is off — the runtime is never booted, so the
packages are never imported.

The invariants below are CONDITIONAL: inert today, and firing on the commit that
turns the feature on in checked-in config. They are deliberately not "assert the
extra is absent" — that would fail the day PR 4 correctly adds it, inviting
someone to delete the test rather than read it.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

#: (name, Dockerfile, fly config) for each deployed image.
IMAGES = [
    ("property-shared", "Dockerfile", "fly.toml"),
    ("propertydata", "Dockerfile.app", "fly.app.toml"),
]

_TRUE = {"1", "true", "yes", "on"}


def _text(name: str, root: Path | None = None) -> str:
    path = (root or REPO) / name
    return path.read_text() if path.exists() else ""


def _installs_snapshot_extra(dockerfile: str, root: Path | None = None) -> bool:
    """Whether the image's uv sync includes the snapshot extra."""
    for line in _text(dockerfile, root).splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "uv sync" not in stripped:
            continue
        # The name must END here: "--extra snapshot-extra" is a
        # different extra, and \b would match before the hyphen.
        if re.search(r"--extra\s+snapshot(?=\s|$)", stripped):
            return True
    return False


def _flag_enabled(*config_files: str, root: Path | None = None) -> bool:
    """Whether any deployment config switches the snapshot flag on.

    Deliberately does not skip comments: a commented-out enable is still worth
    surfacing loudly rather than silently treating as off.
    """
    pattern = re.compile(
        r"""PPD_SNAPSHOT_ENABLED\s*[=:]\s*["']?([A-Za-z0-9]+)["']?""")
    for name in config_files:
        for match in pattern.finditer(_text(name, root)):
            if match.group(1).strip().lower() in _TRUE:
                return True
    return False


@pytest.mark.parametrize("image, dockerfile, flyconfig", IMAGES,
                         ids=[i[0] for i in IMAGES])
def test_an_image_that_enables_the_snapshot_in_repo_config_installs_the_extra(
        image, dockerfile, flyconfig):
    """Secondary guard, not gate G3.

    Covers only the flag being enabled in checked-in config. A Fly secret or an
    injected environment variable enables it without touching this repository,
    and this test cannot see that. G3 is enforced by built-image smoke tests and
    the fail-closed runtime check.
    """
    if not _flag_enabled(dockerfile, flyconfig):
        pytest.skip(
            f"{image}: flag not enabled in checked-in config. NOTE: this does not "
            f"prove the flag is off in the deployed image — a Fly secret would not "
            f"appear here."
        )
    assert _installs_snapshot_extra(dockerfile), (
        f"{image} enables PPD_SNAPSHOT_ENABLED in checked-in config but "
        f"{dockerfile} does not `uv sync --extra snapshot`. The boot runtime "
        f"imports duckdb and zstandard, so this image would fail at startup."
    )


@pytest.mark.parametrize("image, dockerfile, flyconfig", IMAGES,
                         ids=[i[0] for i in IMAGES])
def test_the_snapshot_flag_is_not_enabled_in_deployment_config(
        image, dockerfile, flyconfig):
    """PR 3 ships inert: no checked-in config may switch the feature on.

    Scope limit as above — this says nothing about secrets or injected env.
    """
    assert not _flag_enabled(dockerfile, flyconfig), (
        f"{image} enables PPD_SNAPSHOT_ENABLED; the feature is not ready to be on"
    )


def test_both_images_are_covered_by_the_lint():
    """A new deployed image must not quietly escape even this partial check."""
    dockerfiles = {p.name for p in REPO.glob("Dockerfile*")}
    covered = {d for _n, d, _f in IMAGES}
    assert dockerfiles == covered, (
        f"Dockerfiles not covered by the config lint: {dockerfiles - covered}"
    )


def test_the_runtime_dependencies_live_only_in_the_snapshot_extra():
    """Both packages stay optional and stay together.

    Splitting them across extras, or promoting either to a required dependency,
    would break the single prerequisite G3 encodes.
    """
    data = tomllib.loads((REPO / "pyproject.toml").read_text())
    extra = data["project"]["optional-dependencies"]["snapshot"]
    assert any(d.startswith("duckdb") for d in extra), extra
    assert any(d.startswith("zstandard") for d in extra), extra

    required = " ".join(data["project"]["dependencies"]).lower()
    assert "duckdb" not in required and "zstandard" not in required

    for name, deps in data["project"]["optional-dependencies"].items():
        if name == "snapshot":
            continue
        joined = " ".join(deps).lower()
        assert "duckdb" not in joined and "zstandard" not in joined, (
            f"snapshot runtime dependency leaked into the {name!r} extra"
        )


def test_the_definitive_gate_is_recorded_in_the_governing_specification():
    """The real gate lives in the spec; this lint is only its cheap shadow.

    Asserts the four requirements that actually enforce it, so the spec cannot
    drift into describing this test as sufficient.
    """
    spec = (REPO / "docs" / "design" / "ppd-source-routing.md").read_text()
    normalised = " ".join(spec.split())

    assert "G3" in normalised, "the image prerequisite is not listed as a rollout gate"
    assert "--extra snapshot" in normalised
    # 1. unconditional install before routing
    assert "unconditionally" in normalised
    # 2. built-image smoke tests
    assert "smoke test" in normalised
    # 3. fail closed with readiness false
    assert "fails closed" in normalised
    # 4. flag stays off until the image checks, G1 and G2 pass
    assert "G1 and G2" in normalised


def test_the_specification_states_this_lint_is_not_sufficient():
    """The limitation must be written down, not only known to whoever wrote it."""
    spec = (REPO / "docs" / "design" / "ppd-source-routing.md").read_text()
    normalised = " ".join(spec.split())
    assert "Fly secret" in normalised, (
        "the spec does not record that a secret bypasses the repo-config lint"
    )


# --------------------------------------------------------------------------
# Prove the gate fires. A conditional invariant that only ever skips in CI is
# not evidence of anything, so its logic is exercised against synthetic inputs.
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "content, expected",
    [
        ("RUN uv sync --frozen --no-dev --extra api", False),
        ("RUN uv sync --frozen --no-dev --extra api --extra snapshot", True),
        ("# RUN uv sync --extra snapshot", False),          # commented out
        ("RUN uv sync --extra snapshots", False),           # near-miss name
        ("RUN uv sync --extra snapshot-extra", False),
        ("RUN pip install property-shared[snapshot]", False),  # not a uv sync line
    ],
)
def test_extra_detection(tmp_path, content, expected):
    (tmp_path / "Dockerfile.fake").write_text(
        "FROM python:3.11-slim\n" + content + "\n")
    assert _installs_snapshot_extra("Dockerfile.fake", root=tmp_path) is expected


@pytest.mark.parametrize(
    "content, expected",
    [
        ('ENV PPD_SNAPSHOT_ENABLED=1', True),
        ('  PPD_SNAPSHOT_ENABLED = "true"', True),
        ("  PPD_SNAPSHOT_ENABLED = 'on'", True),
        ('ENV PPD_SNAPSHOT_ENABLED=0', False),
        ('  PPD_SNAPSHOT_ENABLED = "false"', False),
        ("# PPD_SNAPSHOT_ENABLED = \"1\"", True),  # commented, but flagged: err loud
        ("SOMETHING_ELSE = \"1\"", False),
    ],
)
def test_flag_detection(tmp_path, content, expected):
    (tmp_path / "fly.fake.toml").write_text("[env]\n" + content + "\n")
    assert _flag_enabled("fly.fake.toml", root=tmp_path) is expected


def test_the_gate_fails_when_the_flag_is_on_without_the_extra(tmp_path):
    """The case that matters: enabled feature, missing dependency."""
    (tmp_path / "Dockerfile.fake").write_text(
        "FROM python:3.11-slim\nRUN uv sync --frozen --no-dev --extra api\n")
    (tmp_path / "fly.fake.toml").write_text('[env]\n  PPD_SNAPSHOT_ENABLED = "1"\n')

    enabled = _flag_enabled("Dockerfile.fake", "fly.fake.toml", root=tmp_path)
    installed = _installs_snapshot_extra("Dockerfile.fake", root=tmp_path)
    assert enabled is True and installed is False
    # This is precisely the combination the parametrised gate refuses.
    with pytest.raises(AssertionError):
        assert installed, "gate would fail here"


def test_the_gate_passes_when_the_flag_is_on_with_the_extra(tmp_path):
    (tmp_path / "Dockerfile.fake").write_text(
        "FROM python:3.11-slim\n"
        "RUN uv sync --frozen --no-dev --extra api --extra snapshot\n")
    (tmp_path / "fly.fake.toml").write_text('[env]\n  PPD_SNAPSHOT_ENABLED = "1"\n')

    assert _flag_enabled("Dockerfile.fake", "fly.fake.toml", root=tmp_path) is True
    assert _installs_snapshot_extra("Dockerfile.fake", root=tmp_path) is True


def test_neither_image_installs_the_extra_today_and_that_is_correct():
    """Records the current state explicitly, with the reason it is fine.

    Informational: the runtime is never booted while the flag is off, so the
    packages are never imported. PR 4 / the rollout changes both sides together.
    """
    installed = {name: _installs_snapshot_extra(dockerfile)
                 for name, dockerfile, _fly in IMAGES}
    enabled = {name: _flag_enabled(dockerfile, fly)
               for name, dockerfile, fly in IMAGES}
    assert enabled == {"property-shared": False, "propertydata": False}
    assert installed == {"property-shared": False, "propertydata": False}, (
        f"{installed} — if an image now installs the extra, the rollout has "
        f"started and this record needs updating alongside it"
    )
