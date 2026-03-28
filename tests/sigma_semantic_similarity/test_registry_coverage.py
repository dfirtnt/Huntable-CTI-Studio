"""Registry coverage: every tuple in CANONICAL_CLASS_REGISTRY appears in exactly one class."""

import pytest
from sigma_similarity.canonical_logsource import CANONICAL_CLASS_REGISTRY


def test_every_tuple_in_exactly_one_canonical_class():
    """Every (product, category, service, event_id) appears in at most one canonical class."""
    tuple_to_class: dict[tuple, str] = {}
    for class_name, tuples in CANONICAL_CLASS_REGISTRY.items():
        for t in tuples:
            if t in tuple_to_class:
                pytest.fail(
                    f"Tuple {t} appears in both {tuple_to_class[t]!r} and {class_name!r}"
                )
            tuple_to_class[t] = class_name
