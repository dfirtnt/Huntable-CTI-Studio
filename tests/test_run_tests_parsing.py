"""Unit tests for run_tests.py output parsing (counts and summary). Fast, no subprocess/browser."""

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests_runner.config import ExecutionContext, RunTestConfig, RunTestType
from tests_runner.runner import RunTestRunner
from tests_runner.tui import _RunnerTUI

pytestmark = pytest.mark.unit

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def runner():
    config = RunTestConfig(
        test_type=RunTestType.UI,
        context=ExecutionContext.LOCALHOST,
        run_teardown=False,
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
            run_teardown=False,
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
            run_teardown=False,
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
            run_teardown=False,
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
            run_teardown=False,
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
            run_teardown=False,
        )
        runner = RunTestRunner(config)
        cmd = runner._build_pytest_command()
        # The timeout flag is only added when pytest-timeout is importable.
        try:
            import pytest_timeout  # noqa: F401

            assert "--timeout=60" in cmd, f"--timeout=60 not in pytest command: {cmd}"
        except ImportError:
            pass  # pytest-timeout not installed — timeout guard disabled, that's fine


class TestTestContainerStartup:
    def test_test_containers_running_reports_both_names(self, runner, monkeypatch):
        responses = {
            "cti_postgres_test": "cti_postgres_test\n",
            "cti_redis_test": "",
        }
        calls: list[list[str]] = []

        def fake_run(cmd, capture_output, text, check):
            calls.append(cmd)
            container_name = cmd[3].split("=", 1)[1]
            return SimpleNamespace(returncode=0, stdout=responses[container_name], stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)

        running, statuses = runner._test_containers_running()

        assert not running
        assert statuses == ["cti_postgres_test=running", "cti_redis_test=missing"]
        assert calls == [
            ["docker", "ps", "--filter", "name=cti_postgres_test", "--format", "{{.Names}}"],
            ["docker", "ps", "--filter", "name=cti_redis_test", "--format", "{{.Names}}"],
        ]

    def test_ensure_test_containers_starts_and_waits_when_missing(self, runner, monkeypatch):
        called = {"start": 0, "wait": 0}

        monkeypatch.setattr(
            runner,
            "_test_containers_running",
            lambda: (False, ["cti_postgres_test=running", "cti_redis_test=missing"]),
        )

        def fake_start():
            called["start"] += 1
            return True

        def fake_wait():
            called["wait"] += 1
            return True

        monkeypatch.setattr(runner, "_start_test_containers", fake_start)
        monkeypatch.setattr(runner, "_wait_for_test_containers", fake_wait)

        assert runner._ensure_test_containers() is True
        assert called == {"start": 1, "wait": 1}

    def test_ensure_test_containers_waits_when_already_running(self, runner, monkeypatch):
        called = {"wait": 0}

        monkeypatch.setattr(
            runner,
            "_test_containers_running",
            lambda: (True, ["cti_postgres_test=running", "cti_redis_test=running"]),
        )

        def fake_wait():
            called["wait"] += 1
            return True

        monkeypatch.setattr(runner, "_wait_for_test_containers", fake_wait)

        assert runner._ensure_test_containers() is True
        assert called == {"wait": 1}

    def test_start_test_containers_invokes_both_services(self, runner, monkeypatch):
        calls: list[list[str]] = []

        def fake_run(cmd, capture_output, text, check):
            calls.append(cmd)
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)

        assert runner._start_test_containers() is True
        assert calls == [
            [
                "docker",
                "compose",
                "-f",
                str(PROJECT_ROOT / "docker-compose.test.yml"),
                "up",
                "-d",
                "postgres_test",
                "redis_test",
            ]
        ]


class TestDryRun:
    """--dry-run flag: command resolution and env-var computation."""

    def _make_runner(self, test_type: RunTestType) -> RunTestRunner:
        config = RunTestConfig(
            test_type=test_type,
            context=ExecutionContext.LOCALHOST,
            run_teardown=False,
            dry_run=True,
        )
        return RunTestRunner(config)

    def test_smoke_has_no_playwright(self):
        runner = self._make_runner(RunTestType.SMOKE)
        assert runner._build_playwright_command() is None

    def test_ui_has_playwright_command(self):
        runner = self._make_runner(RunTestType.UI)
        cmd = runner._build_playwright_command()
        assert cmd is not None
        assert "playwright" in cmd

    def test_pytest_command_contains_pytest(self):
        runner = self._make_runner(RunTestType.SMOKE)
        cmd = runner._build_pytest_command()
        assert any("pytest" in part for part in cmd)

    def test_dry_run_env_always_has_app_env_test(self):
        runner = self._make_runner(RunTestType.SMOKE)
        env = runner._build_dry_run_env()
        assert env["APP_ENV"] == "test"

    def test_dry_run_env_api_type_sets_asgi_client(self):
        runner = self._make_runner(RunTestType.API)
        env = runner._build_dry_run_env()
        assert env.get("USE_ASGI_CLIENT") == "1"

    def test_dry_run_env_smoke_does_not_set_asgi_client(self):
        runner = self._make_runner(RunTestType.SMOKE)
        env = runner._build_dry_run_env()
        assert "USE_ASGI_CLIENT" not in env

    def test_dry_run_env_ui_full_sets_quarantine(self):
        runner = self._make_runner(RunTestType.UI_FULL)
        env = runner._build_dry_run_env()
        assert env.get("CTI_INCLUDE_QUARANTINE") == "1"

    def test_dry_run_env_smoke_no_quarantine(self):
        runner = self._make_runner(RunTestType.SMOKE)
        env = runner._build_dry_run_env()
        assert "CTI_INCLUDE_QUARANTINE" not in env


class TestVerbosityFlags:
    """_build_pytest_command verbosity flag behaviour (T2.3)."""

    def _make_runner(
        self,
        output_format: str = "progress",
        verbose: bool = False,
        test_type: RunTestType = RunTestType.SMOKE,
    ) -> RunTestRunner:
        config = RunTestConfig(
            test_type=test_type,
            context=ExecutionContext.LOCALHOST,
            run_teardown=False,
            output_format=output_format,
            verbose=verbose,
        )
        return RunTestRunner(config)

    def test_default_progress_format_no_v_flag(self):
        """progress format without --verbose must NOT add -v."""
        cmd = self._make_runner(output_format="progress", verbose=False)._build_pytest_command()
        assert "-v" not in cmd and "-vv" not in cmd and "-q" not in cmd

    def test_verbose_flag_adds_v(self):
        """--verbose adds -v regardless of output_format."""
        cmd = self._make_runner(output_format="progress", verbose=True)._build_pytest_command()
        assert "-v" in cmd

    def test_verbose_format_adds_vv(self):
        """output_format='verbose' adds -vv."""
        cmd = self._make_runner(output_format="verbose")._build_pytest_command()
        assert "-vv" in cmd

    def test_quiet_format_adds_q(self):
        """output_format='quiet' adds -q."""
        cmd = self._make_runner(output_format="quiet")._build_pytest_command()
        assert "-q" in cmd

    def test_verbose_format_takes_precedence_over_verbose_flag(self):
        """output_format='verbose' uses -vv even when --verbose is also set."""
        cmd = self._make_runner(output_format="verbose", verbose=True)._build_pytest_command()
        assert "-vv" in cmd
        assert "-v" not in [p for p in cmd if p == "-v"]


class TestCoverageFlags:
    """T3.3: --cov-branch, --cov-fail-under, --cov-append, JSON snapshot."""

    def _make_runner(self, coverage: bool = True, cov_append: bool = False) -> RunTestRunner:
        config = RunTestConfig(
            test_type=RunTestType.UNIT,
            context=ExecutionContext.LOCALHOST,
            run_teardown=False,
            coverage=coverage,
            cov_append=cov_append,
        )
        return RunTestRunner(config)

    def test_coverage_includes_cov_branch(self):
        cmd = self._make_runner()._build_pytest_command()
        assert "--cov-branch" in cmd

    def test_coverage_includes_json_snapshot(self):
        cmd = self._make_runner()._build_pytest_command()
        assert any(p.startswith("--cov-report=json:test-results/coverage_") for p in cmd)

    def test_cov_append_flag(self):
        cmd = self._make_runner(cov_append=True)._build_pytest_command()
        assert "--cov-append" in cmd

    def test_no_cov_append_by_default(self):
        cmd = self._make_runner(cov_append=False)._build_pytest_command()
        assert "--cov-append" not in cmd

    def test_cov_fail_under_from_env(self, monkeypatch):
        monkeypatch.setenv("CTI_COVERAGE_FAIL_UNDER", "75")
        cmd = self._make_runner()._build_pytest_command()
        assert "--cov-fail-under=75" in cmd

    def test_no_cov_fail_under_when_env_unset(self, monkeypatch):
        monkeypatch.delenv("CTI_COVERAGE_FAIL_UNDER", raising=False)
        cmd = self._make_runner()._build_pytest_command()
        assert not any(p.startswith("--cov-fail-under") for p in cmd)

    def test_no_coverage_flags_when_disabled(self):
        cmd = self._make_runner(coverage=False)._build_pytest_command()
        assert "--cov-branch" not in cmd
        assert not any(p.startswith("--cov") for p in cmd)


class TestPathGroupResolution:
    """T3.5(b): _get_pytest_test_groups uses Path.parts for exact dir match."""

    def _make_runner(self, paths: list[str]) -> RunTestRunner:
        config = RunTestConfig(
            test_type=RunTestType.SMOKE,
            context=ExecutionContext.LOCALHOST,
            run_teardown=False,
            test_paths=paths,
        )
        return RunTestRunner(config)

    def test_smoke_path_resolves_to_smoke(self):
        groups = self._make_runner(["tests/smoke/test_foo.py"])._get_pytest_test_groups()
        assert groups == ["smoke"]

    def test_api_path_with_smoke_in_name_resolves_to_api(self):
        """tests/api/test_smoke_endpoints.py must not be misclassified as smoke."""
        groups = self._make_runner(["tests/api/test_smoke_endpoints.py"])._get_pytest_test_groups()
        assert "smoke" not in groups
        assert "api" in groups

    def test_unrecognised_path_returns_all(self):
        groups = self._make_runner(["tests/unknown/test_foo.py"])._get_pytest_test_groups()
        assert groups == ["all"]


class TestContainerHealthBatch:
    """T3.4: _poll_container_health_batch parses docker compose ps JSON output."""

    def _make_runner(self) -> RunTestRunner:
        config = RunTestConfig(
            test_type=RunTestType.SMOKE,
            context=ExecutionContext.LOCALHOST,
            run_teardown=False,
        )
        return RunTestRunner(config)

    def test_both_healthy(self, monkeypatch):
        import json
        from types import SimpleNamespace

        lines = [
            json.dumps({"Service": "postgres_test", "Health": "healthy"}),
            json.dumps({"Service": "redis_test", "Health": "healthy"}),
        ]
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **kw: SimpleNamespace(returncode=0, stdout="\n".join(lines), stderr=""),
        )
        runner = self._make_runner()
        statuses, all_healthy = runner._poll_container_health_batch(
            ["docker", "compose", "-f", "docker-compose.test.yml"],
            ("postgres_test", "redis_test"),
        )
        assert all_healthy
        assert statuses == ["postgres_test=healthy", "redis_test=healthy"]

    def test_one_missing_falls_through(self, monkeypatch):
        import json
        from types import SimpleNamespace

        lines = [json.dumps({"Service": "postgres_test", "Health": "healthy"})]
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **kw: SimpleNamespace(returncode=0, stdout="\n".join(lines), stderr=""),
        )
        runner = self._make_runner()
        statuses, all_healthy = runner._poll_container_health_batch(
            ["docker", "compose", "-f", "docker-compose.test.yml"],
            ("postgres_test", "redis_test"),
        )
        assert not all_healthy
        assert "redis_test=missing" in statuses

    def test_json_parse_error_falls_back_to_legacy(self, monkeypatch):
        from types import SimpleNamespace

        calls: list[str] = []

        def fake_run(cmd, **kw):
            calls.append(cmd[0])
            return SimpleNamespace(returncode=0, stdout="not-json\n", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)
        monkeypatch.setattr(
            self._make_runner().__class__,
            "_poll_container_health_legacy",
            lambda self, base, services: (["postgres_test=healthy", "redis_test=healthy"], True),
        )
        runner = self._make_runner()
        statuses, all_healthy = runner._poll_container_health_batch(
            ["docker", "compose", "-f", "docker-compose.test.yml"],
            ("postgres_test", "redis_test"),
        )
        assert all_healthy


class TestRunnerTUI:
    """T3.1: _RunnerTUI activation logic and plain-mode no-op behaviour."""

    def test_plain_mode_never_activates(self):
        tui = _RunnerTUI(mode="plain")
        assert not tui._active

    def test_non_tty_does_not_activate(self, monkeypatch):
        """auto mode on a non-TTY (CI) must not activate rich."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        tui = _RunnerTUI(mode="auto")
        assert not tui._active

    def test_no_color_disables_tui(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)
        tui = _RunnerTUI(mode="auto")
        assert not tui._active

    def test_is_active_false_before_start(self):
        """is_active is False until start() is called (even if _active=True)."""
        tui = _RunnerTUI.__new__(_RunnerTUI)
        tui._live = None
        tui._active = True
        assert not tui.is_active

    def test_finish_is_noop_when_not_active(self):
        """finish() on a plain-mode TUI must not raise."""
        tui = _RunnerTUI(mode="plain")
        tui.finish()  # must not raise

    def test_on_line_buffers_stripped_lines(self):
        tui = _RunnerTUI(mode="plain")
        tui.on_line("hello\n")
        tui.on_line("world\n")
        assert tui._log_lines == ["hello", "world"]

    def test_log_buffer_capped_at_max(self):
        tui = _RunnerTUI(mode="plain")
        for i in range(_RunnerTUI.MAX_LOG_LINES + 5):
            tui.on_line(f"line {i}\n")
        assert len(tui._log_lines) == _RunnerTUI.MAX_LOG_LINES

    def test_on_category_updates_seen_list(self):
        tui = _RunnerTUI(mode="plain")
        tui._all_categories = ["smoke", "unit", "api"]
        tui.on_category({"smoke", "unit"}, test_count=12)
        assert set(tui._categories_seen) == {"smoke", "unit"}
        assert tui._test_count == 12

    def test_rich_mode_flag_in_config(self):
        """RunTestConfig accepts tui='rich' without error."""
        config = RunTestConfig(
            test_type=RunTestType.SMOKE,
            context=ExecutionContext.LOCALHOST,
            run_teardown=False,
            tui="rich",
        )
        assert config.tui == "rich"
