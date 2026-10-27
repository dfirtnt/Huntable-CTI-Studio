#!/usr/bin/env python3
"""Fail on rules that break the repository's layout and metadata conventions.

Vendored into Huntable-SIGMA-Rules as scripts/check_rule_layout.py. The canonical copy
lives in Huntable CTI Studio (scripts/sigma_repo_ci/check_rule_layout.py), where a test
keeps its slug and directory logic identical to the publisher's. Directory mapping is
read from .huntable/rule-layout.yml, the same table CTI Studio publishes with.

Checks, per rule:

- filename == slug(title).yml, or slug(title)_<first 8 id chars>.yml after a collision
- generic rules (no detection.emerging-threats tag) sit in rules/<logsource dir>/
- emerging-threat rules sit in rules-emerging-threats/<family>/ (a lowercase-hyphen
  slug, or _unsorted); the family is a reviewer's call, so any valid slug passes
- date (and modified, when present) are YYYY-MM-DD
- tags use a known namespace; attack.* tags are lowercase with hyphens
- title, id, author, date, references, falsepositives and tags are present and non-empty

Usage: check_rule_layout.py [repo root]   (default: current directory)
"""

from __future__ import annotations

import datetime as dt
import pathlib
import re
import sys
import unicodedata

import yaml

LAYOUT_FILE = pathlib.Path(".huntable") / "rule-layout.yml"
EMERGING_THREATS_TAG = "detection.emerging-threats"
MAX_SLUG_LENGTH = 90
COLLISION_SUFFIX_LENGTH = 8
TAG_NAMESPACES = {"attack", "car", "cve", "d3fend", "detection", "stp", "tlp"}
REQUIRED = ("title", "id", "author", "date", "references", "falsepositives", "tags")

_ATTACK_TECHNIQUE_ID = re.compile(r"\bt\d{4}(?:\.\d{3})?\b", re.IGNORECASE)
_NON_SLUG = re.compile(r"[^a-z0-9]+")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ATTACK_TAG = re.compile(r"^attack\.(?:t\d{4}(?:\.\d{3})?|[gs]\d{4}|ta\d{4}|[a-z]+(?:-[a-z]+)*)$")
_CVE_TAG = re.compile(r"^cve\.\d{4}-\d+$")
_FAMILY = re.compile(r"^(?:_unsorted|[a-z0-9]+(?:-[a-z0-9]+)*)$")


def slugify_title(title: str) -> str:
    text = unicodedata.normalize("NFKD", str(title or "")).encode("ascii", "ignore").decode("ascii")
    text = _ATTACK_TECHNIQUE_ID.sub(" ", text.lower())
    slug = _NON_SLUG.sub("_", text).strip("_")
    if len(slug) > MAX_SLUG_LENGTH:
        cut = slug[: MAX_SLUG_LENGTH + 1]
        slug = cut[: cut.rfind("_")] if "_" in cut else slug[:MAX_SLUG_LENGTH]
    return slug or "untitled_rule"


def allowed_filenames(title: str, rule_id: str) -> set[str]:
    slug = slugify_title(title)
    suffix = re.sub(r"[^a-z0-9]", "", str(rule_id).lower())[:COLLISION_SUFFIX_LENGTH]
    base = slug[: MAX_SLUG_LENGTH - COLLISION_SUFFIX_LENGTH - 1].rstrip("_")
    return {f"{slug}.yml", f"{base}_{suffix}.yml"}


def _norm(value):
    if value is None:
        return None
    text = str(value).strip().lower()
    return text or None


def load_layout(root: pathlib.Path) -> dict:
    data = yaml.safe_load((root / LAYOUT_FILE).read_text(encoding="utf-8"))
    dirs = {}
    for entry in data.get("logsource_dirs") or []:
        key = (_norm(entry.get("product")), _norm(entry.get("category")), _norm(entry.get("service")))
        dirs[key] = str(entry["dir"]).strip().strip("/")
    return {
        "generic_root": data.get("generic_root") or "rules",
        "emerging_threats_root": data.get("emerging_threats_root") or "rules-emerging-threats",
        "dirs": dirs,
    }


def logsource_dir(logsource, layout: dict) -> str | None:
    if not isinstance(logsource, dict):
        return None
    product, category, service = (_norm(logsource.get(k)) for k in ("product", "category", "service"))
    candidates = [(product, category, service)]
    if category:
        candidates.append((product, category, None))
        if product:
            candidates.append((None, category, None))
    elif service:
        candidates.append((product, None, service))
    for key in candidates:
        if key in layout["dirs"]:
            return layout["dirs"][key]
    return None


def _is_date(value) -> bool:
    if isinstance(value, dt.date):
        return True
    return isinstance(value, str) and bool(_ISO_DATE.match(value.strip()))


def _tag_error(tag) -> str | None:
    if not isinstance(tag, str):
        return f"tag {tag!r} is not a string"
    namespace, sep, name = tag.partition(".")
    if not sep or not name or namespace not in TAG_NAMESPACES:
        return f"tag {tag!r} has an unknown namespace"
    if tag != tag.lower():
        return f"tag {tag!r} must be lowercase"
    if namespace == "attack" and not _ATTACK_TAG.match(tag):
        return f"tag {tag!r} is not attack.<tactic-with-hyphens> or attack.tNNNN[.NNN]"
    if namespace == "cve" and not _CVE_TAG.match(tag):
        return f"tag {tag!r} must be cve.YYYY-NNNNN"
    return None


def check_rule(path: pathlib.Path, root: pathlib.Path, layout: dict) -> list[str]:
    rel = path.relative_to(root)
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return []  # yamllint and sigma check report YAML problems
    if not isinstance(doc, dict):
        return [f"{rel}: not a single rule mapping"]
    errors = []
    for key in REQUIRED:
        value = doc.get(key)
        if value is None or (isinstance(value, (str, list)) and not value):
            errors.append(f"{rel}: missing required {key}")
    title, rule_id = doc.get("title"), doc.get("id")
    if isinstance(title, str) and title and rule_id:
        if path.name not in allowed_filenames(title, str(rule_id)):
            errors.append(f"{rel}: filename should be {slugify_title(title)}.yml")
    for key in ("date", "modified"):
        if key in doc and doc[key] is not None and not _is_date(doc[key]):
            errors.append(f"{rel}: {key} {doc[key]!r} is not YYYY-MM-DD")
    tags = doc.get("tags") or []
    if isinstance(tags, list):
        errors.extend(f"{rel}: {err}" for err in map(_tag_error, tags) if err)
    expected = logsource_dir(doc.get("logsource"), layout)
    if expected is None:
        errors.append(f"{rel}: logsource {doc.get('logsource')} has no directory in {LAYOUT_FILE}")
    emerging = EMERGING_THREATS_TAG in tags if isinstance(tags, list) else False
    parent = rel.parent.as_posix()
    if emerging:
        root_dir, _, family = parent.partition("/")
        if root_dir != layout["emerging_threats_root"] or "/" in family or not _FAMILY.match(family):
            errors.append(f"{rel}: emerging-threat rules belong in {layout['emerging_threats_root']}/<family>/")
    elif expected is not None and parent != f"{layout['generic_root']}/{expected}":
        errors.append(f"{rel}: should be in {layout['generic_root']}/{expected}/ for its logsource")
    return errors


def main(argv: list[str]) -> int:
    root = pathlib.Path(argv[1] if len(argv) > 1 else ".").resolve()
    if not (root / LAYOUT_FILE).is_file():
        print(f"ERROR: {LAYOUT_FILE} not found under {root}", file=sys.stderr)
        return 2
    layout = load_layout(root)
    files = []
    for top in (layout["generic_root"], layout["emerging_threats_root"]):
        base = root / top
        if base.is_dir():
            files.extend(sorted(p for p in base.rglob("*") if p.suffix in (".yml", ".yaml")))
    errors = []
    for path in files:
        if path.suffix == ".yaml":
            errors.append(f"{path.relative_to(root)}: use the .yml extension")
            continue
        errors.extend(check_rule(path, root, layout))
    for error in errors:
        print(f"ERROR: {error}")
    print(f"{len(files)} rules checked: {len(errors)} layout/metadata error(s).")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
