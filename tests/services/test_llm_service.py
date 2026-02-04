"""Tests for LLM service functionality."""

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
            mock_client.post = AsyncMock(side_effect=Exception("API error"))
            mock_client_class.return_value.__aenter__.return_value = mock_client

            with pytest.raises(Exception):
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
                        "user_template": (
                            "Title: {title}\nURL: {url}\nContent:\n{content}\nTask: {task}\n"
                            "JSON: {json_example}\nInstructions: {instructions}"
                        ),
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
                        "user_template": (
                            "Title: {title}\nURL: {url}\nContent:\n{content}\nTask: {task}\n"
                            "JSON: {json_example}\nInstructions: {instructions}"
                        ),
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
                        "user_template": (
                            "Title: {title}\nURL: {url}\nContent:\n{content}\nTask: {task}\n"
                            "JSON: {json_example}\nInstructions: {instructions}"
                        ),
                        "task": "Extract",
                        "instructions": "Output JSON",
                        "json_example": "{}",
                    },
                    attention_preprocessor_enabled=True,
                )
                assert "items" in result
