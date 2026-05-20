"""Regression tests for observable traceability gaps (dev-io-6.1.3).

Three bugs fixed:
  1. HuntQueriesExtract normalization stripped confidence_score/source_evidence/
     extraction_justification from query items before supervisor aggregation.
  2. _build_observables_response only exposed cmdline/process_lineage/hunt_queries;
     registry_artifacts, windows_services, scheduled_tasks were silently dropped.
  3. (Frontend) filterObservablesForRule flat array omitted the same three types,
     causing valid observables_used indices to resolve to nothing. Covered
     indirectly by Bug 2 -- if the API returns all types, the JS index math is
     correct by construction.
"""

import pytest

from src.web.routes.workflow_executions import _build_observables_response

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_extraction_result(*observable_dicts):
    """Wrap a list of observable dicts into the extraction_result envelope."""
    return {
        "observables": list(observable_dicts),
        "summary": {"count": len(observable_dicts)},
    }


def _hunt_query_item(**kwargs):
    """Return a minimal hunt_queries observable entry."""
    base = {
        "type": "hunt_queries",
        "value": {
            "query": "index=main sourcetype=sysmon EventCode=1",
            "type": "splunk",
            "context": "suspicious process spawned",
        },
        "source": "supervisor_aggregation",
    }
    base.update(kwargs)
    return base


def _registry_item(**kwargs):
    """Return a minimal registry_artifacts observable entry."""
    base = {
        "type": "registry_artifacts",
        "value": {
            "key": "HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\Run",
            "value_name": "socks5",
            "value_data": "powershell.exe -windowstyle hidden",
        },
        "source": "supervisor_aggregation",
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# Bug 1 -- HuntQueries traceability fields survive normalization
# ---------------------------------------------------------------------------


class TestHuntQueriesTraceabilityPreserved:
    """Confidence and traceability fields must survive the HuntQueriesExtract
    normalization step and appear in the observables API response."""

    def test_confidence_score_not_null_for_hunt_query(self):
        """confidence_score must be carried through when the LLM returns it."""
        item = _hunt_query_item(confidence_score=0.88)
        result = _build_observables_response(
            execution_id=1,
            extraction_result=_make_extraction_result(item),
        )
        hq = result.observables["hunt_queries"]
        assert len(hq) == 1
        assert hq[0].confidence_score == 0.88, "confidence_score was stripped from hunt_queries during normalization"

    def test_source_evidence_preserved_for_hunt_query(self):
        """source_evidence must not be dropped from hunt_queries items."""
        item = _hunt_query_item(source_evidence="The attacker ran Splunk query X to evade detection.")
        result = _build_observables_response(
            execution_id=1,
            extraction_result=_make_extraction_result(item),
        )
        hq = result.observables["hunt_queries"]
        assert hq[0].source_evidence == "The attacker ran Splunk query X to evade detection."

    def test_extraction_justification_preserved_for_hunt_query(self):
        """extraction_justification must not be dropped from hunt_queries items."""
        item = _hunt_query_item(extraction_justification="Matches hunt query rubric: EDR search string.")
        result = _build_observables_response(
            execution_id=1,
            extraction_result=_make_extraction_result(item),
        )
        hq = result.observables["hunt_queries"]
        assert hq[0].extraction_justification == "Matches hunt query rubric: EDR search string."

    def test_null_confidence_round_trips_as_none(self):
        """Items where the LLM omitted confidence_score should surface as None, not crash."""
        item = _hunt_query_item()  # no confidence_score key
        result = _build_observables_response(
            execution_id=1,
            extraction_result=_make_extraction_result(item),
        )
        hq = result.observables["hunt_queries"]
        assert hq[0].confidence_score is None


# ---------------------------------------------------------------------------
# Bug 2 -- All six observable types exposed by the API
# ---------------------------------------------------------------------------


class TestObservableTypeCoverage:
    """_build_observables_response must return all six extractor types, not just
    cmdline/process_lineage/hunt_queries."""

    @pytest.mark.parametrize(
        "obs_type",
        [
            "cmdline",
            "process_lineage",
            "hunt_queries",
            "registry_artifacts",
            "windows_services",
            "scheduled_tasks",
        ],
    )
    def test_type_present_in_response(self, obs_type):
        """Every supported observable type must appear as a key in the response."""
        result = _build_observables_response(
            execution_id=1,
            extraction_result=_make_extraction_result(),
        )
        assert obs_type in result.observables, (
            f"'{obs_type}' missing from observables response -- OBS_TYPES is incomplete"
        )

    def test_registry_artifacts_items_returned(self):
        """registry_artifacts observables must be surfaced, not silently dropped."""
        item = _registry_item(
            confidence_score=0.92,
            source_evidence="Registry run key found in article.",
            extraction_justification="Matches Autoruns persistence pattern.",
        )
        result = _build_observables_response(
            execution_id=1,
            extraction_result=_make_extraction_result(item),
        )
        reg = result.observables["registry_artifacts"]
        assert len(reg) == 1, "registry_artifacts item was dropped from response"
        assert reg[0].confidence_score == 0.92
        assert reg[0].source_evidence == "Registry run key found in article."

    def test_windows_services_items_returned(self):
        """windows_services observables must not be dropped."""
        item = {
            "type": "windows_services",
            "value": {"service_name": "MalSvc", "binary_path": "C:\\evil.exe"},
            "confidence_score": 0.75,
            "source": "supervisor_aggregation",
        }
        result = _build_observables_response(
            execution_id=1,
            extraction_result=_make_extraction_result(item),
        )
        assert len(result.observables["windows_services"]) == 1

    def test_scheduled_tasks_items_returned(self):
        """scheduled_tasks observables must not be dropped."""
        item = {
            "type": "scheduled_tasks",
            "value": {"task_name": "\\Microsoft\\evil", "action": "cmd.exe /c evil.bat"},
            "confidence_score": 0.80,
            "source": "supervisor_aggregation",
        }
        result = _build_observables_response(
            execution_id=1,
            extraction_result=_make_extraction_result(item),
        )
        assert len(result.observables["scheduled_tasks"]) == 1

    def test_mixed_types_routed_correctly(self):
        """Items of different types must end up in their respective buckets."""
        cmdline_item = {
            "type": "cmdline",
            "value": "cmd.exe /c whoami",
            "confidence_score": 0.9,
        }
        registry_item = _registry_item(confidence_score=0.85)
        result = _build_observables_response(
            execution_id=1,
            extraction_result=_make_extraction_result(cmdline_item, registry_item),
        )
        assert len(result.observables["cmdline"]) == 1
        assert len(result.observables["registry_artifacts"]) == 1
        assert len(result.observables["process_lineage"]) == 0

    def test_unknown_type_not_included(self):
        """Items with an unrecognised type should be silently ignored."""
        item = {"type": "unknown_future_type", "value": "x"}
        result = _build_observables_response(
            execution_id=1,
            extraction_result=_make_extraction_result(item),
        )
        assert "unknown_future_type" not in result.observables

    def test_empty_extraction_result_returns_all_empty_buckets(self):
        """No observables should return all six buckets as empty lists, not missing keys."""
        result = _build_observables_response(execution_id=1, extraction_result={})
        for t in (
            "cmdline",
            "process_lineage",
            "hunt_queries",
            "registry_artifacts",
            "windows_services",
            "scheduled_tasks",
        ):
            assert result.observables[t] == []

    def test_none_extraction_result_returns_all_empty_buckets(self):
        """None extraction_result should not crash and should return all six empty buckets."""
        result = _build_observables_response(execution_id=1, extraction_result=None)
        for t in (
            "cmdline",
            "process_lineage",
            "hunt_queries",
            "registry_artifacts",
            "windows_services",
            "scheduled_tasks",
        ):
            assert result.observables[t] == []

    def test_type_filter_still_works_for_extended_types(self):
        """type_filter parameter must work for registry_artifacts, not just legacy types."""
        reg = _registry_item()
        cmd = {"type": "cmdline", "value": "cmd.exe /c test"}
        result = _build_observables_response(
            execution_id=1,
            extraction_result=_make_extraction_result(reg, cmd),
            type_filter="registry_artifacts",
        )
        assert len(result.observables["registry_artifacts"]) == 1
        assert len(result.observables["cmdline"]) == 0


# ---------------------------------------------------------------------------
# Cross-layer canonical-order contract
#
# A SIGMA rule's observables_used indices are 0-based offsets into the flat
# extraction_result["observables"] list, which the supervisor builds in
# canonical sub-agent order (agentic_workflow.py:1288 + :1355). Every frontend
# consumer must reflatten by the SAME canonical OBS_TYPE_ORDER, or rule
# provenance gets mis-attributed -- the silent recurrence pattern behind
# be80168c, 8415f5bc, and the workflow.html observablesUsedSection twin.
#
# These tests pin the contract at both ends. A reorder anywhere -- schema,
# backend, or any of the three templates -- trips a single named failure
# pointing directly at the drifted file. This is the tripwire the
# 18 backend tests above could not provide because they exercise
# _build_observables_response with a hand-built envelope, never the
# producer's ordering nor the template-duplicated consumers.
# ---------------------------------------------------------------------------


CANONICAL_AGENT_NAMES_SUB = [
    "CmdlineExtract",
    "ProcTreeExtract",
    "HuntQueriesExtract",
    "RegistryExtract",
    "ServicesExtract",
    "ScheduledTasksExtract",
]

CANONICAL_CATEGORIES = [
    "cmdline",
    "process_lineage",
    "hunt_queries",
    "registry_artifacts",
    "windows_services",
    "scheduled_tasks",
]

# Every template that flattens/unflattens the per-rule observables list.
# Adding a fourth must add it here -- silence on a new file is the failure
# mode this contract is designed to prevent.
OBS_TYPE_ORDER_TEMPLATES = [
    "src/web/templates/workflow.html",
    "src/web/templates/workflow_executions.html",
    "src/web/templates/sigma_queue.html",
]


class TestCanonicalObservableOrderContract:
    """Pin the canonical sub-agent / observable-category ordering at the
    schema (producer) AND every template (consumer) that depends on it."""

    def test_agent_names_sub_matches_canonical_order(self):
        """Schema tripwire. observables_used indices are numbered by
        enumerating extraction_result["observables"], which the supervisor
        builds in AGENT_NAMES_SUB order. Reordering this list silently
        mis-attributes every rule's provenance going forward."""
        from src.config.workflow_config_schema import AGENT_NAMES_SUB

        assert list(AGENT_NAMES_SUB) == CANONICAL_AGENT_NAMES_SUB, (
            "AGENT_NAMES_SUB drift would silently change observables_used "
            "index numbering for every new execution. If reordering is "
            "intentional, also update CANONICAL_CATEGORIES + every template's "
            "OBS_TYPE_ORDER in lockstep."
        )

    @pytest.mark.parametrize("rel_path", OBS_TYPE_ORDER_TEMPLATES)
    def test_frontend_obs_type_order_matches_canonical(self, rel_path):
        """Template tripwire. Each template flattens/unflattens observables
        using its own OBS_TYPE_ORDER. Three separate recurrences of the same
        bug class (cmdline+proc+hunt only) traced to ONE template drifting
        while the others were fixed -- this asserts every occurrence in every
        listed template equals the canonical sequence, so the next drift fails
        loudly and names the file."""
        import re
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[2]
        path = repo_root / rel_path
        assert path.exists(), f"template missing: {rel_path}"
        content = path.read_text()

        matches = re.findall(r"OBS_TYPE_ORDER\s*=\s*\[([^\]]+)\]", content)
        assert matches, (
            f"{rel_path} has no OBS_TYPE_ORDER declaration. Every template "
            f"that groups observables by type is required to declare it so "
            f"this contract test can verify it."
        )

        for i, body in enumerate(matches):
            parsed = [
                item.strip().strip("'").strip('"')
                for item in body.split(",")
                if item.strip()
            ]
            assert parsed == CANONICAL_CATEGORIES, (
                f"{rel_path} OBS_TYPE_ORDER occurrence #{i} is not canonical.\n"
                f"  expected: {CANONICAL_CATEGORIES}\n"
                f"  got:      {parsed}"
            )

    def test_supervisor_subresults_dict_init_uses_canonical_order(self):
        """Producer-runtime tripwire. agentic_workflow.py:1288 initializes
        `subresults` as a dict literal whose insertion order IS the order in
        which the supervisor appends to all_observables -- the supervisor
        iterates `for cat, data in subresults.items()`, and Python preserves
        insertion order, so reordering this literal silently mis-numbers
        observables_used indices for every new execution.

        The schema and template tests sandwich the contract from above and
        below; this pins the actual runtime emission. Parsed with ast (not
        regex) because the dict's values are themselves dict literals
        ({"items": [], "count": 0}) -- nested braces break a flat regex but
        ast captures source-order keys unambiguously.
        """
        import ast
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[2]
        src = (repo_root / "src/workflows/agentic_workflow.py").read_text()
        tree = ast.parse(src)

        canonical_set = set(CANONICAL_CATEGORIES)
        # Find the assignment `subresults = {<6 canonical type keys>: <dict>}`.
        # Set-membership filter disambiguates THE canonical init from any
        # other `subresults = {...}` literal that might appear elsewhere.
        found_keys: list[str] | None = None
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if not (isinstance(target, ast.Name) and target.id == "subresults"):
                    continue
                if not isinstance(node.value, ast.Dict):
                    continue
                keys = [
                    k.value for k in node.value.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)
                ]
                if set(keys) == canonical_set:
                    found_keys = keys
                    break
            if found_keys is not None:
                break

        assert found_keys is not None, (
            "Could not locate canonical subresults dict literal in "
            "agentic_workflow.py. If the init has moved or been refactored "
            "(e.g., built from AGENT_NAMES_SUB programmatically), update "
            "this test to assert the new producer-order anchor."
        )
        assert found_keys == CANONICAL_CATEGORIES, (
            "agentic_workflow.py subresults dict literal is not in canonical "
            "order. THIS dict's insertion order is the runtime order of "
            "extraction_result['observables'] (the supervisor iterates "
            "subresults.items()). A reorder here silently mis-numbers "
            "observables_used for every new execution -- without tripping "
            "the schema or template tests above.\n"
            f"  expected: {CANONICAL_CATEGORIES}\n"
            f"  got:      {found_keys}"
        )
