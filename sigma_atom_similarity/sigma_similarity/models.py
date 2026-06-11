"""
Data models for Sigma semantic similarity.

SimilarityResult is JSON-serializable with stable key order when serialized
via json.dumps(..., sort_keys=True, separators=(",", ":")).
"""

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class SimilarityResult:
    """Structured result of comparing two Sigma rules."""

    similarity: float
    jaccard: float
    containment_factor: float
    filter_penalty: float
    surface_score_a: float
    surface_score_b: float
    canonical_class: str
    explanation: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable dict. Use with sort_keys=True for stable output."""
        return asdict(self)
