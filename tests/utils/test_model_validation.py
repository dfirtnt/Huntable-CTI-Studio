"""Tests for src.utils.model_validation."""

import re

from src.utils.model_validation import (
    OPENAI_DATED,
    _anthropic_family,
    clamp_temperature_for_provider,
    filter_anthropic_models_latest_only,
    filter_openai_models_latest_only,
    is_valid_openai_chat_model,
    suggest_base_model,
)


class TestFilterAnthropicModelsLatestOnly:
    """filter_anthropic_models_latest_only: one main/latest per family (Haiku, Opus, Sonnet versions)."""

    def test_empty(self):
        assert filter_anthropic_models_latest_only([]) == []

    def test_non_claude_ignored(self):
        assert filter_anthropic_models_latest_only(["gpt-4o", "claude-sonnet-4-5"]) == [
            "claude-sonnet-4-5",
        ]

    def test_one_per_family_prefer_main_over_dated(self):
        ids = [
            "claude-sonnet-4-5-20250929",
            "claude-sonnet-4-5",
            "claude-opus-4-6",
            "claude-3-7-sonnet-20250219",
        ]
        out = filter_anthropic_models_latest_only(ids)
        assert len(out) == 3
        assert "claude-sonnet-4-5" in out  # main preferred over dated
        assert "claude-opus-4-6" in out
        assert any(m.startswith("claude-3-7-sonnet") for m in out)

    def test_one_per_family_prefer_latest_over_dated(self):
        ids = ["claude-3-7-sonnet-20250219", "claude-3-7-sonnet-latest"]
        out = filter_anthropic_models_latest_only(ids)
        assert len(out) == 1
        assert out[0].endswith("-latest")

    def test_dated_only_keeps_one_per_family_latest_date_wins(self):
        ids = ["claude-3-5-haiku-20241022", "claude-3-5-haiku-20250101"]
        out = filter_anthropic_models_latest_only(ids)
        assert len(out) == 1
        dates = [m[-8:] for m in ids if re.search(r"-\d{8}$", m)]
        assert out[0].endswith(max(dates))  # later date chosen

    def test_one_output_per_distinct_family(self):
        ids = [
            "claude-3-5-haiku-20241022",
            "claude-3-7-sonnet-20250219",
            "claude-3-haiku-20240307",
            "claude-haiku-4-5-20251001",
            "claude-opus-4-1-20250805",
            "claude-opus-4-20250514",
            "claude-opus-4-5-20251101",
            "claude-opus-4-6",
            "claude-sonnet-4-20250514",
            "claude-sonnet-4-5",
            "claude-sonnet-4-5-20250929",
        ]
        out = filter_anthropic_models_latest_only(ids)
        families_in = {_anthropic_family(m) for m in ids}
        assert len(out) == len(families_in)
        assert {_anthropic_family(m) for m in out} == families_in
        # Main preferred where present (no -YYYYMMDD)
        assert "claude-opus-4-6" in out
        assert "claude-sonnet-4-5" in out


class TestFilterOpenaiModelsLatestOnly:
    """filter_openai_models_latest_only: chat-only, latest only (no -YYYY-MM-DD)."""

    def test_empty(self):
        assert filter_openai_models_latest_only([]) == []

    def test_dated_excluded(self):
        ids = ["gpt-4o", "gpt-4o-2024-05-13", "gpt-4.1-mini", "gpt-4.1-mini-2025-04-14"]
        out = filter_openai_models_latest_only(ids)
        assert "gpt-4o" in out
        assert "gpt-4.1-mini" in out
        assert not any(OPENAI_DATED.search(m) for m in out)

    def test_non_chat_excluded(self):
        ids = ["gpt-4o", "gpt-4o-audio-preview", "gpt-5-codex", "o1"]
        out = filter_openai_models_latest_only(ids)
        assert "gpt-4o" in out
        assert "o1" in out
        assert "gpt-4o-audio-preview" not in out
        assert "gpt-5-codex" not in out

    def test_base_names_kept(self):
        ids = ["gpt-4o", "gpt-4.1-mini", "o1", "o3-mini"]
        out = filter_openai_models_latest_only(ids)
        assert set(out) >= {"gpt-4o", "gpt-4.1-mini", "o1", "o3-mini"}


class TestClampTemperatureForProvider:
    """clamp_temperature_for_provider: enforce provider-specific temperature ranges."""

    def test_openai_clamps_to_0_2(self):
        assert clamp_temperature_for_provider("openai", -0.1) == 0.0
        assert clamp_temperature_for_provider("openai", 0.0) == 0.0
        assert clamp_temperature_for_provider("openai", 1.5) == 1.5
        assert clamp_temperature_for_provider("openai", 2.5) == 2.0

    def test_anthropic_clamps_to_0_1(self):
        assert clamp_temperature_for_provider("anthropic", -0.1) == 0.0
        assert clamp_temperature_for_provider("anthropic", 0.0) == 0.0
        assert clamp_temperature_for_provider("anthropic", 1.0) == 1.0
        assert clamp_temperature_for_provider("anthropic", 1.5) == 1.0

    def test_lmstudio_uses_0_2(self):
        assert clamp_temperature_for_provider("lmstudio", 2.5) == 2.0
        assert clamp_temperature_for_provider("lmstudio", 0.5) == 0.5

    def test_unknown_provider_defaults_to_0_2(self):
        assert clamp_temperature_for_provider("unknown", 3.0) == 2.0
        assert clamp_temperature_for_provider("", 0.5) == 0.5

    def test_provider_case_insensitive(self):
        assert clamp_temperature_for_provider("ANTHROPIC", 1.5) == 1.0
        assert clamp_temperature_for_provider("OpenAI", 2.5) == 2.0


class TestIsValidOpenaiChatModel:
    """is_valid_openai_chat_model: OpenAI chat-only validation, excludes codex/audio/image/etc."""

    def test_empty_or_none_false(self):
        assert is_valid_openai_chat_model("") is False
        assert is_valid_openai_chat_model(None) is False  # type: ignore[arg-type]
        assert is_valid_openai_chat_model("   ") is False

    def test_non_string_false(self):
        assert is_valid_openai_chat_model(123) is False  # type: ignore[arg-type]
        assert is_valid_openai_chat_model([]) is False  # type: ignore[arg-type]

    def test_non_openai_pattern_false(self):
        assert is_valid_openai_chat_model("claude-3-opus") is False
        assert is_valid_openai_chat_model("gemini-1.5-pro") is False
        assert is_valid_openai_chat_model("unknown-model") is False

    def test_non_chat_patterns_excluded(self):
        assert is_valid_openai_chat_model("gpt-5-codex") is False
        assert is_valid_openai_chat_model("gpt-4o-audio-preview") is False
        assert is_valid_openai_chat_model("gpt-4o-image") is False
        assert is_valid_openai_chat_model("gpt-4o-realtime") is False
        assert is_valid_openai_chat_model("gpt-realtime-preview") is False
        assert is_valid_openai_chat_model("text-davinci-003") is False
        assert is_valid_openai_chat_model("o3-deep-research") is False

    def test_valid_base_names_true(self):
        assert is_valid_openai_chat_model("gpt-4o") is True
        assert is_valid_openai_chat_model("gpt-4.1-mini") is True
        assert is_valid_openai_chat_model("gpt-4o-mini") is True
        assert is_valid_openai_chat_model("o1") is True
        assert is_valid_openai_chat_model("o3-mini") is True
        assert is_valid_openai_chat_model("gpt-3.5-turbo") is True

    def test_dated_whitelist_base_true(self):
        assert is_valid_openai_chat_model("gpt-4o-2024-05-13") is True
        assert is_valid_openai_chat_model("gpt-4.1-mini-2025-04-14") is True
        assert is_valid_openai_chat_model("o1-2025-01-01") is True  # o1 in whitelist

    def test_dated_unknown_base_false(self):
        # Base gpt-99 does not match VALID_CHAT_BASE_PATTERNS or whitelist; dated → conservative False
        assert is_valid_openai_chat_model("gpt-99-2025-01-01") is False

    def test_fallback_gpt_or_o_true(self):
        assert is_valid_openai_chat_model("gpt-some-new-model") is True
        assert is_valid_openai_chat_model("o2-custom") is True


class TestSuggestBaseModel:
    """suggest_base_model: suggest base name for dated model IDs."""

    def test_empty_or_none_returns_none(self):
        assert suggest_base_model("") is None
        assert suggest_base_model(None) is None  # type: ignore[arg-type]

    def test_no_date_suffix_returns_none(self):
        assert suggest_base_model("gpt-4o") is None
        assert suggest_base_model("o1") is None

    def test_dated_returns_base_when_valid(self):
        assert suggest_base_model("gpt-4o-2024-05-13") == "gpt-4o"
        assert suggest_base_model("gpt-4.1-mini-2025-04-14") == "gpt-4.1-mini"

    def test_dated_unknown_base_returns_none(self):
        # Base gpt-4o-audio is invalid (non-chat); no suggestion
        assert suggest_base_model("gpt-4o-audio-2025-01-01") is None

    def test_preview_suffix_stripped(self):
        assert suggest_base_model("gpt-4o-2024-05-13-preview") == "gpt-4o"
