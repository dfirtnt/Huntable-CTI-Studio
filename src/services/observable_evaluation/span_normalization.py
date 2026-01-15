"""
Span normalization utilities for observable extraction evaluation.

Normalizes spans before comparison to ensure consistent evaluation
across different extraction methods.

Two normalization modes:
- relaxed: For eval datasets (whitespace, quotes, allows some flexibility)
- strict: For gold datasets (trim whitespace, normalize quotes, NO argument reordering, NO semantic canonicalization)
"""

import re
from typing import Literal

NormalizationMode = Literal["relaxed", "strict"]


def normalize_span(text: str, mode: NormalizationMode = "relaxed") -> str:
    """
    Normalize a span for comparison.
    
    Args:
        text: The span text to normalize
        mode: "relaxed" for eval, "strict" for gold
        
    Returns:
        Normalized span text
        
    Rules by mode:
    - relaxed (eval): Collapse whitespace, normalize quotes, preserve argument order
    - strict (gold): Trim whitespace, normalize quotes, NO argument reordering, NO semantic canonicalization
    """
    if not text:
        return ""
    
    if mode == "strict":
        # STRICT: Only trim whitespace and normalize quotes
        # NO argument reordering, NO semantic canonicalization
        normalized = text.strip()
        # Normalize quote types only (including smart quotes)
        normalized = re.sub(r'["""\u201C\u201D]', '"', normalized)
        normalized = re.sub(r'[\'\'\u2018\u2019]', "'", normalized)
        return normalized
    else:
        # RELAXED: Collapse whitespace, normalize quotes
        normalized = re.sub(r'\s+', ' ', text)
        normalized = re.sub(r'["""\u201C\u201D]', '"', normalized)
        normalized = re.sub(r'[\'\'\u2018\u2019]', "'", normalized)
        normalized = normalized.strip()
        return normalized


def compute_token_overlap(predicted: str, annotated: str, mode: NormalizationMode = "relaxed") -> float:
    """
    Compute token-level overlap (IoU) between predicted and annotated spans.
    
    Args:
        predicted: Predicted span text
        annotated: Annotated span text
        mode: Normalization mode ("relaxed" for eval, "strict" for gold)
        
    Returns:
        Token overlap F1 score (IoU) between 0.0 and 1.0
    """
    pred_normalized = normalize_span(predicted, mode)
    ann_normalized = normalize_span(annotated, mode)
    
    if not pred_normalized and not ann_normalized:
        return 1.0
    if not pred_normalized or not ann_normalized:
        return 0.0
    
    # Tokenize by splitting on whitespace
    pred_tokens = set(pred_normalized.split())
    ann_tokens = set(ann_normalized.split())
    
    if not pred_tokens and not ann_tokens:
        return 1.0
    if not pred_tokens or not ann_tokens:
        return 0.0
    
    # Compute intersection and union
    intersection = len(pred_tokens & ann_tokens)
    union = len(pred_tokens | ann_tokens)
    
    if union == 0:
        return 0.0
    
    return intersection / union


def is_exact_match(predicted: str, annotated: str, mode: NormalizationMode = "strict") -> bool:
    """
    Check if predicted span exactly matches annotated span after normalization.
    
    Args:
        predicted: Predicted span text
        annotated: Annotated span text
        mode: Normalization mode (defaults to "strict" for gold correctness)
        
    Returns:
        True if normalized spans are identical, False otherwise
    """
    return normalize_span(predicted, mode) == normalize_span(annotated, mode)


def compute_span_length_delta(predicted: str, annotated: str, mode: NormalizationMode = "relaxed") -> int:
    """
    Compute the difference in character length between predicted and annotated spans.
    
    Args:
        predicted: Predicted span text
        annotated: Annotated span text
        mode: Normalization mode
        
    Returns:
        Length delta (predicted_length - annotated_length)
    """
    pred_normalized = normalize_span(predicted, mode)
    ann_normalized = normalize_span(annotated, mode)
    return len(pred_normalized) - len(ann_normalized)

