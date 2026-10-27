"""Where a published Sigma rule lives in the customer rules repository.

One table decides every rule's directory: ``.huntable/rule-layout.yml`` in the destination
repository, falling back to the bundled ``config/sigma_rule_layout.yml``. The PR writer,
``scripts/migrate_sigma_repo_layout.py`` and the rules repository's own CI check all read
that table, so they cannot disagree about where a rule belongs.

* Generic rules: ``rules/<logsource dir>/<slug>.yml`` (SigmaHQ directory names).
* Emerging-threat rules (tagged ``detection.emerging-threats``):
  ``rules-emerging-threats/<family>/<slug>.yml``, or ``_unsorted/`` when no family resolves.

A logsource the table does not map raises :class:`UnmappedLogsourceError`; nothing falls
into a catch-all directory.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

DESTINATION_LAYOUT = Path(".huntable") / "rule-layout.yml"
BUNDLED_LAYOUT = Path(__file__).resolve().parents[2] / "config" / "sigma_rule_layout.yml"

EMERGING_THREATS_TAG = "detection.emerging-threats"

# SigmaHQ's filename convention is [a-z0-9_]{10,90}.yml (sigmahq_filename validator).
MAX_SLUG_LENGTH = 90
COLLISION_SUFFIX_LENGTH = 8

_ATTACK_TECHNIQUE_ID = re.compile(r"\bt\d{4}(?:\.\d{3})?\b", re.IGNORECASE)
_NON_SLUG = re.compile(r"[^a-z0-9]+")
_CVE = re.compile(r"\bCVE-(\d{4})-(\d{4,})\b", re.IGNORECASE)


class RuleLayoutError(ValueError):
    """A rule cannot be placed in the destination repository."""


class UnmappedLogsourceError(RuleLayoutError):
    """The rule's logsource has no entry in the layout table."""


@dataclass(frozen=True)
class FamilyAlias:
    family: str
    alias: str
    pattern: re.Pattern[str]


@dataclass(frozen=True)
class RuleLayout:
    generic_root: str
    emerging_threats_root: str
    unsorted_family: str
    logsource_dirs: Mapping[tuple[str | None, str | None, str | None], str]
    family_aliases: tuple[FamilyAlias, ...]
    source: Path

    @property
    def roots(self) -> tuple[str, str]:
        return (self.generic_root, self.emerging_threats_root)


@dataclass(frozen=True)
class RulePlacement:
    """Where one rule goes, before repository-wide collision handling."""

    directory: PurePosixPath
    slug: str
    emerging_threat: bool
    family: str | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def unsorted(self) -> bool:
        return self.emerging_threat and self.family is None

    def path(self, filename: str | None = None) -> PurePosixPath:
        return self.directory / (filename or f"{self.slug}.yml")


def _norm(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    return text or None


def _alias_pattern(alias: str) -> re.Pattern[str]:
    # Word boundaries that also hold next to a non-word alias edge such as "Ligolo-ng".
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])", re.IGNORECASE)


def parse_rule_layout(data: Mapping[str, Any], source: Path) -> RuleLayout:
    """Build a :class:`RuleLayout` from the YAML mapping; malformed tables raise."""
    if not isinstance(data, Mapping) or data.get("version") != 1:
        raise RuleLayoutError(f"{source}: expected a version 1 rule layout")
    dirs: dict[tuple[str | None, str | None, str | None], str] = {}
    for entry in data.get("logsource_dirs") or []:
        key = (_norm(entry.get("product")), _norm(entry.get("category")), _norm(entry.get("service")))
        directory = str(entry.get("dir") or "").strip().strip("/")
        if key == (None, None, None) or not directory:
            raise RuleLayoutError(f"{source}: logsource_dirs entry needs a logsource key and a dir: {entry}")
        if key in dirs and dirs[key] != directory:
            raise RuleLayoutError(f"{source}: logsource {key} is mapped twice ({dirs[key]}, {directory})")
        dirs[key] = directory
    aliases: list[FamilyAlias] = []
    for entry in data.get("families") or []:
        family = str(entry.get("family") or "").strip()
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", family):
            raise RuleLayoutError(f"{source}: family slug must be lowercase-hyphenated: {family!r}")
        for alias in entry.get("aliases") or []:
            aliases.append(FamilyAlias(family, str(alias), _alias_pattern(str(alias))))
    # Longest alias first so "Chaos Loader" wins over a shorter overlapping alias.
    aliases.sort(key=lambda a: len(a.alias), reverse=True)
    return RuleLayout(
        generic_root=str(data.get("generic_root") or "rules"),
        emerging_threats_root=str(data.get("emerging_threats_root") or "rules-emerging-threats"),
        unsorted_family=str(data.get("unsorted_family") or "_unsorted"),
        logsource_dirs=dirs,
        family_aliases=tuple(aliases),
        source=source,
    )


def layout_path(repo_path: Path | None) -> Path:
    """The destination repository's layout table when present, else the bundled copy."""
    if repo_path is not None:
        candidate = Path(repo_path) / DESTINATION_LAYOUT
        if candidate.is_file():
            return candidate
    return BUNDLED_LAYOUT


def load_rule_layout(repo_path: Path | None = None) -> RuleLayout:
    path = layout_path(repo_path)
    return parse_rule_layout(yaml.safe_load(path.read_text(encoding="utf-8")), path)


def slugify_title(title: str) -> str:
    """Filename stem for a rule title: ``[a-z0-9_]``, no ATT&CK IDs, cut on a word boundary.

    Punctuation becomes a separator rather than vanishing, so ``amsi.dll`` is ``amsi_dll``
    and not ``amsidll``.
    """
    text = unicodedata.normalize("NFKD", str(title or "")).encode("ascii", "ignore").decode("ascii")
    text = _ATTACK_TECHNIQUE_ID.sub(" ", text.lower())
    slug = _NON_SLUG.sub("_", text).strip("_")
    if len(slug) > MAX_SLUG_LENGTH:
        cut = slug[: MAX_SLUG_LENGTH + 1]
        slug = cut[: cut.rfind("_")] if "_" in cut else slug[:MAX_SLUG_LENGTH]
    return slug or "untitled_rule"


def collision_filename(slug: str, rule_id: str) -> str:
    """Deterministic alternative filename for a slug already owned by another rule."""
    suffix = re.sub(r"[^a-z0-9]", "", str(rule_id).lower())[:COLLISION_SUFFIX_LENGTH]
    if not suffix:
        raise RuleLayoutError(f"Cannot derive a collision suffix from rule id {rule_id!r}")
    base = slug[: MAX_SLUG_LENGTH - COLLISION_SUFFIX_LENGTH - 1].rstrip("_")
    return f"{base}_{suffix}.yml"


def is_emerging_threat(tags: Iterable[Any] | None) -> bool:
    return any(str(tag).strip().lower() == EMERGING_THREATS_TAG for tag in tags or [])


def _family_in(text: str, layout: RuleLayout) -> str | None:
    best: tuple[int, int, str] | None = None  # (-length, position, family)
    for alias in layout.family_aliases:
        match = alias.pattern.search(text)
        if match:
            candidate = (-len(alias.alias), match.start(), alias.family)
            if best is None or candidate < best:
                best = candidate
    if best is not None:
        return best[2]
    cve = _CVE.search(text)
    if cve:
        return f"cve-{cve.group(1)}-{cve.group(2)}"
    return None


def resolve_family(title: str | None, description: str | None, layout: RuleLayout) -> str | None:
    """Family slug from the title, else the description; ``None`` when neither names one."""
    for text in (title, description):
        if isinstance(text, str) and text.strip():
            family = _family_in(text, layout)
            if family:
                return family
    return None


def logsource_dir(logsource: Any, layout: RuleLayout) -> str:
    """Directory (under the generic root) for a logsource; unmapped combinations raise."""
    if not isinstance(logsource, Mapping):
        raise UnmappedLogsourceError("Rule has no logsource mapping")
    product, category, service = (_norm(logsource.get(k)) for k in ("product", "category", "service"))
    candidates = [(product, category, service)]
    if category:
        candidates.append((product, category, None))
        if product:
            candidates.append((None, category, None))
    elif service:
        candidates.append((product, None, service))
    for key in candidates:
        if key in layout.logsource_dirs:
            return layout.logsource_dirs[key]
    described = ", ".join(f"{k}={v}" for k, v in zip(("product", "category", "service"), candidates[0]) if v)
    raise UnmappedLogsourceError(
        f"Logsource {{{described or 'empty'}}} has no directory in {layout.source.name}; "
        "add a logsource_dirs entry before publishing"
    )


def place_rule(rule: Mapping[str, Any], layout: RuleLayout) -> RulePlacement:
    """Directory and slug for a parsed rule. Raises :class:`RuleLayoutError` when unplaceable."""
    title = rule.get("title")
    if not isinstance(title, str) or not title.strip():
        raise RuleLayoutError("Rule has no title to derive a filename from")
    generic_dir = logsource_dir(rule.get("logsource"), layout)  # validates the logsource for every rule
    slug = slugify_title(title)
    if not is_emerging_threat(rule.get("tags")):
        return RulePlacement(PurePosixPath(layout.generic_root, generic_dir), slug, emerging_threat=False)
    family = resolve_family(title, rule.get("description"), layout)
    if family is None:
        return RulePlacement(
            PurePosixPath(layout.emerging_threats_root, layout.unsorted_family),
            slug,
            emerging_threat=True,
            warnings=(
                f"No threat family resolved from the title or description; filed under "
                f"{layout.emerging_threats_root}/{layout.unsorted_family}/. Add an alias to the rule layout "
                "or move the file before merging.",
            ),
        )
    return RulePlacement(PurePosixPath(layout.emerging_threats_root, family), slug, emerging_threat=True, family=family)


def index_repository_filenames(repo_path: Path, layout: RuleLayout) -> dict[str, tuple[PurePosixPath, str | None]]:
    """``filename -> (relative path, rule id)`` for every rule under both roots.

    ``duplicate_filename`` is a repository-wide validator, so collisions are checked across
    the whole repository, not just the target directory.
    """
    index: dict[str, tuple[PurePosixPath, str | None]] = {}
    for root in layout.roots:
        base = Path(repo_path) / root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.yml")):
            rule_id = None
            try:
                doc = yaml.safe_load(path.read_text(encoding="utf-8"))
                if isinstance(doc, Mapping) and doc.get("id") is not None:
                    rule_id = str(doc["id"])
            except (yaml.YAMLError, OSError, UnicodeDecodeError):
                pass
            index.setdefault(path.name, (PurePosixPath(path.relative_to(repo_path).as_posix()), rule_id))
    return index


def assign_filenames(
    placements: Mapping[str, RulePlacement],
    existing: Mapping[str, tuple[PurePosixPath, str | None]],
) -> dict[str, PurePosixPath]:
    """Final relative path per rule id, resolving slug collisions deterministically.

    A rule whose ``<slug>.yml`` is already owned by a *different* rule id (in the repository
    or elsewhere in this batch) gets ``<slug>_<first 8 id chars>.yml``. The outcome depends
    only on the rule ids, never on processing order. A rule re-published under its own id
    keeps its filename.
    """
    claims: dict[str, set[str]] = {}
    for rule_id, placement in placements.items():
        claims.setdefault(f"{placement.slug}.yml", set()).add(rule_id)
    result: dict[str, PurePosixPath] = {}
    for rule_id, placement in placements.items():
        filename = f"{placement.slug}.yml"
        owner = existing.get(filename)
        taken_in_repo = owner is not None and owner[1] != rule_id
        taken_in_batch = len(claims[filename]) > 1
        if taken_in_repo or taken_in_batch:
            filename = collision_filename(placement.slug, rule_id)
            other = existing.get(filename)
            if other is not None and other[1] != rule_id:
                raise RuleLayoutError(f"Filename {filename} is already used by rule {other[1]} at {other[0]}")
        result[rule_id] = placement.path(filename)
    return result
