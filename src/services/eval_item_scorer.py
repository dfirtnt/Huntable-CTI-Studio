"""
Item-level precision/recall scorer for subagent evaluation.

Compares expected_items (ground truth) against the items an extractor produced,
using per-agent canonical identities plus relaxed normalization to produce
matched/missed/extra item lists and precision/recall metrics.

Ground truth (`expected_items`) is authored as a flat list of identity strings
(command lines, registry paths, service names, "parent -> child" pairs, ...).
Actual extractor output is a list of structured dicts whose schema differs per
agent. This module defines the canonical comparison identity for every supported
extraction agent so structured results are compared on the same key GT uses --
instead of on the generic ``value`` field, which for registry/services/
scheduled-task items is a stringified Python dict that never matches GT.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

AGENT_EVAL_FBETA_BETA = 0.5

_CMD_WRAPPER_RE = re.compile(r"^(?:cmd(?:\.exe)?|%comspec%)\s+/[ck]\s+(.+)$", re.IGNORECASE)

# Registry hive abbreviations vary across articles (HKLM vs HKEY_LOCAL_MACHINE);
# the extractor reproduces them verbatim, so the scorer canonicalizes both sides.
_HIVE_ALIASES = {
    "hklm": "hkey_local_machine",
    "hkey_local_machine": "hkey_local_machine",
    "hkcu": "hkey_current_user",
    "hkey_current_user": "hkey_current_user",
    "hkcr": "hkey_classes_root",
    "hkey_classes_root": "hkey_classes_root",
    "hku": "hkey_users",
    "hkey_users": "hkey_users",
    "hkcc": "hkey_current_config",
    "hkey_current_config": "hkey_current_config",
}

_HUNT_QUERY_AGENTS = frozenset({"hunt_queries", "hunt_queries_edr", "hunt_queries_sigma"})


def calculate_f_beta(precision: float, recall: float, beta: float = AGENT_EVAL_FBETA_BETA) -> float:
    beta_squared = beta * beta
    denominator = (beta_squared * precision) + recall
    if denominator <= 0:
        return 0.0
    return ((1 + beta_squared) * precision * recall) / denominator


def _collapse_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _defang(s: str) -> str:
    return s.replace("[.]", ".").replace("[:]", ":")


def _normalize_cmdline(s: str) -> str:
    """Normalize a command-line string.

    Strip a leading ``cmd /c`` / ``/k`` wrapper (cmd, cmd.exe, or %COMSPEC%),
    lowercase, defang IOC bracket notation, and collapse whitespace.
    """
    s = s.strip()
    wrapper_match = _CMD_WRAPPER_RE.match(s)
    if wrapper_match:
        s = wrapper_match.group(1).strip()
    return _collapse_ws(_defang(s.lower()))


# Back-compat alias: pre-refactor generic normalize, still used by
# tests/unit/test_ground_truth_files.py for cross-subagent reachability checks.
_normalize = _normalize_cmdline


def _normalize_registry(s: str) -> str:
    """Canonicalize a ``hive\\key_path`` registry identity for comparison."""
    s = s.strip().lower().replace("/", "\\")
    s = re.sub(r"\\{2,}", r"\\", s)  # collapse repeated backslashes
    parts = [p for p in s.split("\\") if p != ""]
    if parts and parts[0] in _HIVE_ALIASES:
        parts[0] = _HIVE_ALIASES[parts[0]]
    return "\\".join(parts)


def _normalize_network(s: str) -> str:
    """Defang a network indicator: ``[.]``/``[:]`` and ``hxxp`` -> real scheme."""
    s = _defang(s.strip().lower()).replace("hxxp", "http")
    return _collapse_ws(s)


def _normalize_proctree(s: str) -> str:
    """Normalize a ``parent -> child`` process-lineage pair."""
    s = s.strip().lower().replace("->", " -> ")
    return _collapse_ws(s)


def _normalize_path_like(s: str) -> str:
    """Lowercase, collapse repeated backslashes and whitespace (task paths/names)."""
    s = re.sub(r"\\{2,}", r"\\", s.strip().lower())
    return _collapse_ws(s)


def _normalize_simple(s: str) -> str:
    return _collapse_ws(s.strip().lower())


def normalize_identity(subagent_name: str | None, s: str) -> str:
    """Return the canonical comparison key for one identity string.

    ``subagent_name`` selects the agent-specific normalization. ``None`` (and
    ``cmdline``) use command-line normalization, preserving the historical
    default behavior for callers that pass flat command strings.
    """
    text = str(s)
    if subagent_name in (None, "cmdline"):
        return _normalize_cmdline(text)
    if subagent_name == "registry_artifacts":
        return _normalize_registry(text)
    if subagent_name == "network_indicators":
        return _normalize_network(text)
    if subagent_name == "process_lineage":
        return _normalize_proctree(text)
    if subagent_name == "scheduled_tasks":
        return _normalize_path_like(text)
    if subagent_name in _HUNT_QUERY_AGENTS:
        return _normalize_simple(text)
    # windows_services and any future agent: simple lowercase/whitespace identity.
    return _normalize_simple(text)


def _s(value: Any) -> str | None:
    """Coerce to a stripped non-blank string, else None."""
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _first_str(item: dict, fields: tuple[str, ...]) -> str | None:
    for field_name in fields:
        candidate = _s(item.get(field_name))
        if candidate is not None:
            return candidate
    return None


def item_candidates(subagent_name: str | None, item: Any) -> list[str]:
    """Return the candidate identity strings for one raw extractor item.

    A single actual item can legitimately match ground truth written in more
    than one form (a registry path with or without its value name; a scheduled
    task by name or by path), so structured agents may return several
    candidates. GT-aware resolution in :func:`score_items` picks the candidate
    that matches ground truth when one does.

    Structured agents deliberately never fall back to the generic ``value``
    field: for registry/services/scheduled-task items that field is a
    stringified Python dict that would never match a GT identity string.
    """
    if isinstance(item, str):
        value = item.strip()
        return [value] if value else []
    if not isinstance(item, dict):
        return []

    if subagent_name == "registry_artifacts":
        hive = _s(item.get("registry_hive"))
        key = _s(item.get("registry_key_path"))
        value_name = _s(item.get("registry_value_name"))
        candidates: list[str] = []
        if key:
            base = f"{hive}\\{key}" if hive else key
            candidates.append(base)
            if value_name:
                candidates.append(f"{base}\\{value_name}")
        elif hive:
            candidates.append(hive)
        fallback = _first_str(item, ("name",))
        if not candidates and fallback:
            candidates.append(fallback)
        return candidates

    if subagent_name == "windows_services":
        return [
            c
            for c in (
                _s(item.get("service_name")),
                _s(item.get("display_name")),
                _s(item.get("binary_path")),
            )
            if c
        ]

    if subagent_name == "scheduled_tasks":
        candidates = [c for c in (_s(item.get("task_name")), _s(item.get("task_path"))) if c]
        fallback = _first_str(item, ("name",))
        if not candidates and fallback:
            candidates.append(fallback)
        return candidates

    if subagent_name == "process_lineage":
        value = _s(item.get("value"))
        if value:
            return [value]
        parent = _s(item.get("parent"))
        child = _s(item.get("child"))
        if parent and child:
            return [f"{parent} -> {child}"]
        return []

    if subagent_name == "network_indicators":
        candidate = _first_str(item, ("value", "indicator"))
        return [candidate] if candidate else []

    if subagent_name in _HUNT_QUERY_AGENTS:
        candidate = _first_str(item, ("query", "value", "detection", "rule", "text"))
        return [candidate] if candidate else []

    # cmdline and any unrecognized agent: generic command-bearing fields.
    candidate = _first_str(item, ("cmdline", "command", "commandline", "value", "name"))
    return [candidate] if candidate else []


@dataclass
class ItemScorerResult:
    precision: float  # TP / (TP + FP)
    recall: float  # TP / (TP + FN)
    matched: list[str]  # items in both expected and actual (using actual text)
    missed: list[str]  # in expected but not in actual
    extra: list[str]  # in actual but not in expected
    neutral: list[str]  # acceptable alternate readings; excluded from scoring
    matched_count: int
    missed_count: int
    extra_count: int
    neutral_count: int
    actual: list[str] = field(default_factory=list)  # resolved actual identities (matched + extra + neutral)


def score_items(
    expected_items: list[str],
    actual_items: list[Any],
    acceptable_items: list[dict[str, str]] | None = None,
    *,
    subagent_name: str | None = None,
) -> ItemScorerResult:
    """Compare expected vs actual item lists and return precision/recall metrics.

    ``expected_items`` is a list of ground-truth identity strings.
    ``actual_items`` may be plain strings or the structured dicts an extractor
    emits; each is reduced to its canonical identity via
    :func:`item_candidates` + :func:`normalize_identity`, selected by
    ``subagent_name``.

    Uses set-based matching on normalized keys so duplicates on either side are
    deduplicated before scoring, mirroring information-retrieval evaluation:
    each unique expected item is either found or not.
    """
    if not isinstance(expected_items, list):
        expected_items = list(expected_items) if expected_items else []
    if not isinstance(actual_items, list):
        actual_items = list(actual_items) if actual_items else []
    if acceptable_items is None:
        acceptable_items = []
    if not isinstance(acceptable_items, list):
        raise ValueError("acceptable_items must be a list")

    def norm(value: Any) -> str:
        return normalize_identity(subagent_name, str(value))

    # Build normalized -> original map for expected (first occurrence wins).
    norm_to_expected: dict[str, str] = {}
    for item in expected_items:
        key = norm(item)
        if key and key not in norm_to_expected:
            norm_to_expected[key] = str(item)

    norm_to_acceptable: dict[str, str] = {}
    for item in acceptable_items:
        if not isinstance(item, dict) or not isinstance(item.get("value"), str) or not item["value"].strip():
            raise ValueError("each acceptable item must provide a non-blank string value")
        if not isinstance(item.get("justification"), str) or not item["justification"].strip():
            raise ValueError("each acceptable item must provide a non-blank justification")
        key = norm(item["value"])
        if key and key not in norm_to_acceptable:
            norm_to_acceptable[key] = item["value"]

    expected_keys = set(norm_to_expected)
    acceptable_keys = set(norm_to_acceptable)

    overlap = expected_keys & acceptable_keys
    if overlap:
        raise ValueError("acceptable items must not duplicate expected items")

    # Resolve each actual item to a single canonical key. When an item exposes
    # several candidate identities, prefer one that matches ground truth (then
    # an acceptable reading), so a legitimate match is never lost to a
    # differently-shaped-but-equivalent candidate.
    norm_to_actual: dict[str, str] = {}
    for item in actual_items:
        candidate_pairs: list[tuple[str, str]] = []
        for raw in item_candidates(subagent_name, item):
            key = norm(raw)
            if key:
                candidate_pairs.append((key, raw))
        if not candidate_pairs:
            continue
        chosen = next((pair for pair in candidate_pairs if pair[0] in expected_keys), None)
        if chosen is None:
            chosen = next((pair for pair in candidate_pairs if pair[0] in acceptable_keys), None)
        if chosen is None:
            chosen = candidate_pairs[0]
        key, raw = chosen
        if key not in norm_to_actual:
            norm_to_actual[key] = raw

    actual_keys = set(norm_to_actual)

    matched_keys = expected_keys & actual_keys
    missed_keys = expected_keys - actual_keys
    neutral_keys = actual_keys & acceptable_keys
    extra_keys = actual_keys - expected_keys - acceptable_keys

    matched = [norm_to_actual[k] for k in sorted(matched_keys)]
    missed = [norm_to_expected[k] for k in sorted(missed_keys)]
    extra = [norm_to_actual[k] for k in sorted(extra_keys)]
    neutral = [norm_to_actual[k] for k in sorted(neutral_keys)]

    tp = len(matched_keys)
    fp = len(extra_keys)
    fn = len(missed_keys)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0

    return ItemScorerResult(
        precision=round(precision, 4),
        recall=round(recall, 4),
        matched=matched,
        missed=missed,
        extra=extra,
        neutral=neutral,
        matched_count=tp,
        missed_count=fn,
        extra_count=fp,
        neutral_count=len(neutral_keys),
        actual=[norm_to_actual[k] for k in sorted(actual_keys)],
    )
