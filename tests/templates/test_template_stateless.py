"""Template for stateless tests (no containers required).

Stateless tests:
- Pure frontend tests (Jinja templates + Tailwind + vanilla JS behavior)
- Backend unit tests without DB connections
- Similarity search with in-memory fixtures
- YAML parsing, linting, round-trip logic
- Utility functions, selectors, scoring logic
"""

import pytest
from pathlib import Path

# Example: YAML validation test
def test_yaml_validation():
    """Test YAML validation logic."""
    # Load fixture
    fixture_path = Path("tests/fixtures/sigma/valid_rule.yaml")
    # ... test logic ...
    pass

# Example: Similarity search with fixtures
def test_similarity_deterministic():
    """Test similarity search deterministic ordering."""
    # Load golden file
    golden_path = Path("tests/fixtures/similarity/expected_ordering.json")
    # ... test logic ...
    pass
