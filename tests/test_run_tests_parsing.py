"""Unit tests for run_tests.py output parsing (counts and summary). Fast, no subprocess/browser."""

import os
import subprocess
from pathlib import Path

import pytest

from run_tests import ExecutionContext, TestConfig, TestRunner, TestType

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def runner():
    config = TestConfig(
        test_type=TestType.UI,
        context=ExecutionContext.LOCALHOST,
        validate_env=False,
    )
    return TestRunner(config)


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
    """Test that --exclude-markers agent_config_mutation sets CTI_EXCLUDE_AGENT_CONFIG_TESTS in env (no agent config mutation)."""

    def test_exclude_agent_config_mutation_sets_env(self):
        config = TestConfig(
            test_type=TestType.UI,
            context=ExecutionContext.LOCALHOST,
            validate_env=False,
            exclude_markers=["agent_config_mutation"],
        )
        runner = TestRunner(config)
        env = runner._get_agent_config_exclude_env()
        assert env == {"CTI_EXCLUDE_AGENT_CONFIG_TESTS": "1"}

    def test_no_exclude_markers_returns_empty(self):
        config = TestConfig(
            test_type=TestType.UI,
            context=ExecutionContext.LOCALHOST,
            validate_env=False,
            exclude_markers=None,
        )
        runner = TestRunner(config)
        assert runner._get_agent_config_exclude_env() == {}

    def test_exclude_other_marker_returns_empty(self):
        config = TestConfig(
            test_type=TestType.UI,
            context=ExecutionContext.LOCALHOST,
            validate_env=False,
            exclude_markers=["slow", "integration"],
        )
        runner = TestRunner(config)
        assert runner._get_agent_config_exclude_env() == {}


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
