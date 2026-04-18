#!/usr/bin/env python3
# Re-exec with the project venv Python if the current interpreter is too old.
# This block uses only Python 2/3-compatible syntax so even /usr/bin/python3 (3.9)
# can parse and execute it before reaching any 3.10+ union-type annotations below.
import os as _os  # noqa: E401
import sys as _sys

_venv_py = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".venv", "bin", "python3")
if _sys.version_info < (3, 10) and _os.path.exists(_venv_py):
    _os.execv(_venv_py, [_venv_py] + _sys.argv)
del _os, _sys, _venv_py

"""
Huntable CTI Studio Unified Test Runner

This is the single entry point for all test execution needs across different contexts.
Consolidates functionality from run_tests.py and run_tests.sh.

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
- Test containers auto-started for stateful tests (api, ui, integration, e2e, all)
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
    python run_tests.py unit api smoke            # Run multiple test types sequentially
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
import queue
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from tests.utils.test_database_url import build_test_database_url

# Augment PATH so subprocesses can find tools (e.g. Docker Desktop CLI on macOS)
# installed outside the default non-login shell PATH.
_EXTRA_PATH_DIRS = ["/usr/local/bin", "/opt/homebrew/bin", "/opt/homebrew/sbin"]
_current_path = os.environ.get("PATH", "")
_path_parts = _current_path.split(os.pathsep)
for _d in reversed(_EXTRA_PATH_DIRS):
    if _d not in _path_parts:
        os.environ["PATH"] = _d + os.pathsep + os.environ.get("PATH", "")
del _EXTRA_PATH_DIRS, _current_path, _path_parts, _d


# Keys from .env that must not be applied in test (guard: TEST_DATABASE_URL only).
# Cloud LLM keys are skipped so they are not loaded from .env into the test process.
_DOTENV_SKIP_IN_TEST = frozenset(
    {
        "DATABASE_URL",
        "REDIS_URL",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "CHATGPT_API_KEY",
    }
)

_CLOUD_LLM_KEYS = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "CHATGPT_API_KEY")


def _strip_cloud_llm_keys() -> None:
    """Remove cloud LLM keys from this process so tests never hit commercial APIs.
    Skipped if ALLOW_CLOUD_LLM_IN_TESTS=true."""
    if os.getenv("ALLOW_CLOUD_LLM_IN_TESTS", "").lower() in ("true", "1", "yes"):
        return
    for key in _CLOUD_LLM_KEYS:
        os.environ.pop(key, None)


def _load_dotenv() -> None:
    """Load .env from project root so POSTGRES_PASSWORD etc. match running Postgres. Does not override existing env.
    Skips DATABASE_URL so test guard (TEST_DATABASE_URL only) passes."""
    env_file = project_root / ".env"
    if not env_file.is_file():
        return
    try:
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                if key in _DOTENV_SKIP_IN_TEST:
                    continue
                value = value.strip().strip("'\"").strip()
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError:
        pass


# Import test environment utilities
try:
    import tests.utils.database_connections  # noqa: F401
    from tests.utils.test_environment import TestEnvironmentManager, TestEnvironmentValidator

    ENVIRONMENT_UTILS_AVAILABLE = True
except ImportError:
    ENVIRONMENT_UTILS_AVAILABLE = False
    print("Warning: Test environment utilities not available. Some features may be limited.")

# Enhanced debugging imports
try:
    from tests.utils.test_failure_analyzer import TestFailureReporter
    from tests.utils.test_isolation import TestIsolationManager
    from tests.utils.test_output_formatter import TestOutputFormatter

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


class RunTestType(Enum):
    """Test execution types."""

    SMOKE = "smoke"
    UNIT = "unit"
    API = "api"
    INTEGRATION = "integration"
    UI = "ui"
    E2E = "e2e"
    REGRESSION = "regression"
    CONTRACT = "contract"
    SECURITY = "security"
    A11Y = "a11y"
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
class RunTestConfig:
    """Test execution configuration."""

    test_type: RunTestType
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
    include_agent_config_tests: bool = False
    include_slow: bool = False  # Include @pytest.mark.slow tests (perf/mobile/a11y); excluded by default in UI runs
    playwright_last_failed: bool = False
    skip_playwright_js: bool = False
    playwright_only: bool = False
    config_file: str | None = None
    output_format: str = "progress"
    fail_fast: bool = False
    retry_count: int = 0
    timeout: int | None = None


class RunTestRunner:
    """Unified test runner with enhanced functionality."""

    def __init__(self, config: RunTestConfig):
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

    def _wait_for_test_containers(self, timeout_seconds: int = 90) -> bool:
        """Wait until required local test containers report healthy status."""
        compose_base = ["docker", "compose", "-f", str(project_root / "docker-compose.test.yml")]
        required_services = ("postgres_test", "redis_test")
        deadline = time.time() + timeout_seconds

        while time.time() < deadline:
            statuses: list[str] = []
            all_healthy = True

            for service in required_services:
                cid_result = subprocess.run(
                    [*compose_base, "ps", "-q", service],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                container_id = (cid_result.stdout or "").strip()

                if not container_id:
                    statuses.append(f"{service}=missing")
                    all_healthy = False
                    continue

                health_result = subprocess.run(
                    [
                        "docker",
                        "inspect",
                        "--format",
                        "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}",
                        container_id,
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                status = (health_result.stdout or "").strip() if health_result.returncode == 0 else "unknown"
                statuses.append(f"{service}={status or 'unknown'}")
                if status != "healthy":
                    all_healthy = False

            if all_healthy:
                logger.info("Test containers ready: %s", ", ".join(statuses))
                return True

            logger.debug("Waiting for test containers: %s", ", ".join(statuses))
            time.sleep(2)

        logger.error("Timed out waiting for test containers to become healthy")
        return False

    def _test_containers_running(self) -> tuple[bool, list[str]]:
        """Return whether the required named test containers are running."""
        required_containers = ("cti_postgres_test", "cti_redis_test")
        statuses: list[str] = []
        all_running = True

        for container_name in required_containers:
            result = subprocess.run(
                ["docker", "ps", "--filter", f"name={container_name}", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                check=False,
            )
            running = container_name in (result.stdout or "")
            statuses.append(f"{container_name}={'running' if running else 'missing'}")
            if not running:
                all_running = False

        return all_running, statuses

    def _start_test_containers(self) -> bool:
        """Start the required local test containers."""
        logger.info("Starting required test containers...")
        result = subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(project_root / "docker-compose.test.yml"),
                "up",
                "-d",
                "postgres_test",
                "redis_test",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            logger.error("Failed to start test containers")
            if result.stderr:
                logger.error("Error: %s", result.stderr.strip())
            return False

        logger.info("Test containers started successfully")
        return True

    def _ensure_test_containers(self) -> bool:
        """Ensure the required local test containers are running and healthy."""
        running, statuses = self._test_containers_running()
        if running:
            logger.info("Test containers already running: %s", ", ".join(statuses))
            if not self._wait_for_test_containers():
                logger.error("Required test containers are not healthy")
                return False
            return True

        logger.warning("Required test containers not running: %s", ", ".join(statuses))
        logger.info("Starting postgres_test and redis_test from docker-compose.test.yml...")

        if not self._start_test_containers():
            return False

        if not self._wait_for_test_containers():
            logger.error("Required test containers are not healthy")
            return False

        return True

    async def setup_environment(self) -> bool:
        """Set up test environment."""
        # Check if test containers are needed for stateful tests
        stateful_test_types = {
            RunTestType.API,
            RunTestType.UI,
            RunTestType.INTEGRATION,
            RunTestType.E2E,
            RunTestType.ALL,
            RunTestType.COVERAGE,
        }

        needs_test_containers = self.config.test_type in stateful_test_types

        if needs_test_containers:
            in_ci = os.getenv("GITHUB_ACTIONS") == "true" or os.getenv("CI") == "true"
            if not in_ci:
                logger.info("Stateful tests detected - checking for test containers...")
                if not self._ensure_test_containers():
                    return False
            else:
                logger.info("CI detected - using GitHub Actions services (postgres/redis)")

            # In CI, GitHub Actions `services:` blocks provide Postgres/Redis with
            # their own health-checks.  _wait_for_test_containers inspects local
            # docker-compose containers which don't exist in CI, so skip it.

        # Set up test environment variables
        os.environ["APP_ENV"] = "test"
        if self.config.test_type in (RunTestType.SMOKE, RunTestType.UNIT, RunTestType.API, RunTestType.INTEGRATION):
            os.environ["TEST_GROUP"] = self.config.test_type.value

        # Set TEST_DATABASE_URL if not already set (password/port match running Postgres via .env)
        if "TEST_DATABASE_URL" not in os.environ:
            os.environ["TEST_DATABASE_URL"] = build_test_database_url(asyncpg=True)
            logger.info(
                "Auto-set TEST_DATABASE_URL from POSTGRES_PASSWORD / .env",
            )

        # Use the test DB for DATABASE_URL in this process so the guard and any imports
        # (e.g. celery_app) never see a leftover production URL from the shell or .env.
        td = os.environ.get("TEST_DATABASE_URL")
        if td:
            os.environ["DATABASE_URL"] = td

        # Use test Redis port when using local test containers (docker-compose.test maps Redis to 6380)
        # In CI, GitHub Actions services use 6379 - do not override
        in_ci = os.getenv("GITHUB_ACTIONS") == "true" or os.getenv("CI") == "true"
        if needs_test_containers and not in_ci and "REDIS_PORT" not in os.environ:
            redis_port = os.getenv("REDIS_TEST_PORT", "6380")
            os.environ["REDIS_PORT"] = redis_port
            if "REDIS_URL" not in os.environ:
                os.environ["REDIS_URL"] = f"redis://localhost:{redis_port}/0"
            logger.info("Auto-set REDIS_PORT=%s for test containers", redis_port)

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

        # Initialize test database schema for stateful tests (API, integration, etc.)
        if needs_test_containers:
            schema_script = project_root / "scripts" / "init_test_schema.py"
            if schema_script.exists():
                schema_initialized = False
                for attempt in range(1, 4):
                    result = subprocess.run(
                        [self.venv_python, str(schema_script)],
                        capture_output=True,
                        text=True,
                        timeout=90,
                        cwd=str(project_root),
                        env={**os.environ, "APP_ENV": "test"},
                    )
                    if result.returncode == 0:
                        schema_initialized = True
                        logger.info("Test database schema initialized")
                        break

                    logger.warning(
                        "Schema init attempt %d/3 failed: %s",
                        attempt,
                        (result.stderr or result.stdout).strip(),
                    )
                    if attempt < 3:
                        time.sleep(2 * attempt)

                if not schema_initialized:
                    logger.error("Schema init failed after retries")
                    return False

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
                if (
                    self.config.test_type == RunTestType.SMOKE
                    and "redis" in critical_validations
                    and not critical_validations["redis"]
                ):
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
        logger.info("Installing test dependencies via uv lockfile...")

        uv_binary = shutil.which("uv")
        if not uv_binary:
            logger.error("uv is required to install dependencies. Install uv and retry.")
            return False

        if not self._run_command(
            f"{uv_binary} sync --frozen --group test",
            "Syncing locked dependencies with uv",
            capture_output=True,
        ):
            logger.error("Failed to sync dependencies from uv.lock")
            return False

        # Install Playwright browser binaries when package is available.
        result = subprocess.run(
            [self.venv_python, "-c", "import playwright"],
            capture_output=True,
            check=False,
        )
        if result.returncode == 0 and not self._run_command(
            f"{self.venv_python} -m playwright install chromium",
            "Installing Playwright browser",
            capture_output=True,
        ):
            logger.warning("Optional step failed: Installing Playwright browser")

        logger.info("Dependencies synced successfully")
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
            RunTestType.SMOKE: ["smoke"],
            RunTestType.UNIT: ["unit", "core", "services", "utils"],
            RunTestType.API: ["api"],
            RunTestType.INTEGRATION: ["integration"],
            RunTestType.UI: ["ui"],
            RunTestType.E2E: ["e2e"],
            RunTestType.REGRESSION: ["regression"],
            RunTestType.CONTRACT: ["contract"],
            RunTestType.SECURITY: ["security"],
            RunTestType.A11Y: ["a11y"],
            RunTestType.PERFORMANCE: ["performance"],
            RunTestType.AI: ["ai", "ui", "integration"],
            RunTestType.AI_UI: ["ai", "ui"],
            RunTestType.AI_INTEGRATION: ["ai", "integration"],
            RunTestType.ALL: ["all"],
            RunTestType.COVERAGE: ["all"],
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
        # When --playwright-last-failed, run from tests/ with local config so .last-run.json is found
        if self.config.playwright_last_failed:
            cmd = ["npx", "playwright", "test", "--config", "playwright.config.ts", "--last-failed"]
            if self.config.verbose or self.config.debug:
                cmd.append("--reporter=list")
            return cmd

        cmd = ["npx", "playwright", "test", "--config", "tests/playwright.config.ts"]

        # Determine which Playwright tests to run based on test type
        test_path_map = {
            RunTestType.SMOKE: [],  # Skip Playwright in smoke tests
            RunTestType.UNIT: [],  # Skip Playwright in unit tests
            RunTestType.API: [],  # Skip Playwright in API tests
            RunTestType.INTEGRATION: [],  # Skip Playwright in integration tests (Python-based)
            RunTestType.UI: ["tests/playwright/", "tests/test_help_buttons.spec.js"],
            RunTestType.E2E: ["tests/playwright/", "tests/test_help_buttons.spec.js"],
            RunTestType.REGRESSION: [],  # Skip Playwright in marker-based category tests
            RunTestType.CONTRACT: [],  # Skip Playwright in marker-based category tests
            RunTestType.SECURITY: [],  # Skip Playwright in marker-based category tests
            RunTestType.A11Y: [],  # Skip Playwright in marker-based category tests
            RunTestType.PERFORMANCE: [],  # Skip Playwright in performance tests
            RunTestType.AI: [],  # Skip Playwright in AI tests (Python-based)
            RunTestType.AI_UI: ["tests/playwright/", "tests/test_help_buttons.spec.js"],
            RunTestType.AI_INTEGRATION: [],  # Skip Playwright in AI integration tests
            RunTestType.ALL: ["tests/playwright/", "tests/test_help_buttons.spec.js"],
            RunTestType.COVERAGE: ["tests/playwright/", "tests/test_help_buttons.spec.js"],
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

    def _requires_docker(self, test_type: RunTestType) -> bool:
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

    def _get_effective_context(self, test_type: RunTestType) -> ExecutionContext:
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
                RunTestType.SMOKE: [
                    "tests/",
                    "-m",
                    "smoke",
                ],  # Restrict to tests/ directory to avoid collection errors
                RunTestType.UNIT: [
                    "tests/",
                    "--ignore=tests/test_web_application.py",  # Exclude web app tests (require running server)
                    "--ignore=tests/ui/",  # Exclude UI tests (require browser/Playwright)
                    "--ignore=tests/api/",  # Exclude api (langfuse+pydantic v1 incompatible with Python 3.14)
                    "-m",
                    "not (smoke or integration or api or ui or e2e or performance "
                    "or infrastructure or prod_data or production_data)",
                ],
                RunTestType.API: ["tests/api/"],
                RunTestType.INTEGRATION: [
                    "tests/integration/",
                    "-m",
                    "integration",
                ],
                RunTestType.UI: ["tests/ui/"],
                RunTestType.E2E: ["tests/e2e/"],
                RunTestType.REGRESSION: ["tests/", "-m", "regression"],
                RunTestType.CONTRACT: ["tests/", "-m", "contract"],
                RunTestType.SECURITY: ["tests/", "-m", "security"],
                RunTestType.A11Y: ["tests/", "-m", "a11y"],
                RunTestType.PERFORMANCE: ["tests/", "-m", "performance"],
                RunTestType.AI: [
                    # "tests/ui/test_ai_assistant_ui.py",  # DEPRECATED: AI Assistant modal removed
                    "tests/integration/test_ai_cross_model_integration.py",
                ],
                RunTestType.AI_UI: [
                    # "tests/ui/test_ai_assistant_ui.py",  # DEPRECATED: AI Assistant modal removed
                    "tests/ui/",
                ],
                RunTestType.AI_INTEGRATION: [
                    "tests/integration/test_ai_cross_model_integration.py",
                ],
                RunTestType.ALL: ["tests/"],
                RunTestType.COVERAGE: ["tests/", "--cov=src"],
            }

            if self.config.test_type in test_path_map:
                cmd.extend(test_path_map[self.config.test_type])
            else:
                cmd.append("tests/")

        # Markers: apply defaults per test type, then exclusions
        default_markers_map = {
            RunTestType.SMOKE: ["smoke"],
            RunTestType.UNIT: [],  # Unit tests: exclude other types, don't require unit marker
            RunTestType.API: ["api"],
            RunTestType.INTEGRATION: ["integration"],
            RunTestType.UI: ["ui"],
            RunTestType.E2E: ["e2e"],
            RunTestType.REGRESSION: ["regression"],
            RunTestType.CONTRACT: ["contract"],
            RunTestType.SECURITY: ["security"],
            RunTestType.A11Y: ["a11y"],
            RunTestType.PERFORMANCE: ["performance"],
            RunTestType.AI: [],
            RunTestType.AI_UI: ["ui"],
            RunTestType.AI_INTEGRATION: ["integration"],
        }

        markers = self.config.markers or default_markers_map.get(self.config.test_type, [])
        marker_expr = " or ".join(markers) if markers else ""

        # Always exclude infrastructure and production data tests by default
        default_excludes = ["infrastructure", "prod_data", "production_data"]
        # Keep smoke fast and under 30 seconds total - exclude UI tests that require browsers
        # UI tests can hang if browsers aren't installed, so exclude them from smoke for speed
        if self.config.test_type == RunTestType.SMOKE:
            default_excludes.extend(["slow", "ui", "ui_smoke"])
        # For unit tests, exclude integration/api/ui/e2e/performance but don't require unit marker
        elif self.config.test_type == RunTestType.UNIT:
            default_excludes.extend(["integration", "api", "ui", "ui_smoke", "e2e", "performance", "smoke"])
        # UI: by default exclude agent/workflow config-mutating tests (use --include-agent-config-tests to run them)
        # Also exclude @pytest.mark.slow by default (performance/mobile/accessibility) — use --include-slow to run them
        elif self.config.test_type == RunTestType.UI and not self.config.include_agent_config_tests:
            default_excludes.append("agent_config_mutation")
            if not self.config.include_slow:
                default_excludes.append("slow")
        if self.config.exclude_markers:
            all_excludes = default_excludes + self.config.exclude_markers
        else:
            all_excludes = default_excludes

        exclude_expr = " and ".join([f"not {marker}" for marker in all_excludes])

        combined_expr = f"({marker_expr}) and ({exclude_expr})" if marker_expr else exclude_expr

        cmd.extend(["-m", combined_expr])

        # API and security tests use in-process ASGI client (USE_ASGI_CLIENT=1 in subprocess env); one event loop for the whole run
        if self.config.test_type in (RunTestType.API, RunTestType.SECURITY):
            cmd.extend(["-o", "asyncio_default_test_loop_scope=session"])

        # UI tests: add a per-test timeout guard so a single hung Playwright test
        # cannot block the entire serial run.  Requires pytest-timeout.
        if self.config.test_type in (RunTestType.UI, RunTestType.E2E, RunTestType.ALL, RunTestType.COVERAGE):
            try:
                import pytest_timeout  # noqa: F401

                cmd.extend(["--timeout=60", "--timeout-method=thread"])
            except ImportError:
                pass  # pytest-timeout not installed; timeout guard disabled

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

        # Parallel execution via pytest-xdist.
        # UI tests hit a single live server (localhost:8001).  Use -n 2 as a safe default
        # for UI runs: enough to parallelise I/O-heavy page loads without overwhelming the
        # server.  Use --parallel to get -n auto (all CPU cores).
        if self.config.parallel:
            cmd.extend(["-n", "auto"])
        elif self.config.test_type in (RunTestType.UI, RunTestType.E2E) and not self.config.fail_fast:
            # Auto-enable -n 2 for UI/E2E when pytest-xdist is available.
            # Bounded to 2 workers to avoid server-side contention on a single live stack.
            try:
                import xdist  # noqa: F401

                cmd.extend(["-n", "2"])
            except ImportError:
                pass  # pytest-xdist not installed; run serially

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
            if self.config.install_deps and not self.install_dependencies():
                return False

            # Determine if we should run Playwright tests
            # --playwright-only forces the JS section on even if --skip-playwright-js was also passed
            if self.config.playwright_only and self.config.skip_playwright_js:
                print(
                    "WARNING: --playwright-only and --skip-playwright-js are mutually exclusive. --playwright-only wins."
                )
                self.config.skip_playwright_js = False
            playwright_cmd = self._build_playwright_command()
            run_playwright = playwright_cmd is not None and not self.config.skip_playwright_js
            if self.config.skip_playwright_js and playwright_cmd is not None:
                print(
                    "\n--skip-playwright-js: skipping npx Playwright (tests/playwright/*.spec.ts). "
                    "Pytest UI tests still run.\n",
                    flush=True,
                )

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

            # Ensure TEST_DATABASE_URL is set (required for stateful tests; matches running Postgres via .env)
            if "TEST_DATABASE_URL" not in env:
                env["TEST_DATABASE_URL"] = build_test_database_url(asyncpg=True)

            # Always pass test DATABASE_URL into pytest (validator module may be unavailable).
            td_url = env.get("TEST_DATABASE_URL")
            if td_url:
                env["DATABASE_URL"] = td_url

            if ENVIRONMENT_UTILS_AVAILABLE:
                try:
                    validator = TestEnvironmentValidator()
                    test_config = validator.load_test_config(self.config.config_file)
                    # Always point DATABASE_URL at the test DB for the pytest subprocess.
                    # A shell-.env production DATABASE_URL must not leak into tests (celery_app guard).
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

            # Use in-process ASGI client for API and security tests (no live server on 127.0.0.1:8001 required)
            # Security tests in tests/api/ use patch() to inject errors; those mocks only work in-process.
            if self.config.test_type in (RunTestType.API, RunTestType.SECURITY):
                env["USE_ASGI_CLIENT"] = "1"
                # In-process app must reach Redis on host (docker port map 6379)
                if (
                    "REDIS_URL" not in env
                    or "redis:6379" in env.get("REDIS_URL", "")
                    or "redis:6380" in env.get("REDIS_URL", "")
                ):
                    env["REDIS_URL"] = "redis://localhost:6379/0"

            env.update(self._get_agent_config_exclude_env())

            # Run pytest tests (skip when --playwright-last-failed or --playwright-only)
            run_pytest = (
                not (self.config.playwright_last_failed and self.config.test_type == RunTestType.UI)
                and not self.config.playwright_only
            )
            pytest_success = True
            pytest_start_time = time.time()

            if self.config.playwright_last_failed and self.config.test_type == RunTestType.UI:
                print("\n" + "=" * 80)
                print("PLAYWRIGHT LAST-FAILED MODE: Skipping pytest, rerunning only failed Playwright tests")
                print("=" * 80 + "\n")

            if self.config.playwright_only:
                print("\n" + "=" * 80)
                print(
                    "PLAYWRIGHT-ONLY MODE: Skipping pytest, running only Node.js Playwright tests (tests/playwright/)"
                )
                print("=" * 80 + "\n")

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

            if run_pytest:
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
                    # Reader drains pipe into queue (avoids BlockingIOError); main thread prints + parses
                    process = subprocess.Popen(
                        cmd,
                        env=env,
                        cwd=project_root,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1,
                    )

                    output_queue: queue.Queue[str | None] = queue.Queue()

                    def drain_to_queue(stream) -> None:
                        for line in stream:
                            output_queue.put(line)
                        output_queue.put(None)

                    reader = threading.Thread(target=drain_to_queue, args=(process.stdout,))
                    reader.daemon = True
                    reader.start()

                    output_lines: list[str] = []
                    test_count = 0
                    categories_seen: set[str] = set()
                    last_progress_update = time.time()

                    while True:
                        line = output_queue.get()
                        if line is None:
                            break
                        output_lines.append(line)
                        print(line, end="", flush=True)

                        # Parse test execution lines for progress
                        if "::" in line and (
                            "PASSED" in line or "FAILED" in line or "SKIPPED" in line or "ERROR" in line
                        ):
                            test_count += 1
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
                                    detected = category_map.get(path_part)
                                    if detected and detected not in categories_seen:
                                        categories_seen.add(detected)
                                        elapsed = time.time() - pytest_start_time
                                        if pytest_groups:
                                            progress_chars = [
                                                "=" if c in categories_seen else " " for c in pytest_groups
                                            ]
                                            n, total = len(categories_seen), len(pytest_groups)
                                            print(
                                                f"\n📊 Category: {detected.upper()} | [{''.join(progress_chars)}] "
                                                f"{n}/{total} | Tests: {test_count} | {elapsed:.1f}s",
                                                flush=True,
                                            )
                                except (IndexError, AttributeError):
                                    pass

                        if time.time() - last_progress_update > 3.0 and pytest_groups:
                            elapsed = time.time() - pytest_start_time
                            progress_chars = ["=" if c in categories_seen else " " for c in pytest_groups]
                            print(
                                f"\r⏳ [{''.join(progress_chars)}] {len(categories_seen)}/{len(pytest_groups)} "
                                f"| {test_count} tests | {elapsed:.1f}s",
                                end="",
                                flush=True,
                            )
                            last_progress_update = time.time()

                    returncode = process.wait(
                        timeout=self.config.timeout - (time.time() - pytest_start_time) if self.config.timeout else None
                    )
                    reader.join(timeout=5.0)

                    stdout_text = "".join(output_lines)
                    stderr_text = ""

                    pytest_success = returncode == 0
                    pytest_duration = time.time() - pytest_start_time

                    # Parse test counts from output; fallback to JUnit or line counts if summary missing
                    pytest_counts = self._parse_pytest_output(stdout_text + stderr_text)
                    if (
                        pytest_counts.get("passed", 0) == 0
                        and pytest_counts.get("failed", 0) == 0
                        and pytest_counts.get("skipped", 0) == 0
                    ):
                        fallback = self._parse_pytest_output_fallback(
                            stdout_text + stderr_text,
                            Path("test-results") / f"junit_{self.timestamp}.xml",
                        )
                        if fallback:
                            pytest_counts = fallback

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
                    passed = pytest_counts.get("passed", 0)
                    failed = pytest_counts.get("failed", 0)
                    skipped = pytest_counts.get("skipped", 0)
                    err_suffix = (
                        f" | Errors: {pytest_counts.get('errors', 0)}" if pytest_counts.get("errors", 0) else ""
                    )
                    print(f"   Passed: {passed} | Failed: {failed} | Skipped: {skipped}{err_suffix}")
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

            if not run_pytest:
                self.results["pytest"] = {"success": True, "skipped": True}

            # Run Playwright tests
            playwright_success = True
            if run_playwright:
                # --playwright-last-failed requires a previous run to create .last-run.json
                if self.config.playwright_last_failed:
                    last_run = project_root / "tests" / "test-results" / ".last-run.json"
                    if not last_run.is_file():
                        print("\n" + "=" * 80)
                        print("⚠️  --playwright-last-failed requires a previous Playwright run with failures.")
                        print(
                            "   Run './run_tests.py ui' first (let Playwright complete), "
                            "then rerun with --playwright-last-failed."
                        )
                        print("   Missing: tests/test-results/.last-run.json")
                        print("=" * 80 + "\n")
                        run_playwright = False
                        playwright_success = False
                        self.results["playwright"] = {"success": False, "skipped": True}

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
                        # Queue-based drain for real-time output (same as pytest)
                        pw_cwd = project_root / "tests" if self.config.playwright_last_failed else project_root
                        process = subprocess.Popen(
                            playwright_cmd,
                            env=env,
                            cwd=pw_cwd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                            bufsize=1,
                        )

                        pw_queue: queue.Queue[str | None] = queue.Queue()

                        def pw_drain(stream) -> None:
                            for line in stream:
                                pw_queue.put(line)
                            pw_queue.put(None)

                        pw_reader = threading.Thread(target=pw_drain, args=(process.stdout,))
                        pw_reader.daemon = True
                        pw_reader.start()

                        pw_output_lines: list[str] = []
                        pw_test_count = 0
                        pw_last_update = time.time()

                        while True:
                            line = pw_queue.get()
                            if line is None:
                                break
                            pw_output_lines.append(line)
                            print(line, end="", flush=True)
                            if any(w in line.lower() for w in ["passed", "failed", "skipped", "✓", "×"]):
                                pw_test_count += 1
                            if time.time() - pw_last_update > 3.0 and playwright_groups:
                                elapsed = time.time() - playwright_start_time
                                est = min(len(playwright_groups), max(1, pw_test_count // 5))
                                bar = "=" * est + " " * (len(playwright_groups) - est)
                                msg = f"\r⏳ [{bar}] {est}/{len(playwright_groups)} | {pw_test_count} | {elapsed:.1f}s"
                                print(msg, end="", flush=True)
                                pw_last_update = time.time()

                        returncode = process.wait(
                            timeout=self.config.timeout - (time.time() - playwright_start_time)
                            if self.config.timeout
                            else None
                        )
                        pw_reader.join(timeout=5.0)

                        stdout_text = "".join(pw_output_lines)
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
                        pp, pf, ps = (
                            playwright_counts.get("passed", 0),
                            playwright_counts.get("failed", 0),
                            playwright_counts.get("skipped", 0),
                        )
                        print(f"   Passed: {pp} | Failed: {pf} | Skipped: {ps}")
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
            # When --playwright-last-failed but we skipped (no .last-run.json), fail the run
            if self.config.playwright_last_failed and not run_playwright and "playwright" in self.results:
                overall_success = False
            else:
                overall_success = pytest_success and playwright_success if run_playwright else pytest_success

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
        Set when UI runs without --include-agent-config-tests, or when --exclude-markers agent_config_mutation is used.
        """
        if self.config.exclude_markers and "agent_config_mutation" in self.config.exclude_markers:
            return {"CTI_EXCLUDE_AGENT_CONFIG_TESTS": "1"}
        if self.config.test_type == RunTestType.UI and not self.config.include_agent_config_tests:
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

    def _parse_pytest_output_fallback(self, output: str, junit_path: Path) -> dict[str, int] | None:
        """When normal summary is missing (e.g. pytest crashed), derive counts from JUnit XML or output."""
        import re
        import xml.etree.ElementTree as ET

        counts = {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "errors": 0}

        # Prefer JUnit XML if present (written by pytest even when terminal summary is lost)
        if junit_path.is_file():
            try:
                tree = ET.parse(junit_path)
                root = tree.getroot()
                # Handle both <testsuites> and single <testsuite>
                suites = list(root.iter("testsuite")) if root.tag != "testsuite" else [root]
                for suite in suites:
                    for tc in suite.iter("testcase"):
                        counts["total"] += 1
                        if tc.find("failure") is not None:
                            counts["failed"] += 1
                        elif tc.find("error") is not None:
                            counts["errors"] += 1
                        elif tc.find("skipped") is not None:
                            counts["skipped"] += 1
                        else:
                            counts["passed"] += 1
                if counts["total"]:
                    return counts
            except (ET.ParseError, OSError):
                pass

        # Fallback: count result lines in output (xdist: "[gwN] PASSED path::test", or plain "path::test PASSED")
        for line in output.splitlines():
            if "::" not in line:
                continue
            if re.search(r"\bPASSED\b", line) and "FAILED" not in line:
                counts["passed"] += 1
            elif re.search(r"\bFAILED\b", line):
                counts["failed"] += 1
            elif re.search(r"\bSKIPPED\b", line):
                counts["skipped"] += 1
        if counts["passed"] or counts["failed"] or counts["skipped"]:
            counts["total"] = counts["passed"] + counts["failed"] + counts["skipped"]
            return counts
        return None

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
        time.time() - self.start_time

        print("\n" + "=" * 60)
        print("📊 Huntable CTI Studio Test Execution Report")
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
            ("regression", "Regression test category"),
            ("contract", "API/schema contract category"),
            ("security", "Security test category"),
            ("a11y", "Accessibility test category"),
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


def parse_arguments() -> RunTestConfig:
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
  e2e          End-to-end tests (~3m) - STATEFUL (auto-starts test containers)
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
    test-results/report_*.html
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

    # Test type (positional argument — accepts one or more types)
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
    parser.add_argument("--coverage", action="store_true", help="Generate coverage report")
    parser.add_argument("--install", action="store_true", help="Install test dependencies")
    parser.add_argument("--no-validate", action="store_true", help="Skip environment validation")

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
    parser.add_argument(
        "--skip-playwright-js",
        action="store_true",
        help="For 'ui' (and e2e/ai-ui/all/coverage): run pytest tests/ui only; "
        "skip npx Playwright tests/playwright (saves most UI wall time)",
    )
    parser.add_argument(
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
                coverage=args.coverage,
                install_deps=args.install,
                validate_env=not args.no_validate,
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

        overall_results: list[tuple[str, bool, dict[str, int]]] = []
        all_passed = True

        for config in configs:
            # Create test runner
            runner = RunTestRunner(config)

            # Setup environment
            if not await runner.setup_environment():
                logger.error(f"Failed to setup test environment for {config.test_type.value}")
                overall_results.append((config.test_type.value, False, {}))
                all_passed = False
                continue

            try:
                # Run tests
                success = runner.run_tests()

                # Generate enhanced report for this type
                runner.print_enhanced_summary()

                counts = _extract_counts(runner)
                overall_results.append((config.test_type.value, success, counts))
                if not success:
                    all_passed = False

            finally:
                # Teardown environment
                await runner.teardown_environment()

        # Print combined summary when multiple types were requested
        if len(configs) > 1:
            _print_combined_summary(overall_results)

        return 0 if all_passed else 1

    except KeyboardInterrupt:
        logger.info("Test execution interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Test runner failed: {e}")
        logger.exception("Full traceback:")
        return 1


def _extract_counts(runner: "RunTestRunner") -> dict[str, int]:
    """Aggregate passed/failed/skipped counts from a runner's results."""
    passed = failed = skipped = 0
    for key in ("pytest", "playwright"):
        if key in runner.results and "counts" in runner.results[key]:
            c = runner.results[key]["counts"]
            passed += c.get("passed", 0)
            failed += c.get("failed", 0) + c.get("errors", 0)
            skipped += c.get("skipped", 0)
    return {"passed": passed, "failed": failed, "skipped": skipped}


def _print_combined_summary(results: list[tuple[str, bool, dict[str, int]]]) -> None:
    """Print a final combined summary across all test types."""
    GREEN = "\033[32m"
    RED = "\033[31m"
    YELLOW = "\033[33m"
    DIM = "\033[2m"
    RESET = "\033[0m"

    print("\n")
    print("=" * 72)
    print("  COMBINED TEST SUMMARY")
    print("=" * 72)
    print(f"  {'Type':<16s} {'Passed':>8s} {'Failed':>8s} {'Skipped':>8s}   Status")
    print(f"  {'-' * 16} {'-' * 8} {'-' * 8} {'-' * 8}   {'-' * 8}")

    totals = {"passed": 0, "failed": 0, "skipped": 0}
    all_passed = True

    for test_type, passed, counts in results:
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


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
