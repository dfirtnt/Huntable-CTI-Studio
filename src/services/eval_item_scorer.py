"""
Item-level precision/recall scorer for subagent evaluation.

Compares expected_items (ground truth) against actual_items (extracted by agent)
using relaxed string normalization to produce matched/missed/extra item lists and
precision/recall metrics.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


def _normalize(s: str) -> str:
    """Normalize a command-line string for comparison.

    - Lowercase
    - Strip leading/trailing whitespace
    - Collapse internal whitespace runs to a single space
    - Defang IOC bracket notation: [.] -> .  [:]  -> :
    """
    s = s.lower().strip()
    s = re.sub(r"\[\.\]", ".", s)
    s = re.sub(r"\[:\]", ":", s)
    s = re.sub(r"\s+", " ", s)
    return s


@dataclass
class ItemScorerResult:
    precision: float  # TP / (TP + FP)
    recall: float  # TP / (TP + FN)
    matched: list[str]  # items in both expected and actual (using actual text)
    missed: list[str]  # in expected but not in actual
    extra: list[str]  # in actual but not in expected
    matched_count: int
    missed_count: int
    extra_count: int


def score_items(
    expected_items: list[str],
    actual_items: list[str],
) -> ItemScorerResult:
    """Compare expected vs actual item lists and return precision/recall metrics.

    Uses set-based matching on normalized strings so duplicates on either side
    are deduplicated before scoring.  This mirrors how a true-positive is counted
    in information-retrieval evaluation: each unique expected item is either found
    or not, regardless of how many times the agent emitted it.
    """
    if not isinstance(expected_items, list):
        expected_items = list(expected_items) if expected_items else []
    if not isinstance(actual_items, list):
        actual_items = list(actual_items) if actual_items else []

    # Build normalized -> original maps (first occurrence wins on duplicates)
    norm_to_expected: dict[str, str] = {}
    for item in expected_items:
        k = _normalize(str(item))
        if k and k not in norm_to_expected:
            norm_to_expected[k] = str(item)

    norm_to_actual: dict[str, str] = {}
    for item in actual_items:
        k = _normalize(str(item))
        if k and k not in norm_to_actual:
            norm_to_actual[k] = str(item)

    expected_keys = set(norm_to_expected)
    actual_keys = set(norm_to_actual)

    matched_keys = expected_keys & actual_keys
    missed_keys = expected_keys - actual_keys
    extra_keys = actual_keys - expected_keys

    matched = [norm_to_actual[k] for k in sorted(matched_keys)]
    missed = [norm_to_expected[k] for k in sorted(missed_keys)]
    extra = [norm_to_actual[k] for k in sorted(extra_keys)]

    tp = len(matched_keys)
    fp = len(extra_keys)
    fn = len(missed_keys)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0

    return ItemScorerResult(
        precision=round(precision, 4),
        recall=round(recall, 4),
        matched=matched,
        missed=missed,
        extra=extra,
        matched_count=tp,
        missed_count=fn,
        extra_count=fp,
    )
