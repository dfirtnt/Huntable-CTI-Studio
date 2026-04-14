#!/usr/bin/env python3
"""Atomically cut a release on dev-io.

Performs every repo-local step of a release in a single commit, then creates
the annotated tag. Does NOT push. Deliberate: the operator must still run
the unlock / merge / lock dance documented in AGENTS.md to move the tag to
main and relock the branch.

Pipeline (all-or-nothing: either every file is updated or none are):

1. Preflight checks
   - Currently on the `dev-io` branch.
   - Working tree clean (no staged or unstaged changes).
   - `dev-io` is up to date with origin (no unpushed/unpulled commits).
   - `git` and `python3` available.

2. Compute edits (in memory, no writes yet)
   - `pyproject.toml`: bump `[project] version`.
   - `docs/CHANGELOG.md`: rename `## [Unreleased]` to the dated section,
     insert a fresh empty `## [Unreleased]` above it.
   - `docs/reference/versioning.md`: shift Current / Previous / Earlier
     labels and insert a history entry.
   - `README.md`: replace the `Huntable CTI Studio vX.Y.Z "Codename"` line.

3. Pre-flight verifier
   - Write the edits to disk.
   - Run `scripts/verify_release_tag.py vX.Y.Z`. If it fails, the operator
     gets the exact diagnostic and can fix up or `git restore`.

4. Commit + tag
   - `git add` the edited files only (never `git add -A`).
   - Commit message: `release: vX.Y.Z "Codename"`.
   - Annotated tag `vX.Y.Z` with a one-line summary.

5. Stops before push.

Usage:
    scripts/release_cut.py 5.4.0 Triton --summary "SBOM + release automation"

Example output (success):
    release-cut: bumped pyproject.toml 5.3.0 -> 5.4.0
    release-cut: rolled docs/CHANGELOG.md
    release-cut: updated docs/reference/versioning.md
    release-cut: updated README.md
    release-tag-verify: OK: v5.4.0 consistent with pyproject and CHANGELOG
    release-cut: committed as <sha> and tagged v5.4.0
    release-cut: DONE. Next steps:
      scripts/release_unlock.sh
      git push origin dev-io
      # open PR: dev-io -> main; merge after CI green
      git push origin v5.4.0
      scripts/release_lock.sh
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
CODENAME_RE = re.compile(r"^[A-Z][a-zA-Z]+$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _die(msg: str) -> None:
    print(f"release-cut: FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def _run(cmd: list[str], capture: bool = True) -> str:
    result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=capture, text=True)
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        _die(f"command {' '.join(cmd)!r} failed: {stderr}")
    return (result.stdout or "").strip()


def _preflight() -> None:
    branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if branch != "dev-io":
        _die(f"must be on dev-io (currently on {branch!r})")

    status = _run(["git", "status", "--porcelain"])
    if status:
        _die(
            "working tree is not clean. Commit, stash, or restore pending "
            f"changes before cutting a release. Current status:\n{status}"
        )

    # Fetch just origin/dev-io so we can compare without side effects on refs.
    _run(["git", "fetch", "origin", "dev-io"])
    local = _run(["git", "rev-parse", "HEAD"])
    remote = _run(["git", "rev-parse", "FETCH_HEAD"])
    if local != remote:
        _die(
            "dev-io is not in sync with origin/dev-io. Pull or push before "
            "cutting a release."
        )


def _bump_pyproject(version: str) -> tuple[Path, str]:
    """Compute new content for pyproject.toml. Returns (path, new_content)."""
    path = REPO_ROOT / "pyproject.toml"
    original = path.read_text(encoding="utf-8")

    # Only the first `version = "..."` under [project] is the package version.
    # Match it narrowly to avoid touching `requires-python` or similar keys.
    pattern = re.compile(
        r'^(version\s*=\s*)"[^"]+"',
        re.MULTILINE,
    )
    new, count = pattern.subn(f'\\1"{version}"', original, count=1)
    if count != 1:
        _die("could not find a single `version = \"...\"` line in pyproject.toml")
    return path, new


def _roll_changelog(version: str, codename: str, date: str) -> tuple[Path, str]:
    path = REPO_ROOT / "docs" / "CHANGELOG.md"
    original = path.read_text(encoding="utf-8")

    # Ensure a [X.Y.Z ...] section for this version does not already exist.
    existing = re.search(
        rf"^##\s+\[{re.escape(version)}[\s\"\]]",
        original,
        re.MULTILINE,
    )
    if existing:
        _die(
            f"docs/CHANGELOG.md already has a section for {version}; "
            "refusing to double-cut."
        )

    # Find the first `## [Unreleased]` heading (the live one at the top).
    heading_re = re.compile(r"^##\s+\[Unreleased\]\s*$", re.MULTILINE)
    match = heading_re.search(original)
    if not match:
        _die("docs/CHANGELOG.md is missing a `## [Unreleased]` heading")
        return  # type: ignore[return-value]

    insertion = f'## [Unreleased]\n\n## [{version} "{codename}"] - {date}'
    new = original[: match.start()] + insertion + original[match.end() :]
    return path, new


def _update_versioning_doc(version: str, codename: str, date: str) -> tuple[Path, str]:
    path = REPO_ROOT / "docs" / "reference" / "versioning.md"
    original = path.read_text(encoding="utf-8")

    # Shift the Current / Previous / Earlier block. Accept any existing
    # version strings; we just rewrite the three lines.
    current_block_re = re.compile(
        r"## Current Version\n\n"
        r"\*\*v(?P<cur>\S+)\s+\"(?P<cur_cn>[^\"]+)\"\*\*.*stable release\n"
        r"\*\*v(?P<prev>\S+)\s+\"(?P<prev_cn>[^\"]+)\"\*\*.*stable release\n"
        r"\*\*v(?P<earlier>\S+)\s+\"(?P<earlier_cn>[^\"]+)\"\*\*.*stable release",
        re.MULTILINE,
    )
    match = current_block_re.search(original)
    if not match:
        _die("could not locate the Current Version block in docs/reference/versioning.md")
        return  # type: ignore[return-value]

    new_block = (
        f"## Current Version\n\n"
        f'**v{version} "{codename}"** - Current stable release\n'
        f'**v{match.group("cur")} "{match.group("cur_cn")}"** - Previous stable release\n'
        f'**v{match.group("prev")} "{match.group("prev_cn")}"** - Earlier stable release'
    )
    new = original[: match.start()] + new_block + original[match.end() :]

    # Insert a Version History entry right after `## Version History`. The
    # body is stubbed with a TODO so the operator knows to fill it in before
    # merging.
    history_re = re.compile(r"^## Version History\n\n", re.MULTILINE)
    history_match = history_re.search(new)
    if not history_match:
        _die("could not locate `## Version History` heading in versioning.md")
        return  # type: ignore[return-value]

    history_entry = (
        f'### v{version} "{codename}" ({date})\n'
        f"<!-- TODO: fill Significance and Features before merging to main; "
        f"pull content from docs/CHANGELOG.md [{version}] section. -->\n"
        f"- **Named After**: <fill>\n"
        f"- **Significance**: <fill>\n"
        f"- **Features**: <fill>\n\n"
    )
    insert_at = history_match.end()
    new = new[:insert_at] + history_entry + new[insert_at:]
    return path, new


def _update_readme(version: str, codename: str) -> tuple[Path, str]:
    path = REPO_ROOT / "README.md"
    original = path.read_text(encoding="utf-8")

    pattern = re.compile(
        r'\*\*Huntable CTI Studio v\d+\.\d+\.\d+\s+"[^"]+"\*\*',
    )
    replacement = f'**Huntable CTI Studio v{version} "{codename}"**'
    new, count = pattern.subn(replacement, original, count=1)
    if count != 1:
        _die(
            "could not locate the `**Huntable CTI Studio vX.Y.Z \"Codename\"**` "
            "line in README.md"
        )
    return path, new


def _apply_edits(edits: list[tuple[Path, str]]) -> None:
    for path, content in edits:
        path.write_text(content, encoding="utf-8")
        rel = path.relative_to(REPO_ROOT)
        print(f"release-cut: wrote {rel}")


def _run_verifier(tag: str) -> None:
    script = REPO_ROOT / "scripts" / "verify_release_tag.py"
    result = subprocess.run(
        ["python3", str(script), tag],
        cwd=REPO_ROOT,
        capture_output=False,
    )
    if result.returncode != 0:
        _die(
            f"verify_release_tag.py rejected {tag}. Edits are on disk; "
            "`git diff` to review, `git restore` to back out."
        )


def _commit_and_tag(version: str, codename: str, summary: str, edited_paths: list[Path]) -> None:
    rel_paths = [str(p.relative_to(REPO_ROOT)) for p in edited_paths]
    _run(["git", "add", "--", *rel_paths])

    commit_msg = f'release: v{version} "{codename}"'
    _run(["git", "commit", "-m", commit_msg])

    sha = _run(["git", "rev-parse", "HEAD"])
    tag = f"v{version}"
    tag_msg = f'{codename} ({version[: version.rindex(".")]} line) -- {summary}'
    _run(["git", "tag", "-a", tag, "-m", tag_msg])

    print(f"release-cut: committed as {sha[:12]} and tagged {tag}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("version", help="New version, e.g. 5.4.0 (no leading v)")
    parser.add_argument("codename", help="Codename, e.g. Triton (CapitalizedOneWord)")
    parser.add_argument(
        "--summary",
        required=True,
        help="One-line summary for the annotated tag message",
    )
    parser.add_argument(
        "--date",
        default=dt.date.today().isoformat(),
        help="Release date (YYYY-MM-DD). Defaults to today.",
    )
    parser.add_argument(
        "--skip-git",
        action="store_true",
        help="Apply file edits only; skip preflight, commit, and tag. For testing.",
    )
    args = parser.parse_args()

    if not VERSION_RE.match(args.version):
        _die(f"invalid version {args.version!r}; expected MAJOR.MINOR.PATCH")
    if not CODENAME_RE.match(args.codename):
        _die(
            f"invalid codename {args.codename!r}; expected a single "
            "capitalized word (e.g. Triton, Ganymede)"
        )
    if not DATE_RE.match(args.date):
        _die(f"invalid --date {args.date!r}; expected YYYY-MM-DD")

    if not args.skip_git:
        _preflight()

    edits: list[tuple[Path, str]] = [
        _bump_pyproject(args.version),
        _roll_changelog(args.version, args.codename, args.date),
        _update_versioning_doc(args.version, args.codename, args.date),
        _update_readme(args.version, args.codename),
    ]
    _apply_edits(edits)

    tag = f"v{args.version}"
    _run_verifier(tag)

    if args.skip_git:
        print("release-cut: --skip-git set; leaving edits on disk without commit/tag")
        return 0

    edited_paths = [path for path, _ in edits]
    _commit_and_tag(args.version, args.codename, args.summary, edited_paths)

    print("release-cut: DONE. Next steps:")
    print("  scripts/release_unlock.sh")
    print("  git push origin dev-io")
    print("  # open PR: dev-io -> main; merge after CI green")
    print(f"  git push origin {tag}")
    print("  scripts/release_lock.sh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
