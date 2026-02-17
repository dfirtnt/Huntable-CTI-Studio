"""Tests for src.utils.model_validation."""
import re

from src.utils.model_validation import _anthropic_family, filter_anthropic_models_latest_only


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
