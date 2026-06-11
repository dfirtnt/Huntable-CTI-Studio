"""API tests for SIGMA A/B test compare endpoint (POST /api/sigma-ab-test/compare)."""

from unittest.mock import MagicMock, patch

import pytest

# Import router; routes package loads llm_optimized_endpoint which creates async_db_manager.
# Patch at SQLAlchemy source so async_manager gets a mock engine when it imports create_async_engine.
with patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=MagicMock()):
    from src.web.routes.sigma_ab_test import _extract_yaml_block
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
        """/compare emits the unified canonical contract via the shared
        serializer (top-level `containment` etc.). Phase 5: canonical-only --
        the Phase-1 legacy aliases are retired."""
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
        # Phase 5: legacy aliases retired -- responses are canonical-only
        assert "similarity_score" not in data
        assert "similarity_breakdown" not in data
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

    def test_compare_accepts_yaml_with_title_not_first(self):
        """YAML whose keys are alphabetically sorted (detection before title --
        the default yaml.safe_dump layout for LLM-shaped output) must keep its
        detection section: marker scanning is text-order, not priority-order."""
        import yaml as _yaml
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(_sigma_ab_test_router)
        client = TestClient(app)

        # sort_keys=True puts detection: first and title: last; the old
        # priority-order scan truncated everything before title:.
        sorted_dump = _yaml.safe_dump(_yaml.safe_load(MINIMAL_RULE), sort_keys=True)
        assert sorted_dump.startswith("detection:")  # fixture sanity

        response = client.post(
            "/api/sigma-ab-test/compare",
            json={"rule_a": sorted_dump, "rule_b": MINIMAL_RULE},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["similarity"] == 1.0

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

    def test_compare_uses_single_match_classifier_for_both_engines(self):
        """Phase 3 fold: both /compare paths classify via
        classify_match_novelty (the Phase-2 single source of truth);
        the weighted-similarity pairwise classifier is retired."""
        import inspect

        from src.web.routes import sigma_ab_test as route_module

        source = inspect.getsource(route_module)
        assert "_classify_pairwise_novelty" not in source, (
            "weighted pairwise classifier must be retired in favor of classify_match_novelty"
        )
        assert "classify_match_novelty" in source

    def test_compare_legacy_fallback_label_conforms_to_match_classifier_table(self):
        """The fallback path's verdict must follow the legacy threshold row
        (atom_jaccard/logic_shape), recomputed here from the response itself
        so the pin holds for any pair."""
        client = self._client()

        rule_a = """
title: Unclassifiable A
logsource:
  product: windows
  service: someunknownservice123
detection:
  selection:
    FieldOne: alpha
    FieldTwo: beta
    FieldThree: gamma
    FieldFour: delta
    FieldFive: epsilon
  condition: selection
"""
        rule_b = """
title: Unclassifiable B
logsource:
  product: windows
  service: someunknownservice123
detection:
  selection_one:
    FieldOne: alpha
    FieldTwo: beta
    FieldThree: gamma
    FieldFour: delta
    FieldFive: epsilon
  selection_two:
    FieldSix: zeta
  condition: selection_one or selection_two
"""
        response = client.post(
            "/api/sigma-ab-test/compare",
            json={"rule_a": rule_a, "rule_b": rule_b},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["similarity_engine"] == "legacy"

        atom_jaccard = data["atom_jaccard"]
        logic_shape = data["logic_shape_similarity"]
        logic_shape = 1.0 if logic_shape is None else logic_shape
        if atom_jaccard > 0.95 and logic_shape > 0.95:
            expected = "DUPLICATE"
        elif atom_jaccard > 0.80:
            expected = "SIMILAR"
        else:
            expected = "NOVEL"
        assert data["novelty_label"] == expected, (
            f"fallback label {data['novelty_label']} does not follow the legacy "
            f"table for jaccard={atom_jaccard}, logic_shape={logic_shape}"
        )


@pytest.mark.api
class TestExtractYamlBlockMarkerScanning:
    """_extract_yaml_block must anchor markers to line starts (commit d943834a).

    Two failure modes the line-anchored, text-order scan fixes:
    - sorted-keys YAML (detection before title) -- covered by the API test above.
    - mid-word substring matches -- a marker name embedded in a longer word on a
      preceding line (e.g. 'subtitle:' contains 'title:') must NOT be mistaken for
      the marker. The old priority-order bare find('title:') matched inside
      'subtitle:' and truncated the rule at the wrong offset; this is that
      regression with no prior coverage.
    """

    def test_midword_marker_substring_is_not_matched(self):
        # 'subtitle:' contains the substring 'title:'; the real key is on the
        # next line. Line-anchored scan must skip the mid-word match.
        text = "subtitle: not the real title\ntitle: Real Rule\ndetection:\n  selection:\n    Image: cmd.exe\n  condition: selection"
        result = _extract_yaml_block(text)
        assert result.startswith("title: Real Rule"), result

    def test_leading_prose_with_embedded_marker_word(self):
        # 'invalid:' contains 'id:'; with no clean earlier marker the scan must
        # still anchor to the real line-start 'title:'.
        text = "The draft is invalid: see notes\ntitle: Real\ndetection:\n  selection:\n    Image: cmd.exe\n  condition: selection"
        result = _extract_yaml_block(text)
        assert result.startswith("title: Real"), result

    def test_first_line_start_marker_wins_in_text_order(self):
        # logsource appears on an earlier line than title -> text-order scan
        # returns from logsource (the earliest line-anchored marker), preserving
        # the whole block, not from the priority-first 'title'.
        text = "logsource:\n  product: windows\n  category: process_creation\ntitle: Ordered Oddly\ndetection:\n  selection:\n    Image: cmd.exe\n  condition: selection"
        result = _extract_yaml_block(text)
        assert result.startswith("logsource:"), result
        assert "title: Ordered Oddly" in result
        assert "detection:" in result
