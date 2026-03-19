"""API tests for SIGMA A/B test compare endpoint (POST /api/sigma-ab-test/compare)."""

from unittest.mock import MagicMock, patch

import pytest

# Import router; routes package loads gpt4o_optimized_endpoint which creates async_db_manager.
# Patch at SQLAlchemy source so async_manager gets a mock engine when it imports create_async_engine.
with patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=MagicMock()):
    from src.web.routes.sigma_ab_test import router as _sigma_ab_test_router


MINIMAL_RULE = """
title: Test Rule
logsource:
  product: windows
  category: process_creation
detection:
  selection:
    Image: cmd.exe
  condition: selection
"""


@pytest.mark.api
class TestSigmaAbTestCompareAPI:
    """Test POST /api/sigma-ab-test/compare for pairwise rule comparison."""

    def test_compare_identical_rules_returns_success_and_similarity_one(self):
        """Identical rules return success with similarity 1.0."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(_sigma_ab_test_router)
        client = TestClient(app)

        response = client.post(
            "/api/sigma-ab-test/compare",
            json={"rule_a": MINIMAL_RULE, "rule_b": MINIMAL_RULE},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["similarity"] == 1.0
        assert data["novelty_label"] == "DUPLICATE"
        assert "atom_jaccard" in data
        assert "logic_shape_similarity" in data
        assert "shared_atoms" in data
        assert "added_atoms" in data
        assert "removed_atoms" in data

    def test_compare_accepts_markdown_wrapped_yaml(self):
        """Rule content wrapped in ```yaml ... ``` is extracted and parsed."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(_sigma_ab_test_router)
        client = TestClient(app)

        wrapped_a = "```yaml\n" + MINIMAL_RULE.strip() + "\n```"
        response = client.post(
            "/api/sigma-ab-test/compare",
            json={"rule_a": wrapped_a, "rule_b": MINIMAL_RULE},
        )

        assert response.status_code == 200
        assert response.json()["success"] is True
        assert response.json()["similarity"] == 1.0

    def test_compare_accepts_crlf_markdown_wrapped_yaml(self):
        """CRLF fenced YAML with trailing prose still extracts and parses."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(_sigma_ab_test_router)
        client = TestClient(app)

        wrapped_a = "```yaml\r\n" + MINIMAL_RULE.strip() + "\r\n```\r\nSome prose after the code fence."
        response = client.post(
            "/api/sigma-ab-test/compare",
            json={"rule_a": wrapped_a, "rule_b": MINIMAL_RULE},
        )

        assert response.status_code == 200
        assert response.json()["success"] is True
        assert response.json()["similarity"] == 1.0

    def test_compare_rule_b_fenced_yaml_with_brace_inside_field(self):
        """rule_b as fenced YAML containing ``}`` in a string must still parse (enrichment compare regression)."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(_sigma_ab_test_router)
        client = TestClient(app)

        rule_with_brace = """
title: Test Rule
logsource:
  product: windows
  category: process_creation
detection:
  selection:
    Image: cmd.exe
    CommandLine: '*foo}bar*'
  condition: selection
"""
        wrapped_b = "```yaml\n" + rule_with_brace.strip() + "\n```"
        response = client.post(
            "/api/sigma-ab-test/compare",
            json={"rule_a": MINIMAL_RULE, "rule_b": wrapped_b},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["similarity"] < 1.0

    def test_compare_accepts_prose_before_yaml(self):
        """Content with leading prose then title:/detection: is parsed from first YAML key."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(_sigma_ab_test_router)
        client = TestClient(app)

        with_prose = "Here is the enriched rule.\ntitle: Test Rule\nlogsource:\n  product: windows\n  category: process_creation\ndetection:\n  selection:\n    Image: cmd.exe\n  condition: selection"
        response = client.post(
            "/api/sigma-ab-test/compare",
            json={"rule_a": with_prose, "rule_b": MINIMAL_RULE},
        )

        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_compare_400_when_rule_empty(self):
        """Empty rule_a or rule_b returns 400."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(_sigma_ab_test_router)
        client = TestClient(app)

        r = client.post(
            "/api/sigma-ab-test/compare",
            json={"rule_a": "", "rule_b": MINIMAL_RULE},
        )
        assert r.status_code == 400
        detail = r.json().get("detail", "")
        assert isinstance(detail, str) and ("empty" in detail.lower() or "content" in detail.lower())

        r = client.post(
            "/api/sigma-ab-test/compare",
            json={"rule_a": MINIMAL_RULE, "rule_b": "   \n  "},
        )
        assert r.status_code == 400

    def test_compare_400_when_invalid_yaml(self):
        """Invalid YAML returns 400 with detail."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(_sigma_ab_test_router)
        client = TestClient(app)

        r = client.post(
            "/api/sigma-ab-test/compare",
            json={"rule_a": "title: [unclosed", "rule_b": MINIMAL_RULE},
        )
        assert r.status_code == 400
        assert "detail" in r.json()

    def test_compare_400_when_missing_detection(self):
        """Rule without detection section returns 400."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(_sigma_ab_test_router)
        client = TestClient(app)

        no_detection = """
title: Only Title
logsource:
  product: windows
  category: process_creation
"""
        r = client.post(
            "/api/sigma-ab-test/compare",
            json={"rule_a": no_detection, "rule_b": MINIMAL_RULE},
        )
        assert r.status_code == 400
        assert "detection" in r.json().get("detail", "").lower()

    def test_compare_different_rules_returns_lower_similarity(self):
        """Two different rules return success with similarity < 1 and NOVEL/SIMILAR label."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(_sigma_ab_test_router)
        client = TestClient(app)

        other_rule = """
title: Other Rule
logsource:
  product: windows
  category: process_creation
detection:
  selection:
    CommandLine: different.exe
  condition: selection
"""
        response = client.post(
            "/api/sigma-ab-test/compare",
            json={"rule_a": MINIMAL_RULE, "rule_b": other_rule},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["similarity"] < 1.0
        assert data["novelty_label"] in ("NOVEL", "SIMILAR", "DUPLICATE")
