"""Tests for scripts/benchmark_llm_providers.py provider dispatch wiring.

Regression context: LLMGenerationService was a second, duplicate provider-dispatch
chain whose only consumer was this script. It drifted -- it never grew a codex
branch when codex was added elsewhere -- and was deleted. The script now
dispatches through LLMService.request_chat() (src/services/llm_client.py), the
same chain the running app uses, so a provider added there is automatically
exercised here too.

These tests pin the wiring that made that swap safe, so it cannot silently
regress:
  - LM Studio's workflow-scoped enablement gate is force-enabled by this
    script, since it benchmarks LM Studio directly, independent of that
    agent-config toggle. Without the override, a fresh LLMService raises on
    the lmstudio provider by default.
  - Codex is included in the default provider list and gated the same way
    openai/anthropic already were -- an "unavailable" result, not a raised
    ValueError (the original bug for the deleted service).
  - request_chat() is called with the provider's default model and the
    response's ``choices[0].message.content`` shape is parsed correctly.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from scripts.benchmark_llm_providers import LLMBenchmark

pytestmark = pytest.mark.unit


@pytest.fixture
def benchmark():
    """Construct LLMBenchmark with LLMService's DB calls mocked out (no real DB)."""
    with patch("src.services.llm_service.DatabaseManager") as mock_db:
        mock_db.return_value.get_session.return_value.query.return_value.all.return_value = []
        return LLMBenchmark()


class TestLMStudioGateOverride:
    """The script must force LM Studio's workflow-enablement gate on."""

    def test_lmstudio_force_enabled_on_init(self, benchmark):
        assert benchmark.service.workflow_lmstudio_enabled is True

    def test_lmstudio_canonicalizes_without_raising(self, benchmark, monkeypatch):
        # Confirm the override actually does something: without it, a fresh
        # LLMService (WORKFLOW_LMSTUDIO_ENABLED unset) raises ValueError here.
        monkeypatch.delenv("WORKFLOW_LMSTUDIO_ENABLED", raising=False)
        assert benchmark.service._canonicalize_provider("lmstudio") == "lmstudio"


class TestCodexAvailabilityGate:
    """Codex must be gated like openai/anthropic (availability check), never raise."""

    async def test_codex_unavailable_when_disabled(self, benchmark):
        benchmark.service.workflow_codex_enabled = False
        with patch.object(benchmark, "test_provider", new=AsyncMock()) as mock_test_provider:
            result = await benchmark.benchmark_provider("codex", "gpt-5.6-luna")

        assert result == {
            "available": False,
            "reason": "Codex provider not enabled (set WORKFLOW_CODEX_ENABLED=true)",
        }
        mock_test_provider.assert_not_called()

    async def test_codex_proceeds_to_dispatch_when_enabled(self, benchmark):
        benchmark.service.workflow_codex_enabled = True
        success = {
            "success": True,
            "response_time": 0.1,
            "response_length": 5,
            "provider": "codex",
            "model_name": "gpt-5.6-luna",
            "response": "hello",
            "error": None,
        }
        with patch.object(benchmark, "test_provider", new=AsyncMock(return_value=success)) as mock_test_provider:
            result = await benchmark.benchmark_provider("codex", "gpt-5.6-luna")

        assert result["available"] is True
        assert result["successful"] is True
        assert mock_test_provider.await_count == len(benchmark.test_prompts)

    def test_codex_in_default_provider_list(self):
        # run_benchmark() falls back to this list when no --provider is given.
        import inspect

        source = inspect.getsource(LLMBenchmark.run_benchmark)
        assert '"codex"' in source


class TestRequestChatDispatch:
    """test_provider() must call request_chat() correctly and parse its response."""

    async def test_calls_request_chat_with_provider_default_model(self, benchmark):
        response = {"choices": [{"message": {"content": "hello world"}}]}
        with patch.object(benchmark.service, "request_chat", new=AsyncMock(return_value=response)) as mock_request_chat:
            result = await benchmark.test_provider("openai", "gpt-4o-mini", "analyze this")

        assert result["success"] is True
        assert result["response_length"] == len("hello world")
        assert result["error"] is None

        mock_request_chat.assert_awaited_once()
        _, kwargs = mock_request_chat.await_args
        assert kwargs["provider"] == "openai"
        assert kwargs["model_name"] == benchmark.service.provider_defaults["openai"]
        assert kwargs["messages"] == [
            {"role": "system", "content": "You are a cybersecurity threat intelligence analyst."},
            {"role": "user", "content": "analyze this"},
        ]

    async def test_provider_failure_is_captured_not_raised(self, benchmark):
        with patch.object(
            benchmark.service, "request_chat", new=AsyncMock(side_effect=RuntimeError("provider exploded"))
        ):
            result = await benchmark.test_provider("anthropic", "claude-sonnet-4-5", "prompt")

        assert result["success"] is False
        assert result["error"] == "provider exploded"
        assert result["response_length"] == 0
