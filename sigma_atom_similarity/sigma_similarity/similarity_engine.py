"""
Similarity engine: orchestrate canonical class, normalization, DNF, atoms, surface,
containment, filter penalty, and final similarity. No global state.
"""

import yaml

from sigma_similarity.ast_builder import build_ast
from sigma_similarity.atom_extractor import (
    extract_negative_atoms,
    extract_positive_atoms,
)
from sigma_similarity.canonical_logsource import resolve_canonical_class
from sigma_similarity.containment_estimator import compute_containment
from sigma_similarity.detection_normalizer import normalize_detection
from sigma_similarity.dnf_normalizer import ast_to_dnf
from sigma_similarity.errors import DeterministicExpansionLimitError
from sigma_similarity.filter_analyzer import filter_penalty
from sigma_similarity.models import SimilarityResult
from sigma_similarity.surface_estimator import surface_score_from_dnf


def _rule_to_dict(rule: dict | str) -> dict:
    """Parse rule from dict or YAML string."""
    if isinstance(rule, dict):
        return rule
    if isinstance(rule, str):
        data = yaml.safe_load(rule)
        if not isinstance(data, dict):
            raise ValueError("Rule must be a dict or YAML string producing a dict")
        return data
    raise ValueError("Rule must be dict or str")


def _zero_result(
    canonical_class: str,
    reason_flags: list[str],
    surface_a: float = 0.0,
    surface_b: float = 0.0,
    overlap_ratio_a: float = 0.0,
    overlap_ratio_b: float = 0.0,
    filter_penalty_val: float = 0.0,
) -> SimilarityResult:
    """Build SimilarityResult with similarity=0 and given reason_flags."""
    return SimilarityResult(
        similarity=0.0,
        jaccard=0.0,
        containment_factor=0.65,
        filter_penalty=filter_penalty_val,
        surface_score_a=surface_a,
        surface_score_b=surface_b,
        canonical_class=canonical_class,
        explanation={
            "reason_flags": reason_flags,
            "overlap_ratio_a": overlap_ratio_a,
            "overlap_ratio_b": overlap_ratio_b,
        },
    )


def compare_rules(rule_a: dict | str, rule_b: dict | str) -> SimilarityResult:
    """
    Compare two Sigma rules. Returns full SimilarityResult.
    UnknownTelemetryClassError and UnsupportedSigmaFeatureError are propagated.
    DeterministicExpansionLimitError is caught and converted to result with reason_flags.
    """
    ra = _rule_to_dict(rule_a)
    rb = _rule_to_dict(rule_b)

    # 1–2. Canonical class: raise on unknown; return 0 on mismatch
    try:
        class_a = resolve_canonical_class(ra)
    except Exception:
        raise
    try:
        class_b = resolve_canonical_class(rb)
    except Exception:
        raise
    if class_a != class_b:
        return _zero_result(
            canonical_class="",
            reason_flags=["canonical_class_mismatch"],
        )

    # 3. Normalize detection (may raise UnsupportedSigmaFeatureError)
    norm_a = normalize_detection(ra.get("detection") or {})
    norm_b = normalize_detection(rb.get("detection") or {})

    # 4. Build ASTs and DNF; catch DeterministicExpansionLimitError
    ast_a = build_ast(norm_a)
    ast_b = build_ast(norm_b)
    try:
        dnf_a = ast_to_dnf(ast_a)
        dnf_b = ast_to_dnf(ast_b)
    except DeterministicExpansionLimitError:
        return _zero_result(
            canonical_class=class_a,
            reason_flags=["dnf_expansion_limit"],
        )

    # 5. Extract atoms
    A1 = extract_positive_atoms(dnf_a)
    A2 = extract_positive_atoms(dnf_b)
    F1 = extract_negative_atoms(dnf_a)
    F2 = extract_negative_atoms(dnf_b)

    surface_a = surface_score_from_dnf(dnf_a)
    surface_b = surface_score_from_dnf(dnf_b)

    intersection = A1 & A2
    union = A1 | A2
    no_shared = len(intersection) == 0

    F = filter_penalty(F1, F2, len(A1), len(A2))

    if no_shared:
        return SimilarityResult(
            similarity=0.0,
            jaccard=0.0,
            containment_factor=0.65,
            filter_penalty=F,
            surface_score_a=surface_a,
            surface_score_b=surface_b,
            canonical_class=class_a,
            explanation={
                "reason_flags": ["no_shared_atoms"],
                "overlap_ratio_a": 0.0,
                "overlap_ratio_b": 0.0,
            },
        )

    # 7. Jaccard
    J = len(intersection) / len(union) if union else 0.0

    # 8. Containment
    B, overlap_ratio_a, overlap_ratio_b = compute_containment(len(intersection), len(A1), len(A2), surface_a, surface_b)

    # 10. Final similarity
    sim = (J * B) - F
    sim = max(0.0, min(1.0, sim))

    return SimilarityResult(
        similarity=sim,
        jaccard=J,
        containment_factor=B,
        filter_penalty=F,
        surface_score_a=surface_a,
        surface_score_b=surface_b,
        canonical_class=class_a,
        explanation={
            "reason_flags": [],
            "overlap_ratio_a": overlap_ratio_a,
            "overlap_ratio_b": overlap_ratio_b,
        },
    )
