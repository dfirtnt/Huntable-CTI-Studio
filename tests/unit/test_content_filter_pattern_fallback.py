"""Tests for the _pattern_based_classification degraded-mode fallback.

Covers the two paths in predict_huntability that reach the fallback:
1. self.model is None (model not loaded / sklearn unavailable)
2. ML prediction raises an exception (corrupt model, feature mismatch, etc.)
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytestmark = [pytest.mark.unit]

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))


@pytest.fixture()
def cf_no_model():
    """ContentFilter with model explicitly set to None (degraded mode)."""
    from src.utils.content_filter import ContentFilter

    cf = ContentFilter()
    cf.model = None
    return cf


class TestPatternBasedFallback:
    def test_no_model_returns_result(self, cf_no_model):
        """predict_huntability returns a valid (bool, float) when model is None."""
        is_huntable, confidence = cf_no_model.predict_huntability(
            "powershell -ep bypass invoke-mimikatz lateral movement"
        )
        assert isinstance(is_huntable, bool)
        assert 0.0 <= confidence <= 1.0

    def test_no_model_huntable_content(self, cf_no_model):
        """High-signal threat-hunting text is classified as huntable in fallback."""
        is_huntable, confidence = cf_no_model.predict_huntability(
            "The attacker used mimikatz to dump LSASS credentials and then "
            "executed invoke-mimikatz via PowerShell with bypass execution policy."
        )
        assert is_huntable is True

    def test_no_model_non_huntable_content(self, cf_no_model):
        """Low-signal text is classified as not huntable in fallback."""
        is_huntable, confidence = cf_no_model.predict_huntability(
            "This is a general news article about the weather forecast for tomorrow."
        )
        assert is_huntable is False

    def test_exception_path_falls_back(self):
        """When model.predict raises, predict_huntability falls back to pattern classification."""
        from src.utils.content_filter import ContentFilter

        cf = ContentFilter()
        cf.model = MagicMock()
        cf.model.predict.side_effect = RuntimeError("corrupt model")

        is_huntable, confidence = cf.predict_huntability(
            "powershell -ep bypass invoke-expression download cradle"
        )
        assert isinstance(is_huntable, bool)
        assert 0.0 <= confidence <= 1.0

    def test_pattern_classification_direct(self, cf_no_model):
        """_pattern_based_classification returns (bool, float) directly."""
        result = cf_no_model._pattern_based_classification(
            "lateral movement via pass-the-hash with mimikatz"
        )
        assert len(result) == 2
        is_huntable, confidence = result
        assert isinstance(is_huntable, bool)
        assert 0.0 <= confidence <= 1.0

    def test_confidence_bounded(self, cf_no_model):
        """Confidence is always in [0, 1] regardless of hunt score input."""
        _, confidence = cf_no_model._pattern_based_classification(
            "some text", hunt_score=150.0
        )
        assert 0.0 <= confidence <= 1.0
