"""Tests for SIGMA similarity search deterministic ordering.

These are unit tests using golden files - no real infrastructure required.
"""

import json
from pathlib import Path

import pytest

# Mark all tests in this file as unit tests (use golden files, no real infrastructure)
pytestmark = pytest.mark.unit


class TestSigmaSimilarityDeterministic:
    """Test deterministic ordering of similarity search results."""

    @pytest.fixture
    def golden_file_path(self):
        """Path to golden file with expected ordering."""
        return Path("tests/fixtures/similarity/expected_ordering.json")

    @pytest.fixture
    def input_queries_path(self):
        """Path to input queries."""
        return Path("tests/fixtures/similarity/input_queries.json")

    @pytest.fixture
    def load_golden_file(self, golden_file_path):
        """Load golden file with expected ordering."""
        if not golden_file_path.exists():
            pytest.skip(f"Golden file not found: {golden_file_path}")

        with open(golden_file_path) as f:
            return json.load(f)

    @pytest.fixture
    def load_input_queries(self, input_queries_path):
        """Load input queries."""
        if not input_queries_path.exists():
            pytest.skip(f"Input queries file not found: {input_queries_path}")

        with open(input_queries_path) as f:
            return json.load(f)

    def test_golden_file_structure(self, load_golden_file):
        """Test that golden file has required structure."""
        golden = load_golden_file

        assert "version" in golden
        assert "created_date" in golden
        assert "model_version" in golden
        assert "queries" in golden

        # Check query structure
        for _query_id, query_data in golden["queries"].items():
            assert "rule_ids" in query_data
            assert "score_ranges" in query_data
            assert "relative_order" in query_data

    def test_golden_file_versioning(self, load_golden_file):
        """Test that golden file versioning is tracked."""
        golden = load_golden_file

        # Version should be semantic version
        version = golden["version"]
        assert isinstance(version, str)
        assert "." in version  # Basic version format check

        # Created date should be ISO format
        created_date = golden["created_date"]
        assert isinstance(created_date, str)
        # Could add more specific date format validation if needed
