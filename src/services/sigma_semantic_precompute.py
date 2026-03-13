"""
Precompute deterministic semantic fields for Sigma rules using sigma_similarity.

Used during indexing and backfill. Produces canonical_class, positive_atoms,
negative_atoms, surface_score for storage — eliminates recomputation during novelty comparison.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# sigma_similarity is optional
try:
    from sigma_similarity.ast_builder import build_ast
    from sigma_similarity.atom_extractor import extract_negative_atoms, extract_positive_atoms
    from sigma_similarity.canonical_logsource import resolve_canonical_class
    from sigma_similarity.detection_normalizer import normalize_detection
    from sigma_similarity.dnf_normalizer import ast_to_dnf
    from sigma_similarity.surface_estimator import surface_score_from_dnf

    _SIGMA_SIMILARITY_AVAILABLE = True
except ImportError:
    _SIGMA_SIMILARITY_AVAILABLE = False


def precompute_semantic_fields(rule_data: dict[str, Any]) -> dict[str, Any] | None:
    """
    Precompute canonical_class, positive_atoms, negative_atoms, surface_score for a rule.

    Uses sigma_similarity (no logic duplication). Returns None if package unavailable
    or rule raises UnknownTelemetryClassError / UnsupportedSigmaFeatureError / DeterministicExpansionLimitError.

    Returns:
        Dict with keys: canonical_class, positive_atoms, negative_atoms, surface_score
        or None if precomputation failed or sigma_similarity not installed.
    """
    if not _SIGMA_SIMILARITY_AVAILABLE:
        return None

    try:
        from sigma_similarity.errors import (
            DeterministicExpansionLimitError,
            UnknownTelemetryClassError,
            UnsupportedSigmaFeatureError,
        )
    except ImportError:
        return None

    try:
        canonical_class = resolve_canonical_class(rule_data)
        norm = normalize_detection(rule_data.get("detection") or {})
        ast = build_ast(norm)
        dnf = ast_to_dnf(ast)

        pos_set = extract_positive_atoms(dnf)
        neg_set = extract_negative_atoms(dnf)
        surface = surface_score_from_dnf(dnf)

        return {
            "canonical_class": canonical_class,
            "positive_atoms": sorted(pos_set),
            "negative_atoms": sorted(neg_set),
            "surface_score": int(surface),
        }
    except (UnknownTelemetryClassError, UnsupportedSigmaFeatureError, DeterministicExpansionLimitError) as e:
        logger.debug("Semantic precompute skipped for rule: %s", e)
        return None
    except Exception as e:
        logger.warning("Semantic precompute failed: %s", e)
        return None


def is_sigma_similarity_available() -> bool:
    """Return True if sigma_similarity package is installed."""
    return _SIGMA_SIMILARITY_AVAILABLE
