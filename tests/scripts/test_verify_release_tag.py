"""Tests for scripts/verify_release_tag.py.

The verifier is the CI/CLI guard that checks three things before a tag
is considered releasable:

1. The tag name matches the canonical `vMAJOR.MINOR.PATCH` format.
2. `pyproject.toml` `[project].version` equals the tag version.
3. `docs/CHANGELOG.md` has a dated `## [<version> "<codename>"?] - YYYY-MM-DD`
   section, AND the `## [Unreleased]` heading above it is empty.

These tests exercise those three rails on a synthetic repo built in
`tmp_path` (passed via `--repo-root`), so no fixtures of the real repo
state are touched.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "verify_release_tag.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("verify_release_tag", SCRIPT_PATH)
    assert spec and spec.loader, f"Cannot load script spec from {SCRIPT_PATH}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script():
    return _load_script_module()


def _build_fake_repo(
    root: Path,
    *,
    pyproject_version: str = "5.4.0",
    changelog_version: str | None = "5.4.0",
    codename: str | None = "Triton",
    unreleased_body: str = "",
    omit_unreleased: bool = False,
    omit_changelog: bool = False,
) -> Path:
    """Create a minimal synthetic repo at `root` and return the path."""
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "cti-scraper"\nversion = "{pyproject_version}"\n',
        encoding="utf-8",
    )
    if omit_changelog:
        return root
    docs = root / "docs"
    docs.mkdir(parents=True, exist_ok=True)

    parts = ["# Changelog", ""]
    if not omit_unreleased:
        parts.extend(["## [Unreleased]", ""])
        if unreleased_body:
            parts.extend([unreleased_body, ""])
    if changelog_version is not None:
        heading_title = f'{changelog_version} "{codename}"' if codename else changelog_version
        parts.extend([f"## [{heading_title}] - 2026-05-01", "", "### Added", "- thing", ""])

    (docs / "CHANGELOG.md").write_text("\n".join(parts), encoding="utf-8")
    return root


def _invoke(script, tag: str, repo_root: Path):
    """Run script.main() with argv patched. Returns exit code from SystemExit or return value."""
    old_argv = sys.argv
    sys.argv = ["verify_release_tag.py", tag, "--repo-root", str(repo_root)]
    try:
        try:
            return script.main()
        except SystemExit as exc:
            return exc.code
    finally:
        sys.argv = old_argv


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_happy_path_with_codename(script, tmp_path, capsys):
    repo = _build_fake_repo(tmp_path)
    rc = _invoke(script, "v5.4.0", repo)
    out = capsys.readouterr().out
    assert rc == 0
    assert "OK" in out


def test_happy_path_without_codename(script, tmp_path):
    repo = _build_fake_repo(tmp_path, codename=None)
    rc = _invoke(script, "v5.4.0", repo)
    assert rc == 0


# ---------------------------------------------------------------------------
# Tag format
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_tag",
    [
        "5.4.0",  # missing v prefix
        "v5.4",  # not MAJOR.MINOR.PATCH
        "v5.4.0-rc.1",  # pre-release tag is out of scope for this verifier
        "v5.4.0-ganymede",
        "kepler-v5.4.0",
        "",
    ],
)
def test_rejects_malformed_tag(script, tmp_path, bad_tag, capsys):
    repo = _build_fake_repo(tmp_path)
    rc = _invoke(script, bad_tag, repo)
    err = capsys.readouterr().err
    assert rc == 1
    assert "canonical format" in err or "FAIL" in err


# ---------------------------------------------------------------------------
# pyproject / CHANGELOG consistency
# ---------------------------------------------------------------------------


def test_rejects_pyproject_version_mismatch(script, tmp_path, capsys):
    repo = _build_fake_repo(tmp_path, pyproject_version="5.3.0")
    rc = _invoke(script, "v5.4.0", repo)
    err = capsys.readouterr().err
    assert rc == 1
    assert "pyproject.toml" in err
    assert "5.3.0" in err


def test_rejects_missing_changelog_section(script, tmp_path, capsys):
    # pyproject says 5.4.0 but CHANGELOG only has 5.3.0.
    repo = _build_fake_repo(tmp_path, changelog_version="5.3.0", codename="Callisto")
    rc = _invoke(script, "v5.4.0", repo)
    err = capsys.readouterr().err
    assert rc == 1
    assert "no dated section for 5.4.0" in err


def test_rejects_missing_pyproject(script, tmp_path, capsys):
    # No pyproject.toml at all.
    rc = _invoke(script, "v5.4.0", tmp_path)
    err = capsys.readouterr().err
    assert rc == 1
    assert "pyproject.toml not found" in err


def test_rejects_missing_changelog(script, tmp_path, capsys):
    repo = _build_fake_repo(tmp_path, omit_changelog=True)
    rc = _invoke(script, "v5.4.0", repo)
    err = capsys.readouterr().err
    assert rc == 1
    assert "CHANGELOG.md not found" in err


def test_rejects_missing_unreleased_heading(script, tmp_path, capsys):
    repo = _build_fake_repo(tmp_path, omit_unreleased=True)
    rc = _invoke(script, "v5.4.0", repo)
    err = capsys.readouterr().err
    assert rc == 1
    assert "Unreleased" in err


# ---------------------------------------------------------------------------
# Unreleased emptiness rule
# ---------------------------------------------------------------------------


def test_rejects_nonempty_unreleased_with_bullets(script, tmp_path, capsys):
    repo = _build_fake_repo(tmp_path, unreleased_body="- forgot to roll this entry")
    rc = _invoke(script, "v5.4.0", repo)
    err = capsys.readouterr().err
    assert rc == 1
    assert "Unreleased" in err
    assert "not empty" in err


def test_rejects_nonempty_unreleased_with_subsections(script, tmp_path, capsys):
    repo = _build_fake_repo(tmp_path, unreleased_body="### Added\n- stray")
    rc = _invoke(script, "v5.4.0", repo)
    err = capsys.readouterr().err
    assert rc == 1
    assert "Unreleased" in err


def test_unreleased_with_only_whitespace_is_allowed(script, tmp_path):
    # Whitespace lines between headings should not fail the empty check.
    repo = _build_fake_repo(tmp_path, unreleased_body="   \n\t\n")
    rc = _invoke(script, "v5.4.0", repo)
    assert rc == 0
