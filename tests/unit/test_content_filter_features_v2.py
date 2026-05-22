"""Contract tests for ContentFilter.extract_features_v2().

v2 is the cleaned-up feature extractor designed alongside the seed corpus
rebuild.  These tests lock the contract so we don't accidentally regress to
v1's problems (train/serve skew, length leakage, over-narrow vocabularies).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.regression]

# Add src/ so the bare 'utils.content_filter' import works
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))


@pytest.fixture(scope="module")
def cf_v2():
    from src.utils.content_filter import ContentFilter

    return ContentFilter(feature_version="v2")


@pytest.fixture(scope="module")
def cf_v1():
    from src.utils.content_filter import ContentFilter

    return ContentFilter(feature_version="v1")


_HUNTABLE_SAMPLE = (
    "The threat actor deploys a Cobalt Strike beacon via DLL sideloading. "
    "Persistence is established by creating a scheduled task that runs "
    "powershell.exe with a base64-encoded payload. Lateral movement uses "
    "mimikatz against LSASS. CVE-2023-12345 is referenced."
)

_MARKETING_SAMPLE = (
    "Our managed security platform empowers your team to streamline threat "
    "detection. Book a demo today to see how our solution can transform "
    "your operations. Read our white paper and sign up for the newsletter."
)


class TestFeatureCount:
    def test_v2_has_19_features(self, cf_v2) -> None:
        feats = cf_v2.extract_features_v2(_HUNTABLE_SAMPLE)
        assert len(feats) == 19, f"v2 contract: 19 features. Got {len(feats)}: {sorted(feats.keys())}"

    def test_v2_features_strictly_fewer_than_v1(self, cf_v1, cf_v2) -> None:
        v1_feats = cf_v1.extract_features(_HUNTABLE_SAMPLE)
        v2_feats = cf_v2.extract_features_v2(_HUNTABLE_SAMPLE)
        assert len(v2_feats) < len(v1_feats), "v2 must be smaller — the whole point was cleanup"


class TestNoTrainServeSkew:
    """v2 must not accept hunt_score (the train/serve skew bug from v1)."""

    def test_v2_signature_takes_only_text(self, cf_v2) -> None:
        import inspect

        sig = inspect.signature(cf_v2.extract_features_v2)
        params = [p for p in sig.parameters if p != "self"]
        assert params == ["text"], (
            f"v2 must take exactly (text,) — found {params}. Optional parameters create train/serve skew risk."
        )


class TestDroppedFeatures:
    """These v1 features must NOT appear in v2 output."""

    @pytest.mark.parametrize(
        "forbidden",
        [
            "char_count",  # length leakage
            "word_count",  # length leakage
            "has_urls",  # redundant with url_count > 0
            "has_file_paths",  # redundant with file_path_count > 0
            "has_commands",  # fragile literal match
            "hunt_score",  # train/serve skew
            "hunt_score_high",  # redundant bin
            "hunt_score_medium",  # redundant bin
            "hunt_score_low",  # redundant bin
            "acknowledgment_count",  # matched "contact" — false positive on legit CTI
            "huntable_pattern_count",  # deprecated, replaced by perfect+other split
            "huntable_pattern_ratio",  # deprecated, replaced by perfect+other split
        ],
    )
    def test_dropped_feature_absent(self, cf_v2, forbidden: str) -> None:
        feats = cf_v2.extract_features_v2(_HUNTABLE_SAMPLE)
        assert forbidden not in feats, f"v2 must not include '{forbidden}' — it was deliberately dropped"


class TestPromotedFeatures:
    """These features were gated behind v1.include_new_features; v2 promotes them."""

    @pytest.mark.parametrize(
        "required",
        [
            "perfect_pattern_count",
            "perfect_pattern_ratio",
            "other_huntable_pattern_count",
            "other_huntable_pattern_ratio",
            "not_huntable_pattern_count",
            "not_huntable_pattern_ratio",
            "technical_term_count",
            "technical_term_ratio",
            "marketing_term_count",
            "marketing_term_ratio",
        ],
    )
    def test_promoted_feature_present(self, cf_v2, required: str) -> None:
        feats = cf_v2.extract_features_v2(_HUNTABLE_SAMPLE)
        assert required in feats


class TestExpandedVocabularies:
    def test_technical_vocab_has_at_least_40_terms(self, cf_v2) -> None:
        from src.utils.content_filter import ContentFilter

        assert len(ContentFilter.V2_TECHNICAL_TERMS) >= 40, (
            "v1's 8 hardcoded terms were too narrow.  v2 vocab must be substantially broader."
        )

    def test_marketing_vocab_has_at_least_20_terms(self, cf_v2) -> None:
        from src.utils.content_filter import ContentFilter

        assert len(ContentFilter.V2_MARKETING_TERMS) >= 20, (
            "v1's 5 hardcoded phrases were too narrow.  v2 vocab must be substantially broader."
        )


class TestDiscrimination:
    """Sanity check: v2 actually separates obviously-huntable from obviously-marketing."""

    def test_huntable_chunk_has_strong_technical_signal(self, cf_v2) -> None:
        feats = cf_v2.extract_features_v2(_HUNTABLE_SAMPLE)
        assert feats["technical_term_count"] >= 5
        assert feats["marketing_term_count"] == 0

    def test_marketing_chunk_has_strong_marketing_signal(self, cf_v2) -> None:
        feats = cf_v2.extract_features_v2(_MARKETING_SAMPLE)
        assert feats["marketing_term_count"] >= 5
        assert feats["technical_term_count"] == 0


class TestRegexFixes:
    """The two regex bugs we found in v1."""

    def test_url_path_does_not_double_count_as_file_path(self, cf_v2) -> None:
        """v1 bug: https://example.com/foo/bar incremented BOTH url_count and file_path_count."""
        text = "See documentation at https://example.com/docs/api/reference for details."
        feats = cf_v2.extract_features_v2(text)
        assert feats["url_count"] == 1
        assert feats["file_path_count"] == 0, (
            "URL paths must not register as file paths — that was a v1 multicollinearity bug"
        )

    def test_process_count_matches_arbitrary_exe(self, cf_v2) -> None:
        """v1 bug: process_count was hardcoded to 4 executables incl. ws_tomcatservice.exe."""
        text = "The attacker dropped svchost.exe and rundll32.exe to disk."
        feats = cf_v2.extract_features_v2(text)
        assert feats["process_count"] >= 2, "v2 process_count must match any .exe — not a hardcoded list"


class TestPipelineIntegration:
    """Wiring contracts: train_model and predict_huntability must honour feature_version."""

    def test_feature_version_default_is_v3(self) -> None:
        """Default flipped from v1 to v3 on 2026-05-21 alongside the v3 feature rollout.

        The live model is now v3-featured; defaulting inference paths to v1
        produced a feature-shape mismatch ("ML processing failed" in chunk
        debugger) and silent fallback to pattern-based classification. The
        default must match the live model.
        """
        from src.utils.content_filter import ContentFilter

        cf = ContentFilter()
        assert cf.feature_version == "v3"

    def test_feature_version_constructor_arg(self) -> None:
        from src.utils.content_filter import ContentFilter

        cf = ContentFilter(feature_version="v2")
        assert cf.feature_version == "v2"

    def test_train_model_branches_on_feature_version(self) -> None:
        """Sanity: source code must branch in train_model on self.feature_version."""
        path = REPO_ROOT / "src" / "utils" / "content_filter.py"
        source = path.read_text()
        assert 'self.feature_version == "v2"' in source, (
            "train_model and predict_huntability must check self.feature_version"
        )
        assert "extract_features_v2" in source, "v2 extractor must be reachable from the pipeline"
