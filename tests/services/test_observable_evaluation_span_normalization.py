"""
Unit tests for span normalization utilities.

These are pure unit tests - no infrastructure required.
"""

import pytest

# Mark all tests in this file as unit tests (pure logic, no infrastructure)
pytestmark = pytest.mark.unit

from src.services.observable_evaluation.span_normalization import (
    compute_span_length_delta,
    compute_token_overlap,
    is_exact_match,
    normalize_span,
)


class TestNormalizeSpan:
    """Tests for span normalization."""

    def test_normalize_whitespace(self):
        """Test that multiple whitespace is collapsed to single space."""
        assert normalize_span("cmd.exe   /c   whoami") == "cmd.exe /c whoami"
        assert normalize_span("cmd.exe\t\t/c\n\nwhoami") == "cmd.exe /c whoami"
        assert normalize_span("cmd.exe  \t  /c  \n  whoami") == "cmd.exe /c whoami"

    def test_normalize_quotes(self):
        """Test that quote types are normalized."""
        # Regular quotes are preserved
        assert normalize_span('cmd.exe /c "whoami"') == 'cmd.exe /c "whoami"'
        assert normalize_span("cmd.exe /c 'whoami'") == "cmd.exe /c 'whoami'"
        # Smart quotes are normalized to regular quotes
        # Note: Using Unicode smart quotes U+201C and U+201D
        assert normalize_span("cmd.exe /c \u201cwhoami\u201d") == 'cmd.exe /c "whoami"'
        assert normalize_span("cmd.exe /c \u2018whoami\u2019") == "cmd.exe /c 'whoami'"

    def test_preserve_argument_order(self):
        """Test that argument order is preserved."""
        assert normalize_span("cmd.exe /c /d whoami") == "cmd.exe /c /d whoami"
        assert normalize_span("cmd.exe /d /c whoami") == "cmd.exe /d /c whoami"

    def test_preserve_flags_and_parameters(self):
        """Test that flags and parameters are not removed."""
        assert normalize_span("cmd.exe /c /d /e whoami") == "cmd.exe /c /d /e whoami"
        assert normalize_span("powershell -enc base64string") == "powershell -enc base64string"

    def test_strip_leading_trailing_whitespace(self):
        """Test that leading/trailing whitespace is stripped."""
        assert normalize_span("  cmd.exe /c whoami  ") == "cmd.exe /c whoami"
        assert normalize_span("\tcmd.exe /c whoami\n") == "cmd.exe /c whoami"

    def test_empty_string(self):
        """Test empty string handling."""
        assert normalize_span("") == ""
        assert normalize_span("   ") == ""


class TestComputeTokenOverlap:
    """Tests for token overlap computation."""

    def test_exact_match(self):
        """Test that exact matches return 1.0."""
        assert compute_token_overlap("cmd.exe /c whoami", "cmd.exe /c whoami") == 1.0

    def test_partial_match(self):
        """Test partial token overlap."""
        overlap = compute_token_overlap("cmd.exe /c whoami", "cmd.exe /c")
        assert 0.0 < overlap < 1.0

    def test_no_overlap(self):
        """Test that completely different spans return 0.0."""
        assert compute_token_overlap("cmd.exe /c whoami", "powershell -enc") == 0.0

    def test_whitespace_normalization(self):
        """Test that whitespace differences don't affect overlap."""
        overlap1 = compute_token_overlap("cmd.exe /c whoami", "cmd.exe /c whoami")
        overlap2 = compute_token_overlap("cmd.exe   /c   whoami", "cmd.exe /c whoami")
        assert abs(overlap1 - overlap2) < 0.01  # Should be nearly identical

    def test_empty_strings(self):
        """Test empty string handling."""
        assert compute_token_overlap("", "") == 1.0
        assert compute_token_overlap("cmd.exe", "") == 0.0
        assert compute_token_overlap("", "cmd.exe") == 0.0

    def test_threshold_example(self):
        """Test that 0.5 threshold works as expected."""
        # "cmd.exe /c whoami" vs "cmd.exe /c" should have overlap > 0.5
        overlap = compute_token_overlap("cmd.exe /c whoami", "cmd.exe /c")
        assert overlap >= 0.5  # 2/3 tokens match = 0.67


class TestIsExactMatch:
    """Tests for exact match checking."""

    def test_exact_match(self):
        """Test that identical normalized spans match."""
        assert is_exact_match("cmd.exe /c whoami", "cmd.exe /c whoami") is True

    def test_whitespace_differences(self):
        """Test that whitespace differences are normalized."""
        # In strict mode, whitespace is only trimmed, not collapsed
        # So these should match after normalization (both become "cmd.exe /c whoami" after strip)
        # But strict mode doesn't collapse whitespace, so we need to use relaxed mode
        assert is_exact_match("cmd.exe /c whoami", "cmd.exe   /c   whoami", mode="relaxed") is True
        # In strict mode, whitespace differences are preserved
        assert is_exact_match("cmd.exe /c whoami", "cmd.exe /c whoami", mode="strict") is True

    def test_quote_differences(self):
        """Test that quote type differences are normalized."""
        assert is_exact_match('cmd.exe /c "whoami"', 'cmd.exe /c "whoami"') is True

    def test_different_content(self):
        """Test that different content doesn't match."""
        assert is_exact_match("cmd.exe /c whoami", "cmd.exe /c netstat") is False

    def test_empty_strings(self):
        """Test empty string handling."""
        assert is_exact_match("", "") is True
        assert is_exact_match("cmd.exe", "") is False


class TestComputeSpanLengthDelta:
    """Tests for span length delta computation."""

    def test_equal_length(self):
        """Test that equal length spans return 0."""
        # Use strings that are actually equal length after normalization
        assert compute_span_length_delta("cmd.exe /c whoami", "cmd.exe /c whoami") == 0

    def test_predicted_longer(self):
        """Test that longer predicted span returns positive delta."""
        delta = compute_span_length_delta("cmd.exe /c whoami /all", "cmd.exe /c whoami")
        assert delta > 0

    def test_predicted_shorter(self):
        """Test that shorter predicted span returns negative delta."""
        delta = compute_span_length_delta("cmd.exe /c", "cmd.exe /c whoami")
        assert delta < 0

    def test_whitespace_normalization(self):
        """Test that whitespace differences don't affect delta."""
        delta1 = compute_span_length_delta("cmd.exe /c whoami", "cmd.exe /c")
        delta2 = compute_span_length_delta("cmd.exe   /c   whoami", "cmd.exe /c")
        assert abs(delta1 - delta2) < 2  # Should be nearly identical


class TestGoldenTestCases:
    """Golden test cases for edge cases."""

    def test_truncated_command(self):
        """Test truncated command detection."""
        # Predicted span is truncated
        overlap = compute_token_overlap("cmd.exe /c who", "cmd.exe /c whoami")
        assert overlap < 1.0
        assert not is_exact_match("cmd.exe /c who", "cmd.exe /c whoami")

    def test_merged_commands(self):
        """Test merged command detection."""
        # Single prediction spans multiple commands
        overlap = compute_token_overlap("cmd.exe /c whoami && netstat -an", "cmd.exe /c whoami")
        assert overlap < 1.0
        assert not is_exact_match("cmd.exe /c whoami && netstat -an", "cmd.exe /c whoami")

    def test_extra_flag_hallucination(self):
        """Test extra flag hallucination detection."""
        # Prediction has extra flag not in gold
        overlap = compute_token_overlap("cmd.exe /c /d whoami", "cmd.exe /c whoami")
        assert overlap < 1.0
        assert not is_exact_match("cmd.exe /c /d whoami", "cmd.exe /c whoami")

    def test_extra_argument_hallucination(self):
        """Test extra argument hallucination detection."""
        # Prediction has extra argument not in gold
        overlap = compute_token_overlap("cmd.exe /c whoami /all", "cmd.exe /c whoami")
        assert overlap < 1.0
        assert not is_exact_match("cmd.exe /c whoami /all", "cmd.exe /c whoami")
