"""Characterization tests for agentic workflow helper functions."""

import pytest

from src.workflows.agentic_workflow import (
    _all_extractors_errored,
    _bool_from_value,
    _extract_actual_count,
    _is_agent_allowed,
    _parse_agent_result,
)

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


# ---------------------------------------------------------------------------
# _parse_agent_result -- extracted from the supervisor loop
# ---------------------------------------------------------------------------


class TestParseAgentResult:
    """Tests for the per-agent result parser extracted from extract_agent_node."""

    def test_hunt_queries_normalizes_field_names(self):
        """LLM may return platform/query_text/source_context; UI expects type/query/context."""
        raw = {
            "queries": [
                {"platform": "KQL", "query_text": "process | where", "source_context": "endpoint"},
            ],
            "count": 1,
        }
        items, entry = _parse_agent_result("HuntQueriesExtract", "hunt_queries", raw)
        assert len(items) == 1
        assert items[0]["type"] == "KQL"
        assert items[0]["query"] == "process | where"
        assert items[0]["context"] == "endpoint"
        assert entry["query_count"] == 1
        assert entry["queries"] is items

    def test_hunt_queries_preserves_canonical_field_names(self):
        """When the LLM already uses the canonical names, they pass through unchanged."""
        raw = {
            "queries": [
                {"type": "sigma", "query": "title: Test", "context": "detection"},
            ],
            "count": 1,
        }
        items, entry = _parse_agent_result("HuntQueriesExtract", "hunt_queries", raw)
        assert items[0]["type"] == "sigma"
        assert items[0]["query"] == "title: Test"

    def test_hunt_queries_legacy_query_count_fallback(self):
        """When `count` is absent, falls back to `query_count`."""
        raw = {"queries": [{"type": "kql", "query": "q1", "context": ""}], "query_count": 5}
        items, entry = _parse_agent_result("HuntQueriesExtract", "hunt_queries", raw)
        assert entry["query_count"] == 5

    def test_hunt_queries_count_defaults_to_len(self):
        """When both count fields are absent, defaults to len(queries)."""
        raw = {"queries": [{"type": "a", "query": "b", "context": "c"}]}
        items, entry = _parse_agent_result("HuntQueriesExtract", "hunt_queries", raw)
        assert entry["query_count"] == 1

    def test_standard_agent_uses_result_key(self):
        """Standard agents look up items by result_key first."""
        raw = {"cmdline": [{"cmd": "whoami"}], "other": "stuff"}
        items, entry = _parse_agent_result("CmdlineExtract", "cmdline", raw)
        assert items == [{"cmd": "whoami"}]
        assert entry["count"] == 1

    def test_standard_agent_cmdline_items_fallback(self):
        """CmdlineExtract has a legacy cmdline_items field fallback."""
        raw = {"cmdline_items": [{"cmd": "dir"}]}
        items, entry = _parse_agent_result("CmdlineExtract", "cmdline", raw)
        assert items == [{"cmd": "dir"}]

    def test_standard_agent_items_fallback(self):
        """Generic 'items' key is used when result_key is missing."""
        raw = {"items": ["a", "b"]}
        items, entry = _parse_agent_result("ProcTreeExtract", "process_lineage", raw)
        assert items == ["a", "b"]

    def test_standard_agent_first_list_fallback(self):
        """When no known key exists, the first list value is used."""
        raw = {"status": "ok", "data": [1, 2, 3]}
        items, entry = _parse_agent_result("ServicesExtract", "services", raw)
        assert items == [1, 2, 3]

    def test_error_fields_copied_uniformly(self):
        """Error fields are copied regardless of agent type."""
        raw = {
            "items": [],
            "error": "timeout",
            "error_details": "LLM timed out",
            "error_type": "llm_timeout",
        }
        _, entry = _parse_agent_result("ProcTreeExtract", "process_lineage", raw)
        assert entry["error"] == "timeout"
        assert entry["error_details"] == "LLM timed out"
        assert entry["error_type"] == "llm_timeout"

    def test_no_error_fields_when_absent(self):
        """When there's no error, no error keys appear in the entry."""
        raw = {"items": []}
        _, entry = _parse_agent_result("ProcTreeExtract", "process_lineage", raw)
        assert "error" not in entry


# ---------------------------------------------------------------------------
# _is_agent_allowed -- consolidated eval-blocking check
# ---------------------------------------------------------------------------


class _FakeExecution:
    """Minimal stand-in for AgenticWorkflowExecutionTable."""

    def __init__(self, config_snapshot=None):
        self.config_snapshot = config_snapshot


class TestIsAgentAllowed:
    """Tests for the consolidated eval-blocking helper."""

    def test_no_eval_filter_allows_all(self):
        """With no subagent_eval, every agent is allowed."""
        assert _is_agent_allowed("CmdlineExtract", None, None, None, 1) is True

    def test_matching_subagent_eval_allows(self):
        """Agent whose subagent alias matches the eval filter is allowed."""
        exec_ = _FakeExecution(config_snapshot={"subagent_eval": "cmdline"})
        assert _is_agent_allowed("CmdlineExtract", exec_, "cmdline", None, 1) is True

    def test_non_matching_subagent_eval_blocks(self):
        """Agent whose subagent alias does NOT match the eval filter is blocked."""
        exec_ = _FakeExecution(config_snapshot={"subagent_eval": "cmdline"})
        assert _is_agent_allowed("ProcTreeExtract", exec_, "cmdline", None, 1) is False

    def test_fallback_to_variable_when_execution_missing(self):
        """When execution is None, falls back to the subagent_eval variable."""
        assert _is_agent_allowed("CmdlineExtract", None, "cmdline", None, 1) is True
        assert _is_agent_allowed("ProcTreeExtract", None, "cmdline", None, 1) is False

    def test_eval_lookup_values_merged(self):
        """Pre-computed eval_lookup_values are merged into the check."""
        assert _is_agent_allowed(
            "HuntQueriesExtract", None, None, {"hunt_queries"}, 1
        ) is True
        assert _is_agent_allowed(
            "CmdlineExtract", None, None, {"hunt_queries"}, 1
        ) is False

    def test_agent_name_match(self):
        """Agent name (lowercased) is also checked, not just the subagent alias."""
        exec_ = _FakeExecution(config_snapshot={"subagent_eval": "cmdlineextract"})
        assert _is_agent_allowed("CmdlineExtract", exec_, None, None, 1) is True

    def test_empty_eval_allows(self):
        """Empty string subagent_eval is treated as no filter."""
        exec_ = _FakeExecution(config_snapshot={"subagent_eval": ""})
        assert _is_agent_allowed("ProcTreeExtract", exec_, "", None, 1) is True


class TestAllExtractorsErrored:
    """Tests for _all_extractors_errored -- the workflow_completed success gate."""

    def _sr(self, error: str | None = None, status: str | None = None) -> dict:
        raw = {}
        if status:
            raw["status"] = status
        if error:
            raw["error"] = error
        return {"error": error, "raw": raw} if error else {"raw": raw}

    def test_all_errored_returns_true_with_reason(self):
        """When every subagent has an error, returns (True, reason)."""
        extraction = {
            "subresults": {
                "AgentA": self._sr(error="LMStudio is not ready"),
                "AgentB": self._sr(error="LMStudio is not ready"),
            }
        }
        all_failed, reason = _all_extractors_errored(extraction)
        assert all_failed is True
        assert reason is not None
        assert "2 extractor(s) failed" in reason

    def test_one_success_returns_false(self):
        """If any subagent succeeded (no error), returns (False, None)."""
        extraction = {
            "subresults": {
                "AgentA": self._sr(error="LMStudio is not ready"),
                "AgentB": {"raw": {}, "error": None},  # success
            }
        }
        all_failed, reason = _all_extractors_errored(extraction)
        assert all_failed is False
        assert reason is None

    def test_skipped_for_eval_not_counted(self):
        """Subagents skipped for eval are excluded; remaining non-skipped must all error."""
        extraction = {
            "subresults": {
                "AgentA": self._sr(error="some error"),
                "AgentB": self._sr(status="skipped_for_eval"),
            }
        }
        all_failed, reason = _all_extractors_errored(extraction)
        assert all_failed is True

    def test_only_skipped_returns_false(self):
        """If all subagents were skipped, no executed agents means returns (False, None)."""
        extraction = {
            "subresults": {
                "AgentA": self._sr(status="skipped_for_eval"),
            }
        }
        all_failed, reason = _all_extractors_errored(extraction)
        assert all_failed is False

    def test_none_input_returns_false(self):
        all_failed, reason = _all_extractors_errored(None)
        assert all_failed is False
        assert reason is None

    def test_empty_subresults_returns_false(self):
        all_failed, reason = _all_extractors_errored({"subresults": {}})
        assert all_failed is False

    def test_reason_deduplicates_identical_errors(self):
        """Identical error messages across agents are deduplicated in the reason string."""
        msg = "LMStudio is not ready"
        extraction = {
            "subresults": {
                "AgentA": self._sr(error=msg),
                "AgentB": self._sr(error=msg),
                "AgentC": self._sr(error=msg),
            }
        }
        all_failed, reason = _all_extractors_errored(extraction)
        assert all_failed is True
        # deduplicated: only one copy of the error message
        assert reason.count(msg) == 1


class TestDeadCodeRemoval:
    """Regression tests verifying dead code was removed and stays removed."""

    def _get_source(self):
        import inspect

        import src.workflows.agentic_workflow as wf
        return inspect.getsource(wf)

    def test_rag_service_not_imported(self):
        """RAGService was a bare instantiation with discarded result; import must be gone."""
        import src.workflows.agentic_workflow as wf
        assert not hasattr(wf, "RAGService"), "RAGService should not be imported into the module namespace"

    def test_bare_rag_service_call_absent(self):
        """The bare RAGService() expression must not exist in the source."""
        src = self._get_source()
        # Allow the class name in comments or strings, but not as a bare call
        import re
        assert not re.search(r"^\s*RAGService\(\)", src, re.MULTILINE), \
            "Bare RAGService() call still present"

    def test_state_skip_flag_removed(self):
        """state_skip_flag was always-False (skip_os_detection not in WorkflowState); must be gone."""
        src = self._get_source()
        assert "state_skip_flag" not in src, "state_skip_flag should have been removed"

    def test_sigma_qa_bare_expressions_absent(self):
        """Bare qa_flags.get('SigmaAgent') and qa_max_retries expressions in sigma node must be gone."""
        src = self._get_source()
        # The bare expression pattern: line that is just the expression with no assignment
        import re
        assert not re.search(r"^\s*qa_flags\.get\(['\"]SigmaAgent", src, re.MULTILINE), \
            "Bare qa_flags.get('SigmaAgent') expression still present"

    def test_novelty_score_not_in_state_return(self):
        """novelty_score was written to state but absent from WorkflowState TypedDict; must be removed."""
        src = self._get_source()
        # novelty_score is still used as a local variable in data dicts -- we only care
        # that it's not being set as a top-level state return key.
        # Check the similarity_search return block doesn't contain '"novelty_score":' as a state key.
        import re
        assert not re.search(r'"novelty_score"\s*:\s*max_novelty_score', src), \
            '"novelty_score" state return key still present'
        assert not re.search(r'"novelty_results"\s*:\s*novelty_results.*New key', src), \
            '"novelty_results" duplicate state key still present'
