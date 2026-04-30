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
            "registry_hive": "HKEY_LOCAL_MACHINE",
            "registry_key_path": "Software\\Microsoft\\Windows\\CurrentVersion\\Run",
            "registry_value_name": "socks5",
            "registry_value_data": "powershell.exe -windowstyle hidden",
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
