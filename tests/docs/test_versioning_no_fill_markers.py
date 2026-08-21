"""Regression guard: release_cut.py stamps a <fill> stub into versioning.md
for every new version, and it has already been forgotten once (v7.7.0).
Fail the build if a stub survives into a committed Version History entry."""

import re
from pathlib import Path

VERSIONING_PATH = Path("docs/reference/versioning.md")
FILL_MARKER_PATTERN = re.compile(r"<fill>|TODO: fill Significance")


def _version_history_section() -> str:
    text = VERSIONING_PATH.read_text(encoding="utf-8")
    start = text.index("## Version History")
    return text[start:]


def test_versioning_has_no_fill_markers():
    section = _version_history_section()
    matches = FILL_MARKER_PATTERN.findall(section)
    assert not matches, (
        f"docs/reference/versioning.md Version History still contains "
        f"unfilled release_cut.py stub marker(s): {matches}. "
        "Fill Named After/Significance/Features from the matching "
        "docs/CHANGELOG.md section before merging to main."
    )


def test_fill_marker_guard_actually_bites(tmp_path):
    """Positive control: prove the guard fires on a reintroduced marker."""
    sample = tmp_path / "versioning.md"
    sample.write_text(
        "## Version History\n\n"
        '### v9.9.9 "Test" (2026-01-01)\n'
        "<!-- TODO: fill Significance and Features before merging to main. -->\n"
        "- **Named After**: <fill>\n"
        "- **Significance**: <fill>\n"
        "- **Features**: <fill>\n",
        encoding="utf-8",
    )
    text = sample.read_text(encoding="utf-8")
    section = text[text.index("## Version History") :]
    assert FILL_MARKER_PATTERN.findall(section)
