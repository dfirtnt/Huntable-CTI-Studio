"""Tests for LLM service functionality."""

import contextlib
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.services.llm_service import (
    MIN_USER_CONTENT_CHARS,
    LLMService,
    PreprocessInvariantError,
    _validate_preprocess_invariants,
)

# Mark all tests in this file as unit tests (use mocks, no real infrastructure)
pytestmark = pytest.mark.unit


@pytest.fixture
def llm_service():
    """Create LLMService instance for tests that need it (e.g. run_extraction_agent)."""
    config_models = {
        "RankAgent": "gpt-4",
        "RankAgent_provider": "openai",
        "ExtractAgent": "gpt-4",
        "ExtractAgent_provider": "openai",
        "SigmaAgent": "gpt-4",
        "SigmaAgent_provider": "openai",
    }
    with patch("src.services.llm_service.DatabaseManager") as mock_db:
        mock_db.return_value.get_session.return_value.query.return_value.all.return_value = []
        return LLMService(config_models=config_models)


class TestLLMService:
    """Test LLMService functionality."""

    @pytest.fixture
    def service(self):
        """Create LLMService instance with mocked dependencies."""
        config_models = {
            "RankAgent": "gpt-4",
            "RankAgent_provider": "openai",
            "ExtractAgent": "gpt-4",
            "ExtractAgent_provider": "openai",
            "SigmaAgent": "gpt-4",
            "SigmaAgent_provider": "openai",
        }
        with patch("src.services.llm_service.DatabaseManager") as mock_db:
            mock_db.return_value.get_session.return_value.query.return_value.all.return_value = []
            return LLMService(config_models=config_models)

    @pytest.fixture
    def service_with_config(self):
        """Create LLMService with config models."""
        config_models = {
            "RankAgent": "test-rank-model",
            "ExtractAgent": "test-extract-model",
            "SigmaAgent": "test-sigma-model",
        }
        with patch("src.services.llm_service.DatabaseManager") as mock_db:
            mock_db.return_value.get_session.return_value.query.return_value.all.return_value = []
            return LLMService(config_models=config_models)

    def test_canonicalize_provider_openai(self, service):
        """Test provider canonicalization for OpenAI."""
        assert service._canonicalize_provider("openai") == "openai"
        assert service._canonicalize_provider("chatgpt") == "openai"
        assert service._canonicalize_provider("gpt-4o") == "openai"

    def test_canonicalize_provider_anthropic(self, service):
        """Test provider canonicalization for Anthropic."""
        assert service._canonicalize_provider("anthropic") == "anthropic"
        assert service._canonicalize_provider("claude") == "anthropic"

    def test_canonicalize_provider_lmstudio(self, service):
        """Test provider canonicalization for LMStudio."""
        assert service._canonicalize_provider("lmstudio") == "lmstudio"
        assert service._canonicalize_provider("local") == "lmstudio"
        assert service._canonicalize_provider(None) == "lmstudio"

    def test_resolve_agent_model_from_config(self, service_with_config):
        """Test model resolution from config."""
        assert service_with_config.model_rank == "test-rank-model"
        assert service_with_config.model_extract == "test-extract-model"
        assert service_with_config.model_sigma == "test-sigma-model"

    def test_convert_messages_for_model_mistral(self, service):
        """Test message conversion for Mistral models."""
        messages = [{"role": "system", "content": "You are a helpful assistant"}, {"role": "user", "content": "Hello"}]

        converted = service._convert_messages_for_model(messages, "mistral-7b-instruct")

        # Should convert system to user message
        assert len(converted) == 1
        assert converted[0]["role"] == "user"

    def test_convert_messages_for_model_qwen(self, service):
        """Test message conversion for Qwen models (supports system role)."""
        messages = [{"role": "system", "content": "You are a helpful assistant"}, {"role": "user", "content": "Hello"}]

        converted = service._convert_messages_for_model(messages, "qwen-7b-instruct")

        # Should keep system role
        assert len(converted) == 2
        assert converted[0]["role"] == "system"

    @pytest.mark.asyncio
    async def test_request_chat_success(self, service):
        """Test successful chat request."""
        mock_response = {
            "choices": [{"message": {"content": "Test response"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            # Create response object with real attributes
            from types import SimpleNamespace

            mock_response_obj = SimpleNamespace()
            mock_response_obj.status_code = 200
            mock_response_obj.text = '{"choices": [{"message": {"content": "Test response"}}]}'
            mock_response_obj.headers = {}
            mock_response_obj.json = lambda: mock_response
            mock_response_obj.raise_for_status = lambda: None

            # Create mock client that returns our response
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response_obj)
            mock_client.aclose = AsyncMock()

            # Make AsyncClient() return our mock client
            mock_client_class.return_value = mock_client
            # Also support async context manager protocol
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await service.request_chat(
                provider="lmstudio",
                model_name="test-model",
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=1000,
                temperature=0.7,
                timeout=30.0,
                failure_context="test_request_chat_success",
            )

            assert result["choices"][0]["message"]["content"] == "Test response"

        with patch("httpx.AsyncClient") as mock_client_class:
            # Create response object with real attributes
            from types import SimpleNamespace

            def create_response():
                resp = SimpleNamespace()
                resp.status_code = 200
                resp.text = '{"choices": [{"message": {"content": "Success after retry"}}]}'
                resp.headers = {}
                resp.json = lambda: mock_response
                resp.raise_for_status = lambda: None
                return resp

            # Create mock client that returns our response
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=[Exception("Connection error"), create_response()])
            mock_client.aclose = AsyncMock()

            # Make AsyncClient() return our mock client
            mock_client_class.return_value = mock_client
            # Also support async context manager protocol
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

    @pytest.mark.asyncio
    async def test_request_chat_error_handling(self, service):
        """Test error handling in chat request."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=RuntimeError("API error"))
            mock_client.aclose = AsyncMock()
            mock_client_class.return_value = mock_client

            with pytest.raises(RuntimeError, match="API error"):
                await service.request_chat(
                    provider="lmstudio",
                    model_name="test-model",
                    messages=[{"role": "user", "content": "Hello"}],
                    max_tokens=1000,
                    temperature=0.7,
                    timeout=30.0,
                    failure_context="test_request_chat_error_handling",
                )

    @pytest.mark.asyncio
    async def test_openai_retries_without_temperature_when_model_rejects_non_default(self, service):
        """Defense-in-depth: unknown model that rejects temperature triggers a retry without it.

        Uses a hypothetical model name that does not match reasoning prefixes, so temperature
        is sent on the first attempt; the 400 retry path is then exercised.
        """
        service.openai_api_key = "test-openai-key"
        service.workflow_openai_enabled = True

        with patch("httpx.AsyncClient") as mock_client_class:
            first_response = Mock()
            first_response.status_code = 400
            first_response.text = (
                '{"error":{"message":"Unsupported value: \'temperature\' does not support 0.0 with this model. '
                'Only the default (1) value is supported.","type":"invalid_request_error","param":"temperature",'
                '"code":"unsupported_value"}}'
            )

            second_response = Mock()
            second_response.status_code = 200
            second_response.text = '{"choices":[{"message":{"content":"ok"}}]}'
            second_response.json = Mock(return_value={"choices": [{"message": {"content": "ok"}}], "usage": {}})

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=[first_response, second_response])
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

            # gpt-4-special is not a reasoning-prefix model, so temperature is sent first
            result = await service.request_chat(
                provider="openai",
                model_name="gpt-4-special",
                messages=[{"role": "user", "content": "hello"}],
                max_tokens=128,
                temperature=0.0,
                timeout=30.0,
                failure_context="openai-temp-retry",
            )

            assert result["choices"][0]["message"]["content"] == "ok"
            assert mock_client.post.await_count == 2

            first_payload = mock_client.post.await_args_list[0].kwargs["json"]
            second_payload = mock_client.post.await_args_list[1].kwargs["json"]
            assert "temperature" in first_payload
            assert "temperature" not in second_payload

    @pytest.mark.asyncio
    async def test_openai_reasoning_model_omits_temperature_proactively(self, service):
        """Reasoning models (o4-mini) must never include temperature in the first request."""
        service.openai_api_key = "test-openai-key"
        service.workflow_openai_enabled = True

        with patch("httpx.AsyncClient") as mock_client_class:
            ok_response = Mock()
            ok_response.status_code = 200
            ok_response.text = '{"choices":[{"message":{"content":"done"}}]}'
            ok_response.json = Mock(return_value={"choices": [{"message": {"content": "done"}}], "usage": {}})

            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=ok_response)
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await service.request_chat(
                provider="openai",
                model_name="o4-mini",
                messages=[{"role": "user", "content": "hello"}],
                max_tokens=128,
                temperature=0.7,
                timeout=30.0,
                failure_context="openai-proactive-omit",
            )

            assert result["choices"][0]["message"]["content"] == "done"
            assert mock_client.post.await_count == 1  # single call, no retry needed

            payload = mock_client.post.await_args_list[0].kwargs["json"]
            assert "temperature" not in payload

    @pytest.mark.asyncio
    async def test_request_chat_empty_messages_raises_preprocess_invariant_error(self, service):
        """Circuit breaker: request_chat must never invoke LLM with empty messages."""
        with pytest.raises(PreprocessInvariantError, match="empty messages"):
            await service.request_chat(
                provider="lmstudio",
                model_name="test-model",
                messages=[],
                max_tokens=1000,
                temperature=0.7,
                timeout=30.0,
                failure_context="test_empty_messages",
            )

    def test_truncate_content(self, service):
        """Test content truncation for context limits."""
        long_content = "x" * 10000

        truncated = service._truncate_content(long_content, max_context_tokens=1000, max_output_tokens=100)

        assert len(truncated) < len(long_content)
        assert "[Content truncated" in truncated

    def test_estimate_tokens(self, service):
        """Test token estimation."""
        text = "x" * 400  # ~100 tokens at 4 chars/token

        tokens = service._estimate_tokens(text)

        assert tokens == 100

    def test_get_top_p_for_agent(self, service_with_config):
        """Test getting top_p for specific agent."""
        top_p = service_with_config.get_top_p_for_agent("RankAgent")

        assert isinstance(top_p, float)
        assert 0.0 <= top_p <= 1.0

    def test_compute_rank_ground_truth(self, service):
        """Test ground truth rank computation."""
        result = service.compute_rank_ground_truth(hunt_score=85.0, ml_score=90.0)

        assert "ground_truth_rank" in result
        assert result["ground_truth_rank"] is not None
        assert 1.0 <= result["ground_truth_rank"] <= 10.0

    def test_compute_rank_ground_truth_none_scores(self, service):
        """Test ground truth rank with None scores."""
        result = service.compute_rank_ground_truth(hunt_score=None, ml_score=None)

        assert result["ground_truth_rank"] is None

    @pytest.mark.asyncio
    async def test_check_model_context_length(self, service):
        """Test model context length checking."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = Mock(
                status_code=200, json=lambda: {"data": [{"id": "test-model", "context_length": 32768}]}
            )
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.post = AsyncMock(
                return_value=Mock(status_code=200, json=lambda: {"choices": [{"message": {"content": "test"}}]})
            )
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await service.check_model_context_length(model_name="test-model", threshold=16384)

            assert "context_length" in result
            assert "is_sufficient" in result
            assert result["is_sufficient"] is True

    @pytest.mark.asyncio
    async def test_check_model_context_length_uses_large_reported_window(self, service):
        """LMStudio-reported large context windows should be returned as-is."""
        service.provider_rank = "lmstudio"
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = Mock(
                status_code=200, json=lambda: {"data": [{"id": "test-model", "context_length": 93835}]}
            )
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.post = AsyncMock(
                return_value=Mock(status_code=200, json=lambda: {"choices": [{"message": {"content": "test"}}]})
            )
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await service.check_model_context_length(model_name="test-model", threshold=16384)

            assert result["context_length"] == 93835
            assert result["method"] == "api_models_endpoint"

    @pytest.mark.asyncio
    async def test_run_extraction_agent_uses_detected_lmstudio_context(self, service):
        """run_extraction_agent should use the detected LMStudio window before truncating content."""
        content = "x" * 10000
        prompt_config = {
            "role": "You are a registry extractor.",
            "objective": "Extract observables.",
            "instructions": "Output valid JSON.",
            "output_format": {"items": []},
            "json_example": '{"items":[],"count":0}',
        }

        truncate_calls = []

        def capture_truncation(text, max_context_tokens, max_output_tokens, prompt_overhead=500):
            truncate_calls.append((len(text), max_context_tokens, max_output_tokens, prompt_overhead))
            return text

        response_payload = {"choices": [{"message": {"content": '{"items": [], "count": 0}'}}], "usage": {}}

        with (
            patch.object(
                service,
                "check_model_context_length",
                AsyncMock(return_value={"context_length": 93835, "method": "api_models_endpoint"}),
            ),
            patch.object(service, "_truncate_content", side_effect=capture_truncation),
            patch.object(service, "request_chat", AsyncMock(return_value=response_payload)),
            patch(
                "src.services.llm_service.trace_llm_call",
                side_effect=lambda *args, **kwargs: contextlib.nullcontext(Mock()),
            ),
            patch("src.services.llm_service.log_llm_completion"),
            patch("src.services.llm_service.log_llm_error"),
        ):
            result = await service.run_extraction_agent(
                agent_name="RegistryExtract",
                content=content,
                title="Test Article",
                url="https://example.com/test",
                prompt_config=prompt_config,
                qa_prompt_config=None,
                max_retries=1,
                execution_id=None,
                model_name="local-large-model",
                provider="lmstudio",
            )

        assert truncate_calls
        assert truncate_calls[0][1] == 93835
        assert result["count"] == 0


class TestPreprocessInvariantGuard:
    """Fail-fast guard: refuse to call LLM with empty/malformed request."""

    def test_empty_messages_raises(self):
        """Empty messages list must raise PreprocessInvariantError."""
        with pytest.raises(PreprocessInvariantError, match="non-empty list"):
            _validate_preprocess_invariants(
                [],
                agent_name="CmdlineExtract",
                content_sha256="abc123",
                attention_preprocessor_enabled=True,
            )

    def test_missing_system_message_raises(self):
        """Messages without system role must raise."""
        with pytest.raises(PreprocessInvariantError, match="system message"):
            _validate_preprocess_invariants(
                [{"role": "user", "content": "x" * (MIN_USER_CONTENT_CHARS + 1) + "\nContent:\nArticle here"}],
                agent_name="CmdlineExtract",
                content_sha256="abc123",
                attention_preprocessor_enabled=True,
            )

    def test_missing_user_message_raises(self):
        """Messages without user role must raise."""
        with pytest.raises(PreprocessInvariantError, match="user message"):
            _validate_preprocess_invariants(
                [{"role": "system", "content": "You are an extractor."}],
                agent_name="CmdlineExtract",
                content_sha256="abc123",
                attention_preprocessor_enabled=True,
            )

    def test_short_user_content_raises(self):
        """User message below MIN_USER_CONTENT_CHARS must raise."""
        short_content = "x" * 100 + "\nContent:\nShort"
        with pytest.raises(PreprocessInvariantError, match="below minimum"):
            _validate_preprocess_invariants(
                [
                    {"role": "system", "content": "You are an extractor."},
                    {"role": "user", "content": short_content},
                ],
                agent_name="CmdlineExtract",
                content_sha256="abc123",
                attention_preprocessor_enabled=True,
            )

    def test_whitespace_only_user_content_raises(self):
        """User message with only whitespace must raise (fails length or empty check)."""
        with pytest.raises(PreprocessInvariantError, match="(empty or whitespace|below minimum)"):
            _validate_preprocess_invariants(
                [
                    {"role": "system", "content": "You are an extractor."},
                    {"role": "user", "content": "   \n\t  " * 200},
                ],
                agent_name="CmdlineExtract",
                content_sha256="abc123",
                attention_preprocessor_enabled=True,
            )

    def test_cmdline_missing_content_delimiter_raises(self):
        """CmdlineExtract user message must contain 'Content:' delimiter."""
        long_no_content = "x" * (MIN_USER_CONTENT_CHARS + 1)
        with pytest.raises(PreprocessInvariantError, match="Content:"):
            _validate_preprocess_invariants(
                [
                    {"role": "system", "content": "You are an extractor."},
                    {"role": "user", "content": long_no_content},
                ],
                agent_name="CmdlineExtract",
                content_sha256="abc123",
                attention_preprocessor_enabled=True,
            )

    def test_valid_messages_pass(self):
        """Valid messages with Content: and sufficient length pass."""
        valid_content = "x" * (MIN_USER_CONTENT_CHARS + 1) + "\nContent:\nArticle text here."
        _validate_preprocess_invariants(
            [
                {"role": "system", "content": "You are an extractor."},
                {"role": "user", "content": valid_content},
            ],
            agent_name="CmdlineExtract",
            content_sha256="abc123",
            attention_preprocessor_enabled=True,
        )

    def test_preprocess_invariant_error_has_debug_artifacts(self):
        """PreprocessInvariantError must include debug_artifacts."""
        try:
            _validate_preprocess_invariants(
                [],
                agent_name="CmdlineExtract",
                content_sha256="abc123",
                attention_preprocessor_enabled=True,
                user_prompt="preview",
            )
        except PreprocessInvariantError as e:
            assert e.debug_artifacts is not None
            assert e.debug_artifacts.get("agent_name") == "CmdlineExtract"
            assert e.debug_artifacts.get("content_sha256") == "abc123"
            assert "user_prompt_sha256" in e.debug_artifacts
            assert "user_prompt_preview" in e.debug_artifacts


class TestNewlineInvariantGuard:
    """Mechanical invariant: preprocessed newline count must match original (±1)."""

    @pytest.mark.asyncio
    async def test_newline_mismatch_raises_preprocess_invariant_error(self, llm_service):
        """When preprocessor returns full_article with wrong newline count, raise PreprocessInvariantError."""
        content = "line1\nline2\nline3"  # 2 newlines
        bad_full_article = "line1\nline2\nline3\n\n\nline4"  # 5 newlines (violation: |5-2| > 1)

        with patch("src.services.cmdline_attention_preprocessor.process") as mock_process:
            mock_process.return_value = {
                "high_likelihood_snippets": [],
                "full_article": bad_full_article,
            }
            with pytest.raises(PreprocessInvariantError, match="newline count mismatch"):
                await llm_service.run_extraction_agent(
                    agent_name="CmdlineExtract",
                    content=content,
                    title="Test",
                    url="https://example.com",
                    prompt_config={
                        "role": "You are an extractor.",
                        "task": "Extract",
                        "instructions": "Output JSON",
                        "json_example": "{}",
                    },
                    attention_preprocessor_enabled=True,
                )

    @pytest.mark.asyncio
    async def test_newline_match_within_tolerance_passes(self, llm_service):
        """When preprocessor preserves newlines (or ±1), extraction proceeds."""
        # Pad to meet MIN_USER_CONTENT_CHARS; preserve 2 newlines for invariant
        content = "line1\nline2\nline3\n" + "x" * (MIN_USER_CONTENT_CHARS - 20)
        with patch("src.services.cmdline_attention_preprocessor.process") as mock_process:
            mock_process.return_value = {
                "high_likelihood_snippets": [],
                "full_article": content,  # exact newline match
            }
            with patch.object(llm_service, "request_chat", new_callable=AsyncMock) as mock_request:
                mock_request.return_value = {
                    "choices": [{"message": {"content": '{"items":[],"count":0}'}}],
                    "usage": {},
                }
                result = await llm_service.run_extraction_agent(
                    agent_name="CmdlineExtract",
                    content=content,
                    title="Test",
                    url="https://example.com",
                    prompt_config={
                        "role": "You are an extractor.",
                        "task": "Extract",
                        "instructions": "Output JSON",
                        "json_example": "{}",
                    },
                    attention_preprocessor_enabled=True,
                )
                assert "items" in result

    @pytest.mark.asyncio
    async def test_newline_invariant_within_plus_minus_one_passes(self, llm_service):
        """When preprocessor adds/removes at most 1 newline (±1), invariant passes."""
        # orig: 2 newlines; prep: 3 newlines -> |3-2|=1, within tolerance
        content = "line1\nline2\nline3" + "x" * (MIN_USER_CONTENT_CHARS - 20)  # 2 newlines
        full_article = "line1\nline2\nline3\n" + "x" * (MIN_USER_CONTENT_CHARS - 21)  # 3 newlines
        with patch("src.services.cmdline_attention_preprocessor.process") as mock_process:
            mock_process.return_value = {
                "high_likelihood_snippets": [],
                "full_article": full_article,
            }
            with patch.object(llm_service, "request_chat", new_callable=AsyncMock) as mock_request:
                mock_request.return_value = {
                    "choices": [{"message": {"content": '{"items":[],"count":0}'}}],
                    "usage": {},
                }
                result = await llm_service.run_extraction_agent(
                    agent_name="CmdlineExtract",
                    content=content,
                    title="Test",
                    url="https://example.com",
                    prompt_config={
                        "role": "You are an extractor.",
                        "task": "Extract",
                        "instructions": "Output JSON",
                        "json_example": "{}",
                    },
                    attention_preprocessor_enabled=True,
                )
                assert "items" in result

    @pytest.mark.asyncio
    async def test_run_extraction_agent_stores_all_api_errors_in_last_result(self, llm_service):
        """On last attempt when request_chat raises, result has error, error_type, error_details."""
        api_error = RuntimeError("Temperature not supported for this model")
        prompt_cfg = {
            "role": "You are an extractor.",
            "task": "Extract",
            "instructions": "Output JSON",
            "json_example": "{}",
        }
        with patch("src.services.llm_service.trace_llm_call") as mock_trace:
            mock_gen = Mock()
            mock_trace.return_value.__enter__ = Mock(return_value=mock_gen)
            mock_trace.return_value.__exit__ = Mock(return_value=False)
            with patch.object(llm_service, "request_chat", new_callable=AsyncMock, side_effect=api_error):
                result = await llm_service.run_extraction_agent(
                    agent_name="CmdlineExtract",
                    content="x" * MIN_USER_CONTENT_CHARS,
                    title="Test",
                    url="https://example.com",
                    prompt_config=prompt_cfg,
                    max_retries=1,
                )
        assert result.get("error") == "Temperature not supported for this model"
        assert result.get("error_type") == "RuntimeError"
        assert result.get("error_details") == {
            "message": "Temperature not supported for this model",
            "exception_type": "RuntimeError",
            "attempt": 1,
            "agent_name": "CmdlineExtract",
        }
        assert result.get("connection_error") is False
        assert result.get("items") == []
        assert result.get("count") == 0

    @pytest.mark.asyncio
    async def test_run_extraction_agent_calls_log_llm_error_when_request_chat_raises(self, llm_service):
        """When request_chat raises inside trace_llm_call, log_llm_error is called with exception and metadata."""
        api_error = ValueError("API key invalid")
        mock_gen = Mock()
        prompt_cfg = {
            "role": "You are an extractor.",
            "task": "Extract",
            "instructions": "Output JSON",
            "json_example": "{}",
        }
        with (
            patch("src.services.llm_service.log_llm_error") as mock_log_error,
            patch("src.services.llm_service.trace_llm_call") as mock_trace,
        ):
            mock_trace.return_value.__enter__ = Mock(return_value=mock_gen)
            mock_trace.return_value.__exit__ = Mock(return_value=False)
            with patch.object(llm_service, "request_chat", new_callable=AsyncMock, side_effect=api_error):
                await llm_service.run_extraction_agent(
                    agent_name="CmdlineExtract",
                    content="x" * MIN_USER_CONTENT_CHARS,
                    title="Test",
                    url="https://example.com",
                    prompt_config=prompt_cfg,
                    max_retries=1,
                )
        mock_log_error.assert_called_once()
        call_args = mock_log_error.call_args
        assert call_args[0][0] is mock_gen
        assert call_args[0][1] is api_error
        assert call_args[1]["metadata"]["agent_name"] == "CmdlineExtract"
        assert call_args[1]["metadata"]["attempt"] == 1
        assert "model" in call_args[1]["metadata"]


class TestTraceabilityNormalization:
    """Tests for the traceability normalization logic in run_extraction_agent.

    Verifies that _normalize_traceability_item correctly wraps plain strings,
    validates confidence_score ranges, maps confidence_level to numeric scores,
    and infers the 'value' field from agent-specific keys.
    """

    _PROMPT_CFG = {
        "role": "You are an extractor.",
        "task": "Extract",
        "instructions": "Output JSON",
        "json_example": "{}",
    }

    @pytest.fixture
    def llm_service(self):
        config_models = {
            "RankAgent": "gpt-4",
            "RankAgent_provider": "openai",
            "ExtractAgent": "gpt-4",
            "ExtractAgent_provider": "openai",
            "SigmaAgent": "gpt-4",
            "SigmaAgent_provider": "openai",
        }
        with patch("src.services.llm_service.DatabaseManager") as mock_db:
            mock_db.return_value.get_session.return_value.query.return_value.all.return_value = []
            return LLMService(config_models=config_models)

    async def _run_extraction(self, llm_service, response_json: str, agent_name: str = "CmdlineExtract"):
        """Helper: run extraction with a mocked LLM response and return the parsed result."""
        with patch.object(llm_service, "request_chat", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {
                "choices": [{"message": {"content": response_json}}],
                "usage": {},
            }
            return await llm_service.run_extraction_agent(
                agent_name=agent_name,
                content="x" * MIN_USER_CONTENT_CHARS,
                title="Test",
                url="https://example.com",
                prompt_config=self._PROMPT_CFG,
            )

    @pytest.mark.asyncio
    async def test_plain_string_items_wrapped_into_objects(self, llm_service):
        """Plain string items in cmdline_items should become {value: ..., confidence_score: None}."""
        resp = '{"cmdline_items": ["cmd.exe /c whoami", "net user /domain"], "count": 2}'
        result = await self._run_extraction(llm_service, resp)
        items = result["cmdline_items"]
        assert len(items) == 2
        assert items[0] == {"value": "cmd.exe /c whoami", "confidence_score": None}
        assert items[1] == {"value": "net user /domain", "confidence_score": None}

    @pytest.mark.asyncio
    async def test_dict_items_with_valid_confidence_pass_through(self, llm_service):
        """Dict items with valid confidence_score (0.0-1.0) are preserved."""
        resp = '{"cmdline_items": [{"value": "cmd.exe /c dir", "confidence_score": 0.85}], "count": 1}'
        result = await self._run_extraction(llm_service, resp)
        assert result["cmdline_items"][0]["confidence_score"] == 0.85

    @pytest.mark.asyncio
    async def test_out_of_range_confidence_nulled(self, llm_service):
        """confidence_score outside 0.0-1.0 is set to None."""
        resp = '{"cmdline_items": [{"value": "cmd.exe /c dir", "confidence_score": 1.5}], "count": 1}'
        result = await self._run_extraction(llm_service, resp)
        assert result["cmdline_items"][0]["confidence_score"] is None

    @pytest.mark.asyncio
    async def test_non_numeric_confidence_nulled(self, llm_service):
        """Non-numeric confidence_score (e.g. string) is set to None."""
        resp = '{"cmdline_items": [{"value": "cmd.exe /c dir", "confidence_score": "high"}], "count": 1}'
        result = await self._run_extraction(llm_service, resp)
        # "high" can't be float-parsed, so confidence_score should be None
        assert result["cmdline_items"][0]["confidence_score"] is None

    @pytest.mark.asyncio
    async def test_confidence_level_maps_to_score(self, llm_service):
        """confidence_level high/medium/low should map to numeric confidence_score when score is absent.

        Note: registry_artifacts gets renamed to 'items' by the extraction pipeline
        before traceability normalization runs.
        """
        resp = (
            '{"registry_artifacts": ['
            '{"value": "HKLM\\\\Run", "confidence_level": "high", "source_evidence": "test"},'
            '{"value": "HKCU\\\\Run", "confidence_level": "medium", "source_evidence": "test"},'
            '{"value": "HKU\\\\Run", "confidence_level": "low", "source_evidence": "test"}'
            '], "count": 3}'
        )
        result = await self._run_extraction(llm_service, resp, agent_name="RegistryExtract")
        # registry_artifacts is renamed to 'items' by the pipeline
        arts = result["items"]
        assert arts[0]["confidence_score"] == 0.95
        assert arts[1]["confidence_score"] == 0.7
        assert arts[2]["confidence_score"] == 0.4

    @pytest.mark.asyncio
    async def test_confidence_level_does_not_override_valid_score(self, llm_service):
        """When both confidence_score and confidence_level exist, the numeric score wins."""
        resp = (
            '{"registry_artifacts": ['
            '{"value": "HKLM\\\\Run", "confidence_score": 0.55, "confidence_level": "high"}'
            '], "count": 1}'
        )
        result = await self._run_extraction(llm_service, resp, agent_name="RegistryExtract")
        # registry_artifacts is renamed to 'items' by the pipeline
        assert result["items"][0]["confidence_score"] == 0.55

    @pytest.mark.asyncio
    async def test_value_inferred_from_query_key(self, llm_service):
        """When 'value' is missing but 'query' exists, it should be used as the value."""
        resp = (
            '{"queries": ['
            '{"query": "index=main sourcetype=sysmon", "source_evidence": "found in article"}'
            '], "count": 1}'
        )
        result = await self._run_extraction(llm_service, resp, agent_name="HuntQueriesExtract")
        assert result["queries"][0]["value"] == "index=main sourcetype=sysmon"

    @pytest.mark.asyncio
    async def test_value_inferred_from_cmdline_key(self, llm_service):
        """When 'value' is missing but 'cmdline' exists, it should be used as the value."""
        resp = '{"cmdline_items": [{"cmdline": "net.exe user admin", "source_evidence": "test"}], "count": 1}'
        result = await self._run_extraction(llm_service, resp)
        assert result["cmdline_items"][0]["value"] == "net.exe user admin"

    @pytest.mark.asyncio
    async def test_normalization_applies_to_cmdline_items(self, llm_service):
        """Normalization wraps plain strings in cmdline_items into objects."""
        resp = '{"cmdline_items": ["cmd.exe /c test", "net.exe user"], "count": 2}'
        result = await self._run_extraction(llm_service, resp)
        for item in result["cmdline_items"]:
            assert isinstance(item, dict), "cmdline_items should be normalized to dicts"
            assert "value" in item

    @pytest.mark.asyncio
    async def test_normalization_applies_to_items_key(self, llm_service):
        """Normalization wraps plain strings in items into objects."""
        resp = '{"items": ["item1", "item2"], "count": 2}'
        result = await self._run_extraction(llm_service, resp)
        for item in result["items"]:
            assert isinstance(item, dict), "items should be normalized to dicts"
            assert "value" in item


class TestQACorrectionsApplication:
    """Tests for the QA corrections-application path in run_extraction_agent.

    Verifies the v1 QA model (CmdlineExtract): extractor runs once, QA runs once,
    QA's `corrections.removed` is applied as a filter on the items list, and the
    function returns immediately with no further re-extraction.
    """

    _EXTRACT_PROMPT = {
        "role": "You are a Windows command-line extractor.",
        "task": "Extract command-line strings.",
        "instructions": "Output JSON only.",
        "json_example": '{"cmdline_items": [], "count": 0}',
    }

    _QA_PROMPT = {
        "role": "You are a QA validator.",
        "instructions": "Validate extractions and return corrections.",
        "evaluation_criteria": [
            "Each command appears verbatim in source.",
            "Each command starts with a recognized executable.",
        ],
        "objective": "Validate command-line extractions.",
    }

    @pytest.fixture
    def llm_service(self):
        config_models = {
            "RankAgent": "gpt-4",
            "RankAgent_provider": "openai",
            "ExtractAgent": "gpt-4",
            "ExtractAgent_provider": "openai",
            "SigmaAgent": "gpt-4",
            "SigmaAgent_provider": "openai",
        }
        with patch("src.services.llm_service.DatabaseManager") as mock_db:
            mock_db.return_value.get_session.return_value.query.return_value.all.return_value = []
            return LLMService(config_models=config_models)

    async def _run_with_qa(
        self,
        llm_service,
        extract_response_json: str,
        qa_response_json: str,
        agent_name: str = "CmdlineExtract",
    ):
        """Helper: run extraction with mocked extract + QA responses."""
        responses = [
            {"choices": [{"message": {"content": extract_response_json}}], "usage": {}},
            {"choices": [{"message": {"content": qa_response_json}}], "usage": {}},
        ]
        with patch.object(llm_service, "request_chat", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = responses
            return await llm_service.run_extraction_agent(
                agent_name=agent_name,
                content="x" * MIN_USER_CONTENT_CHARS,
                title="Test",
                url="https://example.com",
                prompt_config=self._EXTRACT_PROMPT,
                qa_prompt_config=self._QA_PROMPT,
                max_retries=3,
            )

    @pytest.mark.asyncio
    async def test_qa_corrections_removed_filters_items(self, llm_service):
        """When QA returns a removal, that item must be absent from the result.

        Regression fixture: article_11 from eval_bundles_v2599_cmdline.zip --
        QA flagged 'findstr searches for cpassword in SYSVOL' as a non-command
        every run, but the item kept appearing in the output. After this fix it
        should be filtered out.
        """
        extract_resp = (
            '{"cmdline_items": ['
            '{"value": "nltest /DCLIST", "confidence_score": 0.95},'
            '{"value": "findstr searches for cpassword in SYSVOL", "confidence_score": 0.9},'
            '{"value": "cmd.exe /c ipconfig /all & whoami", "confidence_score": 0.95}'
            '], "count": 3}'
        )
        qa_resp = (
            '{"status": "needs_revision", "summary": "found one bad item", '
            '"issues": [], '
            '"corrections": {"removed": ['
            '{"command": "findstr searches for cpassword in SYSVOL", "reason": "not a command"}'
            '], "added": []}}'
        )
        result = await self._run_with_qa(llm_service, extract_resp, qa_resp)

        values = [item["value"] for item in result["cmdline_items"]]
        assert "findstr searches for cpassword in SYSVOL" not in values
        assert "nltest /DCLIST" in values
        assert "cmd.exe /c ipconfig /all & whoami" in values
        assert result["count"] == 2

        qa_meta = result["_qa_result"]
        assert qa_meta["pre_filter_count"] == 3
        assert qa_meta["corrections_applied"]["removed"] == ["findstr searches for cpassword in SYSVOL"]

    @pytest.mark.asyncio
    async def test_qa_pass_with_empty_corrections_returns_unchanged(self, llm_service):
        """A clean QA pass with empty corrections must return items unchanged in 1 attempt."""
        extract_resp = '{"cmdline_items": [{"value": "cmd.exe /c whoami", "confidence_score": 0.95}], "count": 1}'
        qa_resp = '{"status": "pass", "summary": "all good", "issues": [], "corrections": {"removed": [], "added": []}}'
        result = await self._run_with_qa(llm_service, extract_resp, qa_resp)

        assert result["count"] == 1
        assert result["cmdline_items"][0]["value"] == "cmd.exe /c whoami"
        assert result["_llm_attempt"] == 1
        assert result["_qa_result"]["verdict"] == "pass"
        assert result["_qa_result"]["pre_filter_count"] == 1
        assert result["_qa_result"]["corrections_applied"]["removed"] == []

    @pytest.mark.asyncio
    async def test_qa_parse_failure_marks_needs_revision(self, llm_service):
        """Fail-closed: QA returning unparseable output must NOT pass the result through.

        Previously the code defaulted to status='pass' on parse failure (silent fail-open).
        After this change it must record needs_revision so the trace surfaces the issue.
        """
        extract_resp = '{"cmdline_items": [{"value": "cmd.exe /c whoami", "confidence_score": 0.95}], "count": 1}'
        qa_resp = "this is not JSON at all, just plain text from a confused model"
        result = await self._run_with_qa(llm_service, extract_resp, qa_resp)

        # Items pass through (we don't have parsed corrections to apply).
        assert result["count"] == 1
        # But the QA verdict reflects the parse failure.
        assert result["_qa_result"]["verdict"] == "needs_revision"
        assert result["_qa_result"]["status"] == "fail"
        assert result["_qa_result"]["pre_filter_count"] == 1

    @pytest.mark.asyncio
    async def test_qa_parse_failure_zero_items_returns_clean(self, llm_service):
        """Parse failure on a zero-item extraction is a no-op: return without recording verdict."""
        extract_resp = '{"cmdline_items": [], "count": 0}'
        qa_resp = "garbage non-JSON output"
        result = await self._run_with_qa(llm_service, extract_resp, qa_resp)

        assert result["count"] == 0
        # Early-exit path doesn't write _qa_result -- the QA call was effectively a no-op.
        assert "_qa_result" not in result

    @pytest.mark.asyncio
    async def test_qa_returns_immediately_no_re_extraction(self, llm_service):
        """After QA runs, run_extraction_agent must return -- no second extract call.

        Before this fix the loop would re-run the extractor with vague feedback up to
        max_retries times. After the fix QA always terminates the loop.
        """
        extract_resp = '{"cmdline_items": [{"value": "cmd.exe /c bad", "confidence_score": 0.5}], "count": 1}'
        qa_resp = (
            '{"status": "needs_revision", "summary": "bad", "issues": [], '
            '"corrections": {"removed": [{"command": "cmd.exe /c bad", "reason": "n/a"}], "added": []}}'
        )

        responses = [
            {"choices": [{"message": {"content": extract_resp}}], "usage": {}},
            {"choices": [{"message": {"content": qa_resp}}], "usage": {}},
        ]
        with patch.object(llm_service, "request_chat", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = responses
            result = await llm_service.run_extraction_agent(
                agent_name="CmdlineExtract",
                content="x" * MIN_USER_CONTENT_CHARS,
                title="Test",
                url="https://example.com",
                prompt_config=self._EXTRACT_PROMPT,
                qa_prompt_config=self._QA_PROMPT,
                max_retries=5,  # large budget; verify we don't consume it
            )
            # Exactly 2 calls: 1 extract + 1 QA. No re-extraction loop.
            assert mock_req.call_count == 2

        assert result["_llm_attempt"] == 1
        assert result["count"] == 0  # the one bad item was filtered out

    @pytest.mark.asyncio
    async def test_qa_corrections_not_applied_for_non_cmdline_in_v1(self, llm_service):
        """v1 scope guard: non-CmdlineExtract agents do NOT have corrections applied.

        The display issues are still built from corrections, but the items list is untouched.
        Per-agent identity mapping is required before extending the filter.
        """
        # RegistryExtract gets renamed to 'items' by the pipeline.
        extract_resp = (
            '{"registry_artifacts": ['
            '{"value": "HKLM\\\\Run\\\\evil", "source_evidence": "x"},'
            '{"value": "HKCU\\\\Run\\\\good", "source_evidence": "y"}'
            '], "count": 2}'
        )
        qa_resp = (
            '{"status": "needs_revision", "summary": "one bad", "issues": [], '
            '"corrections": {"removed": ['
            '{"command": "HKLM\\\\Run\\\\evil", "reason": "should be removed"}'
            '], "added": []}}'
        )
        result = await self._run_with_qa(llm_service, extract_resp, qa_resp, agent_name="RegistryExtract")

        # Items list is unchanged for non-cmdline agents in v1.
        assert result["count"] == 2
        # But corrections_applied reflects that nothing was applied.
        assert result["_qa_result"]["corrections_applied"]["removed"] == []
        assert result["_qa_result"]["pre_filter_count"] == 2

    @pytest.mark.asyncio
    async def test_qa_handles_null_command_in_corrections(self, llm_service):
        """Defensive: a model emitting `{"command": null}` must not crash the filter."""
        extract_resp = '{"cmdline_items": [{"value": "cmd.exe /c whoami", "confidence_score": 0.95}], "count": 1}'
        # Mix of bad and good entries: the bad ones should be ignored, not crash.
        qa_resp = (
            '{"status": "needs_revision", "summary": "messy", "issues": [], '
            '"corrections": {"removed": ['
            '{"command": null, "reason": "model emitted null"},'
            '{"command": "", "reason": "empty string"},'
            '{"reason": "no command field at all"},'
            '{"command": "cmd.exe /c whoami", "reason": "this one is real"}'
            '], "added": []}}'
        )
        result = await self._run_with_qa(llm_service, extract_resp, qa_resp)

        # The one valid removal applies; the malformed entries are silently skipped.
        assert result["count"] == 0
        assert result["_qa_result"]["corrections_applied"]["removed"] == ["cmd.exe /c whoami"]

    @pytest.mark.asyncio
    async def test_qa_handles_null_items_field(self, llm_service):
        """Defensive: a model emitting `{"cmdline_items": null, "count": 0}` must not crash on len()."""
        extract_resp = '{"cmdline_items": null, "count": 0}'
        qa_resp = (
            '{"status": "pass", "summary": "nothing to validate", "issues": [], '
            '"corrections": {"removed": [], "added": []}}'
        )
        # Should not raise; pre_filter_count should be 0.
        result = await self._run_with_qa(llm_service, extract_resp, qa_resp)
        assert result["_qa_result"]["pre_filter_count"] == 0

    @pytest.mark.asyncio
    async def test_qa_handles_null_status_field(self, llm_service):
        """Defensive: a model emitting `{"status": null}` must not crash on .lower()."""
        extract_resp = '{"cmdline_items": [{"value": "cmd.exe /c whoami", "confidence_score": 0.95}], "count": 1}'
        qa_resp = (
            '{"status": null, "summary": "model returned null status", "issues": [], '
            '"corrections": {"removed": [], "added": []}}'
        )
        result = await self._run_with_qa(llm_service, extract_resp, qa_resp)

        # Null status must not crash; it falls through to needs_revision.
        assert result["count"] == 1  # nothing removed
        assert result["_qa_result"]["status"] == "needs_revision"

    @pytest.mark.asyncio
    async def test_qa_handles_null_value_in_extracted_item(self, llm_service):
        """Defensive: an item with `value: null` must not crash the filter, just be left alone."""
        extract_resp = (
            '{"cmdline_items": ['
            '{"value": null, "confidence_score": 0.5},'
            '{"value": "cmd.exe /c whoami", "confidence_score": 0.95}'
            '], "count": 2}'
        )
        qa_resp = (
            '{"status": "needs_revision", "summary": "remove one", "issues": [], '
            '"corrections": {"removed": ['
            '{"command": "cmd.exe /c whoami", "reason": "test"}'
            '], "added": []}}'
        )
        result = await self._run_with_qa(llm_service, extract_resp, qa_resp)

        # The null-valued item stays (filter compared "" not in {"cmd.exe /c whoami"}, which is True).
        # The matching item is removed.
        values = [item.get("value") for item in result["cmdline_items"]]
        assert values == [None]
        assert result["count"] == 1
