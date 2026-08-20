"""Characterization tests for agentic workflow helper functions."""

import pytest

from src.workflows.agentic_workflow import (
    _agent_supported_for_platforms,
    _all_extractors_errored,
    _bool_from_value,
    _build_sigma_full_content_fallback_group,
    _build_sigma_generation_groups,
    _enrich_observable_metadata,
    _eval_snapshot,
    _extract_actual_count,
    _extraction_is_infra_failure,
    _has_sigma_generation_eligible_observables,
    _is_agent_allowed,
    _make_skip_record,
    _normalize_platform_value,
    _parse_agent_result,
    _platforms_from_os_detection,
    _rebase_group_observable_indices,
    _repair_empty_observable_attribution,
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


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Windows", "windows"),
        ("Linux", "linux"),
        ("MacOS", "macos"),
        ("multiple", "cross_platform"),
        ("darwin", "macos"),
        ("not-real", "unknown"),
    ],
)
def test_normalize_platform_value(value, expected):
    assert _normalize_platform_value(value) == expected


def test_platforms_from_os_detection_expands_multiple_similarity():
    platforms = _platforms_from_os_detection(
        "multiple",
        {"similarities": {"Windows": 0.7, "Linux": 0.6, "MacOS": 0.0}},
    )

    assert platforms == ["windows", "linux"]


def test_agent_capabilities_skip_windows_only_extractors_for_linux():
    assert _agent_supported_for_platforms("CmdlineExtract", ["linux"]) is True
    assert _agent_supported_for_platforms("RegistryExtract", ["linux"]) is False


def test_make_skip_record_has_stable_shape():
    record = _make_skip_record(
        agent_name="RegistryExtract",
        reason_code="unsupported_platform",
        reason="RegistryExtract supports windows only.",
        detected_platforms=["linux"],
        telemetry_categories=["registry"],
    )

    assert record["extractor"] == "RegistryExtract"
    assert record["status"] == "skipped"
    assert record["reason_code"] == "unsupported_platform"
    assert record["supported_platforms"] == ["windows"]
    assert record["detected_platforms"] == ["linux"]
    assert record["telemetry_categories"] == ["registry"]


def test_enrich_observable_metadata_adds_linux_process_logsource():
    obs = {"type": "cmdline", "value": "bash -c id", "source": "test"}

    _enrich_observable_metadata(obs, item="bash -c id", observable_type="cmdline", article_platforms=["linux"])

    assert obs["platform"] == "linux"
    assert obs["platform_confidence"] == "medium"
    assert obs["telemetry_category"] == "process_creation"
    assert obs["logsource_hint"] == {"product": "linux", "category": "process_creation"}


def test_enrich_observable_metadata_keeps_mixed_generic_command_unknown():
    obs = {"type": "cmdline", "value": "curl http://example", "source": "test"}

    _enrich_observable_metadata(
        obs,
        item="curl http://example",
        observable_type="cmdline",
        article_platforms=["windows", "linux"],
    )

    assert obs["platform"] == "unknown"
    assert obs["platform_confidence"] == "low"
    assert obs["telemetry_category"] == "process_creation"
    assert "logsource_hint" not in obs


def test_has_sigma_generation_eligible_observables_requires_logsource_hint():
    eligible = {
        "observables": [
            {
                "type": "cmdline",
                "platform": "linux",
                "telemetry_category": "process_creation",
                "logsource_hint": {"product": "linux", "category": "process_creation"},
            }
        ]
    }
    ineligible = {
        "observables": [
            {
                "type": "cmdline",
                "platform": "unknown",
                "telemetry_category": "process_creation",
            }
        ]
    }

    assert _has_sigma_generation_eligible_observables(eligible) is True
    assert _has_sigma_generation_eligible_observables(ineligible) is False


def test_sigma_generation_groups_split_mixed_windows_linux_by_logsource():
    extraction_result = {
        "observables": [
            {
                "type": "cmdline",
                "value": "cmd.exe /c whoami",
                "platform": "windows",
                "telemetry_category": "process_creation",
                "logsource_hint": {"product": "windows", "category": "process_creation"},
            },
            {
                "type": "cmdline",
                "value": "/bin/bash -c id",
                "platform": "linux",
                "telemetry_category": "process_creation",
                "logsource_hint": {"product": "linux", "category": "process_creation"},
            },
        ],
        "summary": {"platforms_detected": ["windows", "linux"]},
        "discrete_huntables_count": 2,
        "content": "cmd.exe /c whoami\n/bin/bash -c id",
    }

    groups = _build_sigma_generation_groups(extraction_result)

    assert [(g["platform"], g["telemetry_category"], g["original_indices"]) for g in groups] == [
        ("windows", "process_creation", [0]),
        ("linux", "process_creation", [1]),
    ]
    assert groups[0]["extraction_result"]["observables"][0]["original_observable_index"] == 0
    assert groups[1]["extraction_result"]["observables"][0]["original_observable_index"] == 1


def test_sigma_generation_groups_exclude_macos_for_phase_one():
    extraction_result = {
        "observables": [
            {
                "type": "cmdline",
                "value": "osascript -e id",
                "platform": "macos",
                "telemetry_category": "process_creation",
                "logsource_hint": {"product": "macos", "category": "process_creation"},
            }
        ]
    }

    assert _build_sigma_generation_groups(extraction_result) == []


def test_sigma_generation_groups_keep_ambiguous_command_display_only_without_logsource():
    extraction_result = {
        "observables": [
            {
                "type": "cmdline",
                "value": "python -m http.server",
                "platform": "unknown",
                "telemetry_category": "process_creation",
            }
        ]
    }

    assert _build_sigma_generation_groups(extraction_result) == []


def test_rebase_group_observable_indices_uses_execution_wide_indices():
    rule = {"observables_used": [0, 1, 99]}

    _rebase_group_observable_indices(rule, [3, 8])

    assert rule["observables_used"] == [3, 8]


def test_repair_empty_observable_attribution_infers_execution_wide_indices():
    rule = {
        "title": "Suspicious WScript from WhatsApp",
        "logsource": {"product": "windows", "category": "process_creation"},
        "detection": {
            "selection": {"CommandLine|contains|all": ["WhatsAppDesktop", "Transfers", ".vbs"]},
            "condition": "selection",
        },
        "observables_used": [],
    }
    extraction_result = {
        "observables": [
            {
                "type": "cmdline",
                "value": (
                    '"C:\\Windows\\System32\\WScript.exe" '
                    '"C:\\Users\\user\\AppData\\Local\\Packages\\5319275A.WhatsAppDesktop_cv1g1gvanyjgm'
                    '\\LocalState\\Sessions\\abc\\Transfers\\financial reports(s).vbs"'
                ),
            },
            {
                "type": "registry_artifacts",
                "value": "HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\System",
            },
        ]
    }

    _repair_empty_observable_attribution(
        rule,
        extraction_result=extraction_result,
        group_original_indices=[1],
        group_logsource_hint={"product": "windows", "category": "registry_event"},
    )

    assert rule["observables_used"] == [0]
    assert rule["observables_used_inferred"] is True
    assert rule["observable_attribution"] == "inferred"
    assert "logsource_mismatch" in rule["observable_attribution_warnings"]


def test_repair_empty_observable_attribution_warns_when_no_match():
    rule = {
        "title": "Generic Rule",
        "logsource": {"product": "windows", "category": "process_creation"},
        "detection": {"selection": {"CommandLine|contains": "not-present"}, "condition": "selection"},
        "observables_used": [],
    }
    extraction_result = {"observables": [{"type": "cmdline", "value": "powershell.exe -enc abc"}]}

    _repair_empty_observable_attribution(
        rule,
        extraction_result=extraction_result,
        group_original_indices=[0],
        group_logsource_hint={"product": "windows", "category": "process_creation"},
    )

    assert rule["observables_used"] == []
    assert rule["observable_attribution_warnings"] == ["empty_for_observable_group"]
    assert rule["observable_attribution"] == "attribution_failed"


def test_sigma_full_content_fallback_group_preserves_legacy_content_path():
    group = _build_sigma_full_content_fallback_group(
        {"summary": {"platforms_detected": ["linux"]}, "observables": [{"type": "cmdline"}]},
        content="full filtered article content",
        platforms_detected=["linux"],
    )

    assert group["platform"] == "linux"
    assert group["telemetry_category"] == "full_content"
    assert group["original_indices"] == []
    assert group["extraction_result"]["content"] == "full filtered article content"
    assert group["extraction_result"]["observables"] == []
    assert group["extraction_result"]["sigma_generation_group"]["generation_basis"] == "full_content_fallback"


def test_extract_actual_count_hunt_queries_variants():
    subresults = {
        "hunt_queries": {
            "queries": ["q1", "q2"],
            "count": 9,
        }
    }
    assert _extract_actual_count("hunt_queries", subresults, execution_id=1) == 9

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
        assert entry["count"] == 1
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

    def test_hunt_queries_count_defaults_to_len(self):
        """When both count fields are absent, defaults to len(queries)."""
        raw = {"queries": [{"type": "a", "query": "b", "context": "c"}]}
        items, entry = _parse_agent_result("HuntQueriesExtract", "hunt_queries", raw)
        assert entry["count"] == 1

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


class _FakeSnapshotRecord:
    """Stand-in for the externalized AgenticWorkflowExecutionSnapshotTable row."""

    def __init__(self, payload):
        self.payload = payload


class _FakeExecution:
    """Minimal stand-in for AgenticWorkflowExecutionTable."""

    def __init__(self, config_snapshot=None, snapshot_record=None):
        self.config_snapshot = config_snapshot
        # Post-externalization executions carry the real payload here and leave
        # only {"snapshot_id": N} on config_snapshot.
        self.snapshot_record = snapshot_record


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
        assert _is_agent_allowed("HuntQueriesExtract", None, None, {"hunt_queries"}, 1) is True
        assert _is_agent_allowed("CmdlineExtract", None, None, {"hunt_queries"}, 1) is False

    def test_agent_name_match(self):
        """Agent name (lowercased) is also checked, not just the subagent alias."""
        exec_ = _FakeExecution(config_snapshot={"subagent_eval": "cmdlineextract"})
        assert _is_agent_allowed("CmdlineExtract", exec_, None, None, 1) is True

    def test_empty_eval_allows(self):
        """Empty string subagent_eval is treated as no filter."""
        exec_ = _FakeExecution(config_snapshot={"subagent_eval": ""})
        assert _is_agent_allowed("ProcTreeExtract", exec_, "", None, 1) is True

    def test_externalized_snapshot_blocks_non_matching_agent(self):
        """Regression: subagent_eval read from an externalized snapshot still isolates.

        Post-externalization the eval filter lives in ``snapshot_record.payload``
        while ``config_snapshot`` holds only the pointer and the ``subagent_eval``
        variable is ``None`` (the router read it from the same broken pointer).
        Reading the pointer raw would allow every agent -- the v6887 symptom where
        an isolated cmdline eval silently ran all seven extractors.
        """
        exec_ = _FakeExecution(
            config_snapshot={"snapshot_id": 42},
            snapshot_record=_FakeSnapshotRecord({"subagent_eval": "cmdline"}),
        )
        assert _is_agent_allowed("CmdlineExtract", exec_, None, None, 1) is True
        assert _is_agent_allowed("ProcTreeExtract", exec_, None, None, 1) is False


class TestEvalSnapshot:
    """_eval_snapshot -- the shared hydration accessor for eval-flag reads."""

    def test_returns_empty_for_missing_execution(self):
        assert _eval_snapshot(None) == {}

    def test_prefers_externalized_payload_over_pointer(self):
        exec_ = _FakeExecution(
            config_snapshot={"snapshot_id": 7},
            snapshot_record=_FakeSnapshotRecord({"subagent_eval": "cmdline", "eval_run": True}),
        )
        assert _eval_snapshot(exec_) == {"subagent_eval": "cmdline", "eval_run": True}

    def test_falls_back_to_legacy_inline_snapshot(self):
        exec_ = _FakeExecution(config_snapshot={"subagent_eval": "registry_artifacts"})
        assert _eval_snapshot(exec_) == {"subagent_eval": "registry_artifacts"}


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

    @pytest.mark.parametrize("status", ["skipped", "disabled", "blocked_by_eval_filter"])
    def test_non_executed_status_does_not_mask_executed_agent_failure(self, status):
        extraction = {
            "subresults": {
                "AgentA": self._sr(error="provider failed"),
                "AgentB": self._sr(status=status),
            }
        }

        all_failed, reason = _all_extractors_errored(extraction)

        assert all_failed is True
        assert reason == "All 1 extractor(s) failed: provider failed"

    @pytest.mark.parametrize("status", ["skipped", "skipped_for_eval", "disabled", "blocked_by_eval_filter"])
    def test_non_executed_status_does_not_mask_infra_failure(self, status):
        extraction = {
            "subresults": {
                "AgentA": self._sr(error="openai api key is not configured"),
                "AgentB": self._sr(status=status),
            }
        }

        assert _extraction_is_infra_failure(extraction) is True

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

        assert not re.search(r"^\s*RAGService\(\)", src, re.MULTILINE), "Bare RAGService() call still present"

    def test_state_skip_flag_removed(self):
        """state_skip_flag was always-False (skip_os_detection not in WorkflowState); must be gone."""
        src = self._get_source()
        assert "state_skip_flag" not in src, "state_skip_flag should have been removed"

    def test_sigma_qa_bare_expressions_absent(self):
        """Bare qa_flags.get('SigmaAgent') and qa_max_retries expressions in sigma node must be gone."""
        src = self._get_source()
        # The bare expression pattern: line that is just the expression with no assignment
        import re

        assert not re.search(r"^\s*qa_flags\.get\(['\"]SigmaAgent", src, re.MULTILINE), (
            "Bare qa_flags.get('SigmaAgent') expression still present"
        )

    def test_novelty_score_not_in_state_return(self):
        """novelty_score was written to state but absent from WorkflowState TypedDict; must be removed."""
        src = self._get_source()
        # novelty_score is still used as a local variable in data dicts -- we only care
        # that it's not being set as a top-level state return key.
        # Check the similarity_search return block doesn't contain '"novelty_score":' as a state key.
        import re

        assert not re.search(r'"novelty_score"\s*:\s*max_novelty_score', src), (
            '"novelty_score" state return key still present'
        )
        assert not re.search(r'"novelty_results"\s*:\s*novelty_results.*New key', src), (
            '"novelty_results" duplicate state key still present'
        )


class TestObservableAttributionIsDiagnosable:
    """A Sigma rule with no observables has three very different causes.

    It can be untied *by design* -- the operator turned on full-article generation, so the
    group carried no observables to cite -- or the group did offer observables and the
    tie-back failed, or the model never emitted the field at all. All three used to leave
    the rule looking identical: no ``observables_used``, no warning, nothing queryable.
    ``observable_attribution`` separates them.
    """

    @staticmethod
    def _rule(**overrides) -> dict:
        rule = {
            "title": "Generic Rule",
            "logsource": {"product": "windows", "category": "process_creation"},
            "detection": {"selection": {"CommandLine|contains": "not-present"}, "condition": "selection"},
        }
        rule.update(overrides)
        return rule

    _EXTRACTION = {"observables": [{"type": "cmdline", "value": "powershell.exe -enc abc"}]}

    def test_full_content_group_is_untied_by_design(self):
        """SigmaFallbackEnabled generation: no observables were offered, so none are owed."""
        rule = self._rule()

        _repair_empty_observable_attribution(
            rule,
            extraction_result=self._EXTRACTION,
            group_original_indices=[],
            group_logsource_hint=None,
        )

        assert rule["observable_attribution"] == "untied_by_design"
        assert "observable_attribution_warnings" not in rule

    def test_absent_field_on_an_observable_group_is_a_failure_not_a_design_choice(self):
        """The model omitted the field entirely; this used to return early and warn nothing."""
        rule = self._rule()

        _repair_empty_observable_attribution(
            rule,
            extraction_result=self._EXTRACTION,
            group_original_indices=[0],
            group_logsource_hint={"product": "windows", "category": "process_creation"},
        )

        assert rule["observable_attribution"] == "attribution_failed"
        assert "missing_observables_used" in rule["observable_attribution_warnings"]

    def test_a_cited_rule_is_marked_grounded(self):
        rule = self._rule(observables_used=[3])

        _repair_empty_observable_attribution(
            rule,
            extraction_result=self._EXTRACTION,
            group_original_indices=[3],
            group_logsource_hint={"product": "windows", "category": "process_creation"},
        )

        assert rule["observable_attribution"] == "grounded"
        assert rule["observables_used"] == [3]

    def test_the_two_untied_outcomes_are_distinguishable(self):
        """The whole point: same empty attribution, two different stamps."""
        by_design = self._rule()
        _repair_empty_observable_attribution(
            by_design, extraction_result=self._EXTRACTION, group_original_indices=[], group_logsource_hint=None
        )
        failed = self._rule(observables_used=[])
        _repair_empty_observable_attribution(
            failed,
            extraction_result=self._EXTRACTION,
            group_original_indices=[0],
            group_logsource_hint={"product": "windows", "category": "process_creation"},
        )

        assert by_design.get("observables_used") in (None, [])
        assert failed["observables_used"] == []
        assert by_design["observable_attribution"] != failed["observable_attribution"]


def test_rebase_flags_indices_that_do_not_exist_in_the_group():
    """Every cited index was out of range: collapsing to [] silently hid the miscitation."""
    rule = {"observables_used": [7, 9]}

    _rebase_group_observable_indices(rule, [3, 8])

    assert rule["observables_used"] == []
    assert rule["observable_attribution_warnings"] == ["out_of_range_observable_indices"]


def test_rebase_does_not_flag_a_partially_valid_citation():
    rule = {"observables_used": [0, 99]}

    _rebase_group_observable_indices(rule, [3, 8])

    assert rule["observables_used"] == [3]
    assert "observable_attribution_warnings" not in rule
