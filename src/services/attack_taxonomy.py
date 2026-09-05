"""MITRE ATT&CK taxonomy lookup for Sigma ``attack.*`` tag validation.

Sigma rules tag MITRE ATT&CK objects as ``attack.t1059.001`` (technique / sub-technique),
``attack.g0016`` (group), ``attack.s0154`` (software), ``attack.m1038`` (mitigation),
``attack.c0001`` (campaign), ``attack.ta0002`` (tactic ID) or ``attack.execution`` (tactic
shortname). LLM-generated rules routinely hallucinate technique IDs or cite IDs MITRE has
since revoked or deprecated. This module answers "does that ID exist, and is it current?"
from a cached copy of the ATT&CK taxonomy (``config/attack_taxonomy.json``), regenerated
by ``scripts/build_attack_taxonomy.py``. Validation never touches the network.

Severity policy:
- Unknown, revoked, or deprecated ATT&CK *IDs* are errors. They are unambiguous facts
  about the taxonomy and the fix is mechanical (use the replacement, or drop the tag).
- Unknown *tactic names* are warnings only. The Sigma tag taxonomy lags MITRE (ATT&CK v19
  renamed Enterprise ``defense-evasion``, which SigmaHQ still uses everywhere), so a hard
  failure here would reject correct community-style rules.
- A missing or unreadable taxonomy file disables the check (logged once) rather than
  failing every rule.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_ATTACK_TAXONOMY_PATH = Path(__file__).resolve().parents[2] / "config" / "attack_taxonomy.json"

ATTACK_TAG_PREFIX = "attack."

# Lower-cased ATT&CK ID shapes that may follow the ``attack.`` prefix.
_ATTACK_ID_RE = re.compile(r"^(?:t\d{4}(?:\.\d{3})?|ta\d{4}|g\d{4}|s\d{4}|m\d{4}|c\d{4})$")

_KIND_BY_PREFIX = {
    "TA": "tactic",
    "T": "technique",
    "G": "group",
    "S": "software",
    "M": "mitigation",
    "C": "campaign",
}


@dataclass(frozen=True)
class AttackTaxonomy:
    """In-memory ATT&CK taxonomy: ``objects`` keyed by upper-case ATT&CK ID."""

    version: str
    tactics: frozenset[str]
    objects: dict[str, dict]

    @property
    def is_empty(self) -> bool:
        return not self.objects

    def lookup(self, attack_id: str) -> dict | None:
        return self.objects.get(attack_id.upper())


EMPTY_TAXONOMY = AttackTaxonomy(version="unknown", tactics=frozenset(), objects={})


def parse_taxonomy(data: object) -> AttackTaxonomy:
    """Build an :class:`AttackTaxonomy` from the decoded JSON payload. Tolerant of junk."""
    if not isinstance(data, dict):
        return EMPTY_TAXONOMY
    source = str(data.get("_source", ""))
    version = source.split(":", 1)[1] if ":" in source else (source or "unknown")
    raw_objects = data.get("objects", {})
    objects = {
        str(attack_id).upper(): entry
        for attack_id, entry in (raw_objects.items() if isinstance(raw_objects, dict) else [])
        if isinstance(entry, dict)
    }
    raw_tactics = data.get("tactics", [])
    tactics = frozenset(str(t).lower() for t in raw_tactics) if isinstance(raw_tactics, list) else frozenset()
    return AttackTaxonomy(version=version or "unknown", tactics=tactics, objects=objects)


@lru_cache(maxsize=8)
def _load_cached(path_str: str) -> AttackTaxonomy:
    path = Path(path_str)
    try:
        taxonomy = parse_taxonomy(json.loads(path.read_text(encoding="utf-8")))
    except Exception as exc:  # noqa: BLE001 - any load failure degrades to "check disabled"
        logger.warning("attack_taxonomy: failed to load %s (%s); ATT&CK tag validation disabled", path, exc)
        return EMPTY_TAXONOMY
    if taxonomy.is_empty:
        logger.warning("attack_taxonomy: %s contains no objects; ATT&CK tag validation disabled", path)
    return taxonomy


def load_attack_taxonomy(path: Path | str | None = None) -> AttackTaxonomy:
    """Load (and cache per path) the ATT&CK taxonomy. Returns an empty taxonomy on error."""
    return _load_cached(str(path) if path else str(DEFAULT_ATTACK_TAXONOMY_PATH))


def clear_taxonomy_cache() -> None:
    """Drop cached taxonomies (tests and post-regeneration reloads)."""
    _load_cached.cache_clear()


def _kind_for(attack_id: str, entry: dict | None) -> str:
    if entry and entry.get("kind"):
        return str(entry["kind"])
    if attack_id.startswith("TA"):
        return _KIND_BY_PREFIX["TA"]
    if attack_id.startswith("T") and "." in attack_id:
        return "sub-technique"
    return _KIND_BY_PREFIX.get(attack_id[:1], "object")


def _describe(attack_id: str, entry: dict | None) -> str:
    name = entry.get("name") if entry else None
    return f"{attack_id} ({name})" if name else attack_id


def check_attack_tag(tag: str, taxonomy: AttackTaxonomy) -> tuple[list[str], list[str]]:
    """Validate one Sigma tag against the taxonomy.

    Returns ``(errors, warnings)``. Tags outside the ``attack.`` namespace, and every tag
    when the taxonomy is empty, produce neither.
    """
    if not isinstance(tag, str) or not tag.lower().startswith(ATTACK_TAG_PREFIX):
        return [], []
    if taxonomy.is_empty:
        return [], []

    suffix = tag[len(ATTACK_TAG_PREFIX) :].strip().lower()
    if not suffix:
        return [], [f"Tag '{tag}' has no ATT&CK tactic or ID after the 'attack.' prefix"]

    if not _ATTACK_ID_RE.match(suffix):
        tactic = suffix.replace("_", "-")
        if tactic in taxonomy.tactics:
            return [], []
        return [], [
            f"Tag '{tag}' is not a recognized ATT&CK tactic or ID in ATT&CK v{taxonomy.version} "
            "(expected attack.<tactic>, attack.tNNNN[.NNN], attack.gNNNN, or attack.sNNNN)"
        ]

    attack_id = suffix.upper()
    entry = taxonomy.lookup(attack_id)
    kind = _kind_for(attack_id, entry)

    if entry is None:
        message = (
            f"Tag '{tag}' references unknown ATT&CK {kind} {attack_id} "
            f"(not in ATT&CK v{taxonomy.version}); use a current ATT&CK ID"
        )
        if "." in attack_id:
            parent_id = attack_id.split(".", 1)[0]
            parent = taxonomy.lookup(parent_id)
            if parent is not None:
                message += (
                    f" -- parent technique {_describe(parent_id, parent)} exists; "
                    "check the sub-technique suffix or tag the parent instead"
                )
        return [message], []

    status = str(entry.get("status", "active")).lower()
    if status == "revoked":
        replacement = entry.get("replaced_by")
        if replacement:
            replacement_id = str(replacement).upper()
            message = (
                f"Tag '{tag}' references revoked ATT&CK {kind} {_describe(attack_id, entry)}; "
                f"it was replaced by {_describe(replacement_id, taxonomy.lookup(replacement_id))} "
                f"-- use '{ATTACK_TAG_PREFIX}{replacement_id.lower()}'"
            )
        else:
            message = (
                f"Tag '{tag}' references revoked ATT&CK {kind} {_describe(attack_id, entry)} "
                "with no recorded replacement; remove the tag or choose a current ATT&CK ID"
            )
        return [message], []

    if status == "deprecated":
        return [
            f"Tag '{tag}' references deprecated ATT&CK {kind} {_describe(attack_id, entry)} "
            f"(deprecated as of ATT&CK v{taxonomy.version}, no replacement); "
            "remove the tag or choose a current ATT&CK ID"
        ], []

    return [], []
