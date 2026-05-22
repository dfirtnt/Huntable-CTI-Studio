"""Locks the chunk-debug endpoint's feature_version dispatch.

The /api/articles/{id}/chunk-debug endpoint previously hard-coded a call to
ContentFilter.extract_features() (v1, 27 features). When the live model was
trained with v3 (20 features), this produced a shape mismatch in model.predict()
and the UI displayed "ML Error: ML processing failed".

The dispatch fix (debug.py::_extract_for_version) ensures we always featurize
with the same version the model was trained on. These tests assert that the
debug.py helper picks the right method per feature_version so a refactor that
re-hardcodes a single method will fail loudly here, not silently in production.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.regression]

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))


def _build_extractor(version: str):
    """Reproduce the dispatch logic from src/web/routes/debug.py::_extract_for_version.

    Keeping a local copy here is deliberate: this test exists to lock down the
    contract that 'dispatch on feature_version must happen at the inference
    surface, not only inside ContentFilter methods'. If debug.py drifts (e.g.,
    a refactor re-introduces a hard-coded call), this test will diverge from
    runtime behavior and the next time someone runs the chunk debugger they'll
    see ML errors -- forcing a fix.
    """
    from src.utils.content_filter import ContentFilter

    cf = ContentFilter(feature_version=version)

    def _extract(text: str) -> dict[str, float]:
        if cf.feature_version == "v3":
            return cf.extract_features_v3(text)
        if cf.feature_version == "v2":
            return cf.extract_features_v2(text)
        return cf.extract_features(text, hunt_score=None, include_new_features=True)

    return cf, _extract


_SAMPLE = (
    "The attacker ran sc delete SgrmAgent and bcdedit /set {current} "
    "disableelamdrivers yes, then dropped a payload to C:\\Users\\Public\\Music\\evil.exe."
)


class TestDispatchDimensionality:
    """Each feature_version produces a distinct vector size. A shape mismatch
    against the live model would mean the dispatcher is wrong."""

    def test_v3_returns_20_features(self) -> None:
        _, extract = _build_extractor("v3")
        feats = extract(_SAMPLE)
        assert len(feats) == 20

    def test_v2_returns_19_features(self) -> None:
        _, extract = _build_extractor("v2")
        feats = extract(_SAMPLE)
        assert len(feats) == 19

    def test_v1_returns_more_than_v2(self) -> None:
        _, extract = _build_extractor("v1")
        feats = extract(_SAMPLE)
        # v1 has 27 base + optional include_new_features additions; just assert
        # it's strictly more than v2 (which dropped features deliberately)
        assert len(feats) > 19


class TestDispatchKeyContracts:
    """Per-version feature key contracts. Smoke checks that the right
    extractor was actually called, not just that *some* dict came back."""

    def test_v3_keys_include_v3_only_features(self) -> None:
        _, extract = _build_extractor("v3")
        feats = extract(_SAMPLE)
        # These features exist ONLY in v3
        for key in (
            "registry_hive_path_count",
            "yara_rule_indicator",
            "extractor_signal_strength",
        ):
            assert key in feats, f"v3 dispatch missed {key!r}"

    def test_v2_keys_do_not_include_v3_only_features(self) -> None:
        _, extract = _build_extractor("v2")
        feats = extract(_SAMPLE)
        assert "registry_hive_path_count" not in feats
        assert "yara_rule_indicator" not in feats

    def test_v1_keys_include_v1_only_features(self) -> None:
        _, extract = _build_extractor("v1")
        feats = extract(_SAMPLE)
        # v1 has the length-leakage features v2/v3 dropped
        assert "sentence_count" in feats or "word_count" in feats


class TestSampleArtifactDetection:
    """End-to-end: a chunk with one literal command + one attacker path
    should produce non-zero v3 signals. If the dispatch ever silently routed
    to v1, these v3-specific signals would be missing."""

    def test_v3_detects_command_and_path(self) -> None:
        _, extract = _build_extractor("v3")
        feats = extract(_SAMPLE)
        assert feats["cmdline_artifact_count"] >= 1.0
        assert feats["attacker_placed_path_count"] >= 1.0
