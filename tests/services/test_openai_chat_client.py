"""Unit tests for shared OpenAI chat client."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock


pytestmark = pytest.mark.unit


class TestOpenAIChatClient:
    """Test openai_chat_client module."""

    def test_openai_is_reasoning_model_o1(self):
        """o1 is a reasoning model."""
        from src.services.openai_chat_client import openai_is_reasoning_model
        assert openai_is_reasoning_model("o1") is True
        assert openai_is_reasoning_model("o1-mini") is True

    def test_openai_is_reasoning_model_o3_o4(self):
        """o3, o4 are reasoning models."""
        from src.services.openai_chat_client import openai_is_reasoning_model
        assert openai_is_reasoning_model("o3") is True
        assert openai_is_reasoning_model("o4") is True
        assert openai_is_reasoning_model("o4-mini") is True

    def test_openai_is_reasoning_model_gpt5(self):
        """gpt-5.x are reasoning models."""
        from src.services.openai_chat_client import openai_is_reasoning_model
        assert openai_is_reasoning_model("gpt-5") is True
        assert openai_is_reasoning_model("gpt-5.2") is True

    def test_openai_is_reasoning_model_standard(self):
        """gpt-4o, gpt-4o-mini are not reasoning models."""
        from src.services.openai_chat_client import openai_is_reasoning_model
        assert openai_is_reasoning_model("gpt-4o") is False
        assert openai_is_reasoning_model("gpt-4o-mini") is False
        assert openai_is_reasoning_model("gpt-4.1") is False

    def test_openai_build_chat_payload_reasoning(self):
        """Reasoning models use max_completion_tokens, no temperature."""
        from src.services.openai_chat_client import openai_build_chat_payload
        payload = openai_build_chat_payload("o1", [{"role": "user", "content": "hi"}])
        assert "max_completion_tokens" in payload
        assert "max_tokens" not in payload
        assert "temperature" not in payload

    def test_openai_build_chat_payload_standard(self):
        """Standard models use max_tokens and temperature."""
        from src.services.openai_chat_client import openai_build_chat_payload
        payload = openai_build_chat_payload("gpt-4o-mini", [{"role": "user", "content": "hi"}])
        assert "max_tokens" in payload
        assert "temperature" in payload
        assert "max_completion_tokens" not in payload

    def test_openai_build_chat_payload_use_reasoning_override(self):
        """use_reasoning override works."""
        from src.services.openai_chat_client import openai_build_chat_payload
        payload = openai_build_chat_payload(
            "gpt-4o-mini", [{"role": "user", "content": "hi"}],
            use_reasoning=True
        )
        assert "max_completion_tokens" in payload
        assert "temperature" not in payload

    @pytest.mark.asyncio
    async def test_openai_chat_completions_empty_key_raises(self):
        """Empty API key raises ValueError."""
        from src.services.openai_chat_client import openai_chat_completions
        with pytest.raises(ValueError, match="API key"):
            await openai_chat_completions(
                api_key="",
                model_name="gpt-4o-mini",
                messages=[{"role": "user", "content": "hi"}],
            )

    @pytest.mark.asyncio
    async def test_openai_chat_completions_success(self):
        """Successful API call returns content."""
        from src.services.openai_chat_client import openai_chat_completions

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello"}}]
        }

        with patch("src.services.openai_chat_client.httpx.AsyncClient") as mock_client:
            mock_instance = MagicMock()
            mock_instance.post = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            result = await openai_chat_completions(
                api_key="sk-test",
                model_name="gpt-4o-mini",
                messages=[{"role": "user", "content": "hi"}],
            )
            assert result == "Hello"

    @pytest.mark.asyncio
    async def test_openai_chat_completions_param_error_retries(self):
        """Param error triggers retry with alternate params."""
        from src.services.openai_chat_client import openai_chat_completions

        fail_response = MagicMock()
        fail_response.status_code = 400
        fail_response.text = '{"error": {"message": "Unsupported parameter: max_tokens"}}'

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {
            "choices": [{"message": {"content": "Retry ok"}}]
        }

        with patch("src.services.openai_chat_client.httpx.AsyncClient") as mock_client:
            mock_instance = MagicMock()
            mock_instance.post = AsyncMock(side_effect=[fail_response, success_response])
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            result = await openai_chat_completions(
                api_key="sk-test",
                model_name="gpt-5.2",
                messages=[{"role": "user", "content": "hi"}],
            )
            assert result == "Retry ok"
            assert mock_instance.post.call_count == 2
