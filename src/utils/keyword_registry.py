"""Faceted keyword registry — the single source of truth for keyword scoring (Phase 1).

Each entry in ``config/keyword_registry.yaml`` carries an optional **huntability** tier
(perfect/good/lolbas/intelligence/negative) and/or an optional **platform** tag
(windows/linux/macos). Two projections read it:

- ``build_hunt_scoring_keywords`` reconstructs ``HUNT_SCORING_KEYWORDS`` (grouped by tier, in
  the historic order) — ``src.utils.content`` derives the dict from this, and a byte-equal
  parity test (``tests/test_keyword_registry.py``) guards against drift (decision D-A).
- ``project_platform`` reuses the existing ``PlatformClassifier`` over the registry's
  platform-tagged entries, which subsume ``config/platform_classification_kb.yaml`` (G3).

Parity-locked (spec 2026-06-20 §8 Phase 1): both projections reproduce current behavior exactly.
The single-pass ``WeightedKeywordScan`` that *unifies* the two matchers (the hunt scorer uses
word-boundary regex, the platform classifier uses substring match) is a behavior change and is
deferred to Phase 4; Phase 1 ships the shared registry + parity-preserving projections.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "config" / "keyword_registry.yaml"

# Registry tier name -> HUNT_SCORING_KEYWORDS key, in the historic dict order (parity-critical).
_TIER_TO_KEY = {
    "perfect": "perfect_discriminators",
    "good": "good_discriminators",
    "lolbas": "lolbas_executables",
    "intelligence": "intelligence_indicators",
    "negative": "negative_indicators",
}
_HUNT_KEY_ORDER = list(_TIER_TO_KEY.values())


def load_registry(path: Path | str | None = None) -> list[dict[str, Any]]:
    """Load the registry entry list. Raises on a missing/malformed file — the registry is
    required (no silent fallback: a wrong hunt score is worse than a loud import failure)."""
    p = Path(path) if path else DEFAULT_REGISTRY_PATH
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    keywords = data.get("keywords") if isinstance(data, dict) else None
    if not isinstance(keywords, list):
        raise ValueError(f"keyword registry at {p} has no 'keywords' list")
    return keywords


def build_hunt_scoring_keywords(registry: list[dict[str, Any]] | None = None) -> dict[str, list[str]]:
    """Project the registry's tier'd entries into the HUNT_SCORING_KEYWORDS dict shape."""
    reg = registry if registry is not None else load_registry()
    out: dict[str, list[str]] = {key: [] for key in _HUNT_KEY_ORDER}
    for entry in reg:
        tier = entry.get("tier")
        if tier:
            out[_TIER_TO_KEY[tier]].append(entry["match"])
    return out


def platform_entries(registry: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """The platform-tagged entries, in PlatformClassifier's expected {match, platforms, weight} shape."""
    reg = registry if registry is not None else load_registry()
    return [
        {"match": e["match"], "platforms": list(e["platforms"]), "weight": e.get("weight", 1)}
        for e in reg
        if e.get("platforms")
    ]


def project_huntability(title: str, content: str) -> dict[str, Any]:
    """Huntability projection — delegates to the (registry-derived) ThreatHuntingScorer."""
    from src.utils.content import ThreatHuntingScorer

    return ThreatHuntingScorer.score_threat_hunting_content(title, content)


_platform_classifier = None


def project_platform(content: str):
    """Platform projection — PlatformClassifier sourced from the registry's platform entries.

    Parity-equivalent to ``platform_classifier.classify_platforms`` because the registry's
    platform entries are the migrated ``platform_classification_kb.yaml`` vocabulary.
    """
    global _platform_classifier
    if _platform_classifier is None:
        from src.services.platform_classifier import PlatformClassifier

        _platform_classifier = PlatformClassifier(entries=platform_entries())
    return _platform_classifier.classify(content)


def build_os_classification(content: str, *, max_evidence: int = 8) -> dict[str, Any]:
    """Compute the compact OS-classification record stored in ``article_metadata`` at scoring
    time (Phase 2). Same shape as ``OSDetectionService.detect_os`` output (so ``os_detection_node``
    can consume it in Phase 3), with per-platform evidence capped to bound metadata size.
    """
    result = project_platform(content).as_os_result()
    evidence = result.get("evidence") or {}
    result["evidence"] = {platform: list(items)[:max_evidence] for platform, items in evidence.items()}
    return result
