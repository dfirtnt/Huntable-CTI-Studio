"""Characterization tests for agentic workflow helper functions."""

import pytest

from src.workflows.agentic_workflow import _bool_from_value, _extract_actual_count

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, True),
        (False, False),
        ("true", True),
        ("TRUE", True),
        ("false", False),
        ("anything_else", False),
        (1, True),
        (0, False),
        (None, False),
        ([], False),
        ([1], True),
    ],
)
def test_bool_from_value_characterization(value, expected):
    assert _bool_from_value(value) is expected


def test_extract_actual_count_hunt_queries_variants():
    subresults = {
        "hunt_queries": {
            "queries": ["q1", "q2"],
            "count": 9,
            "query_count": 3,
        }
    }
    assert _extract_actual_count("hunt_queries", subresults, execution_id=1) == 3

    subresults_without_query_count = {"hunt_queries": {"count": 7, "queries": ["q1", "q2"]}}
    assert _extract_actual_count("hunt_queries", subresults_without_query_count, execution_id=1) == 7

    subresults_with_queries_only = {"hunt_queries": {"queries": ["q1", "q2", "q3"]}}
    assert _extract_actual_count("hunt_queries", subresults_with_queries_only, execution_id=1) == 3


def test_extract_actual_count_hunt_queries_edr_and_standard_agents():
    assert (
        _extract_actual_count(
            "hunt_queries_edr",
            {"hunt_queries": {"query_count": 4}},
            execution_id=2,
        )
        == 4
    )

    assert (
        _extract_actual_count(
            "hunt_queries_edr",
            {"hunt_queries": {"queries": ["a", "b"]}},
            execution_id=2,
        )
        == 2
    )

    assert (
        _extract_actual_count(
            "cmdline",
            {"cmdline": {"count": 6, "items": ["x"]}},
            execution_id=3,
        )
        == 6
    )

    assert (
        _extract_actual_count(
            "process_lineage",
            {"process_lineage": {"items": ["a", "b"]}},
            execution_id=3,
        )
        == 2
    )

    # Characterization: missing standard subagent key currently falls back to empty dict -> 0.
    assert _extract_actual_count("cmdline", {"other": {}}, execution_id=3) == 0
