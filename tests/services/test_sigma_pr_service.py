"""Tests for SigmaPRService — path resolution and defaults."""

from pathlib import Path
from unittest.mock import patch

import pytest

from src.services.sigma_pr_service import SigmaPRService

pytestmark = pytest.mark.unit


class TestSigmaPRServicePathResolution:
    """Test path resolution uses sigma-repo default and respects explicit paths."""

    @pytest.fixture(autouse=True)
    def _mock_db_settings(self):
        """Avoid DB access; _get_setting returns None."""
        with patch.object(SigmaPRService, "_get_setting", return_value=None):
            yield

    def test_explicit_absolute_path_used_as_is(self, tmp_path):
        """When repo_path is absolute, it is used unchanged."""
        with patch.dict("os.environ", {}, clear=False):
            svc = SigmaPRService(repo_path=str(tmp_path))
        assert svc.repo_path == tmp_path.resolve()
        assert svc.rules_path == tmp_path / "rules"

    def test_explicit_relative_path_resolves_from_app_root(self):
        """When repo_path is relative, it resolves from app root."""
        app_root = Path(__file__).parent.parent.parent
        with patch.dict("os.environ", {}, clear=False):
            svc = SigmaPRService(repo_path="sigma-repo")
        assert svc.repo_path == (app_root / "sigma-repo").resolve()
        assert svc.rules_path == svc.repo_path / "rules"

    def test_default_path_is_sigma_repo_when_no_setting_or_env(self):
        """Default path is sigma-repo when DB and env have no value."""
        app_root = Path(__file__).parent.parent.parent
        with patch.dict("os.environ", {}, clear=False):
            svc = SigmaPRService(repo_path=None)
        assert svc.repo_path == (app_root / "sigma-repo").resolve()
