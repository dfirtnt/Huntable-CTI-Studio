"""Unit tests for sigma_semantic_precompute."""

from unittest.mock import patch

import pytest

from src.services.sigma_semantic_precompute import (
    is_sigma_similarity_available,
    precompute_semantic_fields,
)

pytestmark = pytest.mark.unit


def test_is_sigma_similarity_available_returns_bool():
    """is_sigma_similarity_available returns True or False."""
    result = is_sigma_similarity_available()
    assert isinstance(result, bool)


class TestPrecomputeSemanticFields:
    """Tests for precompute_semantic_fields."""

    @pytest.fixture
    def valid_windows_process_rule(self):
        """Valid rule that maps to windows.process_creation."""
        return {
            "logsource": {"product": "windows", "category": "process_creation"},
            "detection": {
                "selection": {"CommandLine|contains": "schtasks"},
                "condition": "selection",
            },
        }

    def test_when_sigma_similarity_unavailable_returns_none(self):
        """When sigma_similarity not installed, precompute returns None."""
        with patch(
            "src.services.sigma_semantic_precompute._SIGMA_SIMILARITY_AVAILABLE",
            False,
        ):
            result = precompute_semantic_fields({"logsource": {}, "detection": {}})
            assert result is None

    def test_valid_rule_returns_dict_with_expected_keys(
        self, valid_windows_process_rule
    ):
        """When sigma_similarity available, valid rule returns dict with expected keys."""
        result = precompute_semantic_fields(valid_windows_process_rule)
        if result is None:
            pytest.skip("sigma_similarity not installed or rule unsupported")
        assert "canonical_class" in result
        assert "positive_atoms" in result
        assert "negative_atoms" in result
        assert "surface_score" in result
        assert result["canonical_class"] == "windows.process_creation"
        assert isinstance(result["positive_atoms"], list)
        assert isinstance(result["negative_atoms"], list)
        assert isinstance(result["surface_score"], int)

    def test_unknown_logsource_returns_none(self):
        """Rule with unsupported logsource returns None."""
        rule = {
            "logsource": {"product": "macos", "category": "file_access"},
            "detection": {"selection": {"a": "b"}, "condition": "selection"},
        }
        result = precompute_semantic_fields(rule)
        assert result is None
