"""API tests for SIGMA A/B test compare endpoint (POST /api/sigma-ab-test/compare)."""

from unittest.mock import MagicMock, patch

import pytest

# Import router; routes package loads llm_optimized_endpoint which creates async_db_manager.
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

    def test_compare_response_includes_canonical_contract_fields(self):
        """Phase 1: /compare emits the unified canonical contract via the shared
        serializer, including the top-level `containment` field, alongside the
        legacy keys existing frontends still read (additive)."""
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
        # canonical contract
        assert "containment" in data
        assert "similarity_engine" in data
        # legacy aliases still present (additive, removed in Phase 5)
        assert data["similarity_score"] == data["similarity"]
        assert "atom_jaccard" in data["similarity_breakdown"]
        # behavior unchanged
        assert data["similarity"] == 1.0
        assert data["novelty_label"] == "DUPLICATE"

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

    def test_compare_accepts_json_fenced_rule_b(self):
        """rule_b wrapped in ```json ... ``` is extracted and compared (LLM enrichment regression)."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(_sigma_ab_test_router)
        client = TestClient(app)

        wrapped_b = "```json\n" + MINIMAL_RULE.strip() + "\n```"
        response = client.post(
            "/api/sigma-ab-test/compare",
            json={"rule_a": MINIMAL_RULE, "rule_b": wrapped_b},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["similarity"] == 1.0

    def test_compare_accepts_json_fenced_rule_b_with_leading_prose(self):
        """rule_b with prose then ```json fence (exact LLM enrichment output pattern) parses correctly."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(_sigma_ab_test_router)
        client = TestClient(app)

        wrapped_b = "Here is the enriched rule:\n\n```json\n" + MINIMAL_RULE.strip() + "\n```"
        response = client.post(
            "/api/sigma-ab-test/compare",
            json={"rule_a": MINIMAL_RULE, "rule_b": wrapped_b},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["similarity"] == 1.0

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


# Repro pair for the filter-polarity bug (Todoist 6gqhWHxjgpWGHGP3):
# SigmaHQ marks these `related: type: similar`. Rule A (DB id 2002,
# 178e615d-...) = 11 positive atoms + 15 filter atoms via
# `not 1 of filter_main_* and not 1 of filter_optional_*`; Rule B (DB id
# 3672, 61065c72-...) = the same 11 positive atoms, filterless.
_REPRO_LOGSOURCE = {"product": "windows", "category": "process_creation"}
_REPRO_POSITIVE_SELECTIONS = {
    "selection_user": {"LogonId": "0x3e7", "User|contains": ["AUTHORI", "AUTORI"]},
    "selection_shell": [
        {"Image|endswith": ["\\powershell.exe", "\\powershell_ise.exe", "\\pwsh.exe", "\\cmd.exe"]},
        {"OriginalFileName": ["PowerShell.EXE", "powershell_ise.EXE", "pwsh.dll", "Cmd.Exe"]},
    ],
}
_REPRO_FILTER_SELECTIONS = {
    "filter_main_generic": {
        "ParentImage|contains": [
            ":\\Program Files (x86)\\",
            ":\\Program Files\\",
            ":\\ProgramData\\",
            ":\\Windows\\System32\\",
            ":\\Windows\\SysWOW64\\",
            ":\\Windows\\Temp\\",
            ":\\Windows\\WinSxS\\",
        ]
    },
    "filter_optional_asgard": {
        "CommandLine|contains": ':\\WINDOWS\\system32\\cmd.exe /c "',
        "CurrentDirectory|contains": ":\\WINDOWS\\Temp\\asgard2-agent\\",
    },
    "filter_main_parent_null": {"ParentImage": None},
    "filter_main_parent_empty": {"ParentImage": ["", "-"]},
    "filter_optional_manageengine": {
        "Image|endswith": "\\cmd.exe",
        "ParentImage|endswith": ":\\ManageEngine\\ADManager Plus\\pgsql\\bin\\postgres.exe",
    },
    "filter_optional_ibm_spectrumprotect": {
        "CommandLine|contains": ":\\IBM\\SpectrumProtect\\webserver\\scripts\\",
        "ParentImage|contains": ":\\IBM\\SpectrumProtect\\webserver\\scripts\\",
    },
}


def _repro_rule_a_yaml() -> str:
    import yaml as _yaml

    detection = {
        "condition": "all of selection_* and not 1 of filter_main_* and not 1 of filter_optional_*",
        **_REPRO_POSITIVE_SELECTIONS,
        **_REPRO_FILTER_SELECTIONS,
    }
    # sort_keys=False keeps `title:` first, matching real Sigma YAML layout
    # (the route's _extract_yaml_block truncates to the first marker it finds).
    return _yaml.safe_dump(
        {"title": "Repro Rule A (filtered)", "logsource": _REPRO_LOGSOURCE, "detection": detection},
        sort_keys=False,
    )


def _repro_rule_b_yaml() -> str:
    import yaml as _yaml

    detection = {"condition": "all of selection_*", **_REPRO_POSITIVE_SELECTIONS}
    return _yaml.safe_dump(
        {"title": "Repro Rule B (filterless variant)", "logsource": _REPRO_LOGSOURCE, "detection": detection},
        sort_keys=False,
    )


@pytest.mark.api
class TestSigmaAbTestCompareExtractorConvergence:
    """/compare converges onto the precompute (sigma_similarity package)
    extractor: filter atoms are polarity=negative, excluded from the positive
    jaccard, and counted exactly once via the filter penalty
    (Todoist 6gqhWHxjgpWGHGP3, slice of collapse task 6gmgRRC44VCwQW93)."""

    def _client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(_sigma_ab_test_router)
        return TestClient(app)

    def test_compare_filter_only_difference_is_not_novel(self):
        """The repro pair (identical positives, divergent filters) must score
        positive-atom jaccard 1.0 and classify as a near-duplicate -- not the
        false NOVEL the mis-polarized in-src extractor produced (42.3%)."""
        pytest.importorskip("sigma_similarity")
        client = self._client()

        response = client.post(
            "/api/sigma-ab-test/compare",
            json={"rule_a": _repro_rule_a_yaml(), "rule_b": _repro_rule_b_yaml()},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["similarity_engine"] == "deterministic"
        assert data["atom_jaccard"] == 1.0
        assert data["logic_shape_similarity"] == 1.0
        assert data["novelty_label"] == "DUPLICATE"
        assert data["novelty_label"] != "NOVEL"

    def test_compare_filter_difference_counted_once_via_penalty(self):
        """No double-count: filters never inflate the jaccard denominator;
        their entire effect is the filter penalty term
        (similarity = jaccard * containment - filter_penalty)."""
        pytest.importorskip("sigma_similarity")
        client = self._client()

        response = client.post(
            "/api/sigma-ab-test/compare",
            json={"rule_a": _repro_rule_a_yaml(), "rule_b": _repro_rule_b_yaml()},
        )

        data = response.json()
        # 15 extra filters / 11 positives, capped at 0.5
        assert data["filter_penalty"] == 0.5
        assert data["similarity"] == 0.5  # 1.0 * 1.0 - 0.5: penalty is the only mechanism
        assert data["weighted_before_penalties"] == 1.0
        # Positive-atom explainability is clean: no filter atoms leak in.
        assert data["added_atoms"] == []
        assert data["removed_atoms"] == []
        assert len(data["filter_differences"]) == 15

    def test_compare_deterministic_populates_containment(self):
        """The deterministic path lifts containment (overlap_ratio_a) into the
        canonical contract field, which the legacy /compare path never filled."""
        pytest.importorskip("sigma_similarity")
        client = self._client()

        response = client.post(
            "/api/sigma-ab-test/compare",
            json={"rule_a": MINIMAL_RULE, "rule_b": MINIMAL_RULE},
        )

        data = response.json()
        assert data["similarity_engine"] == "deterministic"
        assert data["containment"] == 1.0
        assert data["semantic_details"] is not None
        assert data["semantic_details"]["canonical_class"]
        # Contract behavior unchanged for identical rules.
        assert data["similarity"] == 1.0
        assert data["novelty_label"] == "DUPLICATE"

    def test_compare_unclassifiable_rule_falls_back_to_legacy_engine(self):
        """Rules the package cannot classify (no canonical class) still
        compare via the in-src fallback -- resilience is kept; only the
        extractor for classifiable rules changed."""
        client = self._client()

        unclassifiable = """
title: Unclassifiable Service Rule
logsource:
  product: windows
  service: someunknownservice123
detection:
  selection:
    SomeField: somevalue
  condition: selection
"""
        response = client.post(
            "/api/sigma-ab-test/compare",
            json={"rule_a": unclassifiable, "rule_b": unclassifiable},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["similarity_engine"] == "legacy"
        assert data["similarity"] == 1.0
        assert data["novelty_label"] == "DUPLICATE"
