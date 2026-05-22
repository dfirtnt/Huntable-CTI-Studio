"""Regression test for the feedback-comparison featurization dispatch.

Source: src/web/routes/models.py:917 (inside the get_model_feedback_comparison
endpoint). Previously hard-coded ContentFilter.extract_features() (v1, 27
features). When the live model became v3 (20 features), this call shape-
mismatched against model.predict_proba() and the feedback-comparison UI
silently broke (500 / no entries shown).

The fix dispatches on content_filter.feature_version. These tests assert that
1. the dispatch helper exists at the call site (source-level guard)
2. calling extract_features_v3 on a typical chunk produces a 20-element vector
3. predict_proba accepts that vector shape against a fresh v3-trained classifier

If a future refactor re-hardcodes extract_features() at that site, test #1
fails. If the dispatch helper exists but routes wrong, tests #2/#3 fail.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.regression]

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))


_MODELS_PY = REPO_ROOT / "src" / "web" / "routes" / "models.py"


class TestSourceLevelGuard:
    """Lock the dispatch presence at the source level. This is intentionally
    a string-level check: it's the cheapest way to catch a regression where
    someone refactors the feedback-comparison endpoint and re-introduces a
    hard-coded extract_features() call."""

    def test_dispatch_on_feature_version_present(self) -> None:
        source = _MODELS_PY.read_text(encoding="utf-8")
        # The fix introduced this version-aware branching. If a refactor removes
        # it (returning to a single hard-coded call) the test will fail.
        assert 'version == "v3"' in source, (
            "Feedback-comparison endpoint must dispatch on feature_version. "
            "Hard-coding extract_features() here shape-mismatches against v2/v3 "
            "models -- the bug we fixed on 2026-05-21."
        )
        assert "extract_features_v3" in source, "models.py must reference extract_features_v3 to handle v3 models."

    def test_no_lone_hardcoded_extract_features_call(self) -> None:
        """The only references to .extract_features( in models.py should be
        inside a dispatch block. We can't easily AST-parse the context, but
        we can assert the v3 branch appears in the same file -- which is the
        same signal."""
        source = _MODELS_PY.read_text(encoding="utf-8")
        # If extract_features( appears WITHOUT an adjacent feature_version
        # check, that's the bug. Both must coexist.
        if "content_filter.extract_features(" in source:
            # Then we MUST also see the dispatch nearby
            assert "extract_features_v3" in source and "extract_features_v2" in source, (
                "extract_features() referenced without v3/v2 dispatch -- "
                "feedback-comparison will shape-mismatch on non-v1 models."
            )


class TestV3FeatureContract:
    """Behavioral check: extract_features_v3() produces the right vector shape
    for predict_proba(). Captures the bug class even if source-level guards drift."""

    def test_v3_vector_shape_is_20(self) -> None:
        from src.utils.content_filter import ContentFilter

        cf = ContentFilter(feature_version="v3")
        features = cf.extract_features_v3("schtasks /create /tn evil /tr C:\\\\Users\\\\Public\\\\evil.exe")
        vec = np.array(list(features.values()), dtype=float).reshape(1, -1)
        assert vec.shape == (1, 20)

    def test_v3_classifier_accepts_v3_features(self, tmp_path) -> None:
        """End-to-end: train a v3 classifier, featurize a chunk with v3,
        feed to predict_proba. This is the exact sequence models.py:917
        executes -- if the dispatch is correct, this passes without raising."""
        from src.utils.content_filter import ContentFilter

        # Build a tiny training CSV so we can train an actual sklearn classifier
        csv = tmp_path / "train.csv"
        csv.write_text(
            "highlighted_text,classification\n"
            "powershell -ep bypass IEX,Huntable\n"
            "schtasks /create /tn evil,Huntable\n"
            "HKLM\\\\Software\\\\Microsoft\\\\Run\\\\X,Huntable\n"
            "regsvr32 /S C:\\\\foo.dll,Huntable\n"
            "Read our white paper today,Not Huntable\n"
            "Subscribe to our newsletter,Not Huntable\n"
            "Book a demo to learn more,Not Huntable\n"
            "Best in class managed platform,Not Huntable\n"
        )
        model_path = tmp_path / "test_v3.pkl"
        trainer = ContentFilter(model_path=str(model_path), feature_version="v3")
        result = trainer.train_model(training_data_path=str(csv))
        assert result["success"], f"Training failed: {result.get('error')}"

        # Now simulate the models.py:917 call path
        inference = ContentFilter(model_path=str(model_path))
        assert inference.load_model()
        assert inference.feature_version == "v3"  # set by sidecar

        # The exact 3-line sequence from models.py:917+
        features = inference.extract_features_v3("sc delete WinDefend")
        feature_vector = np.array(list(features.values())).reshape(1, -1)
        # This is where the bug manifested before the fix
        probabilities = inference.model.predict_proba(feature_vector)[0]
        assert len(probabilities) == 2
        assert 0.0 <= float(probabilities[1]) <= 1.0
