"""Entity-driven platform classifier (Phase A: Windows / Linux / macOS).

Deterministic keyword/entity knowledge-base scoring with margin-based confidence.
No LLM, no embedding model -- fast, free, and explainable. Replaces the
embedding-similarity OS detector as the primary article-level platform classifier.

See docs/superpowers/specs/2026-06-19-entity-driven-platform-classification-design.md.

Design points:
- Confidence is derived from evidence weight AND the margin between the top two
  platforms -- never a flat score. A near-tie is never "high" (the failure mode of
  the embedding detector, which reported "high" on ~0.04 margins).
- Weak evidence below an absolute floor does not claim a platform (returns
  ``unknown``/``low``), honoring the phase-one rule against inferring an OS from
  generic signals.
- Multi-label by design: a genuinely mixed article emits multiple platforms.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

PLATFORM_WINDOWS = "windows"
PLATFORM_LINUX = "linux"
PLATFORM_MACOS = "macos"
SUPPORTED_PLATFORMS = (PLATFORM_WINDOWS, PLATFORM_LINUX, PLATFORM_MACOS)

_CANONICAL_OS_LABEL = {PLATFORM_WINDOWS: "Windows", PLATFORM_LINUX: "Linux", PLATFORM_MACOS: "MacOS"}

DEFAULT_KB_PATH = Path(__file__).resolve().parents[2] / "config" / "platform_classification_kb.yaml"

# Tuning constants (see spec §5.3).
MIN_EVIDENCE_WEIGHT = 3.0  # top platform must reach this weight to claim a platform at all
HIGH_MARGIN = 0.5  # single dominant platform leading by >= this fraction of its score => "high"
MULTI_LABEL_FRACTION = 0.5  # a platform scoring >= this fraction of the top is co-labelled


@dataclass
class PlatformClassification:
    """Result of platform classification for one article."""

    platforms: list[str]  # canonical lowercase labels, e.g. ["linux"] or ["windows", "linux"]
    primary: str  # top platform, or "unknown"
    confidence: str  # "high" | "medium" | "low"
    scores: dict[str, float]  # raw weighted score per platform
    evidence: dict[str, list[str]] = field(default_factory=dict)  # matched entities per platform
    method: str = "kb_scoring"

    def as_os_result(self) -> dict[str, Any]:
        """Map to the OSDetectionService.detect_os return shape (backward-compatible).

        The workflow consumes ``platforms_detected`` (a list) directly and falls back
        to ``operating_system``/``similarities`` for display.
        """
        if not self.platforms:
            operating_system = "Unknown"
        elif len(self.platforms) > 1:
            operating_system = "multiple"
        else:
            operating_system = _CANONICAL_OS_LABEL.get(self.platforms[0], "Unknown")

        total = sum(self.scores.values()) or 1.0
        similarities = {_CANONICAL_OS_LABEL[p]: round(self.scores.get(p, 0.0) / total, 2) for p in SUPPORTED_PLATFORMS}
        return {
            "operating_system": operating_system,
            "method": self.method,
            "confidence": self.confidence,
            "similarities": similarities,
            "max_similarity": max(similarities.values()) if similarities else 0.0,
            "platforms_detected": [_CANONICAL_OS_LABEL[p] for p in self.platforms],
            "evidence": self.evidence,
        }


class PlatformClassifier:
    """Scores article content against an entity->platform knowledge base."""

    def __init__(
        self,
        entries: list[dict[str, Any]] | None = None,
        kb_path: Path | str | None = None,
        attack_map: dict[str, list[str]] | None = None,
        attack_map_path: Path | str | None = None,
    ):
        if entries is not None:
            self._entries = entries
        else:
            path = Path(kb_path) if kb_path else DEFAULT_KB_PATH
            self._entries = self._load_kb(path)
        # ATT&CK technique -> platform signal (Phase C). Loaded from the shipped map
        # unless an explicit map is injected (tests). Empty map => KB-only behavior.
        if attack_map is not None:
            self._attack_map = attack_map
        else:
            from src.services.attack_platform_signal import load_attack_map

            self._attack_map = load_attack_map(attack_map_path)

    @staticmethod
    def _load_kb(path: Path) -> list[dict[str, Any]]:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            entries = data.get("entities", []) if isinstance(data, dict) else []
            return [e for e in entries if isinstance(e, dict) and e.get("match") and e.get("platforms")]
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"PlatformClassifier: failed to load KB {path}: {e}")
            return []

    def classify(self, content: str) -> PlatformClassification:
        text = (content or "").lower()
        scores: dict[str, float] = {p: 0.0 for p in SUPPORTED_PLATFORMS}
        evidence: dict[str, list[str]] = {p: [] for p in SUPPORTED_PLATFORMS}

        for entry in self._entries:
            token = str(entry.get("match", "")).lower()
            if not token or token not in text:
                continue
            weight = float(entry.get("weight", 1))
            for platform in entry.get("platforms", []):
                if platform in scores:
                    scores[platform] += weight
                    evidence[platform].append(str(entry.get("match")))

        # ATT&CK technique citations REINFORCE platforms the entity KB already has
        # evidence for; they do not originate a classification on their own. Technique
        # citations enumerate threat capabilities and often span platforms, so a KB-blank
        # article defers to LLM adjudication for precise narrowing rather than being
        # committed to a (possibly multi-platform) verdict from citations alone.
        if self._attack_map:
            from src.services.attack_platform_signal import technique_platform_votes

            att_scores, att_evidence = technique_platform_votes(content, self._attack_map)
            for platform in scores:
                if scores[platform] > 0:
                    scores[platform] += att_scores.get(platform, 0.0)
                    evidence[platform].extend(att_evidence.get(platform, []))

        return self._score(scores, evidence)

    @staticmethod
    def _score(scores: dict[str, float], evidence: dict[str, list[str]]) -> PlatformClassification:
        # Rank platforms by score (desc), stable tiebreak by canonical platform order.
        ranked = sorted(SUPPORTED_PLATFORMS, key=lambda p: (-scores[p], SUPPORTED_PLATFORMS.index(p)))
        top = ranked[0]
        top_score = scores[top]
        second_score = scores[ranked[1]] if len(ranked) > 1 else 0.0

        # Below the evidence floor: do not claim a platform (avoid generic-signal inference).
        if top_score < MIN_EVIDENCE_WEIGHT:
            return PlatformClassification(
                platforms=[], primary="unknown", confidence="low", scores=scores, evidence=evidence
            )

        labels = [p for p in ranked if scores[p] > 0 and scores[p] >= MULTI_LABEL_FRACTION * top_score]
        margin = (top_score - second_score) / top_score if top_score else 0.0

        if len(labels) == 1 and margin >= HIGH_MARGIN:
            confidence = "high"
        else:
            confidence = "medium"

        return PlatformClassification(
            platforms=labels, primary=top, confidence=confidence, scores=scores, evidence=evidence
        )


_default_classifier: PlatformClassifier | None = None


def classify_platforms(content: str) -> PlatformClassification:
    """Classify using a process-wide default classifier (loads the shipped KB once)."""
    global _default_classifier
    if _default_classifier is None:
        _default_classifier = PlatformClassifier()
    return _default_classifier.classify(content)
