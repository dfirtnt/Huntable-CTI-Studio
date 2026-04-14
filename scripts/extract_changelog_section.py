#!/usr/bin/env python3
"""Print the body of a single dated CHANGELOG section to stdout.

Used by `.github/workflows/release.yml` to pipe release notes into
`gh release create --notes-file -`. The body is everything between the
requested `## [X.Y.Z ...]` heading and the next `## [` heading,
stripped of leading/trailing blank lines.

Also prints the codename (when present in the heading) to stderr as
`codename: <NAME>` so the workflow can use it in the release title.

Usage: extract_changelog_section.py 5.3.0 [--file docs/CHANGELOG.md]

Exits non-zero if the section is missing.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

HEADING_RE = re.compile(
    r"^##\s+\[(?P<version>\d+\.\d+\.\d+)(?:\s+\"(?P<codename>[^\"]+)\")?\]"
    r"\s+-\s+\d{4}-\d{2}-\d{2}\s*$"
)
SECTION_BREAK_RE = re.compile(r"^##\s+\[")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="Version to extract, e.g. 5.3.0")
    parser.add_argument(
        "--file",
        type=Path,
        default=REPO_ROOT / "docs" / "CHANGELOG.md",
        help="Path to CHANGELOG (defaults to docs/CHANGELOG.md)",
    )
    args = parser.parse_args()

    if not args.file.is_file():
        print(f"extract-changelog: FAIL: file not found: {args.file}", file=sys.stderr)
        return 1

    lines = args.file.read_text(encoding="utf-8").splitlines()

    start_idx = None
    codename = ""
    for i, line in enumerate(lines):
        match = HEADING_RE.match(line)
        if match and match.group("version") == args.version:
            start_idx = i
            codename = match.group("codename") or ""
            break

    if start_idx is None:
        print(
            f"extract-changelog: FAIL: no dated section for {args.version} in {args.file}",
            file=sys.stderr,
        )
        return 1

    end_idx = len(lines)
    for j in range(start_idx + 1, len(lines)):
        if SECTION_BREAK_RE.match(lines[j]):
            end_idx = j
            break

    body = "\n".join(lines[start_idx + 1 : end_idx]).strip()
    if not body:
        print(
            f"extract-changelog: FAIL: section {args.version} has no body",
            file=sys.stderr,
        )
        return 1

    print(f"codename: {codename}", file=sys.stderr)
    print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
