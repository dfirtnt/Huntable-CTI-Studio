"""Unified serializer for Sigma similarity matches.

Phase 1 of the sigma-similarity unification
(docs/development/sigma-similarity-unification-plan-2026-06-05.md).

Every similarity endpoint currently hand-shapes the raw match dict emitted by
``SigmaMatchingService.assess_rule_novelty()`` differently (nesting, rounding,
field pruning, renaming). That divergence is why a fix in one surface does not
propagate to the others. ``serialize_similarity_match`` projects a raw match
onto a single canonical contract so all endpoints emit the same shape.

Responses are canonical-only. The serializer originally also emitted additive
legacy aliases (`similarity_score`, `similarity_breakdown`) so it could be wired
into every route without a flag day; those were retired in Phase 5 once all
surfaces moved onto the shared similarity-display.js component. (The component's
``normalizeSimilarityData`` keeps reading those aliases as a defensive adapter.)
"""

from __future__ import annotations

from typing import Any

# Single rounding policy for every similarity metric (was per-route before).
_PRECISION = 4


def _round(value: Any) -> Any:
    """Round a numeric metric to the canonical precision, preserving None."""
    if value is None:
        return None
    try:
        return round(float(value), _PRECISION)
    except (TypeError, ValueError):
        return value


def serialize_similarity_match(match: dict[str, Any]) -> dict[str, Any]:
    """Project a raw engine match onto the canonical similarity contract.

    Canonical ``containment`` is lifted out of ``semantic_details`` (where the
    deterministic engine stores it as ``overlap_ratio_a``) so every surface reads
    directional containment the same way — the divergence behind the 2026-06-05
    containment bug.
    """
    semantic_details = match.get("semantic_details") or None

    similarity = _round(match.get("similarity", 0.0))
    atom_jaccard = _round(match.get("atom_jaccard", 0.0))
    logic_shape = _round(match.get("logic_shape_similarity"))  # None preserved
    containment = _round((semantic_details or {}).get("overlap_ratio_a"))

    return {
        # --- identity / metadata ---
        "id": match.get("id"),
        "rule_id": match.get("rule_id"),
        "title": match.get("title"),
        "description": match.get("description"),
        "logsource": match.get("logsource"),
        "detection": match.get("detection"),
        "tags": match.get("tags"),
        "level": match.get("level"),
        "status": match.get("status"),
        "file_path": match.get("file_path"),
        # --- canonical metrics ---
        "similarity": similarity,
        "atom_jaccard": atom_jaccard,
        "logic_shape_similarity": logic_shape,
        "containment": containment,
        "novelty_label": match.get("novelty_label"),
        "novelty_score": _round(match.get("novelty_score")),
        "similarity_engine": match.get("similarity_engine", "legacy"),
        # --- penalties (weighted subtotal vs final) ---
        "service_penalty": _round(match.get("service_penalty", 0.0)),
        "filter_penalty": _round(match.get("filter_penalty", 0.0)),
        "weighted_before_penalties": _round(match.get("weighted_before_penalties")),
        # --- explainability ---
        "shared_atoms": match.get("shared_atoms") or [],
        "added_atoms": match.get("added_atoms") or [],
        "removed_atoms": match.get("removed_atoms") or [],
        "filter_differences": match.get("filter_differences") or [],
        # --- deterministic engine detail (preserved for surfaces that read it) ---
        "semantic_details": semantic_details,
    }
