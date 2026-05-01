"""Tests for QAEvaluator -- the shared QA primitive."""

import json
from unittest.mock import AsyncMock, Mock

import pytest

from src.services.qa_evaluator import QAEvaluator, _normalize_verdict

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# _normalize_verdict
# ---------------------------------------------------------------------------


def test_normalize_verdict_pass():
    assert _normalize_verdict("pass") == "pass"
    assert _normalize_verdict("PASS") == "pass"
    assert _normalize_verdict("  Pass  ") == "pass"


def test_normalize_verdict_critical_failure():
    assert _normalize_verdict("critical_failure") == "critical_failure"
    assert _normalize_verdict("CRITICAL_FAILURE") == "critical_failure"


def test_normalize_verdict_needs_revision_variants():
    assert _normalize_verdict("needs_revision") == "needs_revision"
    assert _normalize_verdict("fail") == "needs_revision"
    assert _normalize_verdict("unknown") == "needs_revision"
    assert _normalize_verdict("") == "needs_revision"


# ---------------------------------------------------------------------------
# QAEvaluator._parse_response_text
# ---------------------------------------------------------------------------


@pytest.fixture
def evaluator():
    llm = Mock()
    llm._convert_messages_for_model = Mock(return_value=[])
    return QAEvaluator(llm)


def test_parse_strategy1_balanced_braces(evaluator):
    text = '{"verdict": "pass", "summary": "ok", "issues": []}'
    result, failed, err = evaluator._parse_response_text(text, "TestAgent")
    assert not failed
    assert result["verdict"] == "pass"
    assert err is None


def test_parse_strategy1_nested_json(evaluator):
    text = '{"verdict": "needs_revision", "corrections": {"removed": [{"command": "foo", "reason": "bar"}]}}'
    result, failed, err = evaluator._parse_response_text(text, "TestAgent")
    assert not failed
    assert result["verdict"] == "needs_revision"
    assert result["corrections"]["removed"][0]["command"] == "foo"


def test_parse_strategy3_markdown_code_block(evaluator):
    text = 'Here is my evaluation:\n```json\n{"verdict": "pass", "summary": "good"}\n```'
    result, failed, err = evaluator._parse_response_text(text, "TestAgent")
    assert not failed
    assert result["verdict"] == "pass"


def test_parse_strategy_prefix_json(evaluator):
    text = 'JSON:\n{"status": "pass", "summary": "ok"}'
    result, failed, err = evaluator._parse_response_text(text, "TestAgent")
    assert not failed
    assert result["status"] == "pass"


def test_parse_all_strategies_fail(evaluator):
    text = "This is not JSON at all."
    result, failed, err = evaluator._parse_response_text(text, "TestAgent")
    assert failed
    assert result == {}
    assert err is not None
    assert "All parsing strategies failed" in err


# ---------------------------------------------------------------------------
# QAEvaluator.evaluate
# ---------------------------------------------------------------------------


def _make_llm(response_json: dict | None = None, response_text: str | None = None) -> Mock:
    """Build a mock LLMService that returns the given QA response."""
    content = response_text if response_text is not None else json.dumps(response_json or {})
    llm = Mock()
    llm._convert_messages_for_model = Mock(return_value=[{"role": "user", "content": "test"}])
    llm.request_chat = AsyncMock(return_value={"choices": [{"message": {"content": content}}], "usage": {}})
    return llm


@pytest.mark.asyncio
async def test_evaluate_pass_verdict():
    llm = _make_llm({"verdict": "pass", "summary": "All good", "issues": []})
    ev = QAEvaluator(llm)
    result = await ev.evaluate(
        messages=[{"role": "user", "content": "test"}],
        agent_name="TestAgent",
        model_name="model",
        provider="openai",
    )
    assert result["verdict"] == "pass"
    assert result["summary"] == "All good"
    assert result["parsing_failed"] is False
    assert "_qa_text" in result


@pytest.mark.asyncio
async def test_evaluate_normalizes_status_to_verdict():
    """Legacy 'status' key is normalized to 'verdict'."""
    llm = _make_llm({"status": "pass", "summary": "Legacy response"})
    ev = QAEvaluator(llm)
    result = await ev.evaluate(
        messages=[{"role": "user", "content": "test"}],
        agent_name="TestAgent",
        model_name="model",
        provider="openai",
    )
    assert result["verdict"] == "pass"


@pytest.mark.asyncio
async def test_evaluate_normalizes_fail_status_to_needs_revision():
    """status=fail maps to verdict=needs_revision."""
    llm = _make_llm({"status": "fail", "summary": "Failed"})
    ev = QAEvaluator(llm)
    result = await ev.evaluate(
        messages=[{"role": "user", "content": "test"}],
        agent_name="TestAgent",
        model_name="model",
        provider="openai",
    )
    assert result["verdict"] == "needs_revision"


@pytest.mark.asyncio
async def test_evaluate_fail_closed_on_parse_failure():
    """Unparseable response -> verdict=needs_revision (fail-closed)."""
    llm = _make_llm(response_text="This is not JSON")
    ev = QAEvaluator(llm)
    result = await ev.evaluate(
        messages=[{"role": "user", "content": "test"}],
        agent_name="TestAgent",
        model_name="model",
        provider="openai",
    )
    assert result["verdict"] == "needs_revision"
    assert result["parsing_failed"] is True
    assert result["_parse_error"] is not None


@pytest.mark.asyncio
async def test_evaluate_preserves_extra_keys():
    """Keys from the LLM response (like 'corrections') are passed through."""
    llm = _make_llm(
        {
            "verdict": "needs_revision",
            "summary": "Removed junk",
            "corrections": {"removed": [{"command": "bad_cmd", "reason": "not in article"}], "added": []},
        }
    )
    ev = QAEvaluator(llm)
    result = await ev.evaluate(
        messages=[{"role": "user", "content": "test"}],
        agent_name="TestAgent",
        model_name="model",
        provider="openai",
    )
    assert result["verdict"] == "needs_revision"
    assert result["corrections"]["removed"][0]["command"] == "bad_cmd"


@pytest.mark.asyncio
async def test_evaluate_critical_failure_preserved():
    llm = _make_llm({"verdict": "critical_failure", "summary": "Hard violation"})
    ev = QAEvaluator(llm)
    result = await ev.evaluate(
        messages=[{"role": "user", "content": "test"}],
        agent_name="TestAgent",
        model_name="model",
        provider="openai",
    )
    assert result["verdict"] == "critical_failure"


@pytest.mark.asyncio
async def test_evaluate_empty_summary_filled_on_pass():
    """When LLM returns no summary for a pass, a positive default is set."""
    llm = _make_llm({"verdict": "pass"})
    ev = QAEvaluator(llm)
    result = await ev.evaluate(
        messages=[{"role": "user", "content": "test"}],
        agent_name="TestAgent",
        model_name="model",
        provider="openai",
    )
    assert result["verdict"] == "pass"
    assert result["summary"]  # non-empty
    assert "passed" in result["summary"].lower()


@pytest.mark.asyncio
async def test_evaluate_qa_text_always_in_result():
    """_qa_text must always be present so call sites can do raw-text fallback."""
    llm = _make_llm(response_text="Not JSON but meaningful")
    ev = QAEvaluator(llm)
    result = await ev.evaluate(
        messages=[{"role": "user", "content": "test"}],
        agent_name="TestAgent",
        model_name="model",
        provider="openai",
    )
    assert "_qa_text" in result
    assert result["_qa_text"] == "Not JSON but meaningful"
