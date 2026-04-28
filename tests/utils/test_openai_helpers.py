"""Tests for src.web.utils.openai_helpers -- payload construction and temperature capability."""

import pytest

pytestmark = pytest.mark.unit


class TestBuildOpenaiPayload:
    """build_openai_payload: temperature omitted for reasoning models, included for standard."""

    def test_standard_model_includes_temperature_chat(self):
        from src.web.utils.openai_helpers import build_openai_payload

        payload = build_openai_payload(
            prompt="hello",
            system_prompt="you are helpful",
            temperature=0.7,
            token_limit=500,
            model="gpt-4o-mini",
            use_responses_api=False,
        )
        assert "temperature" in payload
        assert payload["temperature"] == 0.7
        assert "max_tokens" in payload

    def test_standard_model_includes_temperature_responses(self):
        from src.web.utils.openai_helpers import build_openai_payload

        payload = build_openai_payload(
            prompt="hello",
            system_prompt="you are helpful",
            temperature=0.5,
            token_limit=500,
            model="gpt-4.1",
            use_responses_api=True,
        )
        assert "temperature" in payload
        assert payload["temperature"] == 0.5
        assert "max_output_tokens" in payload

    def test_reasoning_model_omits_temperature_chat(self):
        from src.web.utils.openai_helpers import build_openai_payload

        for model in ("o3-mini", "o4-mini", "o1"):
            payload = build_openai_payload(
                prompt="hello",
                system_prompt="system",
                temperature=0.7,
                token_limit=500,
                model=model,
                use_responses_api=False,
            )
            assert "temperature" not in payload, f"temperature should be absent for {model}"

    def test_reasoning_model_omits_temperature_responses(self):
        from src.web.utils.openai_helpers import build_openai_payload

        payload = build_openai_payload(
            prompt="hello",
            system_prompt="system",
            temperature=0.9,
            token_limit=500,
            model="o4-mini",
            use_responses_api=True,
        )
        assert "temperature" not in payload

    def test_gpt5_omits_temperature(self):
        from src.web.utils.openai_helpers import build_openai_payload

        payload = build_openai_payload(
            prompt="hello",
            system_prompt="system",
            temperature=0.3,
            token_limit=500,
            model="gpt-5",
            use_responses_api=False,
        )
        assert "temperature" not in payload

    def test_payload_structure_chat(self):
        from src.web.utils.openai_helpers import build_openai_payload

        payload = build_openai_payload(
            prompt="user msg",
            system_prompt="sys msg",
            temperature=0.1,
            token_limit=256,
            model="gpt-4o",
            use_responses_api=False,
        )
        assert payload["model"] == "gpt-4o"
        assert payload["max_tokens"] == 256
        messages = payload["messages"]
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "sys msg"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "user msg"

    def test_payload_structure_responses(self):
        from src.web.utils.openai_helpers import build_openai_payload

        payload = build_openai_payload(
            prompt="user msg",
            system_prompt="sys msg",
            temperature=0.2,
            token_limit=128,
            model="gpt-4o-mini",
            use_responses_api=True,
        )
        assert payload["model"] == "gpt-4o-mini"
        assert payload["max_output_tokens"] == 128
        input_msgs = payload["input"]
        assert input_msgs[0]["role"] == "system"
        assert input_msgs[1]["role"] == "user"
