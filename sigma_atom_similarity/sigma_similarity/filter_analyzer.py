"""
Filter penalty from symmetric difference of negative atom sets.
F = min(0.5, len(extra_filters) / max(|A1|, |A2|)). Filters never increase similarity.
"""


def filter_penalty(
    negative_atoms_a: set[str],
    negative_atoms_b: set[str],
    positive_len_a: int,
    positive_len_b: int,
) -> float:
    """Compute filter penalty F. Never increases similarity."""
    extra = negative_atoms_a.symmetric_difference(negative_atoms_b)
    denom = max(positive_len_a, positive_len_b)
    if denom <= 0:
        return 0.0
    return min(0.5, len(extra) / denom)
