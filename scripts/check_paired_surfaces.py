#!/usr/bin/env python3
"""Fail a PR when one side of a paired surface changes without the other.

Two pairs in this repo have no runtime error when they drift, only a later
silent failure:

1. ``src/database/models.py`` -> a ``scripts/migrate_*.py``. Migrations are
   never auto-applied; the runtime falls back silently, so a schema change
   without a migration ships an inert fix. Escape label when a models.py edit
   genuinely needs no migration (a comment, a relationship flag):
   ``no-migration-needed``.
2. ``src/prompts/**`` or ``src/config/workflow_config_schema.py`` ->
   ``config/presets/**``. The validator and runtime never read the prompt
   files; the quickstart presets are a separate sink and must move with them.
   Escape label: ``no-preset-sync-needed``.

Usage (CI, pull_request only):
    check_paired_surfaces.py --base origin/<base_ref> --head HEAD --labels "a,b"

Exit 0 when no pair is violated, 1 on violations, 2 on a git failure.
"""

from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
from collections.abc import Iterable

LABEL_NO_MIGRATION = "no-migration-needed"
LABEL_NO_PRESET_SYNC = "no-preset-sync-needed"

# (trigger globs, satisfying globs, escape label, message)
PAIRS: tuple[tuple[tuple[str, ...], tuple[str, ...], str, str], ...] = (
    (
        ("src/database/models.py",),
        ("scripts/migrate_*.py",),
        LABEL_NO_MIGRATION,
        "src/database/models.py changed but no scripts/migrate_*.py did. "
        "Migrations are never auto-applied -- add one, or label the PR "
        f"'{LABEL_NO_MIGRATION}' if this edit truly needs none.",
    ),
    (
        ("src/prompts/*", "src/prompts/**/*", "src/config/workflow_config_schema.py"),
        ("config/presets/*", "config/presets/**/*"),
        LABEL_NO_PRESET_SYNC,
        "src/prompts/ or workflow_config_schema.py changed but nothing under "
        "config/presets/ did. Presets are a separate sink the runtime reads "
        f"instead of the prompt files -- update them, or label the PR '{LABEL_NO_PRESET_SYNC}'.",
    ),
)


def _matches(path: str, globs: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(path, g) for g in globs)


def find_violations(changed_files: Iterable[str], labels: Iterable[str] = ()) -> list[str]:
    """Return one message per violated pair. Pure; no git access."""
    changed = [p.strip() for p in changed_files if p.strip()]
    label_set = {label.strip() for label in labels if label.strip()}
    violations = []
    for triggers, satisfiers, escape_label, message in PAIRS:
        if escape_label in label_set:
            continue
        if not any(_matches(p, triggers) for p in changed):
            continue
        if any(_matches(p, satisfiers) for p in changed):
            continue
        violations.append(message)
    return violations


def changed_files_between(base: str, head: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", required=True, help="base ref, e.g. origin/europa-dev")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--labels", default="", help="comma-separated PR labels")
    args = parser.parse_args(argv)

    try:
        changed = changed_files_between(args.base, args.head)
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: git diff failed: {exc.stderr.strip()}", file=sys.stderr)
        return 2

    violations = find_violations(changed, args.labels.split(","))
    if violations:
        print("ERROR: paired-surface check failed:")
        for message in violations:
            print(f"  - {message}")
        return 1
    print(f"Paired surfaces consistent ({len(changed)} changed files).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
