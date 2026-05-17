"""Pin tests for prompt assembly behavior.

These tests pin the hardcoded prompt components that the UI does not show:
- Traceability block allowlist (which agents get it)
- System prompt fallback ("You are a detection engineer.")
- Legacy scaffold structure (Title/URL/Content/Task/Output Format/CRITICAL INSTRUCTIONS)
- QA feedback prepend
- Preset user: prefix
- Content truncation marker
- Actual count fallback (len(items) when count field is missing)

See docs/concepts/agents.md#prompt-architecture for the design rationale.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.services.llm_service import MIN_USER_CONTENT_CHARS, LLMService
from src.workflows.agentic_workflow import _extract_actual_count

pytestmark = pytest.mark.unit


@pytest.fixture
def llm_service():
    """Create LLMService with mocked DB."""
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
        yield LLMService(config_models=config_models)


# ---------------------------------------------------------------------------
# Traceability block allowlist
# ---------------------------------------------------------------------------


class TestTraceabilityBlockAllowlist:
    """Pin which agents get the hardcoded traceability block appended."""

    TRACEABILITY_AGENTS = {
        "CmdlineExtract",
        "ProcTreeExtract",
        "HuntQueriesExtract",
        "RegistryExtract",
        "ServicesExtract",
    }

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "agent_name",
        [
            "CmdlineExtract",
            "ProcTreeExtract",
            "HuntQueriesExtract",
            "RegistryExtract",
            "ServicesExtract",
        ],
    )
    async def test_traceability_block_appended(self, llm_service, agent_name):
        """Agents in the allowlist get source_evidence/confidence_score/extraction_justification appended."""
        content = "x" * (MIN_USER_CONTENT_CHARS + 100)

        with patch.object(llm_service, "request_chat", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = {
                "choices": [{"message": {"content": '{"items":[],"count":0}'}}],
                "usage": {},
            }
            await llm_service.run_extraction_agent(
                agent_name=agent_name,
                content=content,
                title="Test Article",
                url="https://example.com/test",
                prompt_config={
                    "system": "You are a test extractor.",
                    "task": "Extract test artifacts.",
                    "instructions": "Output valid JSON.",
                    "json_example": '{"items":[],"count":0}',
                },
            )

            # Inspect the user message that was sent
            call_args = mock_chat.call_args
            messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
            user_msg = next(m["content"] for m in messages if m["role"] == "user")
            assert "TRACEABILITY (REQUIRED)" in user_msg, f"{agent_name} should get traceability block appended"
            assert "source_evidence" in user_msg
            assert "extraction_justification" in user_msg
            assert "confidence_score" in user_msg


# ---------------------------------------------------------------------------
# System prompt fallback
# ---------------------------------------------------------------------------


class TestSystemFallback:
    """Extractor Contract enforcement: missing system/role is a hard fail, not a silent fallback."""

    @pytest.mark.asyncio
    async def test_system_fallback_when_role_missing(self, llm_service):
        """When prompt_config has no 'system' or 'role', raises ValueError (contract enforcement).

        Previously the code silently substituted "You are a detection engineer." which masked
        misconfigured prompts. The Extractor Contract (extractor-standard.md sec 1) requires a
        hard fail so callers see the misconfiguration immediately.
        """
        content = "x" * (MIN_USER_CONTENT_CHARS + 100)

        with pytest.raises(ValueError, match="missing required 'system'/'role' key"):
            await llm_service.run_extraction_agent(
                agent_name="CmdlineExtract",
                content=content,
                title="Test",
                url="https://example.com",
                prompt_config={
                    "task": "Extract commands.",
                    "instructions": "Output JSON.",
                    "json_example": '{"items":[],"count":0}',
                },
            )

    @pytest.mark.asyncio
    async def test_system_uses_role_field(self, llm_service):
        """When prompt_config has 'role' but no 'system', use role."""
        content = "x" * (MIN_USER_CONTENT_CHARS + 100)

        with patch.object(llm_service, "request_chat", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = {
                "choices": [{"message": {"content": '{"items":[],"count":0}'}}],
                "usage": {},
            }
            await llm_service.run_extraction_agent(
                agent_name="CmdlineExtract",
                content=content,
                title="Test",
                url="https://example.com",
                prompt_config={
                    "role": "You are a specialized Windows command extractor.",
                    "task": "Extract commands.",
                    "instructions": "Output JSON.",
                    "json_example": '{"items":[],"count":0}',
                },
            )

            call_args = mock_chat.call_args
            messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
            system_msg = next(m["content"] for m in messages if m["role"] == "system")
            assert system_msg == "You are a specialized Windows command extractor."

    @pytest.mark.asyncio
    async def test_system_field_takes_precedence_over_role(self, llm_service):
        """When both 'system' and 'role' are present, 'system' wins."""
        content = "x" * (MIN_USER_CONTENT_CHARS + 100)

        with patch.object(llm_service, "request_chat", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = {
                "choices": [{"message": {"content": '{"items":[],"count":0}'}}],
                "usage": {},
            }
            await llm_service.run_extraction_agent(
                agent_name="CmdlineExtract",
                content=content,
                title="Test",
                url="https://example.com",
                prompt_config={
                    "system": "I am the system prompt.",
                    "role": "I am the role prompt.",
                    "task": "Extract commands.",
                    "instructions": "Output JSON.",
                    "json_example": '{"items":[],"count":0}',
                },
            )

            call_args = mock_chat.call_args
            messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
            system_msg = next(m["content"] for m in messages if m["role"] == "system")
            assert system_msg == "I am the system prompt."


# ---------------------------------------------------------------------------
# Legacy scaffold structure
# ---------------------------------------------------------------------------


class TestLegacyScaffold:
    """Extractor Contract enforcement: user_template in preset is a hard fail (scaffold is code-owned)."""

    @pytest.mark.asyncio
    async def test_legacy_scaffold_ignores_user_template(self, llm_service):
        """prompt_config with user_template raises ValueError (was previously silently ignored).

        The Extractor Contract (extractor-standard.md sec 5 note) states the user message scaffold
        is code-owned; preset authors must not write or edit user_template. The check was promoted
        from a silent no-op to a hard fail so misconfigured presets are caught immediately.
        """
        content = "This is a test article about malware.\n" * 50

        with pytest.raises(ValueError, match="must not contain 'user_template'"):
            await llm_service.run_extraction_agent(
                agent_name="CmdlineExtract",
                content=content,
                title="Malware Analysis Report",
                url="https://example.com/report",
                prompt_config={
                    "system": "You are an extractor.",
                    "user_template": "IGNORED TEMPLATE: {title}",
                    "objective": "Extract commands.",
                    "instructions": "Output valid JSON.",
                    "output_format": {"items": [], "count": 0},
                },
            )

    @pytest.mark.asyncio
    async def test_legacy_scaffold_json_nudge(self, llm_service):
        """Legacy path appends 'must end with a valid JSON object' nudge."""
        content = "x" * (MIN_USER_CONTENT_CHARS + 100)

        with patch.object(llm_service, "request_chat", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = {
                "choices": [{"message": {"content": '{"items":[],"count":0}'}}],
                "usage": {},
            }
            await llm_service.run_extraction_agent(
                agent_name="CmdlineExtract",
                content=content,
                title="Test",
                url="https://example.com",
                prompt_config={
                    "system": "You are an extractor.",
                    "task": "Extract.",
                    "instructions": "Output JSON.",
                    "output_format": {"items": [], "count": 0},
                    "json_example": '{"items":[],"count":0}',
                },
            )

            call_args = mock_chat.call_args
            messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
            user_msg = next(m["content"] for m in messages if m["role"] == "user")
            assert "must end with a valid JSON object" in user_msg



# ---------------------------------------------------------------------------
# Preset user: prefix
# ---------------------------------------------------------------------------


class TestPresetUserPrefix:
    """Pin that preset 'user' field is prepended to user message."""

    @pytest.mark.asyncio
    async def test_user_prefix_prepended(self, llm_service):
        """When prompt_config has a 'user' field, it's prepended to the user message."""
        content = "x" * (MIN_USER_CONTENT_CHARS + 100)

        with patch.object(llm_service, "request_chat", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = {
                "choices": [{"message": {"content": '{"items":[],"count":0}'}}],
                "usage": {},
            }
            await llm_service.run_extraction_agent(
                agent_name="CmdlineExtract",
                content=content,
                title="Test",
                url="https://example.com",
                prompt_config={
                    "system": "You are an extractor.",
                    "user": "Analyze the following threat intelligence article.",
                    "task": "Extract.",
                    "instructions": "Output JSON.",
                    "json_example": '{"items":[],"count":0}',
                },
            )

            call_args = mock_chat.call_args
            messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
            user_msg = next(m["content"] for m in messages if m["role"] == "user")
            assert user_msg.startswith("Analyze the following threat intelligence article.")


# ---------------------------------------------------------------------------
# Content truncation marker
# ---------------------------------------------------------------------------


class TestContentTruncation:
    """Pin the truncation marker injection."""

    def test_truncation_marker_injected(self, llm_service):
        """When content exceeds available tokens, a truncation marker is added."""
        long_content = "x" * 100000  # very long

        truncated = llm_service._truncate_content(long_content, max_context_tokens=1000, max_output_tokens=100)

        assert "[Content truncated" in truncated
        assert len(truncated) < len(long_content)

    def test_short_content_not_truncated(self, llm_service):
        """Short content is returned unchanged (no marker)."""
        short_content = "This is a short article."

        result = llm_service._truncate_content(short_content, max_context_tokens=100000, max_output_tokens=100)

        assert result == short_content
        assert "[Content truncated" not in result


# ---------------------------------------------------------------------------
# Actual count fallback (len(items) when count field is missing)
# ---------------------------------------------------------------------------


class TestActualCountFallback:
    """Pin that _extract_actual_count falls back to len(items) when count is missing."""

    def test_count_field_preferred(self):
        """When count field is present, use it."""
        subresults = {"cmdline": {"count": 5, "items": [1, 2, 3]}}
        assert _extract_actual_count("cmdline", subresults, execution_id=1) == 5

    def test_fallback_to_len_items(self):
        """When count is missing, fall back to len(items)."""
        subresults = {"cmdline": {"items": ["a", "b", "c"]}}
        assert _extract_actual_count("cmdline", subresults, execution_id=1) == 3

    def test_fallback_to_zero_when_no_items(self):
        """When both count and items are missing, return 0."""
        subresults = {"cmdline": {}}
        assert _extract_actual_count("cmdline", subresults, execution_id=1) == 0

    def test_hunt_queries_prefers_count(self):
        """hunt_queries subagent prefers `count` (current contract) over legacy `query_count` alias."""
        subresults = {"hunt_queries": {"query_count": 7, "count": 3, "queries": [1]}}
        assert _extract_actual_count("hunt_queries", subresults, execution_id=1) == 3

    def test_hunt_queries_falls_back_to_query_count(self):
        """hunt_queries falls back to legacy `query_count` when `count` is missing (cached executions)."""
        subresults = {"hunt_queries": {"query_count": 4, "queries": [1, 2]}}
        assert _extract_actual_count("hunt_queries", subresults, execution_id=1) == 4

    def test_hunt_queries_falls_back_to_len_queries(self):
        """hunt_queries falls back to len(queries) when both count fields are missing."""
        subresults = {"hunt_queries": {"queries": ["q1", "q2", "q3"]}}
        assert _extract_actual_count("hunt_queries", subresults, execution_id=1) == 3

    def test_non_dict_result_returns_none(self):
        """Non-dict subresult returns None (logged as warning)."""
        subresults = {"cmdline": "not a dict"}
        assert _extract_actual_count("cmdline", subresults, execution_id=1) is None

    def test_missing_subagent_returns_none(self):
        """Missing subagent key returns 0 (empty dict fallback)."""
        subresults = {}
        result = _extract_actual_count("cmdline", subresults, execution_id=1)
        assert result == 0


# ---------------------------------------------------------------------------
# task key used when objective is absent (eval 3802 fix)
# ---------------------------------------------------------------------------


class TestTaskKeyFallback:
    """Pin that prompt_config 'task' key is used when 'objective' is absent.

    Extractor prompts using the new envelope format (role/task/json_example/instructions)
    previously had their task description silently ignored -- the code looked for 'objective'
    only and fell back to the generic 'Extract information.' string. Fixed in eval 3802.
    """

    @pytest.mark.asyncio
    async def test_task_key_appears_in_user_message(self, llm_service):
        """When prompt_config has 'task' but no 'objective', task text appears in user message."""
        content = "x" * (MIN_USER_CONTENT_CHARS + 100)

        with patch.object(llm_service, "request_chat", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = {
                "choices": [{"message": {"content": '{"items":[],"count":0}'}}],
                "usage": {},
            }
            await llm_service.run_extraction_agent(
                agent_name="CmdlineExtract",
                content=content,
                title="Test",
                url="https://example.com",
                prompt_config={
                    "system": "You are a test extractor.",
                    "task": "Extract only Windows command-line literals for EDR use.",
                    "instructions": "Output valid JSON.",
                    "json_example": '{"items":[],"count":0}',
                },
            )

            call_args = mock_chat.call_args
            messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
            user_msg = next(m["content"] for m in messages if m["role"] == "user")
            assert "Extract only Windows command-line literals for EDR use." in user_msg, (
                "The 'task' field must appear in the user message when 'objective' is absent. "
                "Before the eval 3802 fix, task was silently ignored and the generic "
                "'Extract information.' fallback was used instead."
            )

    @pytest.mark.asyncio
    async def test_objective_takes_precedence_over_task(self, llm_service):
        """When both 'objective' and 'task' are present, 'objective' wins (backward compat)."""
        content = "x" * (MIN_USER_CONTENT_CHARS + 100)

        with patch.object(llm_service, "request_chat", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = {
                "choices": [{"message": {"content": '{"items":[],"count":0}'}}],
                "usage": {},
            }
            await llm_service.run_extraction_agent(
                agent_name="CmdlineExtract",
                content=content,
                title="Test",
                url="https://example.com",
                prompt_config={
                    "system": "You are a test extractor.",
                    "objective": "Objective text (should win).",
                    "task": "Task text (should lose).",
                    "instructions": "Output valid JSON.",
                    "json_example": '{"items":[],"count":0}',
                },
            )

            call_args = mock_chat.call_args
            messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
            user_msg = next(m["content"] for m in messages if m["role"] == "user")
            assert "Objective text (should win)." in user_msg
            assert "Task text (should lose)." not in user_msg
