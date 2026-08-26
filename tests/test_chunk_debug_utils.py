"""Tests for chunk debug utility helpers."""

import pytest

from src.utils.llm_optimizer import GPT4O_INPUT_COST_PER_MILLION_TOKENS
from src.web.routes.debug import _build_chunk_reason, calculate_filtered_costs

pytestmark = pytest.mark.unit


class TestBuildChunkReason:
    """A kept chunk's reason must never read as though it was removed, and
    should name the deciding feature when one is available (2026-08-20 dogfood
    finding: 'Content filtered successfully' on a kept chunk reads as removal)."""

    def test_kept_with_feature_contribution_names_top_feature(self):
        reason = _build_chunk_reason(
            is_huntable=True,
            feature_contribution={"cmdline_artifact_count": 0.9, "perfect_pattern_count": 0.4},
        )
        assert reason.lower().startswith("kept")
        assert "cmdline artifact count" in reason
        assert "not kept" not in reason.lower()

    def test_kept_without_feature_contribution_still_reads_as_kept(self):
        reason = _build_chunk_reason(is_huntable=True, feature_contribution=None)
        assert reason.lower().startswith("kept")
        assert "not kept" not in reason.lower()

    def test_removed_with_feature_contribution_names_top_feature(self):
        reason = _build_chunk_reason(
            is_huntable=False,
            feature_contribution={"atomic_ioc_density": 0.7, "sentence_count": 0.1},
        )
        assert reason.lower().startswith("not kept")
        assert "atomic ioc density" in reason

    def test_removed_without_feature_contribution_has_no_kept_prefix(self):
        reason = _build_chunk_reason(is_huntable=False, feature_contribution=None)
        assert reason.lower().startswith("not kept")

    def test_empty_feature_contribution_dict_falls_back_like_none(self):
        reason = _build_chunk_reason(is_huntable=True, feature_contribution={})
        assert reason == "Kept - huntable content detected"


def test_calculate_filtered_costs_reuses_filtered_tokens():
    """Cost estimation should use filtered token length and never exceed original."""
    estimate = calculate_filtered_costs(original_length=10000, filtered_length=4000)

    # Token estimates use 4 chars/token heuristic
    assert estimate["original_tokens"] == 2500
    assert estimate["filtered_tokens"] == 1000

    # Savings reflect the difference between original and filtered tokens, at
    # the shared GPT-4o input rate (not a hardcoded literal -- see
    # tests/unit/test_llm_optimizer_cost_rate.py for the dedup regression).
    expected_savings = (2500 - 1000) * (GPT4O_INPUT_COST_PER_MILLION_TOKENS / 1_000_000)
    assert estimate["tokens_saved"] == 1500
    assert abs(estimate["cost_savings"] - expected_savings) < 1e-9

    # Input cost should be based on filtered tokens plus prompt tokens
    expected_input_tokens = 1000 + estimate["prompt_tokens"]
    expected_input_cost = (expected_input_tokens / 1_000_000) * GPT4O_INPUT_COST_PER_MILLION_TOKENS
    assert estimate["input_tokens"] == expected_input_tokens
    assert abs(estimate["input_cost"] - expected_input_cost) < 1e-9
