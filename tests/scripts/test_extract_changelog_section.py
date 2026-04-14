"""Tests for scripts/extract_changelog_section.py.

The script is invoked from `.github/workflows/release.yml` to pipe a
single release section body into `gh release create --notes-file -`.
Its contract:

- stdout: the body between the requested `## [X.Y.Z ...]` heading and
  the next `## [` heading, with leading/trailing blank lines stripped.
- stderr: `codename: <NAME>` (empty string if no codename in heading).
- Exit 0 on success; non-zero with a diagnostic if the section is
  missing, the file is missing, or the body is empty.

These tests guard the heading regex, section-break detection, and the
stderr codename contract (the workflow reads stderr to build the
release title).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "extract_changelog_section.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("extract_changelog_section", SCRIPT_PATH)
    assert spec and spec.loader, f"Cannot load script spec from {SCRIPT_PATH}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script():
    return _load_script_module()


SAMPLE_CHANGELOG = """\
# Changelog

## [Unreleased]

## [5.4.0 "Triton"] - 2026-05-01

### Added
- New feature A
- New feature B

### Fixed
- Bug X

## [5.3.0 "Callisto"] - 2026-04-14

### Added
- Older feature

## [5.2.0] - 2026-03-01

### Changed
- Plain section (no codename)
"""


def _run(script, argv, capsys):
    """Invoke script.main() with argv patched and return (rc, stdout, stderr)."""
    old_argv = sys.argv
    sys.argv = argv
    try:
        rc = script.main()
    finally:
        sys.argv = old_argv
    captured = capsys.readouterr()
    return rc, captured.out, captured.err


def test_extracts_section_with_codename(script, tmp_path, capsys):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(SAMPLE_CHANGELOG, encoding="utf-8")

    rc, out, err = _run(
        script,
        ["extract_changelog_section.py", "5.4.0", "--file", str(changelog)],
        capsys,
    )

    assert rc == 0
    # Body starts and ends trimmed of blank lines.
    assert out.startswith("### Added")
    assert out.rstrip().endswith("- Bug X")
    # Does not bleed into the next section.
    assert "Callisto" not in out
    assert "Older feature" not in out
    # Codename is surfaced on stderr for the workflow.
    assert "codename: Triton" in err


def test_extracts_section_without_codename(script, tmp_path, capsys):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(SAMPLE_CHANGELOG, encoding="utf-8")

    rc, out, err = _run(
        script,
        ["extract_changelog_section.py", "5.2.0", "--file", str(changelog)],
        capsys,
    )

    assert rc == 0
    assert "Plain section (no codename)" in out
    assert "codename: " in err  # empty codename still emitted


def test_last_section_extends_to_end_of_file(script, tmp_path, capsys):
    # 5.2.0 is the last section in SAMPLE_CHANGELOG, so there is no
    # following `## [` break -- body should still extract cleanly.
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(SAMPLE_CHANGELOG, encoding="utf-8")

    rc, out, _ = _run(
        script,
        ["extract_changelog_section.py", "5.2.0", "--file", str(changelog)],
        capsys,
    )

    assert rc == 0
    assert out.rstrip().endswith("Plain section (no codename)")


def test_missing_version_is_rejected(script, tmp_path, capsys):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(SAMPLE_CHANGELOG, encoding="utf-8")

    rc, _out, err = _run(
        script,
        ["extract_changelog_section.py", "9.9.9", "--file", str(changelog)],
        capsys,
    )

    assert rc == 1
    assert "no dated section for 9.9.9" in err


def test_missing_file_is_rejected(script, tmp_path, capsys):
    missing = tmp_path / "nope.md"
    rc, _out, err = _run(
        script,
        ["extract_changelog_section.py", "5.4.0", "--file", str(missing)],
        capsys,
    )

    assert rc == 1
    assert "file not found" in err


def test_empty_body_is_rejected(script, tmp_path, capsys):
    # Heading present but no body content before next `## [` break.
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        '# Changelog\n\n## [5.0.0 "Io"] - 2026-01-01\n\n## [4.9.0] - 2025-12-01\n\nsomething\n',
        encoding="utf-8",
    )

    rc, _out, err = _run(
        script,
        ["extract_changelog_section.py", "5.0.0", "--file", str(changelog)],
        capsys,
    )

    assert rc == 1
    assert "no body" in err


def test_unreleased_heading_is_not_matched(script, tmp_path, capsys):
    # The `## [Unreleased]` heading has no date and must not be picked
    # up when someone asks for version "Unreleased".
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(SAMPLE_CHANGELOG, encoding="utf-8")

    rc, _out, err = _run(
        script,
        ["extract_changelog_section.py", "Unreleased", "--file", str(changelog)],
        capsys,
    )

    assert rc == 1
    assert "no dated section" in err
