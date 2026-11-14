#!/usr/bin/env python3
"""One-time migration of an existing Huntable-SIGMA-Rules checkout to the rule layout.

Dry run by default: prints every old -> new path, the emerging-threat rules that resolve
to no family (_unsorted), every metadata change, and what still needs a human. Nothing is
written.

``--apply`` (refuses on a dirty tree, an unmapped logsource, or a path collision):

1. creates ``--branch`` from the current HEAD,
2. commit 1: ``git mv`` every rule to its layout path and removes the now-empty platform
   placeholder directories (``rules/<platform>/.gitkeep``),
3. commit 2: the metadata fixes (author, YYYY-MM-DD dates, tag syntax, leftover keys).

It never pushes, and never changes ``id``, ``title``, ``logsource`` or ``detection``: the
normalizer edits other top-level blocks only and refuses any edit that would alter them.

Directories come from the same table CTI Studio publishes with: the repository's
``.huntable/rule-layout.yml`` when present, else ``config/sigma_rule_layout.yml``.

Author: rules recorded as ``source_provided`` in the CTI Studio queue (matched by rule id)
keep their author. Without queue provenance, a missing author or a known internal
variant gets the configured author; any other author is treated as a publisher's.

Usage:
    python scripts/migrate_sigma_repo_layout.py [--repo PATH] [--report report.md]
    python scripts/migrate_sigma_repo_layout.py --apply --branch chore/rule-layout-migration
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path, PurePosixPath

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.services.sigma_publish_layout import (  # noqa: E402
    RuleLayoutError,
    RulePlacement,
    assign_filenames,
    load_rule_layout,
    place_rule,
    resolve_family,
)
from src.services.sigma_publish_normalizer import SOURCE_ORIGIN, normalize_rule_yaml  # noqa: E402

DEFAULT_AUTHOR = "Huntable CTI Studio"
# Author strings CTI Studio (or its earlier prompts and users) wrote on generated rules.
INTERNAL_AUTHORS = frozenset(
    {
        "Huntable CTI Studio",
        "Huntable CTI Studio User",
        "Huntable",
        "Huntable CTI Studio - Andrew Skatoff",
        "Cybersecurity Detection Engineer",
    }
)
PLATFORM_PLACEHOLDERS = ("cloud", "linux", "macos", "network", "web", "windows")
COMMIT_TRAILER = "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"


@dataclass
class RulePlan:
    old: PurePosixPath
    sigma_id: str | None
    title: str | None
    description: str | None = None
    origin: str = "generated"
    origin_basis: str = ""
    family_basis: str = ""
    date_basis: str = ""
    new: PurePosixPath | None = None
    placement: RulePlacement | None = None
    new_yaml: str | None = None
    changes: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)  # block --apply

    @property
    def moved(self) -> bool:
        return self.new is not None and self.new != self.old


def _git(repo: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
    if check and result.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def _database_url() -> str | None:
    url = os.getenv("DATABASE_URL")
    if url:
        return url.replace("postgresql+asyncpg://", "postgresql://")
    try:
        from dotenv import dotenv_values

        env = dotenv_values(Path(__file__).resolve().parent.parent / ".env")
    except ImportError:
        return None
    password = env.get("POSTGRES_PASSWORD")
    if not password:
        return None
    user = env.get("POSTGRES_USER") or "cti_user"
    name = env.get("POSTGRES_DB") or "cti_scraper"
    return f"postgresql://{user}:{password}@localhost:5432/{name}"


def first_commit_date(repo: Path, rel: PurePosixPath) -> date | None:
    """Date the file first entered the repository (author date), following renames."""
    out = _git(repo, "log", "--follow", "--diff-filter=A", "--format=%as", "--", str(rel), check=False).split()
    try:
        return date.fromisoformat(out[-1]) if out else None
    except ValueError:
        return None


def queue_provenance(url: str) -> dict[str, tuple[str, str | None]]:
    """Sigma id -> (rule_origin, attribution) for every queue row, read-only."""
    from sqlalchemy import create_engine, text

    engine = create_engine(url)
    provenance: dict[str, tuple[str, str | None]] = {}
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT rule_yaml, rule_origin, attribution FROM sigma_rule_queue ORDER BY id"))
        for rule_yaml, origin, attribution in rows:
            match = re.search(r"^id:\s*['\"]?([0-9A-Za-z-]+)", rule_yaml or "", re.MULTILINE)
            if match:
                current = provenance.get(match.group(1))
                # A publisher row wins over a generated copy of the same rule.
                if current is None or origin == SOURCE_ORIGIN:
                    provenance[match.group(1)] = (origin or "generated", attribution)
    engine.dispose()
    return provenance


def build_plan(
    repo: Path, *, author: str, today: date, provenance: dict[str, tuple[str, str | None]] | None
) -> tuple[list[RulePlan], object]:
    layout = load_rule_layout(repo)
    plans: list[RulePlan] = []
    placements: dict[str, RulePlacement] = {}
    by_id: dict[str, RulePlan] = {}
    files = []
    for root in layout.roots:
        base = repo / root
        if base.is_dir():
            files.extend(sorted(p for p in base.rglob("*") if p.suffix in (".yml", ".yaml")))
    for path in files:
        text = path.read_text(encoding="utf-8")
        rel = PurePosixPath(path.relative_to(repo).as_posix())
        try:
            doc = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            plans.append(RulePlan(rel, None, None, errors=[f"YAML does not parse: {exc}"]))
            continue
        if not isinstance(doc, dict):
            plans.append(RulePlan(rel, None, None, errors=["not a single rule mapping"]))
            continue
        sigma_id = str(doc.get("id")) if doc.get("id") else None
        plan = RulePlan(rel, sigma_id, doc.get("title"), doc.get("description"))
        plans.append(plan)
        if provenance is not None and sigma_id in provenance:
            plan.origin, attribution = provenance[sigma_id]
            plan.origin_basis = f"queue: {plan.origin}"
        else:
            attribution = None
            current = str(doc.get("author") or "").strip()
            if current and current not in INTERNAL_AUTHORS:
                plan.origin, plan.origin_basis = SOURCE_ORIGIN, "no queue row; non-internal author kept"
            else:
                plan.origin_basis = "no queue row; internal or missing author"
        # A rule with no date gets the day it was first committed here, not today.
        fill_date = today
        if doc.get("date") in (None, ""):
            committed = first_commit_date(repo, rel)
            fill_date = committed or today
            plan.date_basis = "first commit" if committed else "today (no commit history)"
        result = normalize_rule_yaml(
            text,
            origin=plan.origin,
            canonical_author=author,
            attribution=attribution or (str(doc.get("author")) if doc.get("author") else None),
            today=fill_date,
            first_publish=False,
            edit_date=today,
        )
        plan.changes, plan.problems = result.changes, result.problems
        plan.new_yaml = result.rule_yaml if result.changed else None
        if path.suffix == ".yaml":
            plan.errors.append("uses the .yaml extension")
        if not sigma_id:
            plan.errors.append("rule has no id")
            continue
        if sigma_id in by_id:
            plan.errors.append(f"id {sigma_id} also used by {by_id[sigma_id].old}")
            continue
        by_id[sigma_id] = plan
        try:
            plan.placement = place_rule(result.rule or doc, layout)
        except RuleLayoutError as exc:
            plan.errors.append(str(exc))
            continue
        placements[sigma_id] = plan.placement
        if plan.placement.family:
            title_family = resolve_family(plan.title, None, layout)
            plan.family_basis = "title" if title_family == plan.placement.family else "description"
    # Every file is being re-placed, so collisions are resolved within the batch.
    for sigma_id, new_path in assign_filenames(placements, {}).items():
        by_id[sigma_id].new = new_path
    return plans, layout


def _md(value: object) -> str:
    return str(value).replace("|", "\\|")


def render_report(plans: list[RulePlan], layout, repo: Path) -> str:
    moved = [p for p in plans if p.moved]
    unsorted = [p for p in plans if p.placement is not None and p.placement.unsorted]
    collisions = [p for p in plans if p.new is not None and p.placement and p.new.name != f"{p.placement.slug}.yml"]
    changed = [p for p in plans if p.changes]
    problems = [p for p in plans if p.problems]
    errors = [p for p in plans if p.errors]
    out = [
        "# Sigma repository layout migration (dry run)",
        "",
        f"Repository: `{repo}`  ",
        f"Layout table: `{layout.source}`",
        "",
        "| | count |",
        "|---|---|",
        f"| rules scanned | {len(plans)} |",
        f"| moved | {len(moved)} |",
        f"| already in place | {len(plans) - len(moved) - len(errors)} |",
        f"| emerging-threat rules in `_unsorted` | {len(unsorted)} |",
        f"| filename collisions (id suffix applied) | {len(collisions)} |",
        f"| unmapped / unplaceable (blocks --apply) | {len(errors)} |",
        f"| rules with metadata changes | {len(changed)} |",
        f"| rules still needing a manual fix | {len(problems)} |",
        "",
        "## Moves (old -> new)",
        "",
        "| old | new |",
        "|---|---|",
    ]
    out += [f"| `{_md(p.old)}` | `{_md(p.new)}` |" for p in sorted(plans, key=lambda p: str(p.new or p.old)) if p.new]
    out += ["", f"## `_unsorted` emerging-threat rules ({len(unsorted)}) -- assign a family", ""]
    out += ["| new path | title | id |", "|---|---|---|"]
    out += [f"| `{_md(p.new)}` | {_md(p.title)} | `{p.sigma_id}` |" for p in unsorted]
    out += [
        "",
        "## Family assignments (from the alias table)",
        "",
        "`description` means the title names no family and the alias matched in the description: review those.",
        "",
        "| family | matched in | title |",
        "|---|---|---|",
    ]
    resolved = [p for p in plans if p.placement is not None and p.placement.family]
    resolved.sort(key=lambda p: (p.placement.family, p.family_basis != "title", str(p.title)))
    out += [f"| `{p.placement.family}` | {p.family_basis} | {_md(p.title)} |" for p in resolved]
    out += ["", "## Metadata changes", ""]
    for p in changed:
        basis = p.origin_basis + (f"; date from {p.date_basis}" if p.date_basis else "")
        out.append(f"- `{_md(p.new or p.old)}` ({basis})")
        out += [f"  - {_md(c)}" for c in p.changes]
    out += ["", "## Needs a manual fix (CI will fail until resolved)", ""]
    for p in problems:
        out.append(f"- `{_md(p.new or p.old)}` ({_md(p.title)}): {_md('; '.join(p.problems))}")
    if not problems:
        out.append("None.")
    out += ["", "## Blocking errors", ""]
    for p in errors:
        out.append(f"- `{_md(p.old)}`: {_md('; '.join(p.errors))}")
    if not errors:
        out.append("None: every rule has a mapped logsource and a unique target path.")
    return "\n".join(out) + "\n"


def apply_plan(repo: Path, plans: list[RulePlan], branch: str, layout) -> None:
    if any(p.errors for p in plans):
        raise SystemExit("Refusing --apply: resolve the blocking errors in the dry-run report first.")
    targets = [p.new for p in plans if p.new]
    if len(targets) != len(set(targets)):
        raise SystemExit("Refusing --apply: two rules map to the same path.")
    if _git(repo, "status", "--porcelain").strip():
        raise SystemExit("Refusing --apply: the rules repository has uncommitted changes.")
    _git(repo, "checkout", "-b", branch)

    for p in plans:
        if p.moved:
            (repo / p.new).parent.mkdir(parents=True, exist_ok=True)
            _git(repo, "mv", str(p.old), str(p.new))
    generic_root = repo / layout.generic_root
    for platform in PLATFORM_PLACEHOLDERS:
        keep = generic_root / platform / ".gitkeep"
        if keep.exists() and not any(f.suffix == ".yml" for f in keep.parent.rglob("*.yml")):
            _git(repo, "rm", "-q", str(keep.relative_to(repo)))
    moved = sum(p.moved for p in plans)
    _git(
        repo,
        "commit",
        "-q",
        "-m",
        "chore(rules): move rules into the SigmaHQ-style layout",
        "-m",
        f"git mv only ({moved} renames, no content changes). Generic rules go to "
        "rules/<logsource dir>/, emerging-threat rules to rules-emerging-threats/<family>/, "
        "per .huntable/rule-layout.yml. Empty platform placeholder directories are removed.",
        "-m",
        COMMIT_TRAILER,
    )

    edited = 0
    for p in plans:
        if p.new_yaml is not None:
            (repo / (p.new or p.old)).write_text(p.new_yaml, encoding="utf-8")
            _git(repo, "add", str(p.new or p.old))
            edited += 1
    if edited:
        _git(
            repo,
            "commit",
            "-q",
            "-m",
            "chore(rules): normalize rule metadata",
            "-m",
            f"{edited} rules: configured author on generated rules (publisher authors kept), "
            "YYYY-MM-DD dates, attack.* tags with hyphens, unknown tag namespaces and "
            "non-Sigma keys removed. id, title, logsource and detection are unchanged.",
            "-m",
            COMMIT_TRAILER,
        )
    print(f"Applied on branch {branch}: {moved} moves, {edited} metadata edits. Nothing was pushed.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo", default=os.getenv("SIGMA_REPO_PATH") or "../Huntable-SIGMA-Rules")
    parser.add_argument("--apply", action="store_true", help="make the two commits (default: dry run)")
    parser.add_argument("--branch", default=f"chore/rule-layout-migration-{date.today():%Y%m%d}")
    parser.add_argument("--author", default=DEFAULT_AUTHOR, help="configured author for generated rules")
    parser.add_argument("--today", type=date.fromisoformat, default=date.today(), help="date for rules with none")
    parser.add_argument("--no-db", action="store_true", help="skip the CTI Studio queue provenance lookup")
    parser.add_argument("--report", type=Path, help="also write the dry-run report to this file")
    args = parser.parse_args(argv)

    repo = Path(args.repo).expanduser().resolve()
    if not (repo / ".git").exists():
        raise SystemExit(f"{repo} is not a git checkout")
    provenance = None
    if not args.no_db:
        url = _database_url()
        if url:
            try:
                provenance = queue_provenance(url)
            except Exception as exc:  # noqa: BLE001 - provenance is optional; say so and continue
                print(f"warning: queue provenance unavailable ({type(exc).__name__}); using author heuristic")
        else:
            print("warning: no DATABASE_URL/POSTGRES_PASSWORD; using author heuristic")

    plans, layout = build_plan(repo, author=args.author, today=args.today, provenance=provenance)
    report = render_report(plans, layout, repo)
    if provenance is not None:
        report = report.replace("(dry run)", f"(dry run, queue provenance for {len(provenance)} rule ids)", 1)
    print(report)
    if args.report:
        args.report.write_text(report, encoding="utf-8")
    if args.apply:
        apply_plan(repo, plans, args.branch, layout)
    return 1 if any(p.errors for p in plans) else 0


if __name__ == "__main__":
    sys.exit(main())
