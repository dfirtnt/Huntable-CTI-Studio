"""Tests for chunk debug utility helpers."""

from src.web.routes.debug import calculate_filtered_costs


def test_calculate_filtered_costs_reuses_filtered_tokens():
    """Cost estimation should use filtered token length and never exceed original."""
    estimate = calculate_filtered_costs(original_length=10000, filtered_length=4000)

    # Token estimates use 4 chars/token heuristic
    assert estimate["original_tokens"] == 2500
    assert estimate["filtered_tokens"] == 1000

    # Savings reflect the difference between original and filtered tokens
    expected_savings = (2500 - 1000) * (5.0 / 1_000_000)
    assert estimate["tokens_saved"] == 1500
    assert abs(estimate["cost_savings"] - expected_savings) < 1e-9

    # Input cost should be based on filtered tokens plus prompt tokens
    expected_input_tokens = 1000 + estimate["prompt_tokens"]
    expected_input_cost = (expected_input_tokens / 1_000_000) * 5.0
    assert estimate["input_tokens"] == expected_input_tokens
    assert abs(estimate["input_cost"] - expected_input_cost) < 1e-9
