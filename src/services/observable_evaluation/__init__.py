"""
Observable extraction model evaluation system.

Provides evaluation and metrics pipeline for observable extraction models
(CMD, PROC_LINEAGE, etc.) with separate eval and gold dataset support.
"""

from src.services.observable_evaluation.evaluator import ObservableModelEvaluator
from src.services.observable_evaluation.model_inference import ObservableModelInference
from src.services.observable_evaluation.pipeline import ObservableEvaluationPipeline
from src.services.observable_evaluation.span_normalization import (
    compute_span_length_delta,
    compute_token_overlap,
    is_exact_match,
    normalize_span,
)

__all__ = [
    "ObservableEvaluationPipeline",
    "ObservableModelEvaluator",
    "ObservableModelInference",
    "normalize_span",
    "compute_token_overlap",
    "is_exact_match",
    "compute_span_length_delta",
]
