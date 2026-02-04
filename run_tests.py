#!/usr/bin/env python3
"""
CTI Scraper Unified Test Runner

This is the single entry point for all test execution needs across different contexts.
Consolidates functionality from run_tests.py, run_tests.sh, and run_tests_standardized.py.

Features:
- Context-aware execution (localhost, Docker, CI/CD)
- Standardized environment management with safety guards
- Enhanced error reporting and debugging
- Comprehensive test discovery and execution
- Rich output formatting and reporting with progress indicators
- Automatic test container management for stateful tests
- Backward compatibility with existing interfaces

Test Infrastructure:
- Test environment guards prevent production database access
  * Requires APP_ENV=test and TEST_DATABASE_URL (auto-set by wrapper)
  * Blocks cloud LLM API keys by default (set ALLOW_CLOUD_LLM_IN_TESTS=true to allow)
- Test containers auto-started for stateful tests (integration, e2e, all)
  * Postgres:5433, Redis:6380, Web:8002 (isolated from production ports)
  * Ephemeral containers (no named volumes, data destroyed on removal)
- Failure reports automatically generated (with timestamps to preserve history):
  * test-results/failures_YYYYMMDD_HHMMSS.log - Text summary of all failures
  * test-results/junit_YYYYMMDD_HHMMSS.xml - Machine-readable XML format
  * test-results/report_YYYYMMDD_HHMMSS.html - Interactive HTML report (if pytest-html available)
  * allure-results/ - Allure report data (use 'allure serve allure-results')
- Progress indicators show category-by-category execution in real-time

Usage:
    python run_tests.py --help                    # Show all options
    python run_tests.py smoke                     # Quick health check (stateless, no containers)
    python run_tests.py unit                      # Unit tests (stateless, runs locally)
    python run_tests.py integration               # Integration tests (stateful, auto-starts containers)
    python run_tests.py ui                        # UI tests (may auto-start containers)
    python run_tests.py all                       # Full test suite (auto-starts containers)
    python run_tests.py --debug --verbose         # Debug mode with verbose output

Manual Container Management:
    make test-up          # Start test containers manually
    make test-down        # Stop test containers
    make test             # Run all tests (starts containers, runs tests, stops containers)
"""

import argparse
import asyncio
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Import test environment utilities
try:
    from tests.utils.database_connections import (
        validate_database_connection,
        validate_redis_connection,
    )
    from tests.utils.test_environment import (
        TestContext,
        TestEnvironmentManager,
        TestEnvironmentValidator,
        get_test_config,
        validate_test_environment,
    )

    ENVIRONMENT_UTILS_AVAILABLE = True
except ImportError:
    ENVIRONMENT_UTILS_AVAILABLE = False
    print("Warning: Test environment utilities not available. Some features may be limited.")

# Enhanced debugging imports
try:
    from tests.utils.test_failure_analyzer import TestFailureReporter
    from tests.utils.test_isolation import TestIsolationManager
    from tests.utils.test_output_formatter import (
        TestOutputFormatter,
        print_header,
        print_summary,
        print_test_result,
    )

    from tests.utils.async_debug_utils import AsyncDebugger
    from tests.utils.performance_profiler import (
        PerformanceProfiler,
        start_performance_monitoring,
        stop_performance_monitoring,
    )

    DEBUGGING_AVAILABLE = True
except ImportError as e:
    DEBUGGING_AVAILABLE = False
    print(f"Warning: Enhanced debugging utilities not available: {e}")
    print("Enhanced debugging features will not be available.")

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class TestType(Enum):
    """Test execution types."""

    SMOKE = "smoke"
    UNIT = "unit"
    API = "api"
    INTEGRATION = "integration"
    UI = "ui"
    E2E = "e2e"
    PERFORMANCE = "performance"
    AI = "ai"
    AI_UI = "ai-ui"
    AI_INTEGRATION = "ai-integration"
    ALL = "all"
    COVERAGE = "coverage"


class ExecutionContext(Enum):
    """Test execution contexts."""

    LOCALHOST = "localhost"
    DOCKER = "docker"
    CI = "ci"
    AUTO = "auto"  # Automatically choose based on test requirements


@dataclass
class TestConfig:
    """Test execution configuration."""

    test_type: TestType
    context: ExecutionContext
    verbose: bool = False
    debug: bool = False
    parallel: bool = False
    coverage: bool = False
    install_deps: bool = False
    validate_env: bool = True
    skip_real_api: bool = False
    test_paths: list[str] | None = None
    markers: list[str] | None = None
    exclude_markers: list[str] | None = None
    config_file: str | None = None
    output_format: str = "progress"
    fail_fast: bool = False
    retry_count: int = 0
    timeout: int | None = None


class TestRunner:
    """Unified test runner with enhanced functionality."""

    def __init__(self, config: TestConfig):
        self.config = config
        self.start_time = time.time()
        # Generate timestamp for result filenames (filesystem-safe format)
        from datetime import datetime

        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.results = {}
        self.environment_manager = None
        self.test_groups_executed = []  # Track which test groups were run

        # Virtual environment paths - always use .venv
        self.venv_python = self._ensure_venv()
        self.venv_pip = self.venv_python.replace("python3", "pip")

        # Enhanced debugging components
        self.failure_reporter = None
        self.async_debugger = None
        self.isolation_manager = None
        self.performance_profiler = None
        self.output_formatter = None

        # Initialize debugging components if available
        if DEBUGGING_AVAILABLE:
            self.failure_reporter = TestFailureReporter()
            self.async_debugger = AsyncDebugger()
            self.isolation_manager = TestIsolationManager()
            self.performance_profiler = PerformanceProfiler()
            self.output_formatter = TestOutputFormatter()

        # Set up logging level
        if config.debug:
            logging.getLogger().setLevel(logging.DEBUG)
        elif config.verbose:
            logging.getLogger().setLevel(logging.INFO)

    def _ensure_venv(self) -> str:
        """Ensure virtual environment exists and return its Python path."""
        venv_path = ".venv"
        venv_python = os.path.join(venv_path, "bin", "python3")

        # Check if .venv exists
        if not os.path.exists(venv_path):
            logger.info("Creating virtual environment at .venv...")
            subprocess.run(["python3", "-m", "venv", venv_path], check=True, capture_output=True)
            logger.info("Virtual environment created")

        # Verify venv python exists
        if not os.path.exists(venv_python):
            logger.warning(f"Virtual environment Python not found at {venv_python}, falling back to system python3")
            return "python3"

        logger.info(f"Using virtual environment: {venv_python}")
        return venv_python

    async def setup_environment(self) -> bool:
        """Set up test environment."""
        # Check if test containers are needed for stateful tests
        stateful_test_types = {
            TestType.INTEGRATION,
            TestType.E2E,
            TestType.ALL,
            TestType.COVERAGE,
        }

        needs_test_containers = self.config.test_type in stateful_test_types

        if needs_test_containers:
            logger.info("Stateful tests detected - checking for test containers...")
            # Check if test containers are running
            result = subprocess.run(
                ["docker", "ps", "--filter", "name=cti_postgres_test", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                check=False,
            )
            if "cti_postgres_test" not in result.stdout:
                logger.warning("Test containers not running. Starting test containers...")
                logger.info("Run 'make test-up' or './scripts/test_setup.sh' to start containers")
                logger.info("Or the test runner will attempt to start them automatically...")

                # Try to start containers
                setup_script = Path("scripts/test_setup.sh")
                if setup_script.exists():
                    result = subprocess.run([str(setup_script)], capture_output=True, text=True, check=False)
                    if result.returncode != 0:
                        logger.error("Failed to start test containers")
                        logger.error(f"Error: {result.stderr}")
                        return False
                    logger.info("Test containers started successfully")
                else:
                    logger.error("Test setup script not found. Please run 'make test-up' manually")
                    return False

        # Set up test environment variables
        os.environ["APP_ENV"] = "test"

        # Set TEST_DATABASE_URL if not already set
        if "TEST_DATABASE_URL" not in os.environ:
            postgres_password = os.getenv("POSTGRES_PASSWORD", "cti_password")
            os.environ["TEST_DATABASE_URL"] = (
                f"postgresql+asyncpg://cti_user:{postgres_password}@localhost:5433/cti_scraper_test"
            )
            logger.info("Auto-set TEST_DATABASE_URL (port 5433 for test containers)")

        # Invoke test environment guard
        try:
            from tests.utils.test_environment import assert_test_environment

            assert_test_environment()
            logger.info("Test environment guard passed")
        except ImportError:
            logger.warning("Test environment guard not available - tests may not be properly isolated")
        except RuntimeError as e:
            logger.error(f"Test environment guard failed: {e}")
            if not self.config.debug:
                return False
            logger.warning("Continuing despite guard failure (debug mode)")

        if not ENVIRONMENT_UTILS_AVAILABLE:
            logger.warning("Environment utilities not available, skipping advanced environment setup")
            return True

        try:
            logger.info("Setting up test environment...")

            # Load configuration
            validator = TestEnvironmentValidator()
            test_config = validator.load_test_config(self.config.config_file)

            # Validate environment if requested
            if self.config.validate_env:
                logger.info("Validating test environment...")
                validation_results = await validator.validate_environment()

                # For smoke tests, Redis validation is non-blocking
                critical_validations = validation_results.copy()
                if self.config.test_type == TestType.SMOKE:
                    if "redis" in critical_validations and not critical_validations["redis"]:
                        logger.warning("Redis validation failed (non-blocking for smoke tests)")
                        critical_validations.pop("redis")

                if not all(critical_validations.values()):
                    logger.error("Environment validation failed")
                    if not self.config.debug:
                        return False
                    logger.warning("Continuing despite validation failures (debug mode)")

            # Set up environment manager
            self.environment_manager = TestEnvironmentManager(test_config)
            await self.environment_manager.setup_test_environment()

            logger.info("Test environment setup completed")
            return True

        except Exception as e:
            logger.error(f"Environment setup failed: {e}")
            if self.config.debug:
                logger.exception("Full traceback:")
            return False

    async def teardown_environment(self):
        """Tear down test environment."""
        # Check if we started test containers and should tear them down
        # For now, we leave containers running (user can run 'make test-down' manually)
        # This allows faster subsequent test runs

        # Skip teardown if validation was skipped (no test DB configured)
        if not self.config.validate_env:
            logger.debug("Skipping teardown (validation disabled)")
            return

        if self.environment_manager:
            try:
                await self.environment_manager.teardown_test_environment()
                logger.info("Test environment teardown completed")
            except Exception as e:
                logger.error(f"Environment teardown failed: {e}")
                if self.config.debug:
                    logger.exception("Full traceback:")

        # Note: Test containers are left running for faster subsequent runs
        # User can run 'make test-down' to stop them

    def install_dependencies(self) -> bool:
        """Install test dependencies."""
        logger.info("Installing test dependencies...")

        # Virtual environment is already set up in __init__

        # Install from requirements files
        commands = [
            (f"{self.venv_pip} install --upgrade pip", "Upgrading pip"),
            (
                f"{self.venv_pip} install -r requirements.txt",
                "Installing project dependencies",
            ),
        ]

        # Add test requirements if it exists (non-blocking)
        if os.path.exists("requirements-test.txt"):
            try:
                logger.info("Attempting to install test dependencies (may have conflicts, continuing if it fails)...")
                commands.append(
                    (
                        f"{self.venv_pip} install -r requirements-test.txt",
                        "Installing test dependencies",
                    )
                )
            except Exception:
                logger.warning("Test dependencies not installed, continuing without them")

        # Install Playwright if it's installed
        result = subprocess.run(
            [self.venv_python, "-c", "import playwright"],
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            commands.append(
                (
                    f"{self.venv_python} -m playwright install chromium",
                    "Installing Playwright browser",
                )
            )

        # Track which commands are optional
        optional_commands = ["Installing test dependencies"]

        for cmd, description in commands:
            result = self._run_command(cmd, description, capture_output=True)
            if not result and description not in optional_commands:
                logger.error(f"Failed to {description.lower()}")
                return False
            if not result:
                logger.warning(f"Optional step failed: {description}")

        logger.info("Dependencies installed successfully")
        return True

    def _check_dependencies(self) -> bool:
        """Check if essential test dependencies are available in venv."""
        try:
            result = subprocess.run(
                [self.venv_python, "-c", "import pytest; import pytest_asyncio"],
                capture_output=True,
                check=False,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _check_playwright_dependencies(self) -> bool:
        """Check if Playwright and npm dependencies are available."""
        try:
            # Check if npm/node is available
            result = subprocess.run(["npm", "--version"], capture_output=True, check=False)
            if result.returncode != 0:
                return False

            # Check if package.json exists and has dependencies installed
            if not os.path.exists("package.json"):
                return False

            # Check if node_modules exists (dependencies installed)
            if not os.path.exists("node_modules"):
                return False

            # Check if allure-playwright is installed
            result = subprocess.run(["npm", "list", "allure-playwright"], capture_output=True, check=False)
            return result.returncode == 0
        except Exception:
            return False

    def _get_pytest_test_groups(self) -> list[str]:
        """Determine which pytest test groups are being executed based on test type."""
        test_type = self.config.test_type

        if self.config.test_paths:
            # Custom paths specified - analyze them
            groups = []
            for path in self.config.test_paths:
                if "smoke" in path:
                    groups.append("smoke")
                elif "api" in path:
                    groups.append("api")
                elif "integration" in path:
                    groups.append("integration")
                elif "ui" in path:
                    groups.append("ui")
                elif "e2e" in path:
                    groups.append("e2e")
                elif "cli" in path:
                    groups.append("cli")
                elif "workflows" in path:
                    groups.append("workflows")
                elif "services" in path:
                    groups.append("services")
                elif "core" in path:
                    groups.append("core")
                elif "utils" in path:
                    groups.append("utils")
            return list(set(groups)) if groups else ["all"]

        # Map test types to groups
        group_map = {
            TestType.SMOKE: ["smoke"],
            TestType.UNIT: ["unit", "core", "services", "utils"],
            TestType.API: ["api"],
            TestType.INTEGRATION: ["integration"],
            TestType.UI: ["ui"],
            TestType.E2E: ["e2e"],
            TestType.PERFORMANCE: ["performance"],
            TestType.AI: ["ai", "ui", "integration"],
            TestType.AI_UI: ["ai", "ui"],
            TestType.AI_INTEGRATION: ["ai", "integration"],
            TestType.ALL: ["all"],
            TestType.COVERAGE: ["all"],
        }

        return group_map.get(test_type, ["all"])

    def _get_playwright_test_groups(self) -> list[str]:
        """Determine which Playwright test groups are being executed."""
        if not self._build_playwright_command():
            return []

        groups = []
        playwright_cmd = self._build_playwright_command()
        if playwright_cmd:
            for arg in playwright_cmd:
                if "playwright" in arg:
                    groups.append("playwright")
                elif "help_buttons" in arg:
                    groups.append("help-buttons")

        return groups if groups else ["playwright"]

    def _build_playwright_command(self) -> list[str]:
        """Build Playwright test command based on configuration."""
        # Use tests/ config so testIgnore and paths resolve correctly when cwd is project root
        cmd = ["npx", "playwright", "test", "--config", "tests/playwright.config.ts"]

        # Determine which Playwright tests to run based on test type
        test_path_map = {
            TestType.SMOKE: [],  # Skip Playwright in smoke tests
            TestType.UNIT: [],  # Skip Playwright in unit tests
            TestType.API: [],  # Skip Playwright in API tests
            TestType.INTEGRATION: [],  # Skip Playwright in integration tests (Python-based)
            TestType.UI: ["tests/playwright/", "tests/test_help_buttons.spec.js"],
            TestType.E2E: ["tests/playwright/", "tests/test_help_buttons.spec.js"],
            TestType.PERFORMANCE: [],  # Skip Playwright in performance tests
            TestType.AI: [],  # Skip Playwright in AI tests (Python-based)
            TestType.AI_UI: ["tests/playwright/", "tests/test_help_buttons.spec.js"],
            TestType.AI_INTEGRATION: [],  # Skip Playwright in AI integration tests
            TestType.ALL: ["tests/playwright/", "tests/test_help_buttons.spec.js"],
            TestType.COVERAGE: ["tests/playwright/", "tests/test_help_buttons.spec.js"],
        }

        if self.config.test_type in test_path_map:
            test_paths = test_path_map[self.config.test_type]
            if test_paths:
                cmd.extend(test_paths)
            else:
                # No Playwright tests for this test type
                return None
        else:
            # Default: run all Playwright tests
            cmd.extend(["tests/playwright/", "tests/test_help_buttons.spec.js"])

        # Add verbosity
        if self.config.verbose or self.config.debug:
            cmd.append("--reporter=list")

        # Allure is configured in playwright.config.ts, so no need to add it here

        return cmd

    def _run_command(self, cmd: str, description: str, capture_output: bool = True) -> bool:
        """Run a command and return success status."""
        logger.info(f"🔄 {description}")

        if self.config.debug:
            logger.debug(f"Command: {cmd}")

        try:
            result = subprocess.run(
                cmd,
                shell=True,
                check=True,
                capture_output=capture_output,
                text=True,
                timeout=self.config.timeout,
            )

            logger.info(f"✅ {description} completed successfully")

            if capture_output and result.stdout and self.config.verbose:
                logger.info(f"Output: {result.stdout}")

            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"❌ {description} failed")
            logger.error(f"Error: {e}")

            if capture_output:
                if e.stdout:
                    logger.error(f"Stdout: {e.stdout}")
                if e.stderr:
                    logger.error(f"Stderr: {e.stderr}")

            return False

        except subprocess.TimeoutExpired as e:
            logger.error(f"⏰ {description} timed out after {e.timeout} seconds")
            return False

        except Exception as e:
            logger.error(f"💥 Unexpected error in {description}: {e}")
            if self.config.debug:
                logger.exception("Full traceback:")
            return False

    def _requires_docker(self, test_type: TestType) -> bool:
        """Determine if a test type requires Docker execution.

        Most tests can run on the host and connect to test containers via exposed ports:
        - Database: localhost:5433
        - Redis: localhost:6380
        - Web server: localhost:8001 (if running)

        Only tests that truly need Docker environment should run there.
        """
        # Test types that require Docker execution (very few)
        # Most tests can run on host and connect to containers via exposed ports
        docker_required = {
            # Only add test types here if they truly need Docker environment
            # (e.g., testing Docker-specific behavior, internal container networking)
        }

        return test_type in docker_required

    def _get_effective_context(self, test_type: TestType) -> ExecutionContext:
        """Get the effective execution context, auto-selecting Docker when needed."""
        if self.config.context == ExecutionContext.AUTO:
            if self._requires_docker(test_type):
                logger.info(
                    f"Auto-selecting Docker context for {test_type.value} tests (requires full application stack)"
                )
                return ExecutionContext.DOCKER
            logger.info(f"Auto-selecting localhost context for {test_type.value} tests")
            return ExecutionContext.LOCALHOST
        return self.config.context

    def _build_pytest_command(self) -> list[str]:
        """Build pytest command based on configuration."""
        cmd = ["python3", "-m", "pytest"]

        # Add test paths
        if self.config.test_paths:
            # Normalize test paths, especially for Docker where /app is the root.
            resolved_paths = []
            effective_context = self._get_effective_context(self.config.test_type)
            for path in self.config.test_paths:
                # Strip leading ./ for consistency
                normalized = path.lstrip("./")
                if effective_context == ExecutionContext.DOCKER:
                    if not normalized.startswith("/"):
                        normalized = f"/app/{normalized}"
                    resolved_paths.append(normalized)
                else:
                    resolved_paths.append(path)
            cmd.extend(resolved_paths)
        else:
            # Default test paths based on test type
            test_path_map = {
                TestType.SMOKE: [
                    "tests/",
                    "-m",
                    "smoke",
                ],  # Restrict to tests/ directory to avoid collection errors
                TestType.UNIT: [
                    "tests/",
                    "--ignore=tests/test_web_application.py",  # Exclude web app tests (require running server)
                    "--ignore=tests/ui/",  # Exclude UI tests (require browser/Playwright)
                    "-m",
                    "not (smoke or integration or api or ui or e2e or performance or infrastructure or prod_data or production_data)",
                ],
                TestType.API: ["tests/api/"],
                TestType.INTEGRATION: [
                    "tests/integration/",
                    "-m",
                    "integration_workflow",
                ],
                TestType.UI: ["tests/ui/"],
                TestType.E2E: ["tests/e2e/"],
                TestType.PERFORMANCE: ["tests/", "-m", "performance"],
                TestType.AI: [
                    # "tests/ui/test_ai_assistant_ui.py",  # DEPRECATED: AI Assistant modal removed
                    "tests/integration/test_ai_*.py",
                    "-m",
                    "ai",
                ],
                TestType.AI_UI: [
                    # "tests/ui/test_ai_assistant_ui.py",  # DEPRECATED: AI Assistant modal removed
                    "-m",
                    "ui and ai",
                ],
                TestType.AI_INTEGRATION: [
                    "tests/integration/test_ai_*.py",
                    "-m",
                    "integration and ai",
                ],
                TestType.ALL: ["tests/"],
                TestType.COVERAGE: ["tests/", "--cov=src"],
            }

            if self.config.test_type in test_path_map:
                cmd.extend(test_path_map[self.config.test_type])
            else:
                cmd.append("tests/")

        # Markers: apply defaults per test type, then exclusions
        default_markers_map = {
            TestType.SMOKE: ["smoke"],
            TestType.UNIT: [],  # Unit tests: exclude other types, don't require unit marker
            TestType.API: ["api"],
            TestType.INTEGRATION: ["integration"],
            TestType.UI: ["ui"],
            TestType.E2E: ["e2e"],
            TestType.PERFORMANCE: ["performance"],
            TestType.AI: ["ai"],
            TestType.AI_UI: ["ai", "ui"],
            TestType.AI_INTEGRATION: ["ai", "integration"],
        }

        markers = self.config.markers or default_markers_map.get(self.config.test_type, [])
        marker_expr = " or ".join(markers) if markers else ""

        # Always exclude infrastructure and production data tests by default
        default_excludes = ["infrastructure", "prod_data", "production_data"]
        # Keep smoke fast and under 30 seconds total - exclude UI tests that require browsers
        # UI tests can hang if browsers aren't installed, so exclude them from smoke for speed
        if self.config.test_type == TestType.SMOKE:
            default_excludes.extend(["slow", "ui", "ui_smoke"])
        # For unit tests, exclude integration/api/ui/e2e/performance but don't require unit marker
        elif self.config.test_type == TestType.UNIT:
            default_excludes.extend(["integration", "api", "ui", "ui_smoke", "e2e", "performance", "smoke"])
        if self.config.exclude_markers:
            all_excludes = default_excludes + self.config.exclude_markers
        else:
            all_excludes = default_excludes

        exclude_expr = " and ".join([f"not {marker}" for marker in all_excludes])

        if marker_expr:
            combined_expr = f"({marker_expr}) and ({exclude_expr})"
        else:
            combined_expr = exclude_expr

        cmd.extend(["-m", combined_expr])

        # Add execution context specific options
        effective_context = self._get_effective_context(self.config.test_type)
        if effective_context == ExecutionContext.DOCKER:
            logger.info("Running tests in Docker container (cti_web)")
            # Use system Python in Docker container, not virtual environment
            cmd[0] = "/usr/local/bin/python3"
            # Pass environment variables to Docker container
            # Get TEST_DATABASE_URL from environment (set earlier in setup)
            test_db_url = os.getenv("TEST_DATABASE_URL", "")
            docker_env_vars = ["-e", "APP_ENV=test"]
            # Unset DATABASE_URL to prevent test guard from rejecting production DB
            docker_env_vars.extend(["-e", "DATABASE_URL="])
            if test_db_url:
                docker_env_vars.extend(["-e", f"TEST_DATABASE_URL={test_db_url}"])
            cmd = ["docker", "exec"] + docker_env_vars + ["cti_web"] + cmd
        else:
            # Use virtual environment python for localhost execution
            cmd[0] = self.venv_python
            if effective_context == ExecutionContext.AUTO:
                # This shouldn't happen as _get_effective_context should resolve AUTO
                logger.warning("Auto context not resolved, defaulting to localhost")
            else:
                logger.info("Running tests on localhost")

        # Add parallel execution
        if self.config.parallel:
            logger.warning("Parallel execution requires pytest-xdist. Install with: pip install pytest-xdist")
            cmd.extend(["-n", "auto"])

        # Add coverage
        if self.config.coverage:
            cmd.extend(
                [
                    "--cov=src",
                    "--cov-report=html:htmlcov",
                    "--cov-report=xml:coverage.xml",
                    "--cov-report=term-missing",
                ]
            )

        # Add output format - default to verbose for better visibility
        if self.config.output_format == "progress":
            # Use verbose by default for better visibility, but allow quiet override
            cmd.append("-v" if self.config.verbose else "-v")  # Always verbose for visibility
        elif self.config.output_format == "verbose":
            cmd.append("-vv")  # Extra verbose
        elif self.config.output_format == "quiet":
            cmd.append("-q")
        else:
            cmd.append("-v")  # Default to verbose

        # Add debugging options
        if self.config.debug:
            cmd.extend(["--tb=long", "--capture=no", "-s"])
        else:
            cmd.extend(["--tb=short"])

        # Add fail fast
        if self.config.fail_fast:
            cmd.extend(["-x", "--maxfail=1"])

        # Add retry
        if self.config.retry_count > 0:
            cmd.extend(["--maxfail=1", f"--reruns={self.config.retry_count}"])

        # Timeout is enforced via subprocess.run(timeout=...), avoid passing
        # pytest-timeout flag unless plugin is guaranteed available.

        # Add reporting (only if allure is available in venv)
        try:
            result = subprocess.run(
                [self.venv_python, "-c", "import allure"],
                capture_output=True,
                check=False,
            )
            if result.returncode == 0:
                cmd.extend(["--alluredir=allure-results"])
        except Exception:
            pass

        # Add JUnit XML report for CI/CD and failure analysis
        # Note: test-results directory is created before this method is called
        # Include timestamp to preserve historical results
        cmd.extend([f"--junit-xml=test-results/junit_{self.timestamp}.xml"])

        # Add HTML report (only if pytest-html is installed)
        # NOTE: Disabled by default due to FileNotFoundError issues with pytest-html
        # The plugin tries to write during test execution, causing crashes
        # Users can enable with --html flag manually if needed
        # try:
        #     result = subprocess.run(
        #         [self.venv_python, "-c", "import pytest_html"],
        #         capture_output=True,
        #         check=False,
        #     )
        #     if result.returncode == 0:
        #         test_results_dir = Path("test-results")
        #         if test_results_dir.exists():
        #             cmd.extend([f"--html=test-results/report_{self.timestamp}.html", "--self-contained-html"])
        # except Exception:
        #     pass

        return cmd

    def run_tests(self) -> bool:
        """Run tests based on configuration."""
        logger.info(f"Running {self.config.test_type.value} tests in {self.config.context.value} context")

        # Start debugging components
        self.start_debugging()

        try:
            # Check if dependencies are available, install if missing
            if not self._check_dependencies():
                logger.info("Missing test dependencies detected, installing...")
                if not self.install_dependencies():
                    return False

            # Install dependencies if explicitly requested
            if self.config.install_deps:
                if not self.install_dependencies():
                    return False

            # Determine if we should run Playwright tests
            playwright_cmd = self._build_playwright_command()
            run_playwright = playwright_cmd is not None

            # Install Playwright dependencies if needed
            if run_playwright and not self._check_playwright_dependencies():
                logger.info("Installing Playwright dependencies...")
                if not self._install_playwright_dependencies():
                    logger.warning("Failed to install Playwright dependencies, skipping Playwright tests")
                    run_playwright = False

            # Set environment variables
            env = os.environ.copy()

            # Ensure APP_ENV=test is set (required by test environment guard)
            env["APP_ENV"] = "test"

            # Ensure TEST_DATABASE_URL is set (required for stateful tests)
            if "TEST_DATABASE_URL" not in env:
                postgres_password = os.getenv("POSTGRES_PASSWORD", "cti_password")
                env["TEST_DATABASE_URL"] = (
                    f"postgresql+asyncpg://cti_user:{postgres_password}@localhost:5433/cti_scraper_test"
                )

            if ENVIRONMENT_UTILS_AVAILABLE:
                try:
                    validator = TestEnvironmentValidator()
                    test_config = validator.load_test_config(self.config.config_file)
                    # Only override if not already set (preserve TEST_DATABASE_URL)
                    if "DATABASE_URL" not in env or env.get("DATABASE_URL") == test_config.database_url:
                        env.update(
                            {
                                "DATABASE_URL": test_config.database_url,
                                "REDIS_URL": test_config.redis_url,
                                "TESTING": "true",
                                "ENVIRONMENT": "test",
                            }
                        )
                except Exception as e:
                    logger.warning(f"Could not set environment variables: {e}")

            # Add skip real API flag
            if self.config.skip_real_api:
                env["SKIP_REAL_API_TESTS"] = "1"

            env.update(self._get_agent_config_exclude_env())

            # Run pytest tests (always run pytest, except when only Playwright tests are needed)
            pytest_success = True
            pytest_start_time = time.time()

            # CRITICAL: Ensure directories exist BEFORE building command
            # pytest-html writes during test execution (not just at end), so directory must exist
            test_results_dir = Path("test-results")
            test_results_dir.mkdir(parents=True, exist_ok=True)

            # Also ensure allure-results exists
            allure_results_dir = Path("allure-results")
            allure_results_dir.mkdir(parents=True, exist_ok=True)

            # Verify directories were created
            if not test_results_dir.exists():
                logger.error("Failed to create test-results directory")
                return False

            # Build and run pytest command
            cmd = self._build_pytest_command()
            cmd_str = " ".join(cmd)

            # Determine which test groups are being executed
            pytest_groups = self._get_pytest_test_groups()
            if pytest_groups:
                self.test_groups_executed.extend([f"pytest:{group}" for group in pytest_groups])

            print("\n" + "=" * 80)
            print("🧪 RUNNING PYTEST TESTS")
            if pytest_groups:
                print(f"   Test Categories: {', '.join(pytest_groups)}")
                print(f"   Progress: [{' ' * len(pytest_groups)}] 0/{len(pytest_groups)} categories")
            print("=" * 80)
            logger.info(f"Executing pytest: {cmd_str}")
            print()

            try:
                # Run with real-time output for progress visibility
                process = subprocess.Popen(
                    cmd,
                    env=env,
                    cwd=project_root,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,  # Line buffered
                )

                # Track progress by parsing output in real-time
                output_lines = []
                categories_seen = set()
                test_count = 0
                last_progress_update = time.time()

                # Print output line by line and track progress
                for line in process.stdout:
                    output_lines.append(line)
                    print(line, end="", flush=True)

                    # Parse test execution lines to detect categories
                    if "::" in line and ("PASSED" in line or "FAILED" in line or "SKIPPED" in line or "ERROR" in line):
                        test_count += 1
                        # Extract category from test path
                        if "tests/" in line:
                            try:
                                path_part = line.split("tests/")[1].split("/")[0]
                                category_map = {
                                    "services": "services",
                                    "utils": "utils",
                                    "api": "api",
                                    "integration": "integration",
                                    "ui": "ui",
                                    "e2e": "e2e",
                                    "docs": "docs",
                                }
                                detected_category = category_map.get(path_part)
                                if detected_category and detected_category not in categories_seen:
                                    categories_seen.add(detected_category)
                                    elapsed = time.time() - pytest_start_time
                                    progress_chars = (
                                        ["=" if cat in categories_seen else " " for cat in pytest_groups]
                                        if pytest_groups
                                        else []
                                    )
                                    progress_bar = "".join(progress_chars)
                                    print(
                                        f"\n📊 Category: {detected_category.upper()} | Progress: [{progress_bar}] {len(categories_seen)}/{len(pytest_groups) if pytest_groups else 1} | Tests: {test_count} | Time: {elapsed:.1f}s",
                                        flush=True,
                                    )
                            except (IndexError, AttributeError):
                                pass  # Ignore parsing errors

                    # Update progress indicator periodically (every 3 seconds)
                    if time.time() - last_progress_update > 3.0 and pytest_groups:
                        elapsed = time.time() - pytest_start_time
                        progress_chars = ["=" if cat in categories_seen else " " for cat in pytest_groups]
                        progress_bar = "".join(progress_chars)
                        print(
                            f"\r⏳ Overall: [{progress_bar}] {len(categories_seen)}/{len(pytest_groups)} categories | {test_count} tests | {elapsed:.1f}s",
                            end="",
                            flush=True,
                        )
                        last_progress_update = time.time()

                # Wait for process to complete
                returncode = process.wait(
                    timeout=self.config.timeout - (time.time() - pytest_start_time) if self.config.timeout else None
                )

                # Get any remaining output
                stdout_text = "".join(output_lines)
                stderr_text = ""  # Combined with stdout above

                pytest_success = returncode == 0
                pytest_duration = time.time() - pytest_start_time

                # Parse test counts from output
                pytest_counts = self._parse_pytest_output(stdout_text + stderr_text)

                self.results["pytest"] = {
                    "success": pytest_success,
                    "returncode": returncode,
                    "duration": pytest_duration,
                    "counts": pytest_counts,
                }

                # Save failure details to file (even if pytest had internal errors)
                if not pytest_success:
                    failed_count = pytest_counts.get("failed", 0) + pytest_counts.get("errors", 0)
                    if failed_count > 0 or "INTERNALERROR" in stdout_text or "FAILED" in stdout_text:
                        self._save_failure_log(stdout_text + stderr_text, pytest_counts)

                # Clear progress line and show final status
                if pytest_groups:
                    print("\r" + " " * 100 + "\r", end="")  # Clear progress line
                print()
                print("=" * 80)
                status = "✅ PASSED" if pytest_success else "❌ FAILED"
                print(f"PYTEST TESTS: {status} ({pytest_duration:.2f}s)")
                print(
                    f"   Passed: {pytest_counts.get('passed', 0)} | Failed: {pytest_counts.get('failed', 0)} | Skipped: {pytest_counts.get('skipped', 0)}"
                    + (f" | Errors: {pytest_counts.get('errors', 0)}" if pytest_counts.get("errors", 0) else "")
                )
                if not pytest_success:
                    print(f"   📄 Failure details saved to: test-results/failures_{self.timestamp}.log")
                    print(f"   📊 HTML report: test-results/report_{self.timestamp}.html")
                    print(f"   📈 JUnit XML: test-results/junit_{self.timestamp}.xml")
                    print("   📈 Allure report: allure serve allure-results")
                print("=" * 80)

            except subprocess.TimeoutExpired:
                process.kill()
                logger.error(f"Pytest execution timed out after {self.config.timeout} seconds")
                pytest_success = False
            except KeyboardInterrupt:
                logger.info("Pytest execution interrupted by user")
                pytest_success = False
            except Exception as e:
                logger.error(f"Pytest execution failed: {e}")
                if self.config.debug:
                    logger.exception("Full traceback:")
                pytest_success = False

            # Run Playwright tests
            playwright_success = True
            if run_playwright:
                playwright_start_time = time.time()
                cmd_str = " ".join(playwright_cmd)

                # Determine which Playwright test groups are being executed
                playwright_groups = self._get_playwright_test_groups()
                if playwright_groups:
                    self.test_groups_executed.extend([f"playwright:{group}" for group in playwright_groups])

                print("\n" + "=" * 80)
                print("🎭 RUNNING PLAYWRIGHT TESTS")
                if playwright_groups:
                    print(f"   Test Groups: {', '.join(playwright_groups)}")
                    print(f"   Progress: [{' ' * len(playwright_groups)}] 0/{len(playwright_groups)} groups")
                print("=" * 80)
                logger.info(f"Executing Playwright: {cmd_str}")
                print()

                try:
                    # Run with real-time output
                    process = subprocess.Popen(
                        playwright_cmd,
                        env=env,
                        cwd=project_root,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1,
                    )

                    output_lines = []
                    test_count = 0
                    last_progress_update = time.time()

                    for line in process.stdout:
                        output_lines.append(line)
                        print(line, end="", flush=True)

                        # Track Playwright test execution
                        if any(word in line.lower() for word in ["passed", "failed", "skipped", "✓", "×"]):
                            test_count += 1

                        # Update progress periodically (every 3 seconds)
                        if time.time() - last_progress_update > 3.0:
                            elapsed = time.time() - playwright_start_time
                            if playwright_groups:
                                # Estimate progress based on test count (rough)
                                estimated_progress = min(len(playwright_groups), max(1, test_count // 5))
                                progress_chars = [
                                    "=" if i < estimated_progress else " " for i in range(len(playwright_groups))
                                ]
                                progress_bar = "".join(progress_chars)
                                print(
                                    f"\r⏳ Progress: [{progress_bar}] {estimated_progress}/{len(playwright_groups)} groups | Tests: {test_count} | Time: {elapsed:.1f}s",
                                    end="",
                                    flush=True,
                                )
                            last_progress_update = time.time()

                    returncode = process.wait(
                        timeout=self.config.timeout - (time.time() - playwright_start_time)
                        if self.config.timeout
                        else None
                    )

                    stdout_text = "".join(output_lines)
                    stderr_text = ""

                    playwright_success = returncode == 0
                    playwright_duration = time.time() - playwright_start_time

                    # Parse test counts from output
                    playwright_counts = self._parse_playwright_output(stdout_text + stderr_text)

                    self.results["playwright"] = {
                        "success": playwright_success,
                        "returncode": returncode,
                        "duration": playwright_duration,
                        "counts": playwright_counts,
                    }

                    # Clear progress line and show final status
                    if playwright_groups:
                        print("\r" + " " * 100 + "\r", end="")  # Clear progress line
                    print()
                    print("=" * 80)
                    status = "✅ PASSED" if playwright_success else "❌ FAILED"
                    print(f"PLAYWRIGHT TESTS: {status} ({playwright_duration:.2f}s)")
                    print(
                        f"   Passed: {playwright_counts.get('passed', 0)} | Failed: {playwright_counts.get('failed', 0)} | Skipped: {playwright_counts.get('skipped', 0)}"
                    )
                    print("=" * 80)

                except subprocess.TimeoutExpired:
                    process.kill()
                    logger.error(f"Playwright execution timed out after {self.config.timeout} seconds")
                    playwright_success = False
                except KeyboardInterrupt:
                    logger.info("Playwright execution interrupted by user")
                    playwright_success = False
                except Exception as e:
                    logger.error(f"Playwright execution failed: {e}")
                    if self.config.debug:
                        logger.exception("Full traceback:")
                    playwright_success = False

            # Overall success requires both to pass (if both ran)
            if run_playwright:
                overall_success = pytest_success and playwright_success
            else:
                overall_success = pytest_success

            self.results[self.config.test_type.value] = {
                "success": overall_success,
                "pytest": pytest_success,
                "playwright": playwright_success if run_playwright else None,
                "duration": time.time() - self.start_time,
            }

            return overall_success

        finally:
            # Stop debugging components
            self.stop_debugging()

    def _get_agent_config_exclude_env(self) -> dict[str, str]:
        """Return env vars to exclude Playwright specs that mutate agent/workflow config.
        Used when --exclude-markers agent_config_mutation is set (no agent config mutation in CI/safe runs).
        """
        if self.config.exclude_markers and "agent_config_mutation" in self.config.exclude_markers:
            return {"CTI_EXCLUDE_AGENT_CONFIG_TESTS": "1"}
        return {}

    def _parse_pytest_output(self, output: str) -> dict[str, int]:
        """Parse pytest output to extract test counts.

        Handles summary line variations: '= X passed in 45s', '= 1 failed, 20 passed, 3 skipped in 45s',
        '= 2 failed, 1 error in 10s'. Order and presence of failed/skipped/error vary.
        """
        import re

        counts = {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "errors": 0}

        # Optional parts (pytest only includes non-zero in summary). \b avoids matching xpassed/xfailed.
        for pattern, key in [
            (r"(\d+)\s+passed\b", "passed"),
            (r"(\d+)\s+failed\b", "failed"),
            (r"(\d+)\s+skipped", "skipped"),
            (r"(\d+)\s+errors?", "errors"),
        ]:
            m = re.search(pattern, output)
            if m:
                counts[key] = int(m.group(1))

        if counts["passed"] or counts["failed"] or counts["skipped"] or counts["errors"]:
            counts["total"] = counts["passed"] + counts["failed"] + counts["skipped"] + counts["errors"]

        return counts

    def _save_failure_log(self, output: str, counts: dict[str, int]) -> None:
        """Save failure details to a log file."""
        from datetime import datetime

        # Ensure test-results directory exists
        test_results_dir = Path("test-results")
        test_results_dir.mkdir(exist_ok=True)

        # Include timestamp to preserve historical results
        failure_log_path = test_results_dir / f"failures_{self.timestamp}.log"

        with open(failure_log_path, "w") as f:
            f.write("=" * 80 + "\n")
            f.write("Test Failure Report\n")
            f.write(f"Generated: {datetime.now().isoformat()}\n")
            f.write(f"Test Type: {self.config.test_type.value}\n")
            f.write(f"Duration: {time.time() - self.start_time:.2f}s\n")
            f.write("=" * 80 + "\n\n")

            f.write("Summary:\n")
            f.write(f"  Total: {counts.get('total', 0)}\n")
            f.write(f"  Passed: {counts.get('passed', 0)}\n")
            f.write(f"  Failed: {counts.get('failed', 0)}\n")
            f.write(f"  Skipped: {counts.get('skipped', 0)}\n")
            f.write(f"  Errors: {counts.get('errors', 0)}\n\n")

            # Extract failure details
            f.write("=" * 80 + "\n")
            f.write("FAILED TESTS:\n")
            f.write("=" * 80 + "\n\n")

            # Find all FAILED test lines
            failed_tests = []
            lines = output.split("\n")
            current_failure = None

            for i, line in enumerate(lines):
                # Match test failure lines
                if "FAILED" in line and "::" in line:
                    test_name = line.split("FAILED")[0].strip()
                    failed_tests.append(
                        {
                            "name": test_name,
                            "start_line": i,
                        }
                    )
                    current_failure = len(failed_tests) - 1
                elif current_failure is not None:
                    # Capture failure details (traceback, assertions, etc.)
                    if "AssertionError" in line or "Error:" in line or "Exception:" in line:
                        failed_tests[current_failure]["error"] = line
                    elif line.strip().startswith("E ") or line.strip().startswith(">"):
                        if "details" not in failed_tests[current_failure]:
                            failed_tests[current_failure]["details"] = []
                        failed_tests[current_failure]["details"].append(line)
                    elif line.strip() and not line.startswith(" "):
                        # End of traceback
                        current_failure = None

            # Write failed tests
            for idx, failure in enumerate(failed_tests, 1):
                f.write(f"{idx}. {failure['name']}\n")
                if "error" in failure:
                    f.write(f"   Error: {failure['error']}\n")
                if "details" in failure:
                    f.write("   Details:\n")
                    for detail in failure["details"][:10]:  # First 10 lines
                        f.write(f"     {detail}\n")
                f.write("\n")

            # If we couldn't parse failures cleanly, include raw output section
            if not failed_tests:
                f.write("(Could not parse individual failures - see raw output below)\n\n")
                f.write("=" * 80 + "\n")
                f.write("RAW OUTPUT (FAILURES SECTION):\n")
                f.write("=" * 80 + "\n\n")

                # Extract just the failure section from pytest output
                in_failures = False
                for line in lines:
                    if "FAILED" in line or "ERROR" in line:
                        in_failures = True
                    if in_failures:
                        f.write(line + "\n")
                        # Stop after reasonable amount
                        if (
                            line.strip() == ""
                            and "short test summary"
                            in " ".join(lines[max(0, lines.index(line) - 5) : lines.index(line) + 1]).lower()
                        ):
                            break

        logger.info(f"Failure log saved to: {failure_log_path}")

    def _parse_playwright_output(self, output: str) -> dict[str, int]:
        """Parse Playwright output to extract test counts.

        Handles list/line reporter output: '30 passed (1m)', '1 failed, 29 passed', etc.
        """
        import re

        counts = {"total": 0, "passed": 0, "failed": 0, "skipped": 0}

        for pattern, key in [
            (r"(\d+)\s+passed", "passed"),
            (r"(\d+)\s+failed", "failed"),
            (r"(\d+)\s+skipped", "skipped"),
        ]:
            m = re.search(pattern, output)
            if m:
                counts[key] = int(m.group(1))

        if counts["passed"] or counts["failed"] or counts["skipped"]:
            counts["total"] = counts["passed"] + counts["failed"] + counts["skipped"]

        return counts

    def _install_playwright_dependencies(self) -> bool:
        """Install Playwright and npm dependencies."""
        try:
            # Install npm dependencies
            logger.info("Installing npm dependencies...")
            result = subprocess.run(["npm", "install"], cwd=project_root, capture_output=True, check=False)
            if result.returncode != 0:
                logger.warning(f"npm install failed: {result.stderr}")
                return False

            # Install Playwright browsers
            logger.info("Installing Playwright browsers...")
            result = subprocess.run(
                ["npx", "playwright", "install", "chromium"],
                cwd=project_root,
                capture_output=True,
                check=False,
            )
            if result.returncode != 0:
                logger.warning(f"Playwright browser installation failed: {result.stderr}")
                # Non-fatal, continue anyway

            return True
        except Exception as e:
            logger.error(f"Failed to install Playwright dependencies: {e}")
            return False

    def generate_report(self) -> None:
        """Generate comprehensive test report."""
        duration = time.time() - self.start_time

        print("\n" + "=" * 60)
        print("📊 CTI Scraper Test Execution Report")
        print("=" * 60)

    def start_debugging(self):
        """Start debugging components."""
        if not DEBUGGING_AVAILABLE:
            logger.warning("Debugging utilities not available")
            return

        # Start performance monitoring if debug mode
        if self.config.debug and self.performance_profiler:
            start_performance_monitoring()
            logger.debug("Performance monitoring started")

        # Start async debugging if available
        if self.async_debugger:
            logger.debug("Async debugging available")

    def stop_debugging(self):
        """Stop debugging components."""
        if not DEBUGGING_AVAILABLE:
            return

        # Stop performance monitoring
        if self.performance_profiler:
            stop_performance_monitoring()
            logger.debug("Performance monitoring stopped")

    def print_enhanced_summary(self):
        """Print enhanced test summary with debugging information."""
        if not DEBUGGING_AVAILABLE or not self.output_formatter:
            self.generate_report()
            # Always print time lines so summary output is consistent (e.g. for CI and run_tests tests).
            total_duration = time.time() - self.start_time
            test_only_duration = 0.0
            if "pytest" in self.results and "duration" in self.results["pytest"]:
                test_only_duration += self.results["pytest"]["duration"]
            if "playwright" in self.results and "duration" in self.results["playwright"]:
                test_only_duration += self.results["playwright"]["duration"]
            if test_only_duration > 0:
                print(f"\n⏱️  Test execution only: {test_only_duration:.2f}s")
            print(f"⏱️  Total (including setup): {total_duration:.2f}s")
            return

        # Calculate duration
        duration = time.time() - self.start_time

        # Aggregate test counts from pytest and playwright
        total_tests = 0
        total_passed = 0
        total_failed = 0
        total_skipped = 0

        if "pytest" in self.results and "counts" in self.results["pytest"]:
            counts = self.results["pytest"]["counts"]
            total_tests += counts.get("total", 0)
            total_passed += counts.get("passed", 0)
            total_failed += counts.get("failed", 0) + counts.get("errors", 0)
            total_skipped += counts.get("skipped", 0)

        if "playwright" in self.results and "counts" in self.results["playwright"]:
            counts = self.results["playwright"]["counts"]
            total_tests += counts.get("total", 0)
            total_passed += counts.get("passed", 0)
            total_failed += counts.get("failed", 0)
            total_skipped += counts.get("skipped", 0)

        # Print enhanced summary with parsed counts
        if total_tests > 0:
            self.output_formatter.print_summary(
                total=total_tests,
                passed=total_passed,
                failed=total_failed,
                skipped=total_skipped,
            )
        else:
            self.output_formatter.print_summary()

        # Print performance information if available
        if self.performance_profiler:
            performance_report = self.performance_profiler.generate_performance_report()
            if performance_report.get("status") == "success":
                self.output_formatter.print_performance_info(performance_report)
        print(f"🎯 Test Type: {self.config.test_type.value}")
        print(f"🌍 Context: {self.config.context.value}")
        print(f"🔧 Debug Mode: {'Yes' if self.config.debug else 'No'}")
        print(f"📈 Coverage: {'Yes' if self.config.coverage else 'No'}")

        # Test Groups Summary
        print("\n" + "=" * 80)
        print("📊 TEST EXECUTION SUMMARY")
        print("=" * 80)

        if self.test_groups_executed:
            print("\n✅ Test Groups Executed:")
            # Group by framework
            pytest_groups = [g.replace("pytest:", "") for g in self.test_groups_executed if g.startswith("pytest:")]
            playwright_groups = [
                g.replace("playwright:", "") for g in self.test_groups_executed if g.startswith("playwright:")
            ]

            if pytest_groups:
                print("  🐍 Pytest:")
                for group in sorted(set(pytest_groups)):
                    print(f"     • {group}")

            if playwright_groups:
                print("  🎭 Playwright:")
                for group in sorted(set(playwright_groups)):
                    print(f"     • {group}")
        else:
            print("\n⚠️  No test groups tracked")

        # Results summary
        if self.results:
            print("\n📋 Test Results:")
            for test_type, result in self.results.items():
                if isinstance(result, dict) and "success" in result:
                    status = "✅ PASS" if result["success"] else "❌ FAIL"
                    duration = result.get("duration", 0)
                    print(f"  {test_type}: {status} ({duration:.2f}s)")

                    # Show pytest/playwright breakdown if available
                    if "pytest" in result or "playwright" in result:
                        if "pytest" in result and result["pytest"] is not None:
                            pytest_status = "✅" if result["pytest"] else "❌"
                            pytest_duration = self.results.get("pytest", {}).get("duration", 0)
                            print(f"    - pytest: {pytest_status} ({pytest_duration:.2f}s)")
                        if "playwright" in result and result["playwright"] is not None:
                            pw_status = "✅" if result["playwright"] else "❌"
                            pw_duration = self.results.get("playwright", {}).get("duration", 0)
                            print(f"    - playwright: {pw_status} ({pw_duration:.2f}s)")

        # Overall statistics: test execution only (pytest + playwright) vs total (including setup)
        total_duration = time.time() - self.start_time
        test_only_duration = 0.0
        if "pytest" in self.results and "duration" in self.results["pytest"]:
            test_only_duration += self.results["pytest"]["duration"]
        if "playwright" in self.results and "duration" in self.results["playwright"]:
            test_only_duration += self.results["playwright"]["duration"]
        if test_only_duration > 0:
            print(f"\n⏱️  Test execution only: {test_only_duration:.2f}s")
        print(f"⏱️  Total (including setup): {total_duration:.2f}s")

        # Success summary
        overall_success = (
            all(
                result.get("success", False)
                for result in self.results.values()
                if isinstance(result, dict) and "success" in result
            )
            if self.results
            else False
        )

        print(f"🎯 Overall Status: {'✅ ALL TESTS PASSED' if overall_success else '❌ SOME TESTS FAILED'}")

        # Report locations
        print("\n📁 Generated Reports:")

        # Test results
        test_results_dir = Path("test-results")
        if test_results_dir.exists():
            print(f"  📊 Test Results: {test_results_dir.absolute()}")

            # Allure results
            allure_results = Path("allure-results")
            if allure_results.exists():
                print(f"  📊 Allure Results: {allure_results.absolute()}")
                print("    💡 Run 'allure serve allure-results' for interactive reports")

            # Report log
            report_log = test_results_dir / "reportlog.jsonl"
            if report_log.exists():
                print(f"  📊 Report Log: {report_log.absolute()}")

        # Coverage report
        coverage_dir = Path("htmlcov")
        if coverage_dir.exists():
            index_file = coverage_dir / "index.html"
            if index_file.exists():
                print(f"  📊 Coverage Report: {index_file.absolute()}")

        # Available test categories
        print("\n🎯 Available Test Categories:")
        categories = [
            ("smoke", "Quick health check (~30s)"),
            ("unit", "Unit tests only (~1m)"),
            ("api", "API endpoint tests (~2m)"),
            ("integration", "System integration tests (~3m)"),
            ("ui", "Web interface tests (~5m)"),
            ("e2e", "End-to-end tests (~3m)"),
            ("performance", "Performance tests (~2m)"),
            ("ai", "AI tests (~3m)"),  # Note: AI Assistant UI tests removed
            ("ai-ui", "AI UI tests only (~1m)"),
            ("ai-integration", "AI integration tests (~2m)"),
            ("all", "Complete test suite (~8m)"),
            ("coverage", "Tests with coverage report"),
        ]

        for category, description in categories:
            print(f"  • {category:<15} {description}")

        # Usage examples
        print("\n💡 Usage Examples:")
        examples = [
            "python run_tests.py smoke",
            "python run_tests.py all --coverage",
            "python run_tests.py --docker integration",
            "python run_tests.py --debug --verbose",
            "python run_tests.py unit --fail-fast",
        ]

        for example in examples:
            print(f"  $ {example}")

        # New test infrastructure notes
        print("\n🔧 New Test Infrastructure:")
        print("  • Test containers: make test-up / make test-down")
        print("  • Test environment guards prevent production DB access")
        print("  • Stateful tests require test containers (auto-started if needed)")
        print("  • See docs/TESTING_STRATEGY.md for details")


def parse_arguments() -> TestConfig:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="CTI Scraper Unified Test Runner",
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
  e2e          End-to-end tests (~3m) - STATEFUL (auto-starts test containers)
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
  - Failure reports (timestamped): test-results/failures_YYYYMMDD_HHMMSS.log, test-results/junit_YYYYMMDD_HHMMSS.xml, test-results/report_YYYYMMDD_HHMMSS.html
  - Progress indicators show category-by-category execution

Examples:
  python run_tests.py smoke                    # Quick health check (stateless, fast)
  python run_tests.py unit --fail-fast         # Unit tests (stateless, no containers)
  python run_tests.py integration              # Integration tests (auto-starts containers)
  python run_tests.py ui                       # UI tests (may auto-start containers)
  python run_tests.py ui --exclude-markers agent_config_mutation  # UI tests that do not mutate agent configs
  python run_tests.py all                      # Full suite (auto-starts containers)
  python run_tests.py --debug --verbose        # Debug mode with verbose output
  python run_tests.py --context localhost unit # Force localhost execution

Manual Container Management:
  make test-up          # Start test containers manually
  make test-down        # Stop test containers
  make test             # Run all tests (starts containers, runs tests, stops containers)
        """,
    )

    # Test type (positional argument)
    parser.add_argument(
        "test_type",
        nargs="?",
        default="smoke",
        choices=[t.value for t in TestType],
        help="Type of tests to run",
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
    parser.add_argument("--coverage", action="store_true", help="Generate coverage report")
    parser.add_argument("--install", action="store_true", help="Install test dependencies")
    parser.add_argument("--no-validate", action="store_true", help="Skip environment validation")

    # Test filtering
    parser.add_argument("--paths", nargs="+", help="Specific test paths to run")
    parser.add_argument("--markers", nargs="+", help="Test markers to include")
    parser.add_argument("--exclude-markers", nargs="+", help="Test markers to exclude")
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

    # Convert test type
    test_type = TestType(args.test_type)

    return TestConfig(
        test_type=test_type,
        context=context,
        verbose=args.verbose,
        debug=args.debug,
        parallel=args.parallel,
        coverage=args.coverage,
        install_deps=args.install,
        validate_env=not args.no_validate,
        skip_real_api=args.skip_real_api,
        test_paths=args.paths,
        markers=args.markers,
        exclude_markers=args.exclude_markers,
        config_file=args.config,
        output_format=args.output_format,
        fail_fast=args.fail_fast,
        retry_count=args.retry,
        timeout=args.timeout,
    )


async def main():
    """Main entry point."""
    try:
        # Parse configuration
        config = parse_arguments()

        # Create test runner
        runner = TestRunner(config)

        # Setup environment
        if not await runner.setup_environment():
            logger.error("Failed to setup test environment")
            return 1

        try:
            # Run tests
            success = runner.run_tests()

            # Generate enhanced report
            runner.print_enhanced_summary()

            return 0 if success else 1

        finally:
            # Teardown environment
            await runner.teardown_environment()

    except KeyboardInterrupt:
        logger.info("Test execution interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Test runner failed: {e}")
        logger.exception("Full traceback:")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
