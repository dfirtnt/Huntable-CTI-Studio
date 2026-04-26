"""Tests for src.utils.model_validation."""

import re

from src.utils.model_validation import (
    OPENAI_DATED,
    PROJECT_OPENAI_ALLOWLIST,
    _anthropic_family,
    clamp_temperature_for_provider,
    filter_anthropic_models_latest_only,
    filter_openai_models_latest_only,
    filter_openai_models_project_allowlist,
    is_valid_openai_chat_model,
    model_supports_variable_temperature,
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

    def test_gpt5_codex_terminal_blocked_by_is_valid(self):
        """gpt-5.3-codex ends in -codex and is rejected by is_valid inside this filter."""
        out = filter_openai_models_latest_only(["gpt-5.3-codex", "gpt-5.3-codex-spark", "gpt-5.4"])
        assert "gpt-5.3-codex" not in out  # terminal -codex -> excluded
        assert "gpt-5.3-codex-spark" in out  # non-terminal -> valid via fallback
        assert "gpt-5.4" in out  # base pattern match


class TestFilterOpenaiModelsProjectAllowlist:
    """filter_openai_models_project_allowlist: narrow to the 6 CTIScraper workflow models."""

    def test_empty(self):
        assert filter_openai_models_project_allowlist([]) == []

    def test_allowlist_members_kept(self):
        assert filter_openai_models_project_allowlist(list(PROJECT_OPENAI_ALLOWLIST)) == sorted(
            PROJECT_OPENAI_ALLOWLIST
        )

    def test_non_allowlisted_chat_models_dropped(self):
        # Valid chat models the project pipeline does not use.
        # gpt-5*/codex-* are intentionally excluded here -- they pass by pattern.
        ids = ["gpt-4-turbo", "gpt-3.5-turbo", "o1", "o1-pro", "o3", "o3-pro"]
        assert filter_openai_models_project_allowlist(ids) == []

    def test_allowlisted_mixed_with_noise(self):
        ids = [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4.1",
            "gpt-4.1-mini",
            "o3-mini",
            "o4-mini",
            # gpt-5* and codex-* pass by pattern (not noise)
            "gpt-5",
            "codex-mini-latest",
            # genuine noise -- dropped
            "gpt-4-turbo",
            "gpt-4o-audio-preview",
            "gpt-4o-2024-05-13",
            "o1",
        ]
        out = filter_openai_models_project_allowlist(ids)
        # All explicit allowlist members must be present
        assert set(PROJECT_OPENAI_ALLOWLIST).issubset(set(out))
        # Pattern-matched models also survive
        assert "gpt-5" in out
        # Non-workflow models are dropped
        assert "gpt-4-turbo" not in out
        assert "o1" not in out

    def test_whitespace_and_dedupe(self):
        ids = ["gpt-4o", " gpt-4o ", "gpt-4o", "o4-mini"]
        out = filter_openai_models_project_allowlist(ids)
        assert out == ["gpt-4o", "o4-mini"]

    def test_gpt5_4_subfamily_all_pass_via_pattern(self):
        """gpt-5.4 family passes via _GPT5_PATTERN -- no explicit allowlist entry required."""
        models = ["gpt-5.4", "gpt-5.4-mini", "gpt-5.4-nano", "gpt-5.4-pro"]
        out = filter_openai_models_project_allowlist(models)
        assert set(out) == set(models)

    def test_gpt5_codex_spark_passes_via_gpt5_pattern(self):
        """gpt-5.3-codex-spark starts with gpt-5 so it passes the allowlist pattern check."""
        out = filter_openai_models_project_allowlist(["gpt-5.3-codex-spark"])
        assert out == ["gpt-5.3-codex-spark"]

    def test_dated_variants_excluded(self):
        # The base-name allowlist is exact; dated variants are filtered by
        # filter_openai_models_latest_only upstream, so this layer must also reject them.
        assert filter_openai_models_project_allowlist(["gpt-4o-2024-05-13", "gpt-4.1-mini-2025-04-14"]) == []

    def test_codex_pattern_passes_new_variants(self):
        """codex-* models pass via _CODEX_PATTERN -- no catalog/allowlist entry required."""
        ids = ["codex-large", "codex-v2", "codex-mini", "codex-future-model"]
        out = filter_openai_models_project_allowlist(ids)
        assert set(out) == {"codex-large", "codex-v2", "codex-mini", "codex-future-model"}

    def test_allowlist_size_matches_spec(self):
        # Canary: if this changes, update the Todoist task / docs before landing.
        assert len(PROJECT_OPENAI_ALLOWLIST) == 7
        assert {
            "gpt-4o-mini",
            "gpt-4o",
            "gpt-4.1-mini",
            "gpt-4.1",
            "o3-mini",
            "o4-mini",
            "codex-mini-latest",
        } == PROJECT_OPENAI_ALLOWLIST


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
        assert is_valid_openai_chat_model("llama-3.1-70b") is False
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

    def test_codex_mini_whitelisted(self):
        """codex-mini is explicitly whitelisted as a chat model."""
        assert is_valid_openai_chat_model("codex-mini") is True
        assert is_valid_openai_chat_model("codex-mini-latest") is True

    def test_codex_prefix_fallback(self):
        """codex- prefix models pass the fallback check (like gpt- and o)."""
        assert is_valid_openai_chat_model("codex-future-model") is True

    def test_gpt_codex_suffix_still_excluded(self):
        """Models with -codex suffix (e.g. gpt-5-codex) remain non-chat."""
        assert is_valid_openai_chat_model("gpt-5-codex") is False
        assert is_valid_openai_chat_model("gpt-5.2-codex") is False

    def test_codex_exclusion_anchor_precision(self):
        """The -codex$ pattern only excludes a terminal suffix; -codex- mid-string is not excluded."""
        # Terminal suffix: excluded
        assert is_valid_openai_chat_model("gpt-5-codex") is False
        # Mid-string: passes (gpt- fallback; not a terminal -codex suffix)
        assert is_valid_openai_chat_model("gpt-5-codex-mini") is True

    def test_gpt5_point_releases_all_valid(self):
        """gpt-5.1 through gpt-5.4 match VALID_CHAT_BASE_PATTERNS."""
        for m in ["gpt-5.1", "gpt-5.2", "gpt-5.3", "gpt-5.4"]:
            assert is_valid_openai_chat_model(m) is True, f"{m} should be valid"

    def test_gpt5_4_subfamily_all_valid(self):
        """gpt-5.4 mini/nano/pro all match the base pattern suffix list."""
        for m in ["gpt-5.4-mini", "gpt-5.4-nano", "gpt-5.4-pro"]:
            assert is_valid_openai_chat_model(m) is True, f"{m} should be valid"

    def test_gpt5_codex_terminal_suffix_excluded(self):
        """gpt-5.3-codex ends in -codex -- excluded by the terminal-anchor NON_CHAT rule."""
        assert is_valid_openai_chat_model("gpt-5.3-codex") is False

    def test_gpt5_codex_spark_valid(self):
        """gpt-5.3-codex-spark does NOT end in -codex, so it is NOT excluded and passes via fallback."""
        assert is_valid_openai_chat_model("gpt-5.3-codex-spark") is True

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


class TestModelSupportsVariableTemperature:
    """model_supports_variable_temperature: False for reasoning models, True for all others."""

    def test_reasoning_models_return_false(self):
        for model in ("o1", "o1-mini", "o3", "o3-mini", "o4", "o4-mini"):
            assert model_supports_variable_temperature(model) is False, model

    def test_gpt5_returns_false(self):
        for model in ("gpt-5", "gpt-5.2", "gpt-5-pro"):
            assert model_supports_variable_temperature(model) is False, model

    def test_standard_gpt_models_return_true(self):
        for model in ("gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "codex-mini-latest"):
            assert model_supports_variable_temperature(model) is True, model

    def test_anthropic_models_return_true(self):
        for model in ("claude-sonnet-4-5", "claude-opus-4-6", "claude-haiku-4-5"):
            assert model_supports_variable_temperature(model) is True, model

    def test_lmstudio_local_models_return_true(self):
        for model in ("llama-3.1-8b", "deepseek-r1-distill", "mistral-7b-instruct"):
            assert model_supports_variable_temperature(model) is True, model

    def test_empty_or_none_returns_true(self):
        assert model_supports_variable_temperature("") is True
        assert model_supports_variable_temperature(None) is True  # type: ignore[arg-type]

    def test_project_allowlist_reasoning_models_are_false(self):
        """All reasoning models from PROJECT_OPENAI_ALLOWLIST must return False."""
        reasoning_in_allowlist = {"o3-mini", "o4-mini"}
        for m in reasoning_in_allowlist:
            assert model_supports_variable_temperature(m) is False, m

    def test_project_allowlist_standard_models_are_true(self):
        """Non-reasoning models from PROJECT_OPENAI_ALLOWLIST must return True."""
        standard_in_allowlist = {"gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "codex-mini-latest"}
        for m in standard_in_allowlist:
            assert model_supports_variable_temperature(m) is True, m
