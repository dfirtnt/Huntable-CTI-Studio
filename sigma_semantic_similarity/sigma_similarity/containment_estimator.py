"""
Containment factor B and overlap ratios. Evaluate before J threshold.
Equivalent / Subset / Superset / Else per spec.
"""


def compute_containment(
    intersection_size: int,
    size_a: int,
    size_b: int,
    surface_a: float,
    surface_b: float,
) -> tuple[float, float, float]:
    """Compute containment factor B and overlap_ratio_a, overlap_ratio_b.

    Returns (B, overlap_ratio_a, overlap_ratio_b).
    """
    if size_a <= 0:
        overlap_a = 0.0
    else:
        overlap_a = intersection_size / size_a
    if size_b <= 0:
        overlap_b = 0.0
    else:
        overlap_b = intersection_size / size_b

    surface_max = max(surface_a, surface_b)
    if surface_max <= 0:
        surface_ratio = 0.0
    else:
        surface_ratio = abs(surface_a - surface_b) / surface_max

    # Equivalent: overlap_ratio_a >= 0.9 and overlap_ratio_b >= 0.9 and surface_ratio <= 0.10
    if overlap_a >= 0.9 and overlap_b >= 0.9 and surface_ratio <= 0.10:
        B = 1.0
    # Subset: overlap_ratio_a >= 0.9 and surface_a < surface_b
    elif overlap_a >= 0.9 and surface_a < surface_b:
        B = 0.85
    # Superset: overlap_ratio_b >= 0.9 and surface_a > surface_b
    elif overlap_b >= 0.9 and surface_a > surface_b:
        B = 0.75
    else:
        B = 0.65

    return (B, overlap_a, overlap_b)
