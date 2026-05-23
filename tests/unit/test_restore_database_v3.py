"""Unit tests for restore_database_v3.py — focuses on check_source_attribution_integrity()."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from restore_database_v3 import _SOURCE_MISMATCH_BASELINE, check_source_attribution_integrity  # noqa: E402

pytestmark = pytest.mark.unit


def _psql_ok(count: int) -> MagicMock:
    m = MagicMock()
    m.returncode = 0
    m.stdout = f" {count}\n"
    m.stderr = ""
    return m


def _psql_err() -> MagicMock:
    m = MagicMock()
    m.returncode = 1
    m.stdout = ""
    m.stderr = "FATAL: role does not exist"
    return m


class TestSourceMismatchBaseline:
    def test_baseline_constant(self):
        """Regression guard: baseline must match the 2026-05-03 audit figure."""
        assert _SOURCE_MISMATCH_BASELINE == 112


class TestCheckSourceAttributionIntegrity:
    def test_passes_when_count_at_baseline(self):
        with patch("subprocess.run", return_value=_psql_ok(_SOURCE_MISMATCH_BASELINE)):
            result = check_source_attribution_integrity()
        assert result["exceeded"] is False
        assert result["mismatch_count"] == _SOURCE_MISMATCH_BASELINE
        assert result["baseline"] == _SOURCE_MISMATCH_BASELINE

    def test_passes_when_count_at_threshold(self):
        threshold = int(_SOURCE_MISMATCH_BASELINE * 1.10)
        with patch("subprocess.run", return_value=_psql_ok(threshold)):
            result = check_source_attribution_integrity()
        assert result["exceeded"] is False

    def test_fails_when_count_one_above_threshold(self):
        threshold = int(_SOURCE_MISMATCH_BASELINE * 1.10)
        with patch("subprocess.run", return_value=_psql_ok(threshold + 1)):
            result = check_source_attribution_integrity()
        assert result["exceeded"] is True
        assert result["mismatch_count"] == threshold + 1

    def test_fails_logs_warning(self, caplog):
        import logging
        threshold = int(_SOURCE_MISMATCH_BASELINE * 1.10)
        with patch("subprocess.run", return_value=_psql_ok(threshold + 50)):
            with caplog.at_level(logging.WARNING, logger="restore_database_v3"):
                check_source_attribution_integrity()
        assert any("FAILED" in r.message for r in caplog.records)

    def test_skipped_on_psql_error(self):
        with patch("subprocess.run", return_value=_psql_err()):
            result = check_source_attribution_integrity()
        assert result.get("skipped") is True
        assert "reason" in result

    def test_skipped_on_subprocess_exception(self):
        with patch("subprocess.run", side_effect=FileNotFoundError("psql not found")):
            result = check_source_attribution_integrity()
        assert result.get("skipped") is True
        assert "psql not found" in result.get("reason", "")

    def test_zero_mismatches_passes(self):
        with patch("subprocess.run", return_value=_psql_ok(0)):
            result = check_source_attribution_integrity()
        assert result["exceeded"] is False
        assert result["mismatch_count"] == 0

    def test_result_included_threshold_field(self):
        with patch("subprocess.run", return_value=_psql_ok(10)):
            result = check_source_attribution_integrity()
        assert "threshold" in result
        assert result["threshold"] == int(_SOURCE_MISMATCH_BASELINE * 1.10)
