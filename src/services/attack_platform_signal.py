"""ATT&CK technique -> platform signal (Phase C).

CTI articles frequently cite MITRE ATT&CK (sub-)technique IDs (e.g. ``T1543.002``).
Platform-discriminative (sub-)techniques are a high-quality, externally-maintained
classification signal: ``T1059.001`` (PowerShell) implies Windows, ``T1543.001``
(Launch Agent) implies macOS. This module extracts technique IDs and turns the
mapped ones into weighted platform votes that the entity-KB gate folds into its score.

The mapping (``config/attack_technique_platforms.json``) is a curated seed; the full,
authoritative map is regenerated from MITRE's ``x_mitre_platforms`` via
``scripts/build_attack_platform_map.py``.

See docs/superpowers/specs/2026-06-19-entity-driven-platform-classification-design.md (Phase C).
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Phase A/C platform scope.
SUPPORTED_PLATFORMS = ("windows", "linux", "macos")

# ATT&CK technique IDs: Txxxx with an optional .yyy sub-technique. Word-bounded so
# T123 / T12345 / TXXXX do not match.
_TECHNIQUE_RE = re.compile(r"\bT\d{4}(?:\.\d{3})?\b")

DEFAULT_ATTACK_MAP_PATH = Path(__file__).resolve().parents[2] / "config" / "attack_technique_platforms.json"

# Vote weights: ATT&CK citations SUPPLEMENT the entity KB rather than dominate it.
# Deliberately below the classifier's evidence floor so a single incidental citation
# (common in broad CTI write-ups that name techniques across platforms) does not by
# itself force a verdict -- it reinforces KB signal or, alone, defers to LLM adjudication.
_SINGLE_PLATFORM_WEIGHT = 2.0
_MULTI_PLATFORM_WEIGHT = 1.0


def extract_technique_ids(content: str) -> set[str]:
    """Return the set of ATT&CK (sub-)technique IDs cited in the content."""
    return set(_TECHNIQUE_RE.findall(content or ""))


def load_attack_map(path: Path | str | None = None) -> dict[str, list[str]]:
    """Load the technique -> platforms mapping. Returns {} on any error."""
    p = Path(path) if path else DEFAULT_ATTACK_MAP_PATH
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        techniques = data.get("techniques", {}) if isinstance(data, dict) else {}
        return {
            str(tid): [str(pl).lower() for pl in plats]
            for tid, plats in techniques.items()
            if isinstance(plats, list) and plats
        }
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"attack_platform_signal: failed to load map {p}: {e}")
        return {}


def technique_platform_votes(
    content: str, mapping: dict[str, list[str]]
) -> tuple[dict[str, float], dict[str, list[str]]]:
    """Turn cited, mapped ATT&CK techniques into weighted platform votes.

    Returns (scores, evidence) keyed by platform. Unmapped or non-discriminative
    techniques contribute nothing.
    """
    scores: dict[str, float] = {p: 0.0 for p in SUPPORTED_PLATFORMS}
    evidence: dict[str, list[str]] = {p: [] for p in SUPPORTED_PLATFORMS}
    if not mapping:
        return scores, evidence

    for tid in extract_technique_ids(content):
        platforms = [p for p in mapping.get(tid, []) if p in scores]
        if not platforms:
            continue
        weight = _SINGLE_PLATFORM_WEIGHT if len(platforms) == 1 else _MULTI_PLATFORM_WEIGHT
        for platform in platforms:
            scores[platform] += weight
            evidence[platform].append(f"ATT&CK {tid}")
    return scores, evidence
