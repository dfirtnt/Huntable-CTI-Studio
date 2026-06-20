"""Generic entity-dimension classifier for the Domains and Products axes (Phase D).

Mirrors the platform gate's keyword/entity KB scoring, generalized over an arbitrary
label set. Domains are independent multi-label (an article can be Identity AND Email AND
Cloud at once), so every label at or above the evidence floor is emitted. Products are
presence-based named-entity detection (deduped by product name).

See docs/superpowers/specs/2026-06-19-entity-driven-platform-classification-design.md (Phase D).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
DOMAIN_KB_PATH = _CONFIG_DIR / "domain_classification_kb.yaml"
PRODUCT_KB_PATH = _CONFIG_DIR / "product_classification_kb.yaml"

# Controlled domain vocabulary (Phase D).
DOMAIN_LABELS = ["Identity", "Cloud", "Network", "Endpoint", "Email", "OT/ICS", "SaaS"]

# A domain label needs at least this much weighted evidence to be emitted.
DOMAIN_FLOOR = 2.0


@dataclass
class DimensionClassification:
    labels: list[str]
    scores: dict[str, float]
    evidence: dict[str, list[str]] = field(default_factory=dict)


def classify_dimension(
    content: str, entries: list[dict[str, Any]], labels: list[str], floor: float = DOMAIN_FLOOR
) -> DimensionClassification:
    """Score ``content`` against ``entries`` over ``labels``; emit every label >= floor."""
    text = (content or "").lower()
    scores: dict[str, float] = {label: 0.0 for label in labels}
    evidence: dict[str, list[str]] = {label: [] for label in labels}

    for entry in entries:
        token = str(entry.get("match", "")).lower()
        if not token or token not in text:
            continue
        weight = float(entry.get("weight", 1))
        for label in entry.get("labels", []):
            if label in scores:
                scores[label] += weight
                evidence[label].append(str(entry.get("match")))

    emitted = sorted(
        (label for label in labels if scores[label] >= floor),
        key=lambda label: (-scores[label], labels.index(label)),
    )
    return DimensionClassification(labels=emitted, scores=scores, evidence=evidence)


def classify_products(content: str, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Presence-based named-product detection, deduped by product name."""
    text = (content or "").lower()
    found: dict[str, list[str]] = {}
    for entry in entries:
        token = str(entry.get("match", "")).lower()
        product = entry.get("product")
        if not token or not product or token not in text:
            continue
        found.setdefault(str(product), [])
        if entry.get("match") not in found[str(product)]:
            found[str(product)].append(str(entry.get("match")))
    return [{"product": name, "evidence": ev} for name, ev in found.items()]


def _load_kb(path: Path, key: str) -> list[dict[str, Any]]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return list(data.get(key, [])) if isinstance(data, dict) else []
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"entity_dimension_classifier: failed to load {path}: {e}")
        return []


_domain_entries: list[dict[str, Any]] | None = None
_product_entries: list[dict[str, Any]] | None = None


def classify_domains(content: str) -> DimensionClassification:
    """Classify the Domain dimension using the shipped domain KB."""
    global _domain_entries
    if _domain_entries is None:
        _domain_entries = _load_kb(DOMAIN_KB_PATH, "entities")
    return classify_dimension(content, _domain_entries, DOMAIN_LABELS)


def classify_named_products(content: str) -> list[dict[str, Any]]:
    """Detect named Products using the shipped product KB."""
    global _product_entries
    if _product_entries is None:
        _product_entries = _load_kb(PRODUCT_KB_PATH, "entities")
    return classify_products(content, _product_entries)
