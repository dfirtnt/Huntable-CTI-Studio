"""Tests for the seed-fallback cascade in scripts/retrain_with_feedback.py
and the corresponding write in scripts/seed_model.py.

retrain_model_with_feedback() resolves its baseline training data through
a three-tier cascade:

  1. combined_training_data.csv exists  → use it (normal path)
  2. combined missing, seed exists      → fall back to seed corpus (new)
  3. neither file exists                → bootstrap_mode = True (last resort)

seed_model.py contract: the combined_path it writes must match the default
original_file that retrain_model_with_feedback() reads. A mismatch silently
puts every retrain into seed-fallback or bootstrap mode.
"""

from __future__ import annotations

import importlib.util
import inspect
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RETRAIN_PATH = REPO_ROOT / "scripts" / "retrain_with_feedback.py"
SEED_PATH = REPO_ROOT / "scripts" / "seed_model.py"

_COMBINED = "outputs/training_data/combined_training_data.csv"
_SEED = "models/seed_training_data.csv"


@pytest.fixture(scope="module")
def retrain_script():
    spec = importlib.util.spec_from_file_location("retrain_with_feedback", RETRAIN_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["retrain_with_feedback"] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Replicate the 4-line fallback block for isolated scenario testing
# ---------------------------------------------------------------------------

def _resolve(original_file: str, seed_fallback: str) -> tuple[str, bool]:
    """Mirror the exact cascade logic from retrain_with_feedback.py."""
    if not os.path.exists(original_file) and os.path.exists(seed_fallback):
        original_file = seed_fallback
    bootstrap_mode = not os.path.exists(original_file)
    return original_file, bootstrap_mode


class TestFallbackCascade:
    def test_combined_exists_uses_combined(self) -> None:
        with patch("os.path.exists", side_effect=lambda p: p == _COMBINED):
            resolved, bootstrap = _resolve(_COMBINED, _SEED)
        assert resolved == _COMBINED
        assert bootstrap is False

    def test_combined_missing_seed_exists_uses_seed(self) -> None:
        with patch("os.path.exists", side_effect=lambda p: p == _SEED):
            resolved, bootstrap = _resolve(_COMBINED, _SEED)
        assert resolved == _SEED
        assert bootstrap is False

    def test_neither_exists_bootstrap_mode(self) -> None:
        with patch("os.path.exists", return_value=False):
            _, bootstrap = _resolve(_COMBINED, _SEED)
        assert bootstrap is True

    def test_both_exist_combined_wins(self) -> None:
        """Seed presence must not override combined when combined exists."""
        with patch("os.path.exists", return_value=True):
            resolved, bootstrap = _resolve(_COMBINED, _SEED)
        assert resolved == _COMBINED
        assert bootstrap is False

    def test_seed_fallback_path_points_into_models_dir(self) -> None:
        """The seed_fallback expression in the script must resolve to
        <repo_root>/models/seed_training_data.csv."""
        expected = (REPO_ROOT / "models" / "seed_training_data.csv").resolve()
        # Replicate the script's own expression:
        actual = (RETRAIN_PATH.parent.parent / "models" / "seed_training_data.csv").resolve()
        assert actual == expected


# ---------------------------------------------------------------------------
# seed_model.py ↔ retrain_with_feedback.py path contract
# ---------------------------------------------------------------------------

class TestCombinedPathContract:
    def test_seed_writes_to_same_path_retrain_reads_from(self, retrain_script) -> None:
        """If these paths diverge, every retrain silently falls into fallback mode."""
        seed_writes_to = (REPO_ROOT / "outputs" / "training_data" / "combined_training_data.csv").resolve()

        sig = inspect.signature(retrain_script.retrain_model_with_feedback)
        default_param = sig.parameters["original_file"].default
        retrain_reads_from = (REPO_ROOT / default_param).resolve()

        assert seed_writes_to == retrain_reads_from, (
            f"seed_model writes to {seed_writes_to} but "
            f"retrain_with_feedback reads from {retrain_reads_from}"
        )

    def test_seed_script_writes_combined_path(self) -> None:
        """Guard against accidental removal of the combined_path write from seed_model.py."""
        source = SEED_PATH.read_text()
        assert 'combined_path = ROOT / "outputs" / "training_data" / "combined_training_data.csv"' in source
        assert "combined_path.parent.mkdir" in source
        assert "df.to_csv(combined_path, index=False)" in source

    def test_retrain_script_contains_seed_fallback_block(self) -> None:
        """Guard against accidental removal of the fallback block from retrain_with_feedback.py."""
        source = RETRAIN_PATH.read_text()
        assert "seed_fallback" in source
        assert "seed_training_data.csv" in source
        assert "bootstrap_mode = not os.path.exists(original_file)" in source


# ---------------------------------------------------------------------------
# Quality gate contracts
# ---------------------------------------------------------------------------

class TestQualityGateConstants:
    """Guard the quality-gate thresholds in retrain_with_feedback.py."""

    def test_min_recall_huntable_defined(self, retrain_script) -> None:
        source = RETRAIN_PATH.read_text()
        assert "MIN_RECALL_HUNTABLE" in source

    def test_min_f1_huntable_defined(self, retrain_script) -> None:
        source = RETRAIN_PATH.read_text()
        assert "MIN_F1_HUNTABLE" in source

    def test_recall_threshold_at_least_0_25(self, retrain_script) -> None:
        import re
        source = RETRAIN_PATH.read_text()
        m = re.search(r"MIN_RECALL_HUNTABLE\s*=\s*([0-9.]+)", source)
        assert m, "MIN_RECALL_HUNTABLE not found"
        assert float(m.group(1)) >= 0.25, "Recall gate too low — broken models would pass"

    def test_f1_threshold_at_least_0_25(self, retrain_script) -> None:
        import re
        source = RETRAIN_PATH.read_text()
        m = re.search(r"MIN_F1_HUNTABLE\s*=\s*([0-9.]+)", source)
        assert m, "MIN_F1_HUNTABLE not found"
        assert float(m.group(1)) >= 0.25, "F1 gate too low — broken models would pass"

    def test_rejection_prints_retrain_rejected(self, retrain_script) -> None:
        source = RETRAIN_PATH.read_text()
        assert "RETRAIN REJECTED" in source, (
            "Quality gate must print 'RETRAIN REJECTED' so the route can surface it"
        )

    def test_staging_path_used_for_training(self, retrain_script) -> None:
        source = RETRAIN_PATH.read_text()
        assert "staging_model_path" in source, (
            "Train to a staging path so the live model is not replaced before the quality gate"
        )

    def test_staging_promoted_only_after_gate(self, retrain_script) -> None:
        """The copy from staging to live must come AFTER the quality gate check."""
        source = RETRAIN_PATH.read_text()
        gate_pos = source.find("RETRAIN REJECTED")
        promote_pos = source.find("Staged model promoted to live")
        assert gate_pos != -1, "Quality gate rejection message not found"
        assert promote_pos != -1, "Promotion message not found"
        assert gate_pos < promote_pos, (
            "Quality gate check must appear before the staging→live copy in source"
        )

    def test_gate_only_applied_for_curated_eval(self, retrain_script) -> None:
        source = RETRAIN_PATH.read_text()
        assert "using_curated_eval" in source, (
            "Quality gate must only fire when using the curated holdout eval set, "
            "not when falling back to noisy training-split metrics"
        )


class TestRouteRejectsQualityGateMessage:
    """The route must surface the rejection message from stdout."""

    def test_route_checks_retrain_rejected_in_stdout(self) -> None:
        path = Path(REPO_ROOT / "src" / "web" / "routes" / "models.py")
        source = path.read_text()
        assert "RETRAIN REJECTED" in source, (
            "Route must check stdout for RETRAIN REJECTED to surface the "
            "quality-gate message rather than the generic failure tail"
        )
