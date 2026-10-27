"""Metadata normalization for Sigma rules CTI Studio publishes.

``normalize_rule_yaml`` fixes what can be fixed mechanically and reports what cannot:

* ``author``: generated rules carry the one configured author (AppSettings ``sigmaAuthor``,
  fallback ``SIGMA_RULE_AUTHOR``). Publisher-imported rules keep their author; a missing
  one is filled from the recorded attribution, never replaced. A publisher rule that is
  changed in any way gets ``modified`` set to the edit date, marking the change as the
  destination's CC-BY license policy requires.
* ``date`` / ``modified``: ``YYYY-MM-DD``. A missing date becomes today. ``modified`` is
  only kept when it records a real edit (a publisher's own, later than ``date``); a
  generated rule's first publish never carries one.
* ``tags``: ATT&CK tags lowercased with hyphens (``attack.defense_evasion`` ->
  ``attack.defense-evasion``), ``cve.YYYY.NNNNN`` -> ``cve.YYYY-NNNNN``, tags in a namespace
  pySigma does not know are dropped, duplicates removed. ``stp.*`` and the rest of
  pySigma's namespaces are kept.
* Keys outside the Sigma rule specification (``name``, pipeline/annotation keys) are removed.

Problems that need a human -- empty ``references``, ``falsepositives`` or ``tags``, or YAML
that is not a single rule mapping -- are returned as ``problems``; callers send such a
rule back to review instead of publishing it.

Edits are made per top-level key block, so ``title``, ``id``, ``logsource`` and
``detection`` keep their exact bytes. A rule that needs no change is returned unchanged.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import yaml

from src.services.sigma_validator import SIGMA_CANONICAL_FIELD_ORDER

SOURCE_ORIGIN = "source_provided"

# Sigma rule specification top-level keys (v2). Everything else is pipeline residue.
SIGMA_SPEC_KEYS: frozenset[str] = frozenset(
    {
        "title",
        "id",
        "related",
        "taxonomy",
        "status",
        "description",
        "license",
        "references",
        "author",
        "date",
        "modified",
        "tags",
        "logsource",
        "detection",
        "fields",
        "falsepositives",
        "level",
        "scope",
    }
)
# ``name`` is a Sigma v2 key for correlation references; this repository publishes no
# correlation rules, and every ``name`` seen so far was generator residue.
STRIPPED_SPEC_KEYS: frozenset[str] = frozenset({"name"})

PROTECTED_KEYS: tuple[str, ...] = ("title", "id", "logsource", "detection")
REQUIRED_LIST_KEYS: tuple[str, ...] = ("references", "falsepositives", "tags")

# pySigma NamespaceTagValidator.allowed_namespace
SIGMA_TAG_NAMESPACES: frozenset[str] = frozenset({"attack", "car", "cve", "d3fend", "detection", "stp", "tlp"})

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SLASH_DATE = re.compile(r"^(\d{4})/(\d{2})/(\d{2})$")
_ATTACK_TAG = re.compile(r"^attack\.(?:t\d{4}(?:\.\d{3})?|[gs]\d{4}|ta\d{4}|[a-z]+(?:-[a-z]+)*)$")
_CVE_DOTTED = re.compile(r"^cve\.(\d{4})\.(\d+)$")
_TOP_LEVEL_KEY = re.compile(r"^([A-Za-z_][\w-]*)\s*:")


@dataclass
class NormalizationResult:
    rule_yaml: str
    changes: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    rule: dict[str, Any] | None = None

    @property
    def changed(self) -> bool:
        return bool(self.changes)

    @property
    def ready(self) -> bool:
        return not self.problems


# --------------------------------------------------------------------------- values


def normalize_date_value(value: Any) -> date | None:
    """``date`` / ``modified`` as a ``datetime.date``; ``None`` when unparseable."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        for pattern in (_ISO_DATE, _SLASH_DATE):
            if pattern.match(text):
                try:
                    return datetime.strptime(text.replace("/", "-"), "%Y-%m-%d").date()
                except ValueError:
                    return None
    return None


def normalize_tag(tag: Any) -> str | None:
    """Canonical form of one tag, or ``None`` when it should be dropped."""
    if not isinstance(tag, str):
        return None
    text = tag.strip().lower()
    namespace, sep, name = text.partition(".")
    if not sep or not name or namespace not in SIGMA_TAG_NAMESPACES:
        return None
    if namespace == "attack":
        text = "attack." + name.replace("_", "-").replace(" ", "-")
        return text if _ATTACK_TAG.match(text) else None
    if namespace == "cve":
        dotted = _CVE_DOTTED.match(text)
        if dotted:
            return f"cve.{dotted.group(1)}-{dotted.group(2)}"
    return text


def normalize_tags(tags: Iterable[Any]) -> tuple[list[str], list[str]]:
    """``(normalized tags, change notes)``; order kept, duplicates removed."""
    result: list[str] = []
    notes: list[str] = []
    for tag in tags:
        fixed = normalize_tag(tag)
        if fixed is None:
            notes.append(f"tags: dropped unknown or malformed tag {tag!r}")
            continue
        if fixed != tag:
            notes.append(f"tags: {tag!r} -> {fixed!r}")
        if fixed in result:
            notes.append(f"tags: dropped duplicate {fixed!r}")
            continue
        result.append(fixed)
    return result, notes


def _non_empty_list(value: Any) -> bool:
    if isinstance(value, list):
        return any(item is not None and str(item).strip() for item in value)
    return False


# ---------------------------------------------------------------------- YAML blocks


def _split_blocks(text: str) -> tuple[list[str], list[tuple[str, list[str]]]]:
    """``(preamble lines, [(top-level key, lines), ...])``; lines keep their newlines."""
    preamble: list[str] = []
    blocks: list[tuple[str, list[str]]] = []
    for line in text.splitlines(keepends=True):
        match = _TOP_LEVEL_KEY.match(line)
        if match:
            blocks.append((match.group(1), [line]))
        elif blocks:
            blocks[-1][1].append(line)
        else:
            preamble.append(line)
    return preamble, blocks


def _sequence_indent(text: str) -> str:
    """The indent this file uses for top-level block sequences (SigmaHQ style is four spaces)."""
    lines = text.splitlines()
    for previous, line in zip(lines, lines[1:]):
        if _TOP_LEVEL_KEY.match(previous) and previous.rstrip().endswith(":"):
            match = re.match(r"^( *)- ", line)
            if match:
                return match.group(1)
    return "    "


def _scalar(value: Any) -> str:
    dumped = yaml.safe_dump(value, default_flow_style=True, allow_unicode=True, width=1_000_000)
    dumped = dumped.rstrip("\n")
    if dumped.endswith("\n..."):
        dumped = dumped[: -len("\n...")]
    elif dumped.endswith("..."):
        dumped = dumped[: -len("...")].rstrip()
    return dumped


def _render_block(key: str, value: Any, indent: str) -> list[str]:
    if isinstance(value, list):
        return [f"{key}:\n", *(f"{indent}- {_scalar(item)}\n" for item in value)]
    return [f"{key}: {_scalar(value)}\n"]


class _BlockEditor:
    def __init__(self, text: str) -> None:
        self.text = text
        self.indent = _sequence_indent(text)
        self.preamble, self.blocks = _split_blocks(text)

    def keys(self) -> list[str]:
        return [key for key, _ in self.blocks]

    def remove(self, key: str) -> None:
        self.blocks = [(k, lines) for k, lines in self.blocks if k != key]

    def set(self, key: str, value: Any) -> None:
        rendered = _render_block(key, value, self.indent)
        for index, (existing_key, lines) in enumerate(self.blocks):
            if existing_key == key:
                # Keep comment / blank lines that trailed the old block.
                trailing = []
                for line in reversed(lines[1:]):
                    if line.strip() == "" or line.lstrip().startswith("#"):
                        trailing.insert(0, line)
                    else:
                        break
                self.blocks[index] = (key, rendered + trailing)
                return
        order = list(SIGMA_CANONICAL_FIELD_ORDER)
        position = order.index(key) if key in order else len(order)
        insert_at = 0
        for index, (existing_key, _) in enumerate(self.blocks):
            existing_position = order.index(existing_key) if existing_key in order else len(order)
            if existing_position <= position:
                insert_at = index + 1
        self.blocks.insert(insert_at, (key, rendered))

    def render(self) -> str:
        parts = list(self.preamble)
        for _, lines in self.blocks:
            if parts and not parts[-1].endswith("\n"):
                parts[-1] += "\n"
            parts.extend(lines)
        out = "".join(parts)
        return out if out.endswith("\n") else out + "\n"


# ------------------------------------------------------------------------ normalize


def _load_single_rule(rule_yaml: str) -> dict[str, Any] | str:
    try:
        documents = [doc for doc in yaml.safe_load_all(rule_yaml) if doc is not None]
    except yaml.YAMLError as exc:
        return f"YAML does not parse: {str(exc).splitlines()[0]}"
    if len(documents) != 1 or not isinstance(documents[0], dict):
        return "Expected exactly one Sigma rule mapping in the YAML"
    return documents[0]


def normalize_rule_yaml(
    rule_yaml: str,
    *,
    origin: str = "generated",
    canonical_author: str,
    attribution: str | None = None,
    today: date | None = None,
    first_publish: bool = True,
    edit_date: date | None = None,
) -> NormalizationResult:
    """Normalize one rule's metadata. See the module docstring for the rules applied.

    ``today`` fills a missing ``date``. ``edit_date`` (default ``today``) is stamped as
    ``modified`` when a publisher's rule is changed, so the change is marked as the
    destination's CC-BY license policy (``mark_changes``) requires.

    ``first_publish`` is true for a rule entering the repository through CTI Studio; the
    one-time repository migration passes false so existing, later ``modified`` dates stay.
    """
    parsed = _load_single_rule(rule_yaml)
    if isinstance(parsed, str):
        return NormalizationResult(rule_yaml, problems=[parsed])
    rule = parsed
    editor = _BlockEditor(rule_yaml)
    if sorted(editor.keys()) != sorted(str(k) for k in rule):
        # Flow-style or otherwise unusual top-level layout: do not risk a block edit.
        return NormalizationResult(
            rule_yaml, problems=["Top-level YAML layout is not one key per line; normalize by hand"], rule=rule
        )

    changes: list[str] = []
    problems: list[str] = []
    publisher = origin == SOURCE_ORIGIN
    today = today or date.today()

    for key in list(rule):
        if key not in SIGMA_SPEC_KEYS or key in STRIPPED_SPEC_KEYS:
            editor.remove(key)
            changes.append(f"removed non-published key {key!r}")

    # author
    author = rule.get("author")
    author_text = str(author).strip() if author is not None else ""
    if publisher:
        if not author_text:
            fill = (attribution or "").strip()
            if fill:
                editor.set("author", fill)
                changes.append(f"author: filled from source attribution {fill!r}")
            else:
                problems.append("Publisher rule has no author and no recorded attribution")
    elif author_text != canonical_author:
        editor.set("author", canonical_author)
        changes.append(f"author: {author_text or '(missing)'!r} -> {canonical_author!r}")

    # date
    rule_date = normalize_date_value(rule.get("date"))
    if "date" not in rule or rule.get("date") in (None, ""):
        rule_date = today
        editor.set("date", today)
        changes.append(f"date: (missing) -> {today.isoformat()}")
    elif rule_date is None:
        problems.append(f"date {rule.get('date')!r} is not a YYYY-MM-DD date")
    elif not (isinstance(rule["date"], date) or _ISO_DATE.match(str(rule["date"]).strip())):
        editor.set("date", rule_date)
        changes.append(f"date: {rule['date']!r} -> {rule_date.isoformat()}")

    # modified
    if "modified" in rule:
        modified = normalize_date_value(rule.get("modified"))
        keep = publisher or not first_publish
        if not keep or modified is None or rule_date is None or modified <= rule_date:
            editor.remove("modified")
            changes.append(f"removed modified {rule.get('modified')!r} (no edit after the rule date)")
        elif not (isinstance(rule["modified"], date) or _ISO_DATE.match(str(rule["modified"]).strip())):
            editor.set("modified", modified)
            changes.append(f"modified: {rule['modified']!r} -> {modified.isoformat()}")

    # tags
    tags = rule.get("tags")
    if isinstance(tags, list):
        fixed_tags, notes = normalize_tags(tags)
        if fixed_tags != tags:
            if fixed_tags:
                editor.set("tags", fixed_tags)
            else:
                editor.remove("tags")
            changes.extend(notes)
        tags = fixed_tags
    elif tags is not None:
        problems.append("tags must be a list")

    for key in REQUIRED_LIST_KEYS:
        value = tags if key == "tags" else rule.get(key)
        if not _non_empty_list(value):
            problems.append(f"Missing required {key}")

    if not changes:
        if rule_yaml and not rule_yaml.endswith("\n"):
            # yamllint new-line-at-end-of-file is an error in the rules repository's CI.
            # Whitespace only: not a content change, so a publisher rule is not stamped.
            return NormalizationResult(
                rule_yaml + "\n", changes=["added the missing final newline"], problems=problems, rule=rule
            )
        return NormalizationResult(rule_yaml, problems=problems, rule=rule)

    if publisher:
        # A publisher's rule was changed: mark it (CC-BY "indicate if changes were made").
        stamp = edit_date or today
        editor.set("modified", stamp)
        changes.append(f"modified: set to {stamp.isoformat()} (publisher rule changed)")

    new_yaml = editor.render()
    reparsed = _load_single_rule(new_yaml)
    if isinstance(reparsed, str) or any(reparsed.get(k) != rule.get(k) for k in PROTECTED_KEYS):
        # Never publish an edit that changed identity or detection logic.
        return NormalizationResult(
            rule_yaml, problems=[*problems, "Normalization would alter a protected field; normalize by hand"], rule=rule
        )
    return NormalizationResult(new_yaml, changes=changes, problems=problems, rule=reparsed)


def resolve_canonical_author(db_session: Any = None) -> str:
    """AppSettings ``sigmaAuthor`` when set, else ``SIGMA_RULE_AUTHOR``."""
    from src.services.sigma_generation_service import SIGMA_RULE_AUTHOR

    if db_session is not None:
        from src.database.models import AppSettingsTable

        row = db_session.query(AppSettingsTable).filter(AppSettingsTable.key == "sigmaAuthor").first()
        if row is not None and row.value and str(row.value).strip():
            return str(row.value).strip()
    return SIGMA_RULE_AUTHOR


def normalize_queue_rule(rule: Any, canonical_author: str, *, today: date | None = None) -> NormalizationResult:
    """Normalize a ``SigmaRuleQueueTable`` row's YAML (does not write to the row)."""
    return normalize_rule_yaml(
        rule.rule_yaml or "",
        origin=getattr(rule, "rule_origin", None) or "generated",
        canonical_author=canonical_author,
        attribution=getattr(rule, "attribution", None),
        today=today,
    )


def normalize_for_queue_entry(
    rule_yaml: str,
    *,
    db_session: Any = None,
    origin: str = "generated",
    attribution: str | None = None,
) -> NormalizationResult:
    """Normalize YAML as it enters the queue. Problems are reported, never enforced here:
    the rule still reaches review, and submit-pr sends a not-ready rule back to pending."""
    return normalize_rule_yaml(
        rule_yaml,
        origin=origin,
        canonical_author=resolve_canonical_author(db_session),
        attribution=attribution,
    )


def readiness_metadata(result: NormalizationResult) -> dict[str, Any]:
    """``rule_metadata["publish_readiness"]`` payload for a normalization result."""
    return {"ready": result.ready, "problems": result.problems, "changes": result.changes}


def problems_as_review_note(problems: Iterable[str]) -> str:
    return "Publish readiness: " + "; ".join(problems)


__all__ = [
    "NormalizationResult",
    "SIGMA_SPEC_KEYS",
    "SIGMA_TAG_NAMESPACES",
    "SOURCE_ORIGIN",
    "normalize_date_value",
    "normalize_for_queue_entry",
    "normalize_queue_rule",
    "normalize_rule_yaml",
    "normalize_tag",
    "normalize_tags",
    "problems_as_review_note",
    "readiness_metadata",
    "resolve_canonical_author",
]
