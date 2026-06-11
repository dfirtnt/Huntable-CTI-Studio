"""Phase 3 of the sigma-similarity unification: single frontend ingress.

Validates that:
- similarity-display.js exports ONE constants object (SIMILARITY_THRESHOLDS)
  carrying the Phase-0 threshold table (legacy + deterministic + display bands)
- normalizeSimilarityData() absorbs every endpoint shaping (canonical
  serializer output, legacy aliases, raw persisted engine matches) into one
  identical normalized form -- the ticket's verify step
- novelty labels derive from the constants table, not inline literals
- the sigma similarity test page consumes the shared constants instead of its
  own hardcoded 0.90/0.75 color bands

Runs normalizeSimilarityData in Node.js via the component's CommonJS export
(same pattern as tests/config/test_parse_prompt_parts_regression.py).
Plan: docs/development/sigma-similarity-unification-plan-2026-06-05.md section 5.
"""

from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

COMPONENT_JS = Path("src/web/static/js/components/similarity-display.js")
SIGMA_SIMILARITY_TEST_HTML = Path("src/web/templates/sigma_similarity_test.html")


def _node_available() -> bool:
    try:
        result = subprocess.run(["node", "--version"], capture_output=True, timeout=5)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


requires_node = pytest.mark.skipif(not _node_available(), reason="node not available")


def _run_in_component(js_body: str) -> dict:
    """Require the real component in Node and run js_body; return parsed JSON.

    js_body must write its result via OUT(value).
    """
    component_path = json.dumps(str(COMPONENT_JS.resolve()))
    script = textwrap.dedent(f"""
        const m = require({component_path});
        const OUT = (v) => process.stdout.write(JSON.stringify(v));
        {js_body}
    """)
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=15)
    if result.returncode != 0:
        raise RuntimeError(f"Node execution failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}")
    return json.loads(result.stdout)


def _normalize(payload: dict) -> dict:
    return _run_in_component(f"OUT(m.normalizeSimilarityData({json.dumps(payload)}))")


# ---------------------------------------------------------------------------
# One engine match, expressed in every live surface's payload shaping.
# Values mirror the 2026-06-10 /compare deterministic repro (rules 2002/3672).
# ---------------------------------------------------------------------------
_SEMANTIC_DETAILS = {
    "canonical_class": "windows.process_creation",
    "jaccard": 1.0,
    "containment_factor": 1.0,
    "filter_penalty": 0.5,
    "surface_score_a": 16.0,
    "surface_score_b": 16.0,
    "overlap_ratio_a": 1.0,
    "overlap_ratio_b": 1.0,
    "reason_flags": [],
}
_CORE = {
    "similarity": 0.5,
    "atom_jaccard": 1.0,
    "logic_shape_similarity": 1.0,
    "novelty_label": "SIMILAR",
    "similarity_engine": "deterministic",
    "service_penalty": 0.0,
    "filter_penalty": 0.5,
    "weighted_before_penalties": 1.0,
    "shared_atoms": ["user|contains:authori"],
    "added_atoms": [],
    "removed_atoms": [],
    "filter_differences": ["process.parent_image|contains:/programdata/"],
    "semantic_details": _SEMANTIC_DETAILS,
}

# (a) Canonical serializer output (every route post-Phase-1): canonical keys
#     + containment lifted to top level + additive legacy aliases.
PAYLOAD_SERIALIZED = {
    **_CORE,
    "containment": 1.0,
    "novelty_score": 0.5,
    "similarity_score": 0.5,
    "similarity_breakdown": {"atom_jaccard": 1.0, "logic_shape_similarity": 1.0},
}

# (b) Raw persisted engine match (queue similarity_scores cache + workflow
#     execution records): canonical metric keys, NO top-level containment,
#     NO aliases -- containment must come from semantic_details.overlap_ratio_a.
PAYLOAD_RAW_MATCH = dict(_CORE)

# (c) Legacy-alias-only consumer shape (pre-serializer frontends): metrics only
#     under similarity_score / similarity_breakdown.
PAYLOAD_ALIAS_ONLY = {
    "similarity_score": 0.5,
    "similarity_breakdown": {"atom_jaccard": 1.0, "logic_shape_similarity": 1.0},
    "novelty_label": "SIMILAR",
    "similarity_engine": "deterministic",
    "service_penalty": 0.0,
    "filter_penalty": 0.5,
    "weighted_before_penalties": 1.0,
    "shared_atoms": ["user|contains:authori"],
    "added_atoms": [],
    "removed_atoms": [],
    "filter_differences": ["process.parent_image|contains:/programdata/"],
    "semantic_details": _SEMANTIC_DETAILS,
}

_COMPARED_FIELDS = [
    "similarity",
    "atom_jaccard",
    "logic_shape_similarity",
    "containment",
    "novelty_label",
    "novelty_score",
    "similarity_engine",
    "filter_penalty",
    "service_penalty",
    "weighted_before_penalties",
    "shared_atoms",
    "added_atoms",
    "removed_atoms",
    "filter_differences",
]


@requires_node
class TestSimilarityThresholdConstants:
    """The Phase-0 threshold table lives in ONE exported constants object."""

    def test_constants_object_exported_with_phase0_table(self):
        constants = _run_in_component("OUT(m.SIMILARITY_THRESHOLDS)")
        assert constants["legacy"]["duplicateAtomJaccard"] == 0.95
        assert constants["legacy"]["duplicateLogicShape"] == 0.95
        assert constants["legacy"]["similarAtomJaccard"] == 0.80
        assert constants["deterministic"]["duplicateSimilarity"] == 0.75
        assert constants["deterministic"]["similarSimilarity"] == 0.50
        assert constants["display"]["strongMatch"] == 0.90
        assert constants["display"]["moderateMatch"] == 0.75

    def test_metric_labels_exported(self):
        labels = _run_in_component("OUT(m.METRIC_LABELS)")
        assert labels["atom_jaccard"]
        assert labels["logic_shape_similarity"]
        assert labels["containment"]
        assert labels["filter_penalty"]


@requires_node
class TestNormalizeAcrossSurfacePayloads:
    """The ticket's verify step: each endpoint shaping of the same engine
    match must normalize to identical output."""

    def test_all_payload_shapes_normalize_identically(self):
        normalized = [
            _normalize(PAYLOAD_SERIALIZED),
            _normalize(PAYLOAD_RAW_MATCH),
            _normalize(PAYLOAD_ALIAS_ONLY),
        ]
        reference = {k: normalized[0][k] for k in _COMPARED_FIELDS}
        for i, n in enumerate(normalized[1:], start=1):
            assert {k: n[k] for k in _COMPARED_FIELDS} == reference, f"payload shape #{i} diverged"

    def test_containment_prefers_top_level_then_semantic_details(self):
        top = _normalize({"similarity": 0.4, "containment": 0.9, "semantic_details": {"overlap_ratio_a": 0.2}})
        assert top["containment"] == 0.9
        from_details = _normalize({"similarity": 0.4, "semantic_details": {"overlap_ratio_a": 0.2}})
        assert from_details["containment"] == 0.2
        absent = _normalize({"similarity": 0.4})
        assert absent["containment"] is None

    def test_containment_zero_is_kept_not_treated_as_absent(self):
        # 0.0 is a valid containment (disjoint atoms); it must NOT fall through
        # to semantic_details.overlap_ratio_a via a falsy check.
        n = _normalize({"similarity": 0.4, "containment": 0, "semantic_details": {"overlap_ratio_a": 0.7}})
        assert n["containment"] == 0
        from_details_zero = _normalize({"similarity": 0.4, "semantic_details": {"overlap_ratio_a": 0}})
        assert from_details_zero["containment"] == 0

    def test_similarity_score_alias_absorbed(self):
        n = _normalize({"similarity_score": 0.73})
        assert n["similarity"] == 0.73

    def test_canonical_similarity_wins_over_legacy_alias_when_both_present(self):
        # Canonical 'similarity' is authoritative; the legacy 'similarity_score'
        # alias is only a fallback when the canonical key is absent.
        n = _normalize({"similarity": 0.6, "similarity_score": 0.99})
        assert n["similarity"] == 0.6

    def test_similarity_zero_is_kept_not_overridden_by_alias(self):
        # similarity == 0 is a valid score (no behavioral overlap); a falsy
        # check must not let similarity_score override it.
        n = _normalize({"similarity": 0, "similarity_score": 0.99})
        assert n["similarity"] == 0

    def test_surface_scores_absorbed_from_semantic_details(self):
        n = _normalize({"similarity": 0.4, "semantic_details": {"surface_score_a": 16.0, "surface_score_b": 4.0}})
        assert n["surface_score_a"] == 16.0
        assert n["surface_score_b"] == 4.0


@requires_node
class TestNoveltyLabelsDeriveFromConstants:
    """Label derivation honors the Phase-0 table rows exactly."""

    @pytest.mark.parametrize(
        ("similarity", "expected"),
        [(0.75, "DUPLICATE"), (0.74, "SIMILAR"), (0.50, "SIMILAR"), (0.49, "NOVEL")],
    )
    def test_deterministic_row(self, similarity, expected):
        n = _normalize(
            {
                "similarity": similarity,
                "atom_jaccard": 0.3,
                "logic_shape_similarity": 0.65,
                "similarity_engine": "deterministic",
                "semantic_details": {"reason_flags": []},
            }
        )
        assert n["novelty_label"] == expected

    @pytest.mark.parametrize(
        ("jaccard", "logic", "expected"),
        [(0.96, 0.96, "DUPLICATE"), (0.96, 0.5, "SIMILAR"), (0.81, 0.2, "SIMILAR"), (0.5, 1.0, "NOVEL")],
    )
    def test_legacy_row_when_no_label_provided(self, jaccard, logic, expected):
        n = _normalize({"similarity": 0.6, "atom_jaccard": jaccard, "logic_shape_similarity": logic})
        assert n["novelty_label"] == expected


class TestNoHardcodedThresholdsOutsideConstants:
    """AC2: grep-level proof that threshold literals live only in the
    constants object (formula weights 0.70/0.30 and containment-bucket
    tooltip text are not thresholds and are exempt)."""

    def test_component_has_no_inline_threshold_comparisons(self):
        js = COMPONENT_JS.read_text(encoding="utf-8")
        for pattern in (
            "similarity >= 0.75",
            "similarity >= 0.50",
            "atomJaccard > 0.95",
            "logicShape > 0.95",
            "atomJaccard > 0.80",
        ):
            assert pattern not in js, f"inline threshold comparison still present: {pattern}"
        assert "SIMILARITY_THRESHOLDS" in js

    def test_sigma_similarity_test_page_uses_shared_constants(self):
        html = SIGMA_SIMILARITY_TEST_HTML.read_text(encoding="utf-8")
        assert "similarity-display.js" in html, "test page must load the shared component"
        assert "match.similarity >= 0.90" not in html
        assert "match.similarity >= 0.75" not in html
        assert "SIMILARITY_THRESHOLDS.display" in html
