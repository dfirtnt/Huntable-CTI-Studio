"""Unit tests for test-artifact cleanup in run_tests.py.

Allure writes result/attachment files into ``allure-results/`` on every pytest run
and nothing pruned them, so the directory grew without bound (millions of files,
filling the disk). Two fixes are covered here:

  1. The runner clears ``allure-results/`` at the start of each invocation via the
     ``_clear_directory_contents`` helper, so reports regenerate per run instead of
     accumulating across runs.
  2. The always-on ``--alluredir`` was removed from the global pytest ``addopts`` so
     ad-hoc ``pytest <path>`` runs stop silently accumulating into ``allure-results/``.
     The runner re-adds ``--alluredir`` itself only when it actually wants a report.

Fast, no subprocess/browser.
"""

import tomllib
from pathlib import Path

import pytest

from tests_runner.runner import _clear_directory_contents

pytestmark = [pytest.mark.unit, pytest.mark.smoke]

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestClearDirectoryContents:
    def test_removes_files_and_subdirs_but_keeps_directory(self, tmp_path):
        target = tmp_path / "allure-results"
        target.mkdir()
        (target / "abc-result.json").write_text("{}")
        (target / "def-container.json").write_text("{}")
        sub = target / "attachments"
        sub.mkdir()
        (sub / "screenshot.png").write_bytes(b"x")

        removed = _clear_directory_contents(target)

        assert target.exists()
        assert list(target.iterdir()) == []
        assert removed == 3  # two files + one subdir

    def test_absent_directory_is_noop(self, tmp_path):
        missing = tmp_path / "does-not-exist"
        assert _clear_directory_contents(missing) == 0
        assert not missing.exists()


class TestGlobalAddoptsNoAllure:
    def test_addopts_does_not_force_alluredir(self):
        with open(PROJECT_ROOT / "pyproject.toml", "rb") as fh:
            data = tomllib.load(fh)
        addopts = data["tool"]["pytest"]["ini_options"]["addopts"]
        assert "--alluredir" not in addopts
