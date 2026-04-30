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
    # Unified contract: prefer `count` (current envelope) over legacy `query_count` alias.
    subresults = {
        "hunt_queries": {
            "queries": ["q1", "q2"],
            "count": 9,
            "query_count": 3,
        }
    }
    assert _extract_actual_count("hunt_queries", subresults, execution_id=1) == 9

    # Legacy fallback: cached/in-flight executions may still emit only `query_count`.
    subresults_legacy_only = {"hunt_queries": {"queries": ["q1", "q2"], "query_count": 3}}
    assert _extract_actual_count("hunt_queries", subresults_legacy_only, execution_id=1) == 3

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


# ---------------------------------------------------------------------------
# Regression: HuntQueriesExtract envelope contract (count is the canonical field)
#
# Background: HuntQueriesExtract historically emitted `query_count` while every
# other extractor emitted `count`. That divergence forced
# test_subagent_traceability_contract.py to skip HuntQueriesExtract from the
# MIGRATED_EXTRACT_AGENTS contract, weakening the test.
#
# Decision (2026-04-30): converge to `count`. Keep `query_count` readable for
# one release as a legacy alias so cached/in-flight subresults stay countable.
# These tests pin the new contract so the divergence cannot silently regress.
# ---------------------------------------------------------------------------


def test_hunt_queries_envelope_canonical_count_wins_over_legacy_alias():
    """Regression: when both fields disagree, `count` is authoritative; `query_count`
    is a legacy alias kept readable for one release.

    Before convergence the priority was inverted (query_count > count), which is what
    forced the contract test to skip HuntQueriesExtract. Flip caught here.
    """
    subresults = {"hunt_queries": {"queries": ["a", "b"], "count": 2, "query_count": 99}}
    assert _extract_actual_count("hunt_queries", subresults, execution_id=1) == 2


def test_hunt_queries_envelope_legacy_only_still_readable():
    """Regression: cached executions written before convergence carry only `query_count`.
    Reads must still succeed -- this is the whole reason we keep the alias for a release."""
    subresults = {"hunt_queries": {"queries": ["a"], "query_count": 1}}
    assert _extract_actual_count("hunt_queries", subresults, execution_id=1) == 1


def test_hunt_queries_prompt_envelope_uses_count_not_query_count():
    """Regression: the prompt's json_example must declare `count`, not `query_count`.
    The runtime envelope builder mirrors the prompt schema; if the prompt drifts back
    to `query_count` the model gets contradictory instructions vs the runtime emit."""
    import json
    from pathlib import Path

    prompt_path = Path(__file__).resolve().parents[2] / "src" / "prompts" / "HuntQueriesExtract"
    prompt = json.loads(prompt_path.read_text(encoding="utf-8"))
    example = json.loads(prompt["json_example"])
    assert "count" in example, "json_example must expose `count`"
    assert "query_count" not in example, "json_example must NOT reintroduce legacy `query_count`"
    assert example["count"] == len(example.get("queries", [])), (
        "json_example count must equal len(queries) so the model sees a self-consistent example"
    )
    # Body of the prompt (task + instructions) must also be free of the legacy name --
    # otherwise the model gets a contradictory schema between example and instructions.
    assert "query_count" not in prompt["task"]
    assert "query_count" not in prompt["instructions"]
