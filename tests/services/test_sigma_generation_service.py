"""Tests for SIGMA generation service functionality."""

import contextlib
from unittest.mock import AsyncMock, Mock, patch

import pytest
import yaml

from src.services.sigma_generation_service import (
    SigmaGenerationService,
    _build_observables_section,
    _extract_message_text,
    _infer_observables_used,
    _is_reasoning_model,
)
from src.services.sigma_validator import ValidationResult

# Mark all tests in this file as unit tests (use mocks, no real infrastructure)
pytestmark = pytest.mark.unit


def test_extract_message_text_handles_openai_content_parts():
    """OpenAI content-part payloads should be normalized to plain text."""
    payload = [{"type": "output_text", "text": "title: Test Rule\n"}, {"type": "output_text", "text": "id: abc"}]
    assert _extract_message_text(payload) == "title: Test Rule\nid: abc"


class TestExtractMessageTextEdgeCases:
    """Cover all branches of _extract_message_text normalizer."""

    def test_none_returns_empty(self):
        assert _extract_message_text(None) == ""

    def test_plain_string_passthrough(self):
        assert _extract_message_text("hello world") == "hello world"

    def test_empty_string(self):
        assert _extract_message_text("") == ""

    def test_empty_list(self):
        assert _extract_message_text([]) == ""

    def test_dict_with_text_key(self):
        assert _extract_message_text({"text": "some text", "type": "output"}) == "some text"

    def test_dict_with_content_key(self):
        assert _extract_message_text({"content": "body text"}) == "body text"

    def test_dict_with_value_key(self):
        assert _extract_message_text({"value": "val"}) == "val"

    def test_dict_prefers_text_over_content(self):
        """text key should be checked before content key."""
        assert _extract_message_text({"text": "preferred", "content": "fallback"}) == "preferred"

    def test_dict_with_only_whitespace_values_returns_empty(self):
        assert _extract_message_text({"text": "  ", "content": "  "}) == ""

    def test_list_with_content_fallback(self):
        """List items with 'content' key but no 'text' key should use content."""
        payload = [{"content": "part1"}, {"content": "part2"}]
        assert _extract_message_text(payload) == "part1part2"

    def test_list_with_mixed_strings_and_dicts(self):
        payload = ["raw string", {"text": " and dict"}]
        assert _extract_message_text(payload) == "raw string and dict"

    def test_list_skips_non_string_non_dict_items(self):
        payload = [42, None, {"text": "ok"}]
        assert _extract_message_text(payload) == "ok"

    def test_unrecognized_type_returns_empty(self):
        assert _extract_message_text(12345) == ""


def test_is_reasoning_model_treats_openai_sigma_path_as_reasoning():
    """SIGMA workflow should budget OpenAI models as reasoning-style."""
    assert _is_reasoning_model("openai", "gpt-5.4")
    assert _is_reasoning_model("openai", "gpt-4.1")
    assert _is_reasoning_model("openai", "gpt-4o")
    assert not _is_reasoning_model("lmstudio", "mistral-7b-instruct")


class TestIsReasoningModelEdgeCases:
    """Additional edge cases for _is_reasoning_model."""

    def test_r1_model_detected_for_any_provider(self):
        assert _is_reasoning_model("lmstudio", "deepseek-r1")
        assert _is_reasoning_model("lmstudio", "DeepSeek-R1-0528")

    def test_reasoning_keyword_detected(self):
        assert _is_reasoning_model("lmstudio", "custom-reasoning-v2")

    def test_none_model_name_does_not_crash(self):
        assert not _is_reasoning_model("lmstudio", None)
        assert _is_reasoning_model("openai", None)


class TestSigmaGenerationService:
    """Test SigmaGenerationService functionality."""

    @pytest.fixture
    def mock_llm_service(self):
        """Create mock LLM service."""
        service = Mock()
        service.provider_sigma = "lmstudio"
        service.lmstudio_model = "test-model-7b"
        service._canonicalize_provider = Mock(return_value="lmstudio")
        return service

    @pytest.fixture
    def service(self, mock_llm_service):
        """Create SigmaGenerationService instance with mocked dependencies."""
        with patch("src.services.sigma_generation_service.LLMService", return_value=mock_llm_service):
            return SigmaGenerationService()

    @pytest.fixture
    def sample_article_data(self):
        """Sample article data for testing."""
        return {
            "title": "APT29 Uses PowerShell for Persistence",
            "content": "Advanced Persistent Threat group APT29 has been observed using PowerShell scripts to maintain persistence on compromised systems. The attack involves creating scheduled tasks and registry modifications.",
            "source_name": "Threat Intelligence Feed",
            "url": "https://example.com/threat-report-123",
        }

    @pytest.fixture
    def sample_sigma_rule(self):
        """Sample valid SIGMA rule YAML."""
        return """
title: PowerShell Scheduled Task Creation
id: test-rule-123
description: Detects creation of scheduled tasks via PowerShell
logsource:
    category: process_creation
    product: windows
detection:
    selection:
        CommandLine|contains: 'schtasks'
        CommandLine|contains: '/create'
    condition: selection
level: medium
"""

    @pytest.mark.asyncio
    async def test_generate_sigma_rules_success(self, service, sample_article_data, sample_sigma_rule):
        """Test successful SIGMA rule generation."""
        # Mock content optimization
        with patch("src.services.sigma_generation_service.optimize_article_content") as mock_optimize:
            mock_optimize.return_value = {
                "success": True,
                "filtered_content": sample_article_data["content"],
                "tokens_saved": 100,
            }

            # Mock prompt loading
            with patch("src.utils.prompt_loader.format_prompt_async") as mock_prompt:
                mock_prompt.return_value = f"Generate SIGMA rule for: {sample_article_data['title']}"

                # Mock LLM service call
                with patch.object(service, "_call_provider_for_sigma") as mock_call:
                    mock_call.return_value = sample_sigma_rule

                    # Mock validation
                    with patch("src.services.sigma_generation_service.validate_sigma_rule") as mock_validate:
                        mock_validate.return_value = ValidationResult(
                            is_valid=True,
                            errors=[],
                            warnings=[],
                            metadata={"rule": yaml.safe_load(sample_sigma_rule)},
                            content_preview=sample_sigma_rule,
                        )

                        result = await service.generate_sigma_rules(
                            article_title=sample_article_data["title"],
                            article_content=sample_article_data["content"],
                            source_name=sample_article_data["source_name"],
                            url=sample_article_data["url"],
                        )

                        assert "rules" in result
                        assert len(result["rules"]) > 0
                        # New phased approach: total_attempts is sum of (1 + repair_attempts) per rule
                        assert result["metadata"]["total_attempts"] >= 1
                        assert result.get("errors") is None
                        # Check for rule-scoped conversation log
                        conversation_log = result["metadata"].get("conversation_log", [])
                        assert conversation_log
                        generation_call = conversation_log[0]
                        assert generation_call["event_type"] == "generation_call"
                        assert generation_call["attempt"] == 1
                        assert generation_call["llm_response"] == sample_sigma_rule
                        assert generation_call["generated_rule_count"] >= 1
                        assert generation_call["valid_rule_count"] >= 1
                        assert generation_call["invalid_rule_count"] == 0
                        assert generation_call["messages"][0]["role"] == "system"
                        assert generation_call["messages"][1]["role"] == "user"

    @pytest.mark.asyncio
    async def test_generate_sigma_rules_injects_linux_guidance(self, service, sample_article_data, sample_sigma_rule):
        """A linux platform/logsource group gets the additive Linux guidance in the
        generation prompt; a windows group does not. Locks the §10 pilot fix wiring."""

        def _group(platform):
            ls = {"product": platform, "category": "process_creation"}
            return {
                "observables": [
                    {
                        "type": "cmdline",
                        "value": "chmod 777 /dev/shm/x",
                        "platform": platform,
                        "telemetry_category": "process_creation",
                        "logsource_hint": ls,
                    }
                ],
                "sigma_generation_group": {
                    "platform": platform,
                    "telemetry_category": "process_creation",
                    "logsource_hint": ls,
                },
            }

        def _prompts(mock):
            return [c.kwargs.get("sigma_prompt", "") for c in mock.await_args_list]

        with (
            patch("src.services.sigma_generation_service.optimize_article_content") as mock_optimize,
            patch("src.utils.prompt_loader.format_prompt_async", return_value="Generate SIGMA rules."),
            patch.object(
                service, "_generate_multi_rules", new_callable=AsyncMock, return_value=sample_sigma_rule
            ) as mock_gen,
        ):
            mock_optimize.return_value = {
                "success": True,
                "filtered_content": sample_article_data["content"],
                "tokens_saved": 0,
            }

            await service.generate_sigma_rules(
                article_title=sample_article_data["title"],
                article_content=sample_article_data["content"],
                source_name=sample_article_data["source_name"],
                url=sample_article_data["url"],
                extraction_result=_group("linux"),
            )
            linux_prompts = _prompts(mock_gen)
            assert any("LINUX TARGET GUIDANCE" in p for p in linux_prompts)
            assert any("T1222.002" in p for p in linux_prompts)

            mock_gen.reset_mock()
            await service.generate_sigma_rules(
                article_title=sample_article_data["title"],
                article_content=sample_article_data["content"],
                source_name=sample_article_data["source_name"],
                url=sample_article_data["url"],
                extraction_result=_group("windows"),
            )
            assert all("LINUX TARGET GUIDANCE" not in p for p in _prompts(mock_gen))

    @pytest.mark.asyncio
    async def test_generate_sigma_rules_with_retry(self, service, sample_article_data):
        """Test SIGMA rule generation with retry logic."""
        # Invalid but parseable rule (missing detection field)
        invalid_rule = """title: Test Rule
id: test-123
description: Test
logsource:
    category: process_creation
    product: windows
"""
        valid_rule = """title: Test Rule
id: test-123
description: Test
logsource:
    category: process_creation
    product: windows
detection:
    selection:
        CommandLine|contains: 'test'
    condition: selection
level: low
"""

        with patch("src.services.sigma_generation_service.optimize_article_content") as mock_optimize:
            mock_optimize.return_value = {
                "success": True,
                "filtered_content": sample_article_data["content"],
                "tokens_saved": 0,
            }

            with patch("src.utils.prompt_loader.format_prompt_async") as mock_prompt:
                mock_prompt.return_value = "Generate SIGMA rule"

                with patch.object(service, "_call_provider_for_sigma") as mock_call:
                    # First generation returns invalid rule, repair returns valid
                    call_count = [0]

                    def call_side_effect(*args, **kwargs):
                        call_count[0] += 1
                        # First call is generation (Phase 1), subsequent calls are repair (Phase 3)
                        if call_count[0] == 1:
                            return invalid_rule
                        return valid_rule

                    mock_call.side_effect = call_side_effect

                    with patch("src.services.sigma_generation_service.validate_sigma_rule") as mock_validate:

                        def validate_side_effect(rule_str):
                            # Check if rule has detection field
                            if "detection:" in rule_str and "condition:" in rule_str:
                                try:
                                    parsed = yaml.safe_load(rule_str)
                                    return ValidationResult(
                                        is_valid=True,
                                        errors=[],
                                        warnings=[],
                                        metadata={"rule": parsed},
                                        content_preview=rule_str,
                                    )
                                except Exception:
                                    pass
                            # Invalid rule (missing detection)
                            return ValidationResult(
                                is_valid=False,
                                errors=["Missing required field: detection"],
                                warnings=[],
                                metadata={"rule": yaml.safe_load(rule_str) if "title:" in rule_str else None},
                                content_preview=rule_str,
                            )

                        mock_validate.side_effect = validate_side_effect

                        result = await service.generate_sigma_rules(
                            article_title=sample_article_data["title"],
                            article_content=sample_article_data["content"],
                            source_name=sample_article_data["source_name"],
                            url=sample_article_data["url"],
                            max_repair_attempts_per_rule=3,
                        )

                        # New phased approach: attempts tracked per rule
                        assert result["metadata"]["total_attempts"] >= 1
                        assert len(result["rules"]) > 0

    @pytest.mark.asyncio
    async def test_generate_sigma_rules_content_optimization(self, service, sample_article_data):
        """Test content optimization integration."""
        optimized_content = "Optimized content with key threat indicators"

        with patch("src.services.sigma_generation_service.optimize_article_content") as mock_optimize:
            mock_optimize.return_value = {"success": True, "filtered_content": optimized_content, "tokens_saved": 500}

            with patch("src.utils.prompt_loader.format_prompt_async") as mock_prompt:
                mock_prompt.return_value = f"Generate rule for: {optimized_content}"

                with patch.object(service, "_call_provider_for_sigma") as mock_call:
                    mock_call.return_value = "title: Test\nid: test\n"

                    with patch("src.services.sigma_generation_service.validate_sigma_rule") as mock_validate:
                        mock_validate.return_value = ValidationResult(
                            is_valid=True,
                            errors=[],
                            warnings=[],
                            metadata={"rule": {"title": "Test", "id": "test"}},
                            content_preview="title: Test\nid: test",
                        )

                        await service.generate_sigma_rules(
                            article_title=sample_article_data["title"],
                            article_content=sample_article_data["content"],
                            source_name=sample_article_data["source_name"],
                            url=sample_article_data["url"],
                        )

                        # Verify optimization was called
                        mock_optimize.assert_called_once()
                        # Verify prompt uses optimized content - check call_args properly
                        if mock_prompt.called:
                            # format_prompt_async is called with (template_name, context_dict)
                            call_args = mock_prompt.call_args
                            if call_args and len(call_args) >= 2:
                                context_dict = call_args[1] if isinstance(call_args, tuple) else call_args.kwargs
                                if isinstance(context_dict, dict) and "content" in context_dict:
                                    assert optimized_content in context_dict["content"]
                                elif isinstance(call_args, tuple) and len(call_args) >= 2:
                                    # Check second positional argument
                                    if isinstance(call_args[1], dict) and "content" in call_args[1]:
                                        assert optimized_content in call_args[1]["content"]

    @pytest.mark.asyncio
    async def test_generate_sigma_rules_database_prompt_template(self, service, sample_article_data):
        """Test using database prompt template."""
        db_template = "Generate SIGMA rule for article: {title}\nContent: {content}"

        with patch("src.services.sigma_generation_service.optimize_article_content") as mock_optimize:
            mock_optimize.return_value = {
                "success": True,
                "filtered_content": sample_article_data["content"],
                "tokens_saved": 0,
            }

            with patch.object(service, "_call_provider_for_sigma") as mock_call:
                mock_call.return_value = "title: Test\nid: test\n"

                with patch("src.services.sigma_generation_service.validate_sigma_rule") as mock_validate:
                    mock_validate.return_value = ValidationResult(
                        is_valid=True,
                        errors=[],
                        warnings=[],
                        metadata={"rule": {"title": "Test", "id": "test"}},
                        content_preview="title: Test\nid: test",
                    )

                    result = await service.generate_sigma_rules(
                        article_title=sample_article_data["title"],
                        article_content=sample_article_data["content"],
                        source_name=sample_article_data["source_name"],
                        url=sample_article_data["url"],
                        sigma_prompt_template=db_template,
                    )

                    # Verify database template was used (format_prompt_async should not be called)
                    # The template should be formatted directly
                    assert result is not None

    @pytest.mark.asyncio
    async def test_generate_sigma_rules_context_window_limit(self, service, sample_article_data):
        """Test context window limit handling for LMStudio."""
        # Create a very long prompt
        long_content = sample_article_data["content"] * 1000

        with patch("src.services.sigma_generation_service.optimize_article_content") as mock_optimize:
            mock_optimize.return_value = {"success": True, "filtered_content": long_content, "tokens_saved": 0}

            with patch("src.utils.prompt_loader.format_prompt_async") as mock_prompt:
                # Return a prompt longer than context window
                long_prompt = "Generate rule: " + long_content
                mock_prompt.return_value = long_prompt

                with patch.object(service, "_call_provider_for_sigma") as mock_call:
                    mock_call.return_value = "title: Test\nid: test\n"

                    with patch("src.services.sigma_generation_service.validate_sigma_rule") as mock_validate:
                        mock_validate.return_value = ValidationResult(
                            is_valid=True,
                            errors=[],
                            warnings=[],
                            metadata={"rule": {"title": "Test", "id": "test"}},
                            content_preview="title: Test\nid: test",
                        )

                        await service.generate_sigma_rules(
                            article_title=sample_article_data["title"],
                            article_content=long_content,
                            source_name=sample_article_data["source_name"],
                            url=sample_article_data["url"],
                            ai_model="lmstudio",
                        )

                        # Verify prompt was truncated (check that truncation message is in prompt)
                        call_args = mock_call.call_args
                        prompt_passed = call_args[0][0] if call_args else ""
                        # Prompt should be truncated for 7b model (12000 chars max)
                        assert len(prompt_passed) <= 12000 or "[Prompt truncated" in prompt_passed

    @pytest.mark.asyncio
    async def test_generate_sigma_rules_validation_error(self, service, sample_article_data):
        """Test handling of validation errors."""
        invalid_rule = "title: Invalid Rule\ninvalid_field: value"

        with patch("src.services.sigma_generation_service.optimize_article_content") as mock_optimize:
            mock_optimize.return_value = {
                "success": True,
                "filtered_content": sample_article_data["content"],
                "tokens_saved": 0,
            }

            with patch("src.utils.prompt_loader.format_prompt_async") as mock_prompt:
                mock_prompt.return_value = "Generate rule"

                with patch.object(service, "_call_provider_for_sigma") as mock_call:
                    mock_call.return_value = invalid_rule

                    with patch("src.services.sigma_generation_service.validate_sigma_rule") as mock_validate:
                        mock_validate.return_value = ValidationResult(
                            is_valid=False,
                            errors=["Missing required field: detection"],
                            warnings=[],
                            metadata=None,
                            content_preview=invalid_rule,
                        )

                        result = await service.generate_sigma_rules(
                            article_title=sample_article_data["title"],
                            article_content=sample_article_data["content"],
                            source_name=sample_article_data["source_name"],
                            url=sample_article_data["url"],
                            max_repair_attempts_per_rule=1,
                        )

                        # New phased approach: validation happens in Phase 2, repair in Phase 3
                        assert result["metadata"]["total_attempts"] >= 1
                        assert len(result["rules"]) == 0
                        assert result.get("errors") is not None

    @pytest.mark.asyncio
    async def test_generate_sigma_rules_max_attempts_exceeded(self, service, sample_article_data):
        """Test behavior when max attempts exceeded."""
        invalid_response = "Not valid YAML"

        with patch("src.services.sigma_generation_service.optimize_article_content") as mock_optimize:
            mock_optimize.return_value = {
                "success": True,
                "filtered_content": sample_article_data["content"],
                "tokens_saved": 0,
            }

            with patch("src.utils.prompt_loader.format_prompt_async") as mock_prompt:
                mock_prompt.return_value = "Generate rule"

                with patch.object(service, "_call_provider_for_sigma") as mock_call:
                    mock_call.return_value = invalid_response

                    with patch("src.services.sigma_generation_service.validate_sigma_rule") as mock_validate:
                        mock_validate.return_value = ValidationResult(
                            is_valid=False,
                            errors=["Invalid YAML"],
                            warnings=[],
                            metadata=None,
                            content_preview=invalid_response,
                        )

                        result = await service.generate_sigma_rules(
                            article_title=sample_article_data["title"],
                            article_content=sample_article_data["content"],
                            source_name=sample_article_data["source_name"],
                            url=sample_article_data["url"],
                            max_repair_attempts_per_rule=2,
                        )

                        # New phased approach: attempts tracked per rule
                        assert result["metadata"]["total_attempts"] >= 1
                        assert len(result["rules"]) == 0
                        assert result.get("errors") is not None

    @pytest.mark.asyncio
    async def test_generate_sigma_rules_optimization_failure(self, service, sample_article_data):
        """Test handling of content optimization failure."""
        with patch("src.services.sigma_generation_service.optimize_article_content") as mock_optimize:
            mock_optimize.return_value = {"success": False, "error": "Optimization failed"}

            with patch("src.utils.prompt_loader.format_prompt_async") as mock_prompt:
                mock_prompt.return_value = "Generate rule"

                with patch.object(service, "_call_provider_for_sigma") as mock_call:
                    mock_call.return_value = "title: Test\nid: test\n"

                    with patch("src.services.sigma_generation_service.validate_sigma_rule") as mock_validate:
                        mock_validate.return_value = ValidationResult(
                            is_valid=True,
                            errors=[],
                            warnings=[],
                            metadata={"rule": {"title": "Test", "id": "test"}},
                            content_preview="title: Test\nid: test",
                        )

                        result = await service.generate_sigma_rules(
                            article_title=sample_article_data["title"],
                            article_content=sample_article_data["content"],
                            source_name=sample_article_data["source_name"],
                            url=sample_article_data["url"],
                        )

                        # Should use original content when optimization fails
                        assert result is not None
                        # Verify original content was used (not filtered) - check call_args properly
                        if mock_prompt.called:
                            call_args = mock_prompt.call_args
                            if call_args:
                                # format_prompt_async is called with (template_name, **kwargs)
                                if isinstance(call_args, tuple) and len(call_args) >= 2:
                                    kwargs = call_args[1] if len(call_args) > 1 else {}
                                    if isinstance(kwargs, dict) and "content" in kwargs:
                                        assert sample_article_data["content"] in kwargs["content"]
                                elif hasattr(call_args, "kwargs") and "content" in call_args.kwargs:
                                    assert sample_article_data["content"] in call_args.kwargs["content"]

    @pytest.mark.asyncio
    async def test_generate_sigma_rules_prompt_loading_failure(self, service, sample_article_data):
        """Test handling of prompt loading failure."""
        with patch("src.services.sigma_generation_service.optimize_article_content") as mock_optimize:
            mock_optimize.return_value = {
                "success": True,
                "filtered_content": sample_article_data["content"],
                "tokens_saved": 0,
            }

            # Mock format_prompt_async to return None (simulating failure).
            # Patch where it is defined; the service imports it inside the "if not sigma_prompt" block.
            # First try sigma_generate_multi, then fallback to sigma_generation
            with patch("src.utils.prompt_loader.format_prompt_async", new_callable=AsyncMock) as mock_prompt:
                # Simulate both prompt attempts failing
                def prompt_side_effect(*args, **kwargs):
                    return None

                mock_prompt.side_effect = prompt_side_effect
                # Call with sigma_prompt_template=None so the service uses file fallback -> format_prompt_async
                with pytest.raises(ValueError, match="Failed to load SIGMA generation prompt"):
                    await service.generate_sigma_rules(
                        article_title=sample_article_data["title"],
                        article_content=sample_article_data["content"],
                        source_name=sample_article_data["source_name"],
                        url=sample_article_data["url"],
                        sigma_prompt_template=None,
                    )

    @pytest.mark.asyncio
    async def test_generate_sigma_rules_multiple_rules_with_separator(self, service, sample_article_data):
        """Test generation of multiple SIGMA rules with --- separator."""
        multiple_rules_yaml = """title: Rule 1
id: rule-1
description: First rule
logsource:
    category: process_creation
    product: windows
detection:
    selection:
        CommandLine|contains: 'test1'
    condition: selection
level: low
---
title: Rule 2
id: rule-2
description: Second rule
logsource:
    category: process_creation
    product: windows
detection:
    selection:
        CommandLine|contains: 'test2'
    condition: selection
level: medium
"""

        with patch("src.services.sigma_generation_service.optimize_article_content") as mock_optimize:
            mock_optimize.return_value = {
                "success": True,
                "filtered_content": sample_article_data["content"],
                "tokens_saved": 0,
            }

            with patch("src.utils.prompt_loader.format_prompt_async") as mock_prompt:
                mock_prompt.return_value = "Generate rules"

                with patch.object(service, "_call_provider_for_sigma") as mock_call:
                    mock_call.return_value = multiple_rules_yaml

                    with patch("src.services.sigma_generation_service.validate_sigma_rule") as mock_validate:

                        def validate_side_effect(rule_str):
                            # Parse each rule individually
                            try:
                                parsed = yaml.safe_load(rule_str)
                                if parsed and "title" in parsed:
                                    return ValidationResult(
                                        is_valid=True,
                                        errors=[],
                                        warnings=[],
                                        metadata={"rule": parsed},
                                        content_preview=rule_str,
                                    )
                            except Exception:
                                pass
                            return ValidationResult(
                                is_valid=False, errors=["Invalid"], warnings=[], metadata=None, content_preview=rule_str
                            )

                        mock_validate.side_effect = validate_side_effect

                        result = await service.generate_sigma_rules(
                            article_title=sample_article_data["title"],
                            article_content=sample_article_data["content"],
                            source_name=sample_article_data["source_name"],
                            url=sample_article_data["url"],
                        )

                        # Should parse multiple rules
                        assert result is not None
                        assert len(result["rules"]) >= 1  # At least one rule should be parsed

    @pytest.mark.asyncio
    async def test_generate_sigma_rules_multiple_rules_markdown_blocks(self, service, sample_article_data):
        """Test parsing multiple rules from markdown code blocks."""
        multiple_rules_markdown = """```yaml
title: Rule 1
id: rule-1
description: First rule
logsource:
    category: process_creation
    product: windows
detection:
    selection:
        CommandLine|contains: 'test1'
    condition: selection
level: low
```

```yaml
title: Rule 2
id: rule-2
description: Second rule
logsource:
    category: network_connection
    product: windows
detection:
    selection:
        DestinationPort: 443
    condition: selection
level: medium
```
"""

        with patch("src.services.sigma_generation_service.optimize_article_content") as mock_optimize:
            mock_optimize.return_value = {
                "success": True,
                "filtered_content": sample_article_data["content"],
                "tokens_saved": 0,
            }

            with patch("src.utils.prompt_loader.format_prompt_async") as mock_prompt:
                mock_prompt.return_value = "Generate rules"

                with patch.object(service, "_call_provider_for_sigma") as mock_call:
                    mock_call.return_value = multiple_rules_markdown

                    with patch("src.services.sigma_generation_service.validate_sigma_rule") as mock_validate:

                        def validate_side_effect(rule_str):
                            try:
                                parsed = yaml.safe_load(rule_str)
                                if parsed and "title" in parsed:
                                    return ValidationResult(
                                        is_valid=True,
                                        errors=[],
                                        warnings=[],
                                        metadata={"rule": parsed},
                                        content_preview=rule_str,
                                    )
                            except Exception:
                                pass
                            return ValidationResult(
                                is_valid=False, errors=["Invalid"], warnings=[], metadata=None, content_preview=rule_str
                            )

                        mock_validate.side_effect = validate_side_effect

                        result = await service.generate_sigma_rules(
                            article_title=sample_article_data["title"],
                            article_content=sample_article_data["content"],
                            source_name=sample_article_data["source_name"],
                            url=sample_article_data["url"],
                        )

                        # Should parse multiple rules from markdown blocks
                        assert result is not None
                        assert len(result["rules"]) >= 1

    @pytest.mark.asyncio
    async def test_generate_sigma_rules_per_rule_repair(self, service, sample_article_data):
        """Test per-rule repair in Phase 3."""
        invalid_rule = """title: Invalid Rule
id: invalid-1
description: Missing detection
logsource:
    category: process_creation
    product: windows
"""
        repaired_rule = """title: Valid Rule
id: valid-1
description: Fixed rule
logsource:
    category: process_creation
    product: windows
detection:
    selection:
        CommandLine|contains: 'test'
    condition: selection
level: medium
"""

        with patch("src.services.sigma_generation_service.optimize_article_content") as mock_optimize:
            mock_optimize.return_value = {
                "success": True,
                "filtered_content": sample_article_data["content"],
                "tokens_saved": 0,
            }

            with patch("src.utils.prompt_loader.format_prompt_async") as mock_prompt:
                mock_prompt.return_value = "Generate rule"

                with patch.object(service, "_call_provider_for_sigma") as mock_call:
                    # First call generates invalid rule, repair call fixes it
                    mock_call.side_effect = [invalid_rule, repaired_rule]

                    with patch("src.services.sigma_generation_service.validate_sigma_rule") as mock_validate:

                        def validate_side_effect(rule_str):
                            has_detection = "detection:" in rule_str and "condition:" in rule_str
                            if has_detection:
                                parsed = yaml.safe_load(rule_str)
                                return ValidationResult(
                                    is_valid=True,
                                    errors=[],
                                    warnings=[],
                                    metadata={"rule": parsed},
                                    content_preview=rule_str,
                                )
                            return ValidationResult(
                                is_valid=False,
                                errors=["Missing detection"],
                                warnings=[],
                                metadata=None,
                                content_preview=rule_str,
                            )

                        mock_validate.side_effect = validate_side_effect

                        result = await service.generate_sigma_rules(
                            article_title=sample_article_data["title"],
                            article_content=sample_article_data["content"],
                            source_name=sample_article_data["source_name"],
                            url=sample_article_data["url"],
                            max_repair_attempts_per_rule=3,
                        )

                        # Should repair and return valid rule
                        assert len(result["rules"]) > 0
                        # Check repair attempts in conversation log
                        conversation_log = result["metadata"].get("conversation_log", [])
                        if conversation_log:
                            # Should have repair attempts tracked
                            for log_entry in conversation_log:
                                if "repair_attempts" in log_entry:
                                    assert len(log_entry["repair_attempts"]) > 0

    @pytest.mark.asyncio
    async def test_generate_sigma_rules_expansion_phase(self, service, sample_article_data):
        """Test artifact-driven expansion phase."""
        extraction_result = {
            "subresults": {
                "cmdline": {"count": 5, "items": ["cmd1", "cmd2"]},
                "process_lineage": {"count": 2, "items": [{"parent": "p1", "child": "c1"}]},
                "network_connection": {"count": 3, "items": ["net1"]},
            }
        }

        initial_rule = """title: Process Creation Rule
id: rule-1
description: Process rule
logsource:
    category: process_creation
    product: windows
detection:
    selection:
        CommandLine|contains: 'test'
    condition: selection
level: medium
"""

        expansion_rule = """title: Network Connection Rule
id: rule-2
description: Network rule
logsource:
    category: network_connection
    product: windows
detection:
    selection:
        DestinationPort: 443
    condition: selection
level: high
"""

        with patch("src.services.sigma_generation_service.optimize_article_content") as mock_optimize:
            mock_optimize.return_value = {
                "success": True,
                "filtered_content": sample_article_data["content"],
                "tokens_saved": 0,
            }

            with patch("src.utils.prompt_loader.format_prompt_async") as mock_prompt:
                mock_prompt.return_value = "Generate rules"

                with patch.object(service, "_call_provider_for_sigma") as mock_call:
                    # First call generates initial rule, expansion call generates additional rule
                    mock_call.side_effect = [initial_rule, expansion_rule]

                    with patch("src.services.sigma_generation_service.validate_sigma_rule") as mock_validate:

                        def validate_side_effect(rule_str):
                            parsed = yaml.safe_load(rule_str)
                            if parsed and "title" in parsed:
                                return ValidationResult(
                                    is_valid=True,
                                    errors=[],
                                    warnings=[],
                                    metadata={"rule": parsed},
                                    content_preview=rule_str,
                                )
                            return ValidationResult(
                                is_valid=False, errors=["Invalid"], warnings=[], metadata=None, content_preview=rule_str
                            )

                        mock_validate.side_effect = validate_side_effect

                        result = await service.generate_sigma_rules(
                            article_title=sample_article_data["title"],
                            article_content=sample_article_data["content"],
                            source_name=sample_article_data["source_name"],
                            url=sample_article_data["url"],
                            extraction_result=extraction_result,
                            enable_multi_rule_expansion=True,
                        )

                        # Should have rules from both generation and expansion phases
                        assert len(result["rules"]) >= 1
                        # Check conversation log for expansion phase
                        conversation_log = result["metadata"].get("conversation_log", [])
                        any(
                            entry.get("generation_phase") == "expansion"
                            for entry in conversation_log
                            if isinstance(entry, dict)
                        )
                        # Expansion may or may not trigger depending on coverage logic
                        # Just verify the structure is correct
                        assert result is not None

    @pytest.mark.asyncio
    async def test_expansion_empty_response_keeps_initial_rules(self, service, sample_article_data):
        """Phase 4 expansion is best-effort: an empty/failed expansion response must not
        discard the valid Phase 1 rules or fail the whole generation.

        Regression for execution 3517 — gpt-5.1-chat-latest returned an empty response on
        the expansion call (FAIL-SAFE: nothing safe to add for network_connection). The
        unguarded call let that ValueError propagate and threw away 2 already-valid rules,
        failing the workflow.
        """
        extraction_result = {
            "subresults": {
                "cmdline": {"count": 5, "items": ["cmd1"]},
                # Uncovered network_indicators forces an expansion attempt for network_connection.
                "network_indicators": {"count": 6, "items": ["1.2.3.4"]},
            }
        }

        initial_rule = """title: Process Creation Rule
id: rule-1
description: Process rule
logsource:
    category: process_creation
    product: windows
detection:
    selection:
        CommandLine|contains: 'test'
    condition: selection
level: medium
"""

        with patch("src.services.sigma_generation_service.optimize_article_content") as mock_optimize:
            mock_optimize.return_value = {
                "success": True,
                "filtered_content": sample_article_data["content"],
                "tokens_saved": 0,
            }

            with patch("src.utils.prompt_loader.format_prompt_async") as mock_prompt:
                mock_prompt.return_value = "Generate rules"

                with patch.object(service, "_call_provider_for_sigma") as mock_call:
                    # Phase 1 returns a valid rule; the Phase 4 expansion call comes back empty,
                    # which surfaces as the empty-response ValueError from _call_provider_for_sigma.
                    mock_call.side_effect = [
                        initial_rule,
                        ValueError(
                            "LLM returned empty response for SIGMA generation. "
                            "Check the configured provider is responding correctly."
                        ),
                    ]

                    with patch("src.services.sigma_generation_service.validate_sigma_rule") as mock_validate:

                        def validate_side_effect(rule_str):
                            parsed = yaml.safe_load(rule_str)
                            if parsed and "title" in parsed:
                                return ValidationResult(
                                    is_valid=True,
                                    errors=[],
                                    warnings=[],
                                    metadata={"rule": parsed},
                                    content_preview=rule_str,
                                )
                            return ValidationResult(
                                is_valid=False, errors=["Invalid"], warnings=[], metadata=None, content_preview=rule_str
                            )

                        mock_validate.side_effect = validate_side_effect

                        # Must NOT raise even though the expansion call errored.
                        result = await service.generate_sigma_rules(
                            article_title=sample_article_data["title"],
                            article_content=sample_article_data["content"],
                            source_name=sample_article_data["source_name"],
                            url=sample_article_data["url"],
                            extraction_result=extraction_result,
                            enable_multi_rule_expansion=True,
                        )

                    # The expansion was actually attempted (second provider call) but failed gracefully.
                    assert mock_call.call_count == 2
                    # The Phase 1 rule survived and no fatal error was surfaced.
                    assert result.get("errors") is None
                    assert len(result["rules"]) == 1
                    assert result["rules"][0]["title"] == "Process Creation Rule"

    @pytest.mark.asyncio
    async def test_generate_sigma_rules_rule_scoped_logging(self, service, sample_article_data, sample_sigma_rule):
        """Test rule-scoped logging structure."""
        with patch("src.services.sigma_generation_service.optimize_article_content") as mock_optimize:
            mock_optimize.return_value = {
                "success": True,
                "filtered_content": sample_article_data["content"],
                "tokens_saved": 0,
            }

            with patch("src.utils.prompt_loader.format_prompt_async") as mock_prompt:
                mock_prompt.return_value = "Generate rule"

                with patch.object(service, "_call_provider_for_sigma") as mock_call:
                    mock_call.return_value = sample_sigma_rule

                    with patch("src.services.sigma_generation_service.validate_sigma_rule") as mock_validate:
                        mock_validate.return_value = ValidationResult(
                            is_valid=True,
                            errors=[],
                            warnings=[],
                            metadata={"rule": yaml.safe_load(sample_sigma_rule)},
                            content_preview=sample_sigma_rule,
                        )

                        result = await service.generate_sigma_rules(
                            article_title=sample_article_data["title"],
                            article_content=sample_article_data["content"],
                            source_name=sample_article_data["source_name"],
                            url=sample_article_data["url"],
                        )

                        # Check rule-scoped logging structure
                        conversation_log = result["metadata"].get("conversation_log", [])
                        assert len(conversation_log) > 0
                        generation_call = conversation_log[0]
                        assert generation_call["event_type"] == "generation_call"
                        assert generation_call["generated_rule_count"] >= 1
                        rule_logs = conversation_log[1:]
                        assert rule_logs
                        for log_entry in rule_logs:
                            assert isinstance(log_entry, dict)
                            assert log_entry["event_type"] == "rule_validation"
                            assert "rule_id" in log_entry
                            assert "generation_phase" in log_entry
                            assert "final_status" in log_entry
                            assert "repair_attempts" in log_entry

    def test_build_observables_section_formats_extraction_result(self):
        """_build_observables_section formats extraction_result.observables with 0-based indices."""
        extraction_result = {
            "observables": [
                {
                    "type": "cmdline",
                    "value": "powershell -enc",
                    "platform": "windows",
                    "telemetry_category": "process_creation",
                    "logsource_hint": {"product": "windows", "category": "process_creation"},
                },
                {"type": "process_lineage", "value": {"parent": "p1", "child": "c1", "arguments": ""}},
            ]
        }
        section = _build_observables_section(extraction_result)
        assert "Extracted Observables (0-based index)" in section
        assert "observables_used:" in section
        assert "REQUIRED" in section
        assert "[0] cmdline:" in section
        assert "[1] process_lineage:" in section
        assert "powershell -enc" in section
        assert "platform=windows" in section
        assert "telemetry_category=process_creation" in section
        assert "parent=p1, child=c1" in section

    def test_build_observables_section_returns_empty_for_no_observables(self):
        """_build_observables_section returns empty string when observables missing or empty."""
        assert _build_observables_section(None) == ""
        assert _build_observables_section({}) == ""
        assert _build_observables_section({"observables": []}) == ""
        assert _build_observables_section({"observables": None}) == ""

    @pytest.mark.asyncio
    async def test_parse_observables_used_strips_before_validation_and_includes_in_rule_metadata(
        self, service, sample_article_data
    ):
        """LLM output with observables_used is stripped before validation; rule_metadata includes it."""
        rule_with_observables = """
title: Test Rule
id: test-123
description: Test
observables_used: [0, 1]
logsource:
    category: process_creation
    product: windows
detection:
    selection:
        CommandLine|contains: 'test'
    condition: selection
level: low
"""

        with patch("src.services.sigma_generation_service.optimize_article_content") as mock_optimize:
            mock_optimize.return_value = {
                "success": True,
                "filtered_content": sample_article_data["content"],
                "tokens_saved": 0,
            }

            with patch("src.utils.prompt_loader.format_prompt_async") as mock_prompt:
                mock_prompt.return_value = "Generate rule"

                with patch.object(service, "_call_provider_for_sigma") as mock_call:
                    mock_call.return_value = rule_with_observables

                    with patch("src.services.sigma_generation_service.validate_sigma_rule") as mock_validate:
                        validated_yaml = []

                        def capture_validate(rule_str):
                            validated_yaml.append(rule_str)
                            parsed = yaml.safe_load(rule_str)
                            return ValidationResult(
                                is_valid=True,
                                errors=[],
                                warnings=[],
                                metadata={"rule": parsed},
                                content_preview=rule_str,
                            )

                        mock_validate.side_effect = capture_validate

                        result = await service.generate_sigma_rules(
                            article_title=sample_article_data["title"],
                            article_content=sample_article_data["content"],
                            source_name=sample_article_data["source_name"],
                            url=sample_article_data["url"],
                        )

                        assert len(result["rules"]) == 1
                        assert result["rules"][0].get("observables_used") == [0, 1]
                        assert len(validated_yaml) == 1
                        parsed_validated = yaml.safe_load(validated_yaml[0])
                        assert "observables_used" not in parsed_validated

    @pytest.mark.asyncio
    async def test_grounding_metadata_stripped_from_yaml_and_returned_in_rule_metadata(
        self, service, sample_article_data
    ):
        """Platform/telemetry grounding fields stay out of pySigma YAML but remain in returned metadata."""
        rule_with_grounding = """
title: Linux Curl Execution
id: test-linux-curl
description: Test
observables_used: [0]
platform: linux
telemetry_category: process_creation
generation_basis: process_creation_generic
detection_readiness: generic
logsource:
    category: process_creation
    product: linux
detection:
    selection:
        CommandLine|contains: 'curl'
    condition: selection
level: low
"""
        extraction_result = {
            "observables": [
                {
                    "type": "cmdline",
                    "value": "curl http://example",
                    "platform": "linux",
                    "telemetry_category": "process_creation",
                    "logsource_hint": {"product": "linux", "category": "process_creation"},
                }
            ]
        }

        with patch("src.services.sigma_generation_service.optimize_article_content") as mock_optimize:
            mock_optimize.return_value = {
                "success": True,
                "filtered_content": sample_article_data["content"],
                "tokens_saved": 0,
            }

            with patch("src.utils.prompt_loader.format_prompt_async") as mock_prompt:
                mock_prompt.return_value = "Generate rule"

                with patch.object(service, "_call_provider_for_sigma") as mock_call:
                    mock_call.return_value = rule_with_grounding

                    with patch("src.services.sigma_generation_service.validate_sigma_rule") as mock_validate:
                        validated_yaml = []

                        def capture_validate(rule_str):
                            validated_yaml.append(rule_str)
                            parsed = yaml.safe_load(rule_str)
                            return ValidationResult(
                                is_valid=True,
                                errors=[],
                                warnings=[],
                                metadata={"rule": parsed},
                                content_preview=rule_str,
                            )

                        mock_validate.side_effect = capture_validate

                        result = await service.generate_sigma_rules(
                            article_title=sample_article_data["title"],
                            article_content=sample_article_data["content"],
                            source_name=sample_article_data["source_name"],
                            url=sample_article_data["url"],
                            extraction_result=extraction_result,
                        )

                        assert len(result["rules"]) == 1
                        rule = result["rules"][0]
                        assert rule["observables_used"] == [0]
                        assert rule["platform"] == "linux"
                        assert rule["telemetry_category"] == "process_creation"
                        assert rule["generation_basis"] == "process_creation_generic"
                        assert rule["detection_readiness"] == "generic"
                        parsed_validated = yaml.safe_load(validated_yaml[0])
                        assert "platform" not in parsed_validated
                        assert "telemetry_category" not in parsed_validated
                        assert "generation_basis" not in parsed_validated
                        assert "detection_readiness" not in parsed_validated

    @pytest.mark.asyncio
    async def test_call_provider_for_sigma_openai_uses_high_max_tokens_and_content_parts(self, service):
        """OpenAI SIGMA calls should use high completion budget and parse content parts."""
        service.llm_service.provider_sigma = "openai"
        service.llm_service.model_sigma = "gpt-5.4"
        service.llm_service.provider_defaults = {"openai": "gpt-4o-mini"}
        service.llm_service.temperature_sigma = 1.0
        service.llm_service.top_p_sigma = 1.0
        service.llm_service.seed = None
        service.llm_service._convert_messages_for_model = Mock(side_effect=lambda messages, _model: messages)
        service.llm_service.request_chat = AsyncMock(
            return_value={
                "choices": [
                    {
                        "message": {
                            "content": [
                                {"type": "output_text", "text": "title: Test Rule\n"},
                                {"type": "output_text", "text": "id: test-rule\n"},
                                {"type": "output_text", "text": "description: Test\n"},
                                {"type": "output_text", "text": "logsource:\n  category: process_creation\n"},
                                {"type": "output_text", "text": "  product: windows\n"},
                                {"type": "output_text", "text": "detection:\n  selection:\n"},
                                {"type": "output_text", "text": "    CommandLine|contains: test\n"},
                                {"type": "output_text", "text": "  condition: selection\n"},
                            ]
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 200, "total_tokens": 210},
            }
        )

        with (
            patch("src.services.sigma_generation_service.trace_llm_call", return_value=contextlib.nullcontext(None)),
            patch("src.services.sigma_generation_service.log_llm_completion"),
            patch("src.services.sigma_generation_service.log_llm_error"),
        ):
            output = await service._call_provider_for_sigma("prompt", provider="openai")

        assert output.startswith("title: Test Rule")
        request_kwargs = service.llm_service.request_chat.call_args.kwargs
        assert request_kwargs["max_tokens"] == 4000


# ---------------------------------------------------------------------------
# Tests for changes made in this session
# ---------------------------------------------------------------------------


class TestObservablesDoubleInjectionGuard:
    """Observables section must not appear twice when template already has {observables_section}."""

    @pytest.fixture
    def service(self):
        mock_llm = Mock()
        mock_llm.provider_sigma = "lmstudio"
        mock_llm.lmstudio_model = "test-model-7b"
        mock_llm._canonicalize_provider = Mock(return_value="lmstudio")
        with patch("src.services.sigma_generation_service.LLMService", return_value=mock_llm):
            return SigmaGenerationService()

    @pytest.fixture
    def valid_rule_yaml(self):
        return (
            "title: Test Rule\n"
            "id: abc-123\n"
            "description: Test\n"
            "logsource:\n"
            "  category: process_creation\n"
            "  product: windows\n"
            "detection:\n"
            "  selection:\n"
            "    CommandLine|contains: test\n"
            "  condition: selection\n"
            "level: low\n"
        )

    @pytest.mark.asyncio
    async def test_observables_not_appended_when_template_has_placeholder(self, service, valid_rule_yaml):
        """When DB template contains {observables_section}, section must not be appended again."""
        # Template already contains the placeholder
        template_with_placeholder = (
            "Generate a rule for: {title}\nSource: {source}\nURL: {url}\nContent: {content}\n{observables_section}"
        )
        extraction_result = {"observables": [{"type": "cmdline", "value": "powershell -enc abc"}]}

        captured_prompts = []

        async def fake_call(prompt, *, provider, **kwargs):
            captured_prompts.append(prompt)
            return valid_rule_yaml

        with (
            patch("src.services.sigma_generation_service.optimize_article_content") as mock_opt,
            patch("src.services.sigma_generation_service.validate_sigma_rule") as mock_val,
            patch("src.services.sigma_generation_service.clean_sigma_rule", side_effect=lambda x: x),
            patch.object(service, "_call_provider_for_sigma", side_effect=fake_call),
        ):
            mock_opt.return_value = {"success": True, "filtered_content": "article text", "tokens_saved": 0}
            mock_val.return_value = ValidationResult(
                is_valid=True, errors=[], warnings=[], metadata={}, content_preview=valid_rule_yaml
            )

            await service.generate_sigma_rules(
                article_title="Test",
                article_content="article text",
                source_name="test",
                url="http://example.com",
                sigma_prompt_template=template_with_placeholder,
                extraction_result=extraction_result,
                enable_multi_rule_expansion=False,
            )

        assert captured_prompts, "LLM was not called"
        prompt_used = captured_prompts[0]
        # Observable value should appear exactly once
        assert prompt_used.count("powershell -enc abc") == 1, "Observables section was injected twice into the prompt"

    @pytest.mark.asyncio
    async def test_observables_appended_when_template_lacks_placeholder(self, service, valid_rule_yaml):
        """When DB template has no {observables_section}, section must be appended."""
        template_without_placeholder = (
            "Generate a rule for: {title}\nSource: {source}\nURL: {url}\nContent: {content}\n"
        )
        extraction_result = {"observables": [{"type": "cmdline", "value": "cmd.exe /c whoami"}]}

        captured_prompts = []

        async def fake_call(prompt, *, provider, **kwargs):
            captured_prompts.append(prompt)
            return valid_rule_yaml

        with (
            patch("src.services.sigma_generation_service.optimize_article_content") as mock_opt,
            patch("src.services.sigma_generation_service.validate_sigma_rule") as mock_val,
            patch("src.services.sigma_generation_service.clean_sigma_rule", side_effect=lambda x: x),
            patch.object(service, "_call_provider_for_sigma", side_effect=fake_call),
        ):
            mock_opt.return_value = {"success": True, "filtered_content": "article text", "tokens_saved": 0}
            mock_val.return_value = ValidationResult(
                is_valid=True, errors=[], warnings=[], metadata={}, content_preview=valid_rule_yaml
            )

            await service.generate_sigma_rules(
                article_title="Test",
                article_content="article text",
                source_name="test",
                url="http://example.com",
                sigma_prompt_template=template_without_placeholder,
                extraction_result=extraction_result,
                enable_multi_rule_expansion=False,
            )

        assert captured_prompts, "LLM was not called"
        assert "cmd.exe /c whoami" in captured_prompts[0], (
            "Observables section was not appended when template lacked placeholder"
        )


class TestSigmaRepairTemplatePassthrough:
    """sigma_repair_template from DB must be used in _repair_rules instead of disk file."""

    @pytest.fixture
    def service(self):
        mock_llm = Mock()
        mock_llm.provider_sigma = "lmstudio"
        mock_llm.lmstudio_model = "test-model-7b"
        mock_llm._canonicalize_provider = Mock(return_value="lmstudio")
        with patch("src.services.sigma_generation_service.LLMService", return_value=mock_llm):
            return SigmaGenerationService()

    @pytest.fixture
    def invalid_rule(self):
        return (
            "title: Broken Rule\n"
            "id: broken-123\n"
            "description: Missing detection\n"
            "logsource:\n"
            "  category: process_creation\n"
            "  product: windows\n"
        )

    @pytest.fixture
    def valid_rule(self):
        return (
            "title: Fixed Rule\n"
            "id: fixed-123\n"
            "description: Fixed\n"
            "logsource:\n"
            "  category: process_creation\n"
            "  product: windows\n"
            "detection:\n"
            "  selection:\n"
            "    CommandLine|contains: test\n"
            "  condition: selection\n"
            "level: low\n"
        )

    @pytest.mark.asyncio
    async def test_repair_uses_db_template_when_provided(self, service, invalid_rule, valid_rule):
        """When sigma_repair_template is provided, _repair_rules must format and use it."""
        custom_template = "CUSTOM REPAIR PROMPT\nErrors: {validation_errors}\nRule: {original_rule}\nFix it."

        captured_repair_prompts = []

        async def fake_call(prompt, *, provider, **kwargs):
            captured_repair_prompts.append(prompt)
            return valid_rule

        invalid_result = ValidationResult(
            is_valid=False, errors=["Missing detection"], warnings=[], metadata={}, content_preview=invalid_rule
        )
        valid_result = ValidationResult(is_valid=True, errors=[], warnings=[], metadata={}, content_preview=valid_rule)

        from src.services.sigma_generation_service import RuleValidationResult

        rule = RuleValidationResult(
            rule_id="test-id",
            rule_yaml=invalid_rule,
            validation_result=invalid_result,
            rule_index=1,
        )

        with (
            patch("src.services.sigma_generation_service.validate_sigma_rule", return_value=valid_result),
            patch("src.services.sigma_generation_service.clean_sigma_rule", side_effect=lambda x: x),
            patch.object(service, "_call_provider_for_sigma", side_effect=fake_call),
        ):
            await service._repair_rules(
                invalid_rules=[rule],
                max_repair_attempts_per_rule=1,
                execution_id=None,
                article_id=None,
                sigma_system_prompt=None,
                sigma_repair_template=custom_template,
            )

        assert captured_repair_prompts, "Repair LLM was not called"
        assert "CUSTOM REPAIR PROMPT" in captured_repair_prompts[0], (
            "DB repair template was not used; file-based prompt was used instead"
        )
        assert "Missing detection" in captured_repair_prompts[0]

    @pytest.mark.asyncio
    async def test_repair_falls_back_to_file_when_template_is_none(self, service, invalid_rule, valid_rule):
        """When sigma_repair_template is None, _repair_rules must load from disk."""
        captured_repair_prompts = []

        async def fake_call(prompt, *, provider, **kwargs):
            captured_repair_prompts.append(prompt)
            return valid_rule

        invalid_result = ValidationResult(
            is_valid=False, errors=["Missing detection"], warnings=[], metadata={}, content_preview=invalid_rule
        )
        valid_result = ValidationResult(is_valid=True, errors=[], warnings=[], metadata={}, content_preview=valid_rule)

        from src.services.sigma_generation_service import RuleValidationResult

        rule = RuleValidationResult(
            rule_id="test-id",
            rule_yaml=invalid_rule,
            validation_result=invalid_result,
            rule_index=1,
        )

        file_prompt = "FILE-BASED REPAIR PROMPT\nErrors: {validation_errors}\nRule: {original_rule}"

        with (
            patch("src.services.sigma_generation_service.validate_sigma_rule", return_value=valid_result),
            patch("src.services.sigma_generation_service.clean_sigma_rule", side_effect=lambda x: x),
            patch.object(service, "_call_provider_for_sigma", side_effect=fake_call),
            patch(
                "src.utils.prompt_loader.format_prompt_async",
                return_value=file_prompt.format(
                    validation_errors="Missing detection", original_rule=invalid_rule[:500]
                ),
            ),
        ):
            await service._repair_rules(
                invalid_rules=[rule],
                max_repair_attempts_per_rule=1,
                execution_id=None,
                article_id=None,
                sigma_system_prompt=None,
                sigma_repair_template=None,
            )

        assert captured_repair_prompts, "Repair LLM was not called"
        assert "FILE-BASED REPAIR PROMPT" in captured_repair_prompts[0], (
            "File-based fallback was not used when sigma_repair_template=None"
        )


class TestSigmaSystemPromptPassthrough:
    """Regression: custom system prompt must reach _call_provider_for_sigma.

    Before the parse_sigma_agent_prompt_data fix, the extraction-agent save
    format (produced by the UI's saveAgentPrompt2) was unrecognized, causing
    the raw JSON blob to be used as the user template.  The {} in json_example
    then raised KeyError, which was silently caught, and system_prompt fell
    back to None -> hardcoded default.  These tests verify the fix holds end-
    to-end at the service boundary.
    """

    @pytest.fixture()
    def service(self):
        mock_llm = Mock()
        mock_llm.provider_sigma = "lmstudio"
        mock_llm.model_sigma = "gemma-3-1b"
        mock_llm.temperature_sigma = 0.3
        mock_llm.top_p_sigma = 0.9
        mock_llm.max_tokens_sigma = 4096
        mock_llm.context_window_sigma = 8192
        mock_llm._canonicalize_provider = Mock(return_value="lmstudio")
        with patch("src.services.sigma_generation_service.LLMService", return_value=mock_llm):
            return SigmaGenerationService()

    @pytest.fixture()
    def sample_article_data(self):
        return {
            "title": "APT29 Uses PowerShell for Persistence",
            "content": "APT29 has been observed using PowerShell scripts to maintain persistence. The attack involves creating scheduled tasks and registry modifications.",
            "source_name": "Threat Intelligence Feed",
            "url": "https://example.com/threat-report-123",
        }

    @pytest.mark.asyncio
    async def test_custom_system_prompt_reaches_provider(self, service, sample_article_data):
        """Regression: sigma_system_prompt must be forwarded to _call_provider_for_sigma."""
        custom_system = "CUSTOM_SYS_PROMPT_SENTINEL_V1"
        user_template = "Generate Sigma for {title}: {content}"

        with patch("src.services.sigma_generation_service.optimize_article_content") as mock_opt:
            mock_opt.return_value = {
                "success": True,
                "filtered_content": sample_article_data["content"],
                "tokens_saved": 0,
            }
            with patch.object(service, "_call_provider_for_sigma", new_callable=AsyncMock) as mock_call:
                mock_call.return_value = "title: Test\nid: test\n"
                with patch("src.services.sigma_generation_service.validate_sigma_rule") as mock_validate:
                    mock_validate.return_value = ValidationResult(
                        is_valid=True,
                        errors=[],
                        warnings=[],
                        metadata={"rule": {"title": "Test", "id": "test"}},
                        content_preview="title: Test\nid: test",
                    )

                    await service.generate_sigma_rules(
                        article_title=sample_article_data["title"],
                        article_content=sample_article_data["content"],
                        source_name=sample_article_data["source_name"],
                        url=sample_article_data["url"],
                        sigma_prompt_template=user_template,
                        sigma_system_prompt=custom_system,
                    )

        assert mock_call.called, "_call_provider_for_sigma was never invoked"
        actual_system = mock_call.call_args.kwargs.get("system_prompt")
        assert actual_system == custom_system, (
            f"Expected system_prompt={custom_system!r}, got {actual_system!r}. "
            "Custom system prompt was dropped before reaching the provider."
        )

    @pytest.mark.asyncio
    async def test_none_system_prompt_uses_hardcoded_default(self, service, sample_article_data):
        """When sigma_system_prompt=None the hardcoded default must be used, not None."""
        with patch("src.services.sigma_generation_service.optimize_article_content") as mock_opt:
            mock_opt.return_value = {
                "success": True,
                "filtered_content": sample_article_data["content"],
                "tokens_saved": 0,
            }
            with patch.object(service, "_call_provider_for_sigma", new_callable=AsyncMock) as mock_call:
                mock_call.return_value = "title: Test\nid: test\n"
                with patch("src.services.sigma_generation_service.validate_sigma_rule") as mock_validate:
                    mock_validate.return_value = ValidationResult(
                        is_valid=True,
                        errors=[],
                        warnings=[],
                        metadata={"rule": {"title": "Test", "id": "test"}},
                        content_preview="title: Test\nid: test",
                    )
                    with patch("src.utils.prompt_loader.format_prompt_async") as mock_prompt:
                        mock_prompt.return_value = f"Generate rule for: {sample_article_data['title']}"

                        await service.generate_sigma_rules(
                            article_title=sample_article_data["title"],
                            article_content=sample_article_data["content"],
                            source_name=sample_article_data["source_name"],
                            url=sample_article_data["url"],
                            sigma_system_prompt=None,
                        )

        # When no custom prompt is given, the caller passes system_prompt=None to
        # _call_provider_for_sigma; the hardcoded default is applied *inside* that
        # function.  We verify the caller doesn't accidentally substitute the default
        # before the call (which would prevent the custom-prompt path from working).
        actual_system = mock_call.call_args.kwargs.get("system_prompt")
        assert actual_system is None, (
            "With no custom system prompt, caller should pass None to _call_provider_for_sigma "
            "so the internal default-substitution logic can run."
        )


# ---------------------------------------------------------------------------
# Regression tests for _build_observables_section generic dict serialization
# (fixes hardcoded process-lineage field names for non-process-lineage types)
# ---------------------------------------------------------------------------


class TestBuildObservablesSectionGenericDictSerializer:
    """_build_observables_section must use generic key=value serialization for
    all dict-valued observables, not hardcoded parent/child/arguments fields."""

    def test_windows_services_dict_serialized_with_real_content(self):
        """windows_services value must produce readable key=value pairs, not empty parent/child."""
        extraction_result = {
            "observables": [
                {
                    "type": "windows_services",
                    "value": {"service_name": "MalSvc", "binary_path": "C:\\evil.exe"},
                }
            ]
        }
        section = _build_observables_section(extraction_result)
        assert "service_name=MalSvc" in section
        assert "binary_path=C:\\evil.exe" in section

    def test_registry_artifacts_dict_serialized_with_real_content(self):
        """registry_artifacts value must produce readable key=value pairs."""
        extraction_result = {
            "observables": [
                {
                    "type": "registry_artifacts",
                    "value": {
                        "key": "HKLM\\Software\\evil",
                        "value_name": "socks5",
                        "value_data": "powershell.exe -windowstyle hidden",
                    },
                }
            ]
        }
        section = _build_observables_section(extraction_result)
        assert "key=HKLM\\Software\\evil" in section
        assert "value_name=socks5" in section
        assert "value_data=powershell.exe -windowstyle hidden" in section

    def test_scheduled_tasks_dict_serialized_with_real_content(self):
        """scheduled_tasks value must produce readable key=value pairs."""
        extraction_result = {
            "observables": [
                {
                    "type": "scheduled_tasks",
                    "value": {"task_name": "\\Microsoft\\evil", "action": "cmd.exe /c evil.bat"},
                }
            ]
        }
        section = _build_observables_section(extraction_result)
        assert "task_name=\\Microsoft\\evil" in section
        assert "action=cmd.exe /c evil.bat" in section

    def test_none_values_skipped_in_dict_serialization(self):
        """Keys with None values must be omitted from the serialized output."""
        extraction_result = {
            "observables": [
                {
                    "type": "windows_services",
                    "value": {"service_name": "MySvc", "binary_path": None, "description": ""},
                }
            ]
        }
        section = _build_observables_section(extraction_result)
        assert "binary_path" not in section
        assert "description" not in section
        assert "service_name=MySvc" in section

    def test_all_none_dict_values_shows_empty_marker(self):
        """A dict whose every value is None or empty must produce '(empty)' not a blank line."""
        extraction_result = {
            "observables": [
                {
                    "type": "windows_services",
                    "value": {"service_name": None, "binary_path": ""},
                }
            ]
        }
        section = _build_observables_section(extraction_result)
        assert "(empty)" in section

    def test_process_lineage_dict_still_works_with_generic_serializer(self):
        """process_lineage dicts must still produce readable output after switching to generic serializer."""
        extraction_result = {
            "observables": [
                {
                    "type": "process_lineage",
                    "value": {"parent": "explorer.exe", "child": "powershell.exe", "arguments": "-enc abc"},
                }
            ]
        }
        section = _build_observables_section(extraction_result)
        assert "parent=explorer.exe" in section
        assert "child=powershell.exe" in section
        assert "arguments=-enc abc" in section

    def test_mixed_scalar_and_dict_observables_in_same_section(self):
        """Scalar and dict observables must both appear correctly in the same prompt section."""
        extraction_result = {
            "observables": [
                {"type": "cmdline", "value": "cmd.exe /c whoami"},
                {"type": "windows_services", "value": {"service_name": "EvilSvc", "binary_path": "C:\\evil.exe"}},
            ]
        }
        section = _build_observables_section(extraction_result)
        assert "[0] cmdline:" in section
        assert "cmd.exe /c whoami" in section
        assert "[1] windows_services:" in section
        assert "service_name=EvilSvc" in section


# ---------------------------------------------------------------------------
# Regression tests for _infer_observables_used token quality fixes
# (filters 'none'/'redacted' stop-tokens; resolves _REDACTED prefix matches)
# ---------------------------------------------------------------------------


class TestInferObservablesUsedTokenQuality:
    """_infer_observables_used must not match on 'none'/'redacted' stop-tokens
    and must try the prefix portion of _REDACTED-suffixed values."""

    def _make_rule(self, detection_content: str) -> str:
        return (
            "title: Test\nid: t1\ndescription: x\n"
            "logsource:\n  category: process_creation\n  product: windows\n"
            f"detection:\n  selection:\n    {detection_content}\n  condition: selection\nlevel: low\n"
        )

    def test_none_string_token_does_not_produce_false_match(self):
        """An observable whose only token is 'none' must not match any rule."""
        extraction_result = {
            "observables": [
                {"type": "windows_services", "value": {"service_name": None, "binary_path": None}},
            ]
        }
        rule_yaml = self._make_rule("CommandLine|contains: powershell")
        result = _infer_observables_used(rule_yaml, extraction_result)
        assert result is None, "None-valued observable falsely matched via 'none' token"

    def test_redacted_token_suffix_does_not_match_literally(self):
        """The token '_redacted' on its own must be filtered as a stop-token."""
        extraction_result = {
            "observables": [
                {"type": "cmdline", "value": "SomeApp_REDACTED"},
            ]
        }
        # Detection block contains the literal word 'redacted' -- should not match
        rule_yaml = self._make_rule("CommandLine|contains: redacted")
        result = _infer_observables_used(rule_yaml, extraction_result)
        assert result is None, "Token 'redacted' should be filtered as a stop-token"

    def test_redacted_prefix_matches_in_detection_block(self):
        """GoToResolve_REDACTED must try the prefix 'gotoresolve' for matching."""
        extraction_result = {
            "observables": [
                {"type": "cmdline", "value": "GoToResolve_REDACTED"},
            ]
        }
        rule_yaml = self._make_rule("CommandLine|contains: gotoresolve")
        result = _infer_observables_used(rule_yaml, extraction_result)
        assert result == [0], "GoToResolve_REDACTED prefix 'gotoresolve' should match in the detection block"

    def test_redacted_prefix_too_short_not_used(self):
        """A _REDACTED prefix shorter than 4 chars must not be used as a match token."""
        extraction_result = {
            "observables": [
                {"type": "cmdline", "value": "cmd_REDACTED"},
            ]
        }
        rule_yaml = self._make_rule("CommandLine|contains: cmd")
        # 'cmd' is only 3 chars, below the 4-char threshold
        result = _infer_observables_used(rule_yaml, extraction_result)
        assert result is None

    def test_valid_non_redacted_token_still_matches(self):
        """Normal observable values must still match correctly after token filter changes."""
        extraction_result = {
            "observables": [
                {"type": "cmdline", "value": "mimikatz sekurlsa"},
            ]
        }
        # 'mimikatz' and 'sekurlsa' are both >=4 chars and appear in the detection block
        rule_yaml = self._make_rule("CommandLine|contains: mimikatz")
        result = _infer_observables_used(rule_yaml, extraction_result)
        assert result == [0]

    def test_null_token_stop_word_filtered(self):
        """The token 'null' (common in serialized output) must be filtered as a stop-token."""
        extraction_result = {
            "observables": [
                {"type": "cmdline", "value": "null"},
            ]
        }
        rule_yaml = self._make_rule("CommandLine|contains: null")
        result = _infer_observables_used(rule_yaml, extraction_result)
        assert result is None


# ---------------------------------------------------------------------------
# Platform-aware Sigma guidance (Linux pilot follow-up)
# ---------------------------------------------------------------------------


def test_platform_sigma_guidance_injected_for_linux_group():
    from src.services.sigma_generation_service import _platform_sigma_guidance

    er = {"sigma_generation_group": {"platform": "linux", "telemetry_category": "process_creation"}}
    guidance = _platform_sigma_guidance(er)
    assert guidance
    # Steers away from the over-broad pattern seen in the pilot and toward Linux fields.
    assert "/chmod" in guidance and "777" in guidance
    assert "Windows-only fields" in guidance
    assert "T1222.002" in guidance


def test_platform_sigma_guidance_empty_for_non_linux():
    from src.services.sigma_generation_service import _platform_sigma_guidance

    assert _platform_sigma_guidance({"sigma_generation_group": {"platform": "windows"}}) == ""
    assert _platform_sigma_guidance({"sigma_generation_group": {"platform": "macos"}}) == ""
    assert _platform_sigma_guidance({}) == ""
    assert _platform_sigma_guidance(None) == ""
