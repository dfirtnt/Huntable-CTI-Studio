"""
Sigma Semantic Similarity — deterministic rule comparison.

Public API: compare_rules, SimilarityResult, and error classes.
"""

from sigma_similarity.errors import (
    DeterministicExpansionLimitError,
    UnknownTelemetryClassError,
    UnsupportedSigmaFeatureError,
)
from sigma_similarity.models import SimilarityResult
from sigma_similarity.similarity_engine import compare_rules

__all__ = [
    "compare_rules",
    "SimilarityResult",
    "UnsupportedSigmaFeatureError",
    "UnknownTelemetryClassError",
    "DeterministicExpansionLimitError",
]
