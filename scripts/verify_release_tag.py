#!/usr/bin/env python3
"""Verify that a release tag is consistent with pyproject.toml and CHANGELOG.

Invoked in two places:

1. `.github/workflows/release.yml` on tag push (CI guard).
2. `scripts/release_cut.sh` as a pre-flight check before creating the tag.

Checks performed for a tag like `v5.3.0`:

- Tag name matches the canonical format `v<MAJOR>.<MINOR>.<PATCH>`.
- `pyproject.toml` `[project] version` equals the tag version (stripped of `v`).
- `docs/CHANGELOG.md` contains a dated section whose heading starts with
  `## [<version>` and ends with `- YYYY-MM-DD` (codename between brackets
  is allowed and ignored).
- The `## [Unreleased]` section above it is empty (no `###` subsections
  and no bullet-point content).

Exit codes: 0 on success, non-zero with a clear diagnostic on failure.

Usage: verify_release_tag.py v5.3.0 [--repo-root PATH]
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

TAG_RE = re.compile(r"^v(?P<version>\d+\.\d+\.\d+)$")
CHANGELOG_HEADING_RE = re.compile(
    r"^##\s+\[(?P<version>\d+\.\d+\.\d+)(?:\s+\"[^\"]+\")?\]\s+-\s+\d{4}-\d{2}-\d{2}\s*$"
)
UNRELEASED_HEADING_RE = re.compile(r"^##\s+\[Unreleased\]\s*$")
SECTION_BREAK_RE = re.compile(r"^##\s+\[")


def _die(msg: str) -> None:
    print(f"release-tag-verify: FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def _parse_tag(tag: str) -> str:
    match = TAG_RE.match(tag)
    if not match:
        _die(
            f"tag {tag!r} does not match canonical format vMAJOR.MINOR.PATCH "
            "(see AGENTS.md Release tagging convention)"
        )
    return match.group("version")  # type: ignore[union-attr]


def _read_pyproject_version(repo_root: Path) -> str:
    pyproject_path = repo_root / "pyproject.toml"
    if not pyproject_path.is_file():
        _die(f"pyproject.toml not found at {pyproject_path}")
    with pyproject_path.open("rb") as f:
        data = tomllib.load(f)
    try:
        return data["project"]["version"]
    except KeyError:
        _die("pyproject.toml is missing [project].version")
        raise  # unreachable; keeps type checker happy


def _check_changelog(repo_root: Path, version: str) -> None:
    changelog_path = repo_root / "docs" / "CHANGELOG.md"
    if not changelog_path.is_file():
        _die(f"docs/CHANGELOG.md not found at {changelog_path}")

    lines = changelog_path.read_text(encoding="utf-8").splitlines()

    # Find the [Unreleased] heading (must exist; may be empty).
    unreleased_idx = next(
        (i for i, line in enumerate(lines) if UNRELEASED_HEADING_RE.match(line)),
        None,
    )
    if unreleased_idx is None:
        _die("docs/CHANGELOG.md is missing a `## [Unreleased]` heading")
        return  # unreachable

    # Find the version heading. Accept any order but typical layout is
    # [Unreleased] immediately above the new [X.Y.Z] heading.
    version_heading_idx = None
    for i, line in enumerate(lines):
        match = CHANGELOG_HEADING_RE.match(line)
        if match and match.group("version") == version:
            version_heading_idx = i
            break
    if version_heading_idx is None:
        _die(
            f"docs/CHANGELOG.md has no dated section for {version}. "
            f"Expected a heading like `## [{version} \"<codename>\"] - YYYY-MM-DD`"
        )
        return  # unreachable

    # Verify [Unreleased] is empty (no ### subsections and no list content
    # between the Unreleased heading and the next `## [` heading).
    scan_end = len(lines)
    for j in range(unreleased_idx + 1, len(lines)):
        if SECTION_BREAK_RE.match(lines[j]):
            scan_end = j
            break

    unreleased_body = [line.strip() for line in lines[unreleased_idx + 1 : scan_end]]
    non_empty = [line for line in unreleased_body if line]
    if non_empty:
        preview = "\n  ".join(non_empty[:5])
        _die(
            "docs/CHANGELOG.md `## [Unreleased]` section is not empty at release "
            "time. Roll pending entries into the dated version section before "
            f"tagging. First few non-empty lines:\n  {preview}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", help="Release tag to verify, e.g. v5.3.0")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Repo root (defaults to parent of this script)",
    )
    args = parser.parse_args()

    version = _parse_tag(args.tag)
    pyproject_version = _read_pyproject_version(args.repo_root)

    if pyproject_version != version:
        _die(
            f"tag {args.tag} implies version {version}, but pyproject.toml has "
            f"version = {pyproject_version!r}. Bump pyproject.toml before tagging."
        )

    _check_changelog(args.repo_root, version)

    print(f"release-tag-verify: OK: {args.tag} consistent with pyproject and CHANGELOG")
    return 0


if __name__ == "__main__":
    sys.exit(main())
