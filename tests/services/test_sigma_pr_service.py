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


class TestResolveDefaultBaseBranch:
    """Test _resolve_default_base_branch branch detection with local/remote fallback."""

    @pytest.fixture(autouse=True)
    def _mock_db_settings(self):
        with patch.object(SigmaPRService, "_get_setting", return_value=None):
            with patch.dict("os.environ", {}, clear=False):
                self.svc = SigmaPRService(repo_path="/tmp/fake-repo")
                yield

    def _mock_git(self, responses: dict[str, str]):
        """Mock _run_git_command to return specific stdout per git subcommand."""
        orig = self.svc._run_git_command

        def side_effect(cmd, check=True):
            for key, stdout in responses.items():
                if key in cmd:
                    return (0, stdout, "")
            return (0, "", "")

        return patch.object(self.svc, "_run_git_command", side_effect=side_effect)

    def test_remote_main_preferred(self):
        with self._mock_git({"branch": "  origin/main\n  origin/master\n"}):
            assert self.svc._resolve_default_base_branch() == "main"

    def test_remote_master_when_no_main(self):
        with self._mock_git({"branch": "  origin/master\n"}):
            assert self.svc._resolve_default_base_branch() == "master"

    def test_local_main_fallback_when_no_remotes(self):
        """Docker scenario: no remote info, but local main branch exists."""
        responses = {"-r": "", "--list": "* main\n  sigma-rules-20260408\n"}
        with self._mock_git(responses):
            assert self.svc._resolve_default_base_branch() == "main"

    def test_local_master_fallback(self):
        responses = {"-r": "", "--list": "* master\n"}
        with self._mock_git(responses):
            assert self.svc._resolve_default_base_branch() == "master"

    def test_defaults_to_main_when_nothing_found(self):
        responses = {"-r": "", "--list": ""}
        with self._mock_git(responses):
            assert self.svc._resolve_default_base_branch() == "main"
