"""Tests for SigmaPRService — path resolution and defaults."""

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.services.sigma_pr_service import SigmaPRService, parse_github_remote

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

    def test_upstream_sigmahq_remote_is_rejected_for_pr_submission(self, tmp_path):
        """The upstream reference clone cannot receive Huntable-created rules."""
        svc = SigmaPRService(repo_path=str(tmp_path))
        with patch.object(
            svc,
            "_run_git_command",
            return_value=(0, "https://github.com/SigmaHQ/sigma.git\n", ""),
        ):
            result = svc._validate_pr_repository()

        assert result["valid"] is False
        assert "upstream SigmaHQ" in result["error"]

    def test_non_sigmahq_remote_is_allowed_for_pr_submission(self, tmp_path):
        """A customer repository remote remains eligible for PR submission."""
        svc = SigmaPRService(repo_path=str(tmp_path))
        with patch.object(
            svc,
            "_run_git_command",
            return_value=(0, "git@github.com:example/Huntable-SIGMA-Rules.git\n", ""),
        ):
            result = svc._validate_pr_repository()

        assert result == {"valid": True}

    def test_submit_pr_rejects_upstream_before_repo_status_mutation(self, tmp_path):
        """The upstream guard runs before status checks can stash or checkout."""
        svc = SigmaPRService(repo_path=str(tmp_path))
        with (
            patch.object(svc, "_validate_pr_repository", return_value={"valid": False, "error": "blocked"}),
            patch.object(svc, "_check_repo_status") as check_status,
        ):
            result = svc.submit_pr([{"id": "rule-1", "rule_yaml": "title: Test\n"}])

        assert result == {"success": False, "error": "blocked"}
        check_status.assert_not_called()


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


class TestRunGitCommand:
    """Test _run_git_command's narrowed exception handling (RuntimeError/SubprocessError/OSError)."""

    @pytest.fixture(autouse=True)
    def _mock_db_settings(self):
        with patch.object(SigmaPRService, "_get_setting", return_value=None):
            with patch.dict("os.environ", {}, clear=False):
                self.svc = SigmaPRService(repo_path="/tmp/fake-repo")
                yield

    def test_nonzero_exit_with_check_raises_runtime_error_with_git_message(self):
        """check=True + non-zero exit raises RuntimeError containing the git failure message."""
        failed = MagicMock(returncode=1, stdout="", stderr="fatal: not a git repository")
        with patch("subprocess.run", return_value=failed):
            with pytest.raises(RuntimeError, match="fatal: not a git repository"):
                self.svc._run_git_command(["status"])

    def test_nonzero_exit_with_check_false_does_not_raise(self):
        """check=False + non-zero exit returns the tuple instead of raising."""
        failed = MagicMock(returncode=1, stdout="", stderr="fatal: error")
        with patch("subprocess.run", return_value=failed):
            returncode, _stdout, stderr = self.svc._run_git_command(["status"], check=False)
        assert returncode == 1
        assert stderr == "fatal: error"

    def test_timeout_propagates_as_runtime_error(self):
        """subprocess.TimeoutExpired propagates as RuntimeError, not swallowed."""
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="git status", timeout=60)):
            with pytest.raises(RuntimeError, match="timed out"):
                self.svc._run_git_command(["status"])

    def test_missing_git_binary_propagates_as_oserror(self):
        """FileNotFoundError (OSError subclass) from a missing git binary propagates, not swallowed."""
        with patch("subprocess.run", side_effect=FileNotFoundError("git not on PATH")):
            with pytest.raises(FileNotFoundError):
                self.svc._run_git_command(["status"])

    def test_unrelated_exception_type_still_propagates(self):
        """An exception type outside the narrowed tuple (e.g. TypeError) is not caught."""
        with patch("subprocess.run", side_effect=TypeError("unexpected")):
            with pytest.raises(TypeError):
                self.svc._run_git_command(["status"])


class TestParseGithubRemote:
    """owner/repo extraction covers every remote URL shape these clones carry."""

    @pytest.mark.parametrize(
        ("remote", "expected"),
        [
            ("https://github.com/dfirtnt/Huntable-SIGMA-Rules.git", "dfirtnt/Huntable-SIGMA-Rules"),
            ("https://github.com/dfirtnt/Huntable-SIGMA-Rules", "dfirtnt/Huntable-SIGMA-Rules"),
            ("https://github.com/dfirtnt/Huntable-SIGMA-Rules/", "dfirtnt/Huntable-SIGMA-Rules"),
            ("git@github.com:dfirtnt/Huntable-SIGMA-Rules.git", "dfirtnt/Huntable-SIGMA-Rules"),
            ("ssh://git@github.com/dfirtnt/Huntable-SIGMA-Rules.git", "dfirtnt/Huntable-SIGMA-Rules"),
            # _configure_remote_auth writes this shape back into the clone.
            (
                "https://x-access-token:github_pat_abc123@github.com/dfirtnt/Huntable-SIGMA-Rules.git",
                "dfirtnt/Huntable-SIGMA-Rules",
            ),
            ("  https://github.com/SigmaHQ/sigma.git\n", "SigmaHQ/sigma"),
        ],
    )
    def test_recognized_shapes(self, remote, expected):
        assert parse_github_remote(remote) == expected

    @pytest.mark.parametrize("remote", ["", None, "   ", "https://gitlab.com/owner/repo.git", "/local/path/repo"])
    def test_unrecognized_shapes_return_none(self, remote):
        assert parse_github_remote(remote) is None


class TestGithubRepoResolution:
    """The clone's remote is the default source; an explicit setting overrides it."""

    @pytest.fixture(autouse=True)
    def _no_env_repo(self):
        with patch.dict("os.environ", {}, clear=False):
            os.environ.pop("GITHUB_REPO", None)
            yield

    def _service(self, tmp_path, stored=None):
        with patch.object(
            SigmaPRService, "_get_setting", side_effect=lambda key: stored if key == "GITHUB_REPO" else None
        ):
            return SigmaPRService(repo_path=str(tmp_path))

    def test_derived_from_origin_remote_when_nothing_configured(self, tmp_path):
        svc = self._service(tmp_path)
        with patch.object(
            svc, "_run_git_command", return_value=(0, "https://github.com/dfirtnt/Huntable-SIGMA-Rules.git\n", "")
        ):
            assert svc.github_repo == "dfirtnt/Huntable-SIGMA-Rules"
        assert svc.describe_github_repo() == {"repo": "dfirtnt/Huntable-SIGMA-Rules", "source": "remote"}

    def test_explicit_setting_wins_over_remote(self, tmp_path):
        """The fork-PR case: push to one repo, open the PR against another."""
        svc = self._service(tmp_path, stored="upstream/rules")
        with patch.object(svc, "_run_git_command", return_value=(0, "https://github.com/fork/rules.git\n", "")) as git:
            assert svc.github_repo == "upstream/rules"
        assert git.call_count == 0
        assert svc.describe_github_repo() == {"repo": "upstream/rules", "source": "setting"}

    def test_env_var_is_an_override_and_is_labelled_as_such(self, tmp_path):
        os.environ["GITHUB_REPO"] = "envowner/envrepo"
        svc = self._service(tmp_path)
        assert svc.github_repo == "envowner/envrepo"
        assert svc.describe_github_repo() == {"repo": "envowner/envrepo", "source": "environment"}

    def test_unresolvable_when_remote_missing(self, tmp_path):
        svc = self._service(tmp_path)
        with patch.object(svc, "_run_git_command", return_value=(1, "", "fatal: No such remote 'origin'")):
            assert svc.github_repo is None
        assert svc.describe_github_repo() == {"repo": None, "source": "unresolved"}

    def test_unresolvable_when_remote_is_not_github(self, tmp_path):
        svc = self._service(tmp_path)
        with patch.object(svc, "_run_git_command", return_value=(0, "https://gitlab.com/owner/repo.git\n", "")):
            assert svc.github_repo is None

    def test_derivation_is_memoized(self, tmp_path):
        svc = self._service(tmp_path)
        with patch.object(svc, "_run_git_command", return_value=(0, "https://github.com/owner/repo.git\n", "")) as git:
            assert svc.github_repo == "owner/repo"
            assert svc.github_repo == "owner/repo"
        assert git.call_count == 1

    def test_missing_repo_path_does_not_shell_out(self, tmp_path):
        svc = self._service(tmp_path / "absent")
        with patch.object(svc, "_run_git_command") as git:
            assert svc.github_repo is None
        assert git.call_count == 0

    def test_validate_reports_unresolvable_repository_with_guidance(self, tmp_path):
        """The failure lands before branch/commit work, not as a 404 from GitHub."""
        svc = self._service(tmp_path)
        with patch.object(svc, "_run_git_command", return_value=(0, "https://gitlab.com/owner/repo.git\n", "")):
            result = svc._validate_pr_repository()

        assert result["valid"] is False
        assert "Could not determine which GitHub repository" in result["error"]
        assert "owner/repo" in result["error"]

    def test_validate_passes_when_repository_derives_cleanly(self, tmp_path):
        svc = self._service(tmp_path)
        with patch.object(
            svc, "_run_git_command", return_value=(0, "https://github.com/dfirtnt/Huntable-SIGMA-Rules.git\n", "")
        ):
            assert svc._validate_pr_repository() == {"valid": True}

    def test_create_pr_returns_none_instead_of_splitting_nothing(self, tmp_path):
        svc = self._service(tmp_path)
        with patch.object(svc, "_run_git_command", return_value=(1, "", "no origin")):
            assert svc._create_github_pr("branch", "title", "body") is None
