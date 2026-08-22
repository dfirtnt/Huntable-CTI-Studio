"""Tests for chunk debug utility helpers."""

import pytest

from src.utils.llm_optimizer import GPT4O_INPUT_COST_PER_MILLION_TOKENS
from src.web.routes.debug import calculate_filtered_costs

pytestmark = pytest.mark.unit


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
