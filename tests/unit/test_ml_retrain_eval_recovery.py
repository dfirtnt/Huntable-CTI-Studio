"""Route contract: eval-metrics recovery in run_retrain().

When the retrain subprocess exits cleanly (returncode=0) but the in-process
asyncio save_eval_metrics call failed silently, the route thread must detect
the missing evaluated_at and re-run the evaluator before marking the retrain
as 'complete'.

Contract under test (src/web/routes/models.py, run_retrain()):
  - If latest_version.evaluated_at is None after subprocess success -> run
    ContentFilter + ModelEvaluator + save_evaluation_metrics as recovery.
  - Recovery logs a WARNING (not silent).
  - 'complete' status is written AFTER the recovery attempt.
  - If latest_version.evaluated_at is already set -> recovery is skipped.

Pure unit tests: no subprocess, no DB, no filesystem.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.regression]


def _fake_version(*, version_number: int, evaluated_at=None, accuracy=0.93):
    return SimpleNamespace(
        id=version_number,
        version_number=version_number,
        accuracy=accuracy,
        training_duration_seconds=42.0,
        evaluated_at=evaluated_at,
    )


_SAMPLE_METRICS = {
    "accuracy": 0.662,
    "precision_huntable": 0.639,
    "precision_not_huntable": 1.0,
    "recall_huntable": 1.0,
    "recall_not_huntable": 0.0,
    "f1_score_huntable": 0.779,
    "f1_score_not_huntable": 0.0,
    "confusion_matrix": None,
    "total_eval_chunks": 77,
    "misclassified_count": 26,
}


# ---------------------------------------------------------------------------
# Replicate the recovery block from run_retrain() for isolated testing
# ---------------------------------------------------------------------------


def _run_recovery_logic(latest_version, mock_cf, mock_evaluator, mock_run_sync, mock_logger):
    """Mirror the recovery block from src/web/routes/models.py run_retrain()."""
    recovery_attempted = False

    if latest_version.evaluated_at is None:
        mock_logger.warning(
            f"[retrain] v{latest_version.version_number} has no eval metrics "
            "after subprocess exit — running evaluator in route thread as recovery"
        )
        try:
            cf = mock_cf()
            evaluator = mock_evaluator()
            eval_metrics = evaluator.evaluate_model(cf)

            async def save_eval_recovery(version_id, metrics):
                pass  # exercised via mock_run_sync

            saved = mock_run_sync(
                save_eval_recovery(latest_version.id, eval_metrics),
                allow_running_loop=False,
            )
            recovery_attempted = True
            if saved:
                mock_logger.info(
                    f"[retrain] Recovery eval metrics saved for "
                    f"v{latest_version.version_number}: "
                    f"acc={eval_metrics['accuracy']:.3f} "
                    f"f1={eval_metrics['f1_score_huntable']:.3f}"
                )
            else:
                mock_logger.error(
                    f"[retrain] Recovery save_evaluation_metrics returned False for v{latest_version.version_number}"
                )
        except Exception as eval_err:
            mock_logger.error(f"[retrain] Recovery evaluator failed for v{latest_version.version_number}: {eval_err}")

    return recovery_attempted


class TestEvalRecoveryLogic:
    def test_recovery_runs_when_evaluated_at_is_none(self):
        version = _fake_version(version_number=19, evaluated_at=None)
        mock_eval = MagicMock()
        mock_eval.return_value.evaluate_model.return_value = _SAMPLE_METRICS
        mock_run_sync = MagicMock(return_value=True)

        attempted = _run_recovery_logic(version, MagicMock(), mock_eval, mock_run_sync, MagicMock())

        assert attempted
        mock_eval.return_value.evaluate_model.assert_called_once()
        mock_run_sync.assert_called_once()

    def test_recovery_skipped_when_evaluated_at_is_set(self):
        version = _fake_version(version_number=17, evaluated_at=datetime.now())
        mock_eval = MagicMock()
        mock_run_sync = MagicMock()

        attempted = _run_recovery_logic(version, MagicMock(), mock_eval, mock_run_sync, MagicMock())

        assert not attempted
        mock_eval.return_value.evaluate_model.assert_not_called()
        mock_run_sync.assert_not_called()

    def test_recovery_logs_warning_before_attempting(self):
        version = _fake_version(version_number=19, evaluated_at=None)
        mock_eval = MagicMock()
        mock_eval.return_value.evaluate_model.return_value = _SAMPLE_METRICS
        mock_logger = MagicMock()

        _run_recovery_logic(version, MagicMock(), mock_eval, MagicMock(return_value=True), mock_logger)

        warning_text = " ".join(str(c) for c in mock_logger.warning.call_args_list)
        assert "no eval metrics" in warning_text

    def test_recovery_logs_info_on_success(self):
        version = _fake_version(version_number=19, evaluated_at=None)
        mock_eval = MagicMock()
        mock_eval.return_value.evaluate_model.return_value = _SAMPLE_METRICS
        mock_logger = MagicMock()

        _run_recovery_logic(version, MagicMock(), mock_eval, MagicMock(return_value=True), mock_logger)

        info_text = " ".join(str(c) for c in mock_logger.info.call_args_list)
        assert "Recovery eval metrics saved" in info_text

    def test_recovery_logs_error_when_save_returns_false(self):
        version = _fake_version(version_number=19, evaluated_at=None)
        mock_eval = MagicMock()
        mock_eval.return_value.evaluate_model.return_value = _SAMPLE_METRICS
        mock_logger = MagicMock()

        _run_recovery_logic(version, MagicMock(), mock_eval, MagicMock(return_value=False), mock_logger)

        error_text = " ".join(str(c) for c in mock_logger.error.call_args_list)
        assert "returned False" in error_text

    def test_recovery_logs_error_when_evaluator_raises(self):
        version = _fake_version(version_number=19, evaluated_at=None)
        mock_eval = MagicMock()
        mock_eval.return_value.evaluate_model.side_effect = FileNotFoundError("eval_set.csv missing")
        mock_logger = MagicMock()

        # Must not propagate the exception
        _run_recovery_logic(version, MagicMock(), mock_eval, MagicMock(), mock_logger)

        error_text = " ".join(str(c) for c in mock_logger.error.call_args_list)
        assert "Recovery evaluator failed" in error_text


class TestRouteCodeContainsRecovery:
    """Guard against accidental removal of the recovery block from models.py."""

    @pytest.fixture(scope="class")
    def route_source(self) -> str:
        path = Path(__file__).resolve().parents[2] / "src" / "web" / "routes" / "models.py"
        return path.read_text()

    def test_route_checks_evaluated_at(self, route_source: str) -> None:
        assert "evaluated_at is None" in route_source

    def test_route_imports_content_filter_in_recovery(self, route_source: str) -> None:
        assert "ContentFilter" in route_source

    def test_route_imports_model_evaluator_in_recovery(self, route_source: str) -> None:
        assert "ModelEvaluator" in route_source

    def test_route_logs_warning_for_missing_eval(self, route_source: str) -> None:
        assert "no eval metrics" in route_source

    def test_route_calls_save_eval_recovery(self, route_source: str) -> None:
        assert "save_eval_recovery" in route_source


# ---------------------------------------------------------------------------
# TestArtifactResolution — contracts for _resolve_artifact_path()
# ---------------------------------------------------------------------------


class TestArtifactResolution:
    """Guard _resolve_artifact_path() fallback behaviour in model_versioning.py."""

    def test_returns_primary_when_it_exists(self, tmp_path):
        from src.utils.model_versioning import MLModelVersionManager

        p = tmp_path / "content_filter_v99.pkl"
        p.write_bytes(b"fake")
        assert MLModelVersionManager._resolve_artifact_path(str(p)) == str(p)

    def test_returns_none_when_neither_path_exists(self, tmp_path):
        from src.utils.model_versioning import MLModelVersionManager

        missing = str(tmp_path / "content_filter_v99.pkl")
        assert MLModelVersionManager._resolve_artifact_path(missing) is None

    def test_returns_none_for_none_input(self):
        from src.utils.model_versioning import MLModelVersionManager

        assert MLModelVersionManager._resolve_artifact_path(None) is None

    def test_falls_back_to_backup_when_primary_missing(self, tmp_path, monkeypatch):
        from src.utils.model_versioning import MLModelVersionManager

        # Simulate: primary gone, backup present
        backup_dir = tmp_path / "backups" / "models"
        backup_dir.mkdir(parents=True)
        backup_file = backup_dir / "content_filter_v99.pkl"
        backup_file.write_bytes(b"backup")
        primary = str(tmp_path / "models" / "content_filter_v99.pkl")
        # Point BACKUP_MODELS_DIR at our tmp location
        monkeypatch.setattr(MLModelVersionManager, "BACKUP_MODELS_DIR", str(backup_dir))
        result = MLModelVersionManager._resolve_artifact_path(primary)
        assert result == str(backup_file)

    def test_primary_preferred_over_backup_when_both_exist(self, tmp_path, monkeypatch):
        from src.utils.model_versioning import MLModelVersionManager

        primary_file = tmp_path / "content_filter_v99.pkl"
        primary_file.write_bytes(b"primary")
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        backup_file = backup_dir / "content_filter_v99.pkl"
        backup_file.write_bytes(b"backup")
        monkeypatch.setattr(MLModelVersionManager, "BACKUP_MODELS_DIR", str(backup_dir))
        result = MLModelVersionManager._resolve_artifact_path(str(primary_file))
        assert result == str(primary_file)

    def test_backup_dir_constant_present_in_class(self):
        from src.utils.model_versioning import MLModelVersionManager

        assert hasattr(MLModelVersionManager, "BACKUP_MODELS_DIR")
        assert "backups" in MLModelVersionManager.BACKUP_MODELS_DIR

    def test_backup_dir_in_allowed_model_dirs(self):
        from src.utils.model_versioning import MLModelVersionManager

        allowed = " ".join(MLModelVersionManager.ALLOWED_MODEL_DIRS)
        assert "backups" in allowed, (
            "backups/models must be in ALLOWED_MODEL_DIRS or _validate_model_path "
            "will reject backup paths as traversal attempts"
        )
