"""CLI entry point for the tests_runner package.

parse_arguments()  -- argparse setup; returns a list of RunTestConfig
main()             -- async orchestrator called by the shim
_extract_counts()  -- extract pass/fail/skip counts from a runner
_print_combined_summary() -- print multi-suite summary

These live here rather than in runner.py so the argparse definition is
separated from execution logic, matching the file-size target of the spec.
"""

from __future__ import annotations

import argparse
import logging
import shlex
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tests_runner.config import ExecutionContext, RunTestConfig, RunTestType  # noqa: E402
from tests_runner.env import load_dotenv as _load_dotenv_raw  # noqa: E402
from tests_runner.env import strip_cloud_llm_keys as _strip_cloud_llm_keys_raw
from tests_runner.runner import RunTestRunner  # noqa: E402

logger = logging.getLogger(__name__)


# Thin wrappers (matching signatures used in main())
def _load_dotenv() -> None:
    _load_dotenv_raw(project_root)


def _strip_cloud_llm_keys() -> None:
    _strip_cloud_llm_keys_raw()


def parse_arguments() -> list[RunTestConfig]:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Huntable CTI Studio Unified Test Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Execution Contexts:
  localhost    Run tests locally using virtual environment (default)
  docker       Run tests inside Docker containers
  auto         Automatically choose Docker or localhost based on test requirements (recommended)
  ci           Run tests in CI/CD environment

Test Types:
  smoke        Quick health check (~30s) - STATELESS (no containers needed)
  unit         Unit tests only (~1m) - STATELESS (no containers needed)
  api          API endpoint tests (~2m) - May need containers
  integration  System integration tests (~3m) - STATEFUL (auto-starts test containers)
  ui           Web interface tests (~5m) - May need containers
  ui-smoke     UI smoke tests (~2m) - STATELESS (pytest @smoke + @ui_smoke markers)
  ui-fast     UI fast subset (~15m) - STATELESS (ui minus @slow)
  ui-full     UI full suite (~45m) - STATEFUL (all UI tests)
  e2e          End-to-end tests (~3m) - STATEFUL (auto-starts test containers)
  all-no-ui    Full suite excluding UI + Playwright JS (~6m) - STATEFUL (auto-starts test containers)
  regression   Regression test marker category (usually stateless)
  contract     API/schema contract marker category (usually stateless)
  security     Security marker category (usually stateless)
  a11y         Accessibility marker category (usually stateless)
  performance  Performance tests (~2m) - May need containers
  ai           AI tests (~3m) - LIMITED (external APIs skipped, AI Assistant UI tests removed)
  ai-ui        AI UI tests only (~1m) - May need containers
  ai-integration AI integration tests (~2m) - STATEFUL (auto-starts test containers)
  all          Complete test suite (~8m) - STATEFUL (auto-starts test containers)
  coverage     Tests with coverage report - STATEFUL (auto-starts test containers)

Test Infrastructure:
  - Test containers (Postgres:5433, Redis:6380) auto-started for stateful tests
  - Environment guards enforce APP_ENV=test and TEST_DATABASE_URL
  - Cloud LLM API keys blocked by default (set ALLOW_CLOUD_LLM_IN_TESTS=true to allow)
  - Failure reports (timestamped): test-results/failures_*.log, test-results/junit_*.xml,
    test-results/report_*.html, test-results/reportlog_*.jsonl
  - Progress indicators show category-by-category execution

UI Test Sections (the 'ui' test type has two independent sections):
  Section 1 - Pytest: Python tests in tests/ui/ (e.g. test_ui_flows.py) using
              pytest-playwright. Runs via pytest. This is the bulk of the wall time.
  Section 2 - Node.js Playwright: TypeScript specs in tests/playwright/*.spec.ts
              using the Node.js @playwright/test runner with allure-playwright reporter.
              Totally separate runner, invoked via 'npx playwright test'.
  By default 'run_tests.py ui' runs both sections sequentially. Use the flags below to
  run them independently.

Examples:
  python run_tests.py smoke                    # Quick health check (stateless, fast)
  python run_tests.py unit --fail-fast         # Unit tests (stateless, no containers)
  python run_tests.py integration              # Integration tests (auto-starts containers)
  python run_tests.py ui                       # Full UI suite: both sections (pytest + Node.js Playwright)
  python run_tests.py ui --skip-playwright-js          # Section 1 only: pytest tests/ui/ (skip Node.js specs)
  python run_tests.py ui --playwright-only             # Section 2 only: Node.js tests/playwright/*.spec.ts (skip pytest)
  python run_tests.py ui --playwright-last-failed      # Rerun only failed Node.js Playwright tests (skips pytest)
  python run_tests.py ui --include-agent-config-tests  # Include tests that mutate agent/workflow config
  python run_tests.py all                      # Full suite (auto-starts containers)
  python run_tests.py --debug --verbose        # Debug mode with verbose output
  python run_tests.py --context localhost unit # Force localhost execution

Manual Container Management:
  make test-up          # Start test containers manually
  make test-down        # Stop test containers
  make test             # Run all tests (starts containers, runs tests, stops containers)
        """,
    )

    # Test type (positional argument -- accepts one or more types)
    valid_types = [t.value for t in RunTestType]
    parser.add_argument(
        "test_types",
        nargs="*",
        default=None,
        metavar="TEST_TYPE",
        help=f"Type(s) of tests to run (e.g. unit api smoke). Defaults to smoke. Choices: {', '.join(valid_types)}",
    )

    # Execution context
    parser.add_argument(
        "--context",
        type=str,
        choices=["localhost", "docker", "auto", "ci"],
        default="auto",
        help="Execution context (auto=recommended)",
    )
    parser.add_argument("--docker", action="store_true", help="Run tests in Docker containers")
    parser.add_argument("--ci", action="store_true", help="Run tests in CI/CD mode")

    # Test execution options
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--debug", action="store_true", help="Debug mode with detailed output")
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Run tests in parallel (requires pytest-xdist)",
    )
    parser.add_argument(
        "--serial",
        action="store_true",
        help="Disable pytest parallelism (UI runs default to -n 4); useful for debugging flakes",
    )
    parser.add_argument(
        "--area",
        choices=["agent-config", "workflow", "sources", "articles", "intelligence", "ui-misc", "quarantine"],
        help="Run only one Playwright feature project (no effect on pytest section)",
    )
    parser.add_argument("--coverage", action="store_true", help="Generate coverage report")
    parser.add_argument("--install", action="store_true", help="Install test dependencies")
    parser.add_argument("--no-teardown", action="store_true", help="Skip environment teardown after tests")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print resolved pytest/Playwright commands and env vars without starting containers or running tests",
    )

    # Test filtering
    parser.add_argument("--paths", nargs="+", help="Specific test paths to run")
    parser.add_argument("--markers", nargs="+", help="Test markers to include")
    parser.add_argument("--exclude-markers", nargs="+", help="Test markers to exclude")
    parser.add_argument(
        "--include-agent-config-tests",
        action="store_true",
        help="Include UI tests that mutate agent/workflow config (only for 'ui' type; default is to exclude them)",
    )
    parser.add_argument(
        "--include-slow",
        action="store_true",
        help="Include @pytest.mark.slow UI tests (performance, mobile, accessibility); excluded by default in 'ui' runs",
    )
    parser.add_argument(
        "--playwright-last-failed",
        action="store_true",
        help="Rerun only Playwright tests that failed in the last run (skips pytest; use after 'ui' run with failures)",
    )
    pw_scope = parser.add_mutually_exclusive_group()
    pw_scope.add_argument(
        "--skip-playwright-js",
        action="store_true",
        help="For 'ui' (and e2e/ai-ui/all/coverage): run pytest tests/ui only; "
        "skip npx Playwright tests/playwright (saves most UI wall time)",
    )
    pw_scope.add_argument(
        "--playwright-only",
        action="store_true",
        help="Run only the Node.js Playwright section (tests/playwright/*.spec.ts); skip pytest entirely",
    )
    parser.add_argument("--skip-real-api", action="store_true", help="Skip real API tests")

    # Output and reporting
    parser.add_argument(
        "--output-format",
        choices=["progress", "verbose", "quiet"],
        default="progress",
        help="Output format",
    )
    parser.add_argument("--fail-fast", "-x", action="store_true", help="Stop on first failure")
    parser.add_argument("--retry", type=int, default=0, help="Number of retries for failed tests")
    parser.add_argument("--timeout", type=int, help="Timeout for test execution in seconds")
    parser.add_argument(
        "--tui",
        choices=["auto", "rich", "plain"],
        default="auto",
        help=(
            "Terminal UI mode: auto (default, uses Rich on TTY), "
            "rich (force Rich Live TUI), plain (force plain streaming text)"
        ),
    )

    # Configuration
    parser.add_argument("--config", help="Path to test configuration file")

    args = parser.parse_args()

    # Determine execution context
    if args.docker:
        context = ExecutionContext.DOCKER
    elif args.ci:
        context = ExecutionContext.CI
    elif args.context == "auto":
        context = ExecutionContext.AUTO
    else:
        context = ExecutionContext(args.context)

    # Validate and build a config per requested test type (deduplicated, order-preserved)
    raw_types = args.test_types if args.test_types else ["smoke"]
    for t in raw_types:
        if t not in {tv.value for tv in RunTestType}:
            parser.error(f"invalid test type: '{t}' (choose from {', '.join(tv.value for tv in RunTestType)})")
    seen: set[str] = set()
    test_types: list[RunTestType] = []
    for t in raw_types:
        if t not in seen:
            seen.add(t)
            test_types.append(RunTestType(t))

    configs: list[RunTestConfig] = []
    for test_type in test_types:
        configs.append(
            RunTestConfig(
                test_type=test_type,
                context=context,
                verbose=args.verbose,
                debug=args.debug,
                parallel=args.parallel,
                serial=args.serial,
                playwright_project=args.area,
                coverage=args.coverage,
                install_deps=args.install,
                run_teardown=not args.no_teardown,
                skip_real_api=args.skip_real_api,
                test_paths=args.paths,
                markers=args.markers,
                exclude_markers=args.exclude_markers,
                include_agent_config_tests=args.include_agent_config_tests,
                include_slow=args.include_slow,
                playwright_last_failed=args.playwright_last_failed,
                skip_playwright_js=args.skip_playwright_js,
                playwright_only=args.playwright_only,
                config_file=args.config,
                output_format=args.output_format,
                fail_fast=args.fail_fast,
                retry_count=args.retry,
                timeout=args.timeout,
                dry_run=args.dry_run,
                tui=args.tui,
            )
        )

    return configs


async def main():
    """Main entry point."""
    _load_dotenv()
    _strip_cloud_llm_keys()
    try:
        # Parse configuration (one config per requested test type)
        configs = parse_arguments()

        # For multi-type runs with --coverage, all but the first coverage config
        # should append rather than reset, so the final report is combined.
        coverage_configs = [c for c in configs if c.coverage]
        for c in coverage_configs[1:]:
            c.cov_append = True

        overall_results: list[tuple[str, bool, dict[str, int]]] = []
        all_passed = True

        for config in configs:
            # Create test runner
            runner = RunTestRunner(config)

            # Dry-run: print resolved commands + env vars, skip setup/run/teardown
            if config.dry_run:
                print(f"\n--- dry-run: {config.test_type.value} ({config.context.value}) ---")
                pytest_cmd = runner._build_pytest_command()
                print(f"pytest:     {shlex.join(pytest_cmd)}")
                playwright_cmd = runner._build_playwright_command()
                if playwright_cmd is None:
                    print("playwright: (no Playwright section)")
                else:
                    print(f"playwright: {shlex.join(playwright_cmd)}")
                dry_env = runner._build_dry_run_env()
                print("env:")
                for k, v in dry_env.items():
                    print(f"  {k}={v}")
                continue

            # Setup environment
            if not await runner.setup_environment():
                logger.error(f"Failed to setup test environment for {config.test_type.value}")
                overall_results.append((config.test_type.value, False, {}, []))
                all_passed = False
                continue

            try:
                # Run tests
                success = runner.run_tests()

                # Generate enhanced report for this type
                runner.print_enhanced_summary()

                counts = _extract_counts(runner)
                overall_results.append((config.test_type.value, success, counts, list(runner.failed_test_names)))
                if not success:
                    all_passed = False

            finally:
                # Teardown environment
                await runner.teardown_environment()

        # Print combined summary when multiple types were requested (skip if all were dry-runs)
        if len(configs) > 1 and overall_results:
            _print_combined_summary(overall_results)

        return 0 if all_passed else 1

    except KeyboardInterrupt:
        logger.info("Test execution interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Test runner failed: {e}")
        logger.exception("Full traceback:")
        return 1


def _extract_counts(runner: RunTestRunner) -> dict[str, int]:
    """Aggregate passed/failed/skipped counts from a runner's results."""
    passed = failed = skipped = 0
    for key in ("pytest", "playwright"):
        if key in runner.results and "counts" in runner.results[key]:
            c = runner.results[key]["counts"]
            passed += c.get("passed", 0)
            failed += c.get("failed", 0) + c.get("errors", 0)
            skipped += c.get("skipped", 0)
    return {"passed": passed, "failed": failed, "skipped": skipped}


def _print_combined_summary(results: list[tuple[str, bool, dict[str, int], list[str]]]) -> None:
    """Print a final combined summary across all test types."""
    GREEN = "\033[32m"
    RED = "\033[31m"
    YELLOW = "\033[33m"
    DIM = "\033[2m"
    RESET = "\033[0m"

    # Collect all failed tests across all types for the failure listing
    all_failed_names: list[tuple[str, str]] = []  # (test_type, test_name)
    for test_type, passed, counts, failed_names in results:
        if not passed:
            for name in failed_names:
                all_failed_names.append((test_type, name))

    # Print failed test listing above the table
    if all_failed_names:
        print("\n")
        print("=" * 72)
        print(f"  {RED}FAILED TESTS{RESET}")
        print("=" * 72)
        current_type = None
        for test_type, name in all_failed_names:
            if test_type != current_type:
                current_type = test_type
                print(f"\n  [{test_type}]")
            print(f"    {RED}x{RESET} {name}")
        print()

    print("=" * 72)
    print("  COMBINED TEST SUMMARY")
    print("=" * 72)
    print(f"  {'Type':<16s} {'Passed':>8s} {'Failed':>8s} {'Skipped':>8s}   Status")
    print(f"  {'-' * 16} {'-' * 8} {'-' * 8} {'-' * 8}   {'-' * 8}")

    totals = {"passed": 0, "failed": 0, "skipped": 0}
    all_passed = True

    for test_type, passed, counts, _failed_names in results:
        p = counts.get("passed", 0)
        f = counts.get("failed", 0)
        s = counts.get("skipped", 0)
        totals["passed"] += p
        totals["failed"] += f
        totals["skipped"] += s

        status = f"{GREEN}PASSED{RESET}" if passed else f"{RED}FAILED{RESET}"
        p_str = f"{GREEN}{p:>8d}{RESET}" if p else f"{DIM}{p:>8d}{RESET}"
        f_str = f"{RED}{f:>8d}{RESET}" if f else f"{DIM}{f:>8d}{RESET}"
        s_str = f"{YELLOW}{s:>8d}{RESET}" if s else f"{DIM}{s:>8d}{RESET}"
        print(f"  {test_type:<16s} {p_str} {f_str} {s_str}   {status}")
        if not passed:
            all_passed = False

    print(f"  {'-' * 16} {'-' * 8} {'-' * 8} {'-' * 8}   {'-' * 8}")
    tp, tf, ts = totals["passed"], totals["failed"], totals["skipped"]
    overall = f"{GREEN}ALL PASSED{RESET}" if all_passed else f"{RED}SOME FAILED{RESET}"
    print(f"  {'Total':<16s} {tp:>8d} {tf:>8d} {ts:>8d}   {overall}")
    print("=" * 72)
    print()
