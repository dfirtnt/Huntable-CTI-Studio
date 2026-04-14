"""Tests for scripts/release_cut.py.

`release_cut.py` is the atomic release-cut pipeline: compute edits across
four files, write them to disk, run `verify_release_tag.py` as a pre-flight
guard, then commit + tag. These tests cover the file-editing helpers in
isolation (pure functions over file contents) and exercise end-to-end
`--skip-git` runs on a synthetic repo to confirm the pipeline wires up.

Git-side behavior (`_preflight`, `_commit_and_tag`) is deliberately NOT
tested here -- it shells out to real git. The `--skip-git` flag exists
specifically so we can exercise the edit pipeline without the git side
effects.

Argument validation (`VERSION_RE`, `CODENAME_RE`, `DATE_RE`) is tested
via `main()` because that's where the validation actually runs.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "release_cut.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("release_cut", SCRIPT_PATH)
    assert spec and spec.loader, f"Cannot load script spec from {SCRIPT_PATH}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script():
    return _load_script_module()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PYPROJECT_SAMPLE = """\
[project]
name = "cti-scraper"
version = "5.3.0"
requires-python = ">=3.10"
dependencies = []
"""

CHANGELOG_SAMPLE = """\
# Changelog

## [Unreleased]

## [5.3.0 "Callisto"] - 2026-04-14

### Added
- Prior feature
"""

VERSIONING_SAMPLE = """\
# Versioning

## Current Version

**v5.3.0 "Callisto"** - Current stable release
**v5.2.0 "Ganymede"** - Previous stable release
**v4.0.0 "Kepler"** - Earlier stable release

## Version History

### v5.3.0 "Callisto" (2026-04-14)
- **Named After**: Jupiter's moon Callisto
- **Significance**: Foo
- **Features**: Bar
"""

README_SAMPLE = """\
# Huntable CTI Studio

**Huntable CTI Studio v5.3.0 "Callisto"**

A threat intelligence platform.
"""


def _seed_repo(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text(PYPROJECT_SAMPLE, encoding="utf-8")
    (tmp_path / "README.md").write_text(README_SAMPLE, encoding="utf-8")
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "CHANGELOG.md").write_text(CHANGELOG_SAMPLE, encoding="utf-8")
    (docs / "reference").mkdir()
    (docs / "reference" / "versioning.md").write_text(VERSIONING_SAMPLE, encoding="utf-8")
    return tmp_path


@pytest.fixture
def repo(tmp_path, script, monkeypatch):
    """Point script.REPO_ROOT at a synthetic repo seeded with fixture files."""
    seeded = _seed_repo(tmp_path)
    monkeypatch.setattr(script, "REPO_ROOT", seeded)
    return seeded


# ---------------------------------------------------------------------------
# _bump_pyproject
# ---------------------------------------------------------------------------


def test_bump_pyproject_updates_only_project_version(script, repo):
    path, new = script._bump_pyproject("5.4.0")
    assert path == repo / "pyproject.toml"
    assert 'version = "5.4.0"' in new
    # requires-python must not be rewritten (it contains `version = "..."`-adjacent
    # syntax but starts with `requires-python`, not `version`).
    assert 'requires-python = ">=3.10"' in new
    assert 'version = "5.3.0"' not in new


def test_bump_pyproject_fails_when_version_line_missing(script, repo):
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "cti-scraper"\n',
        encoding="utf-8",
    )
    with pytest.raises(SystemExit):
        script._bump_pyproject("5.4.0")


# ---------------------------------------------------------------------------
# _roll_changelog
# ---------------------------------------------------------------------------


def test_roll_changelog_inserts_fresh_unreleased_and_dated_section(script, repo):
    path, new = script._roll_changelog("5.4.0", "Triton", "2026-05-01")
    assert path == repo / "docs" / "CHANGELOG.md"
    # A fresh [Unreleased] block sits above the new dated section.
    assert new.count("## [Unreleased]") == 1
    assert '## [5.4.0 "Triton"] - 2026-05-01' in new
    # Previous Callisto section still intact.
    assert '## [5.3.0 "Callisto"] - 2026-04-14' in new
    # Order: Unreleased must come before the new dated section.
    assert new.index("## [Unreleased]") < new.index('## [5.4.0 "Triton"]')
    assert new.index('## [5.4.0 "Triton"]') < new.index('## [5.3.0 "Callisto"]')


def test_roll_changelog_refuses_double_cut(script, repo):
    # A section for 5.3.0 already exists in the seed; cutting 5.3.0 again must abort.
    with pytest.raises(SystemExit):
        script._roll_changelog("5.3.0", "Callisto", "2026-04-14")


def test_roll_changelog_requires_unreleased_heading(script, repo):
    (repo / "docs" / "CHANGELOG.md").write_text(
        '# Changelog\n\n## [5.3.0 "Callisto"] - 2026-04-14\n',
        encoding="utf-8",
    )
    with pytest.raises(SystemExit):
        script._roll_changelog("5.4.0", "Triton", "2026-05-01")


# ---------------------------------------------------------------------------
# _update_versioning_doc
# ---------------------------------------------------------------------------


def test_update_versioning_shifts_current_block_and_prepends_history(script, repo):
    path, new = script._update_versioning_doc("5.4.0", "Triton", "2026-05-01")
    assert path == repo / "docs" / "reference" / "versioning.md"
    # New version becomes Current; prior Current/Previous shift down.
    assert '**v5.4.0 "Triton"** - Current stable release' in new
    assert '**v5.3.0 "Callisto"** - Previous stable release' in new
    assert '**v5.2.0 "Ganymede"** - Earlier stable release' in new
    # v4.0.0 "Kepler" falls off the three-slot block.
    assert '**v4.0.0 "Kepler"** - Earlier stable release' not in new
    # A stubbed history entry is inserted right after the heading.
    assert '### v5.4.0 "Triton" (2026-05-01)' in new
    # History entry appears ABOVE the prior 5.3.0 history entry.
    assert new.index('### v5.4.0 "Triton"') < new.index('### v5.3.0 "Callisto"')
    # TODO stubs are present so the operator knows to fill them in.
    assert "TODO" in new


def test_update_versioning_fails_when_current_block_missing(script, repo):
    (repo / "docs" / "reference" / "versioning.md").write_text(
        "# Versioning\n\n## Version History\n\n### v5.3.0\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit):
        script._update_versioning_doc("5.4.0", "Triton", "2026-05-01")


# ---------------------------------------------------------------------------
# _update_readme
# ---------------------------------------------------------------------------


def test_update_readme_replaces_version_line(script, repo):
    path, new = script._update_readme("5.4.0", "Triton")
    assert path == repo / "README.md"
    assert '**Huntable CTI Studio v5.4.0 "Triton"**' in new
    assert '**Huntable CTI Studio v5.3.0 "Callisto"**' not in new


def test_update_readme_fails_when_line_missing(script, repo):
    (repo / "README.md").write_text("# Huntable CTI Studio\n\nJust a readme.\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        script._update_readme("5.4.0", "Triton")


# ---------------------------------------------------------------------------
# End-to-end main(--skip-git)
# ---------------------------------------------------------------------------


def _run_main(script, argv):
    """Invoke script.main() with argv patched; returns exit code."""
    old_argv = sys.argv
    sys.argv = argv
    try:
        try:
            return script.main()
        except SystemExit as exc:
            return exc.code if isinstance(exc.code, int) else 1
    finally:
        sys.argv = old_argv


def test_main_skip_git_applies_all_edits_and_passes_verifier(script, repo, monkeypatch):
    """With --skip-git, main() should:
    - skip _preflight (no git calls)
    - apply all four edits on disk
    - invoke the verifier subprocess and exit 0 when it returns 0
    """
    called = {"verify": 0}

    def fake_run_verifier(tag):
        called["verify"] += 1
        assert tag == "v5.4.0"

    monkeypatch.setattr(script, "_run_verifier", fake_run_verifier)

    rc = _run_main(
        script,
        [
            "release_cut.py",
            "5.4.0",
            "Triton",
            "--summary",
            "SBOM + release automation",
            "--date",
            "2026-05-01",
            "--skip-git",
        ],
    )

    assert rc == 0
    assert called["verify"] == 1

    # All four files were updated on disk.
    assert 'version = "5.4.0"' in (repo / "pyproject.toml").read_text()
    changelog = (repo / "docs" / "CHANGELOG.md").read_text()
    assert '## [5.4.0 "Triton"] - 2026-05-01' in changelog
    versioning = (repo / "docs" / "reference" / "versioning.md").read_text()
    assert '**v5.4.0 "Triton"** - Current stable release' in versioning
    readme = (repo / "README.md").read_text()
    assert '**Huntable CTI Studio v5.4.0 "Triton"**' in readme


# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "version",
    ["5.4", "v5.4.0", "5.4.0-rc.1", "abc"],
)
def test_main_rejects_bad_version(script, repo, version, monkeypatch):
    monkeypatch.setattr(script, "_run_verifier", lambda tag: None)
    rc = _run_main(
        script,
        ["release_cut.py", version, "Triton", "--summary", "x", "--skip-git"],
    )
    assert rc == 1


@pytest.mark.parametrize(
    # Note: the current CODENAME_RE is `^[A-Z][a-zA-Z]+$`, which does accept
    # all-caps like "TRITON". The docstring suggests only an initial cap is
    # intended, but that's a script-side question; tests pin the actual regex.
    "codename",
    ["triton", "Triton2", "Two Words", ""],
)
def test_main_rejects_bad_codename(script, repo, codename, monkeypatch):
    monkeypatch.setattr(script, "_run_verifier", lambda tag: None)
    rc = _run_main(
        script,
        ["release_cut.py", "5.4.0", codename, "--summary", "x", "--skip-git"],
    )
    assert rc == 1


def test_main_rejects_bad_date(script, repo, monkeypatch):
    monkeypatch.setattr(script, "_run_verifier", lambda tag: None)
    rc = _run_main(
        script,
        [
            "release_cut.py",
            "5.4.0",
            "Triton",
            "--summary",
            "x",
            "--date",
            "May 1 2026",
            "--skip-git",
        ],
    )
    assert rc == 1
