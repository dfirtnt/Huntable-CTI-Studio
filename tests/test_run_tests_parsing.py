"""Unit tests for run_tests.py output parsing (counts and summary). Fast, no subprocess/browser."""

import os
import subprocess
from pathlib import Path

import pytest

from run_tests import ExecutionContext, RunTestConfig, RunTestRunner, RunTestType

pytestmark = pytest.mark.unit

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def runner():
    config = RunTestConfig(
        test_type=RunTestType.UI,
        context=ExecutionContext.LOCALHOST,
        validate_env=False,
    )
    return RunTestRunner(config)


class TestParsePytestOutput:
    def test_failed_passed_skipped(self, runner):
        out = "= 1 failed, 20 passed, 3 skipped in 45.32s ="
        got = runner._parse_pytest_output(out)
        assert got == {"total": 24, "passed": 20, "failed": 1, "skipped": 3, "errors": 0}

    def test_passed_only(self, runner):
        out = "= 23 passed in 12.50s ="
        got = runner._parse_pytest_output(out)
        assert got == {"total": 23, "passed": 23, "failed": 0, "skipped": 0, "errors": 0}

    def test_failed_and_errors(self, runner):
        out = "= 2 failed, 1 error in 10.00s ="
        got = runner._parse_pytest_output(out)
        assert got == {"total": 3, "passed": 0, "failed": 2, "skipped": 0, "errors": 1}

    def test_no_xpassed_contamination(self, runner):
        out = "= 1 failed, 20 passed, 1 xpassed, 3 skipped in 45s ="
        got = runner._parse_pytest_output(out)
        assert got["passed"] == 20
        assert got["total"] == 24


class TestParsePlaywrightOutput:
    def test_failed_skipped_passed(self, runner):
        out = "  15 failed, 2 skipped, 18 passed (1m)"
        got = runner._parse_playwright_output(out)
        assert got == {"total": 35, "passed": 18, "failed": 15, "skipped": 2}

    def test_passed_only(self, runner):
        out = "  30 passed (1m)"
        got = runner._parse_playwright_output(out)
        assert got == {"total": 30, "passed": 30, "failed": 0, "skipped": 0}

    def test_failed_and_passed(self, runner):
        out = "  1 failed, 29 passed"
        got = runner._parse_playwright_output(out)
        assert got == {"total": 30, "passed": 29, "failed": 1, "skipped": 0}


class TestAgentConfigExcludeEnv:
    """UI excludes agent config tests by default; --include-agent-config-tests or --exclude-markers control env."""

    def test_exclude_markers_agent_config_mutation_sets_env(self):
        config = RunTestConfig(
            test_type=RunTestType.UI,
            context=ExecutionContext.LOCALHOST,
            validate_env=False,
            exclude_markers=["agent_config_mutation"],
        )
        runner = RunTestRunner(config)
        env = runner._get_agent_config_exclude_env()
        assert env == {"CTI_EXCLUDE_AGENT_CONFIG_TESTS": "1"}

    def test_ui_default_excludes_agent_config_tests(self):
        """UI without --include-agent-config-tests sets CTI_EXCLUDE_AGENT_CONFIG_TESTS=1."""
        config = RunTestConfig(
            test_type=RunTestType.UI,
            context=ExecutionContext.LOCALHOST,
            validate_env=False,
            exclude_markers=None,
            include_agent_config_tests=False,
        )
        runner = RunTestRunner(config)
        assert runner._get_agent_config_exclude_env() == {"CTI_EXCLUDE_AGENT_CONFIG_TESTS": "1"}

    def test_ui_include_agent_config_tests_returns_empty(self):
        """UI with --include-agent-config-tests does not set exclude env."""
        config = RunTestConfig(
            test_type=RunTestType.UI,
            context=ExecutionContext.LOCALHOST,
            validate_env=False,
            exclude_markers=None,
            include_agent_config_tests=True,
        )
        runner = RunTestRunner(config)
        assert runner._get_agent_config_exclude_env() == {}

    def test_exclude_other_marker_ui_still_excludes_agent_config_by_default(self):
        """UI with other exclude_markers but not include_agent_config_tests still sets exclude env."""
        config = RunTestConfig(
            test_type=RunTestType.UI,
            context=ExecutionContext.LOCALHOST,
            validate_env=False,
            exclude_markers=["slow", "integration"],
            include_agent_config_tests=False,
        )
        runner = RunTestRunner(config)
        assert runner._get_agent_config_exclude_env() == {"CTI_EXCLUDE_AGENT_CONFIG_TESTS": "1"}


class TestRunTestsSummaryOutput:
    """Invoke run_tests.py with a short run and assert summary (count + time) is printed."""

    def test_summary_includes_count_and_time_lines(self):
        # Use a different test path to avoid recursion (this file contains this test).
        env = os.environ.copy()
        env["APP_ENV"] = "test"
        env.setdefault(
            "TEST_DATABASE_URL",
            "postgresql+asyncpg://u:p@localhost:5433/cti_scraper_test",
        )
        result = subprocess.run(
            [
                str(PROJECT_ROOT / ".venv" / "bin" / "python3"),
                str(PROJECT_ROOT / "run_tests.py"),
                "unit",
                "--paths",
                "tests/test_utils.py",
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=90,
            env=env,
        )
        out = result.stdout + result.stderr
        assert "PYTEST TESTS:" in out, "Pytest section header missing"
        assert "Passed:" in out and "Failed:" in out and "Skipped:" in out, (
            "Count line (Passed | Failed | Skipped) missing"
        )
        assert "Test execution only:" in out, "Test execution only line missing"
        assert "Total (including setup):" in out, "Total (including setup) line missing"
        assert result.returncode == 0, f"run_tests exited {result.returncode}\n{out[-2000:]}"


class TestUITestOptimizations:
    """Regression tests that guard the UI test speed optimisations.

    These verify *invariants of the test files* rather than runtime browser
    behaviour, so they can run in the fast unit suite without Playwright.
    """

    _UI_DIR = PROJECT_ROOT / "tests" / "ui"

    # ------------------------------------------------------------------ #
    # 1. No redundant post-goto blanket sleeps
    # ------------------------------------------------------------------ #

    def _load_ui_lines(self) -> dict[str, list[str]]:
        lines_by_file: dict[str, list[str]] = {}
        for p in sorted(self._UI_DIR.glob("*.py")):
            lines_by_file[p.name] = p.read_text().splitlines()
        return lines_by_file

    def test_no_redundant_post_goto_timeout(self):
        """wait_for_load_state('load') must NOT be immediately followed by wait_for_timeout.

        Playwright's expect() retries up to its own timeout; the extra sleep is
        pure dead time.  Chat page uses element-specific waits instead.
        """
        violations: list[str] = []
        files = self._load_ui_lines()
        for fname, lines in files.items():
            for i, line in enumerate(lines):
                if "wait_for_load_state" in line and '"load"' in line:
                    next_line = lines[i + 1] if i + 1 < len(lines) else ""
                    if "wait_for_timeout" in next_line:
                        violations.append(f"{fname}:{i + 2}: {next_line.strip()}")
        assert not violations, (
            "Redundant post-goto wait_for_timeout found (remove them — "
            "expect() already retries):\n" + "\n".join(violations)
        )

    # ------------------------------------------------------------------ #
    # 2. Chat page React-mount waits are element-specific, not blanket
    # ------------------------------------------------------------------ #

    def test_chat_react_waits_are_element_specific(self):
        """After page.goto('/chat') + wait_for_load_state the chat tests must
        wait for the React textarea, not a blanket timeout."""
        chat_file = "test_chat_comprehensive_ui.py"
        if chat_file not in self._load_ui_lines():
            return  # File doesn't exist, skip
        lines = self._load_ui_lines()[chat_file]
        for i, line in enumerate(lines):
            if "wait_for_load_state" in line and '"load"' in line:
                next_line = lines[i + 1] if i + 1 < len(lines) else ""
                assert "wait_for_timeout" not in next_line, (
                    f"{chat_file}:{i + 2}: blanket wait_for_timeout after load_state — "
                    f"use textarea.wait_for(state='visible') instead"
                )

    # ------------------------------------------------------------------ #
    # 3. class_page fixture exists in conftest
    # ------------------------------------------------------------------ #

    def test_class_page_fixture_in_conftest(self):
        conftest = (self._UI_DIR / "conftest.py").read_text()
        assert "def class_page" in conftest, "class_page fixture missing from tests/ui/conftest.py"
        assert 'scope="class"' in conftest, "class_page fixture must be scope='class'"

    # ------------------------------------------------------------------ #
    # 4. Timeout guard present in conftest
    # ------------------------------------------------------------------ #

    def test_timeout_guard_in_conftest(self):
        conftest = (self._UI_DIR / "conftest.py").read_text()
        assert "_UI_TEST_TIMEOUT_SECONDS" in conftest, (
            "_UI_TEST_TIMEOUT_SECONDS constant missing from tests/ui/conftest.py"
        )
        assert "pytest_itemcollected" in conftest, (
            "pytest_itemcollected hook missing — needed to apply per-test timeout"
        )

    # ------------------------------------------------------------------ #
    # 5. run_tests.py passes --timeout to UI pytest run
    # ------------------------------------------------------------------ #

    def test_run_tests_adds_timeout_for_ui(self):
        """_build_pytest_command for UI suite includes --timeout when pytest-timeout available."""
        config = RunTestConfig(
            test_type=RunTestType.UI,
            context=ExecutionContext.LOCALHOST,
            validate_env=False,
        )
        runner = RunTestRunner(config)
        cmd = runner._build_pytest_command()
        # The timeout flag is only added when pytest-timeout is importable.
        try:
            import pytest_timeout  # noqa: F401

            assert "--timeout=60" in cmd, f"--timeout=60 not in pytest command: {cmd}"
        except ImportError:
            pass  # pytest-timeout not installed — timeout guard disabled, that's fine
