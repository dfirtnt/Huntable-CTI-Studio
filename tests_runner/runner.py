"""RunTestRunner -- orchestrator for all test suite execution.

This module owns the RunTestRunner class, which drives environment setup,
subprocess management, output parsing, and reporting.  The class delegates to
helpers in config.py, env.py, tui.py, containers.py, etc.
"""

from __future__ import annotations

import logging
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

# Project root is two levels up from this file (tests_runner/runner.py -> /)
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tests.utils.test_database_url import build_test_database_url  # noqa: E402
from tests_runner.config import ExecutionContext, RunTestConfig, RunTestType  # noqa: E402
from tests_runner.env import in_ci as _in_ci  # noqa: E402
from tests_runner.env import load_dotenv as _load_dotenv_raw
from tests_runner.env import strip_cloud_llm_keys as _strip_cloud_llm_keys_raw
from tests_runner.tui import Glyph, _RunnerTUI  # noqa: E402

# Logging (mirrors run_tests.py setup)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Thin wrappers to preserve internal call signatures
def _load_dotenv() -> None:
    _load_dotenv_raw(project_root)

def _strip_cloud_llm_keys() -> None:
    _strip_cloud_llm_keys_raw()

# Enhanced debugging (best-effort; optional test utilities)
try:
    from tests.utils.test_failure_analyzer import TestFailureReporter  # noqa: F401
    from tests.utils.test_isolation import TestIsolationManager  # noqa: F401
    from tests.utils.test_output_formatter import TestOutputFormatter  # noqa: F401

    from tests.utils.async_debug_utils import AsyncDebugger  # noqa: F401
    from tests.utils.performance_profiler import (  # noqa: F401
        PerformanceProfiler,
        start_performance_monitoring,
        stop_performance_monitoring,
    )
    DEBUGGING_AVAILABLE = True
except ImportError:
    DEBUGGING_AVAILABLE = False


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
        self.failed_test_names: list[str] = []  # Collect names of failed tests for combined summary
        self._plugin_cache: dict[str, bool] = {}  # Cache for venv plugin availability checks

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

    def _check_plugin(self, name: str) -> bool:
        """Return True if the named Python package is importable in the venv.

        Results are cached on this instance so multiple calls within the same
        test run do not spawn extra subprocesses.
        """
        if name not in self._plugin_cache:
            result = subprocess.run(
                [self.venv_python, "-c", f"import {name}"],
                capture_output=True,
                check=False,
            )
            self._plugin_cache[name] = result.returncode == 0
        return self._plugin_cache[name]

    def _wait_for_test_containers(self, timeout_seconds: int = 90) -> bool:
        """Wait until required local test containers report healthy status.

        Uses a single ``docker compose ps --format json`` call per cycle (one
        subprocess instead of 2*N).  Falls back to the legacy per-service
        ``docker inspect`` path when the JSON format is unavailable (older
        Docker installs) or cannot be parsed.
        """
        compose_base = ["docker", "compose", "-f", str(project_root / "docker-compose.test.yml")]
        required_services = ("postgres_test", "redis_test")
        deadline = time.time() + timeout_seconds

        while time.time() < deadline:
            statuses, all_healthy = self._poll_container_health_batch(compose_base, required_services)
            if all_healthy:
                logger.info("Test containers ready: %s", ", ".join(statuses))
                return True
            logger.debug("Waiting for test containers: %s", ", ".join(statuses))
            time.sleep(2)

        logger.error("Timed out waiting for test containers to become healthy")
        return False

    def _poll_container_health_batch(
        self,
        compose_base: list[str],
        required_services: tuple[str, ...],
    ) -> tuple[list[str], bool]:
        """Return (statuses, all_healthy) using one docker compose ps call.

        Falls back to per-service docker inspect when the JSON format is
        unavailable or unparseable (older Docker / Compose versions).
        """
        import json as _json

        try:
            result = subprocess.run(
                [*compose_base, "ps", "--format", "json", *required_services],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                raise ValueError("docker compose ps --format json failed")

            # Docker Compose v2 emits one JSON object per line.
            health_by_service: dict[str, str] = {}
            for raw_line in result.stdout.splitlines():
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                obj = _json.loads(raw_line)
                svc = obj.get("Service") or obj.get("Name", "")
                # Health is nested under State in some versions, top-level in others.
                health = (
                    obj.get("Health")
                    or (obj.get("State") or {}).get("Health", {}).get("Status", "")
                    or obj.get("Status", "unknown")
                )
                if svc:
                    health_by_service[svc] = health

            statuses: list[str] = []
            all_healthy = True
            for service in required_services:
                status = health_by_service.get(service, "missing")
                statuses.append(f"{service}={status}")
                if status != "healthy":
                    all_healthy = False
            return statuses, all_healthy

        except Exception:
            # Fall back to legacy per-service inspect path.
            return self._poll_container_health_legacy(compose_base, required_services)

    def _poll_container_health_legacy(
        self,
        compose_base: list[str],
        required_services: tuple[str, ...],
    ) -> tuple[list[str], bool]:
        """Legacy per-service docker inspect fallback for older Docker versions."""
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
                fallback_name = f"cti_{service}"
                fb_result = subprocess.run(
                    ["docker", "inspect", "--format", "{{.Id}}", fallback_name],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                container_id = (fb_result.stdout or "").strip() if fb_result.returncode == 0 else ""

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

        return statuses, all_healthy

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
            RunTestType.UI_SMOKE,
            RunTestType.UI_FAST,
            RunTestType.UI_FULL,
            RunTestType.INTEGRATION,
            RunTestType.E2E,
            RunTestType.ALL,
            RunTestType.ALL_NO_UI,
            RunTestType.COVERAGE,
        }

        needs_test_containers = self.config.test_type in stateful_test_types

        if needs_test_containers:
            if not _in_ci():
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
        if needs_test_containers and not _in_ci() and "REDIS_PORT" not in os.environ:
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

        # Test environment utilities not currently available
        logger.debug("Advanced environment setup not available; using basic setup")
        return True

    async def teardown_environment(self):
        """Tear down test environment."""
        # Check if we started test containers and should tear them down
        # For now, we leave containers running (user can run 'make test-down' manually)
        # This allows faster subsequent test runs

        # Skip teardown if validation was skipped (no test DB configured)
        if not self.config.run_teardown:
            logger.debug("Skipping teardown (teardown disabled)")
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
            [uv_binary, "sync", "--frozen", "--group", "test"],
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
            [self.venv_python, "-m", "playwright", "install", "chromium"],
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

    # Map from tests/ subdirectory name to the display category used in progress bars.
    # Every directory that pytest might collect from must appear here so the progress
    # tracker and the group list use the same vocabulary.
    _DIR_TO_CATEGORY = {
        "smoke": "smoke",
        "unit": "unit",
        "services": "unit",
        "utils": "unit",
        "core": "unit",
        "config": "unit",
        "cli": "unit",
        "workflows": "unit",
        "database": "unit",
        "quality": "unit",
        "scripts": "unit",
        "sigma_semantic_similarity": "unit",
        "templates": "unit",
        "worker": "unit",
        "api": "api",
        "integration": "integration",
        "ui": "ui",
        "e2e": "e2e",
        "docs": "docs",
    }

    def _get_pytest_test_groups(self) -> list[str]:
        """Determine which pytest test groups are being executed based on test type.

        Returns display-level category names (the same vocabulary used by the
        progress-bar tracker) so the denominator and numerator always agree.
        """
        test_type = self.config.test_type

        if self.config.test_paths:
            # Resolve each path to a display category by exact directory-part
            # match.  String substring matching mis-classifies paths such as
            # tests/api/test_smoke_endpoints.py (contains "smoke" as substring).
            groups: set[str] = set()
            for path in self.config.test_paths:
                parts = set(Path(path).parts)
                for dirname, category in self._DIR_TO_CATEGORY.items():
                    if dirname in parts:
                        groups.add(category)
                        break
            return sorted(groups) if groups else ["all"]

        # Map test types to display categories (deduplicated).
        group_map = {
            RunTestType.SMOKE: ["smoke"],
            RunTestType.UNIT: ["unit"],
            RunTestType.API: ["api"],
            RunTestType.INTEGRATION: ["integration"],
            RunTestType.UI: ["ui"],
            RunTestType.E2E: ["e2e"],
            RunTestType.REGRESSION: ["regression"],
            RunTestType.CONTRACT: ["contract"],
            RunTestType.SECURITY: ["security"],
            RunTestType.A11Y: ["a11y"],
            RunTestType.PERFORMANCE: ["performance"],
            RunTestType.AI: ["ui", "integration"],
            RunTestType.AI_UI: ["ui"],
            RunTestType.AI_INTEGRATION: ["integration"],
            RunTestType.ALL: ["smoke", "unit", "api", "integration", "ui", "e2e"],
            RunTestType.COVERAGE: ["smoke", "unit", "api", "integration", "ui", "e2e"],
        }

        return group_map.get(test_type, ["all"])

    def _get_playwright_test_groups(self) -> list[str]:
        """Determine which Playwright test groups are being executed."""
        playwright_cmd = self._build_playwright_command()
        if not playwright_cmd:
            return []

        groups = []
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
            RunTestType.UI_SMOKE: [],  # Tier 1: pytest smoke only; no Playwright
            RunTestType.UI_FAST: ["tests/playwright/", "tests/test_help_buttons.spec.js"],
            RunTestType.UI_FULL: ["tests/playwright/", "tests/test_help_buttons.spec.js"],
            RunTestType.E2E: ["tests/playwright/", "tests/test_help_buttons.spec.js"],
            RunTestType.ALL_NO_UI: [],  # Explicitly skip Playwright for all-no-ui runs
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

        # --area: scope to a single Playwright feature project
        if self.config.playwright_project:
            cmd.extend(["--project", self.config.playwright_project])

        # Add verbosity
        if self.config.verbose or self.config.debug:
            cmd.append("--reporter=list")

        # Allure is configured in playwright.config.ts, so no need to add it here

        return cmd

    def _run_command(self, cmd: list[str], description: str, capture_output: bool = True) -> bool:
        """Run a command and return success status."""
        logger.info(f"Running: {description}")

        if self.config.debug:
            logger.debug(f"Command: {cmd}")

        try:
            result = subprocess.run(
                cmd,
                shell=False,
                check=True,
                capture_output=capture_output,
                text=True,
                timeout=self.config.timeout,
            )

            logger.info(f"Completed: {description}")

            if capture_output and result.stdout and self.config.verbose:
                logger.info(f"Output: {result.stdout}")

            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed: {description}")
            logger.error(f"Error: {e}")

            if capture_output:
                if e.stdout:
                    logger.error(f"Stdout: {e.stdout}")
                if e.stderr:
                    logger.error(f"Stderr: {e.stderr}")

            return False

        except subprocess.TimeoutExpired as e:
            logger.error(f"Timed out: {description} after {e.timeout} seconds")
            return False

        except Exception as e:
            logger.error(f"Unexpected error in {description}: {e}")
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
                ],  # Restrict to tests/ directory to avoid collection errors
                RunTestType.UNIT: [
                    "tests/",
                    "--ignore=tests/test_web_application.py",  # Exclude web app tests (require running server)
                    "--ignore=tests/ui/",  # Exclude UI tests (require browser/Playwright)
                    "--ignore=tests/api/",  # Exclude api (langfuse+pydantic v1 incompatible with Python 3.14)
                    "-m",
                    "not (smoke or integration or api or ui or e2e or performance or infrastructure or prod_data or production_data)",
                ],
                RunTestType.API: ["tests/api/"],
                RunTestType.INTEGRATION: [
                    "tests/integration/",
                    "-m",
                    "integration",
                ],
                RunTestType.UI: ["tests/ui/"],
                RunTestType.UI_SMOKE: ["tests/ui/"],
                RunTestType.UI_FAST: ["tests/ui/"],
                RunTestType.UI_FULL: ["tests/ui/"],
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
                RunTestType.ALL_NO_UI: [
                    "tests/",
                    "--ignore=tests/ui/",
                    "--ignore=tests/e2e/",
                ],
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
            RunTestType.UI_SMOKE: ["ui_smoke or smoke"],
            RunTestType.UI_FAST: ["ui"],
            RunTestType.UI_FULL: ["ui"],
            RunTestType.E2E: ["e2e"],
            RunTestType.REGRESSION: ["regression"],
            RunTestType.CONTRACT: ["contract"],
            RunTestType.SECURITY: ["security"],
            RunTestType.A11Y: ["a11y"],
            RunTestType.PERFORMANCE: ["performance"],
            RunTestType.AI: [],
            RunTestType.AI_UI: ["ui"],
            RunTestType.AI_INTEGRATION: ["integration"],
            RunTestType.ALL_NO_UI: [],
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
        # Also exclude @pytest.mark.slow by default (performance/mobile/accessibility) -- use --include-slow to run them
        elif self.config.test_type == RunTestType.UI and not self.config.include_agent_config_tests:
            default_excludes.append("agent_config_mutation")
            if not self.config.include_slow:
                default_excludes.append("slow")
        # UI tiers: ui-smoke (tier 1) skips slow + agent-config-mutating
        elif self.config.test_type == RunTestType.UI_SMOKE:
            default_excludes.extend(["slow", "agent_config_mutation"])
        # ui-fast (tier 3): full UI minus @slow (mobile/a11y/perf), parallel by default
        elif self.config.test_type == RunTestType.UI_FAST:
            default_excludes.extend(["slow"])
            if not self.config.include_agent_config_tests:
                default_excludes.append("agent_config_mutation")
        # ui-full (tier 4): everything including @slow; only excluded by explicit --exclude-markers
        # all-no-ui: run the full suite, but exclude UI-marked tests and Playwright JS.
        elif self.config.test_type == RunTestType.ALL_NO_UI:
            default_excludes.extend(["ui", "ui_smoke", "e2e"])
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
        if self.config.test_type in (
            RunTestType.UI,
            RunTestType.UI_SMOKE,
            RunTestType.UI_FAST,
            RunTestType.UI_FULL,
            RunTestType.E2E,
            RunTestType.ALL,
            RunTestType.COVERAGE,
        ):
            if self._check_plugin("pytest_timeout"):
                cmd.extend(["--timeout=60", "--timeout-method=signal"])

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
        # UI tests hit a single live server (localhost:8001).  Default to -n 4 for UI runs
        # to match the Playwright worker cap on macOS; matches well with browser-driven
        # I/O parallelism without overwhelming the single live stack.  Use --parallel for
        # -n auto (all CPU cores), or --serial to disable parallelism entirely.
        if self.config.serial:
            pass  # Explicit serial; do not add -n
        elif self.config.parallel:
            cmd.extend(["-n", "auto"])
        elif (
            self.config.test_type
            in (RunTestType.UI, RunTestType.UI_SMOKE, RunTestType.UI_FAST, RunTestType.UI_FULL, RunTestType.E2E)
            and not self.config.fail_fast
        ):
            if self._check_plugin("xdist"):
                # ui-smoke is fast pytest-only; cap at 2 since smoke tests are already short
                # and worker startup overhead dominates
                workers = "2" if self.config.test_type == RunTestType.UI_SMOKE else "4"
                cmd.extend(["-n", workers])

        # Add coverage
        if self.config.coverage:
            ts = time.strftime("%Y%m%d_%H%M%S")
            cov_args = [
                "--cov=src",
                "--cov-branch",
                "--cov-report=html:htmlcov",
                "--cov-report=xml:coverage.xml",
                "--cov-report=term-missing",
                f"--cov-report=json:test-results/coverage_{ts}.json",
            ]
            if self.config.cov_append:
                cov_args.append("--cov-append")
            fail_under = os.getenv("CTI_COVERAGE_FAIL_UNDER")
            if fail_under:
                cov_args.append(f"--cov-fail-under={fail_under}")
            cmd.extend(cov_args)

        # Add output format.
        # progress (default): no -v; --verbose flag adds -v; verbose format adds -vv; quiet adds -q.
        if self.config.output_format == "verbose":
            cmd.append("-vv")
        elif self.config.output_format == "quiet":
            cmd.append("-q")
        elif self.config.verbose:
            cmd.append("-v")

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
        if self._check_plugin("allure"):
            cmd.extend(["--alluredir=allure-results"])

        # Add JUnit XML report for CI/CD and failure analysis.
        # Use absolute paths so pytest-html can write incrementally regardless of cwd.
        results_dir = project_root / "test-results"
        cmd.extend([f"--junit-xml={results_dir / f'junit_{self.timestamp}.xml'}"])

        # Add HTML report only if pytest-html is installed (avoids pytest usage error)
        html_check = subprocess.run(
            [self.venv_python, "-c", "import pytest_html"],
            capture_output=True,
            check=False,
        )
        if html_check.returncode == 0:
            cmd.append(f"--html={results_dir / f'report_{self.timestamp}.html'}")

        # Add JSONL report log only if pytest-reportlog is installed
        reportlog_check = subprocess.run(
            [self.venv_python, "-c", "import pytest_reportlog"],
            capture_output=True,
            check=False,
        )
        if reportlog_check.returncode == 0:
            cmd.append(f"--report-log={results_dir / f'reportlog_{self.timestamp}.jsonl'}")

        # Redirect pytest-playwright output to a subdirectory so its session-start rmtree()
        # does not delete test-results/ itself (which would cause pytest-html FileNotFoundError).
        cmd.append(f"--output={results_dir / 'playwright-output'}")

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

            # Environment utilities configuration disabled (not currently available)

            # Add skip real API flag
            if self.config.skip_real_api:
                env["SKIP_REAL_API_TESTS"] = "1"

            # Use in-process ASGI client for any run that may collect from tests/api/.
            # API/Security: direct. Regression/All/Coverage: sweep tests/ with markers that
            # include api-marked tests -- without this flag the async_client fixture falls
            # through to http://127.0.0.1:8001 which has no live server, causing ConnectError.
            _api_collecting_runs = (
                RunTestType.API,
                RunTestType.SECURITY,
                RunTestType.REGRESSION,
                RunTestType.ALL,
                RunTestType.ALL_NO_UI,
                RunTestType.COVERAGE,
            )
            if self.config.test_type in _api_collecting_runs:
                env["USE_ASGI_CLIENT"] = "1"
                # In-process app must reach Redis on host (docker port map 6379)
                if (
                    "REDIS_URL" not in env
                    or "redis:6379" in env.get("REDIS_URL", "")
                    or "redis:6380" in env.get("REDIS_URL", "")
                ):
                    env["REDIS_URL"] = "redis://localhost:6379/0"

            env.update(self._get_agent_config_exclude_env())

            # ui-full tier: also run quarantined Playwright suites
            if self.config.test_type == RunTestType.UI_FULL:
                env["CTI_INCLUDE_QUARANTINE"] = "1"

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
            # pytest-html writes during test execution (not just at end), so directory must exist.
            # Use project_root-relative paths because pytest runs with cwd=project_root.
            test_results_dir = project_root / "test-results"
            test_results_dir.mkdir(parents=True, exist_ok=True)

            # Also ensure allure-results exists
            allure_results_dir = project_root / "allure-results"
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

                # Show progress bar only for multi-category runs (e.g. "all");
                # single-category runs (smoke, unit, api) just show the banner.
                show_progress = len(pytest_groups) > 1

                print("\n" + "=" * 80)
                print("RUNNING PYTEST TESTS")
                if pytest_groups:
                    print(f"   Test Categories: {', '.join(pytest_groups)}")
                    if show_progress:
                        print(f"   Progress: [{' ' * len(pytest_groups)}] 0/{len(pytest_groups)} categories")
                print("=" * 80)
                logger.info(f"Executing pytest: {cmd_str}")
                print()

                process: subprocess.Popen | None = None
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

                    tui = _RunnerTUI(self.config.tui)
                    tui.start(pytest_groups)

                    while True:
                        line = output_queue.get()
                        if line is None:
                            break
                        output_lines.append(line)
                        if tui.is_active:
                            tui.on_line(line)
                        else:
                            print(line, end="", flush=True)

                        # Count individual test results (visible at -v and above).
                        # Also captures failed test names for the summary.
                        if "::" in line and (
                            "PASSED" in line or "FAILED" in line or "SKIPPED" in line or "ERROR" in line
                        ):
                            test_count += 1
                            if "FAILED" in line or "ERROR" in line:
                                # Extract test identifier (e.g. "tests/ui/test_foo.py::test_bar")
                                # Formats: "tests/x.py::test FAILED" or "[gw0] FAILED tests/x.py::test"
                                stripped = line.strip()
                                if stripped.startswith("["):
                                    # xdist: "[gw0] FAILED tests/x.py::test"
                                    parts = stripped.split(None, 2)
                                    if len(parts) >= 3:
                                        self.failed_test_names.append(parts[2].strip())
                                else:
                                    # plain: "tests/x.py::test FAILED"
                                    name = stripped.split(" FAILED")[0].split(" ERROR")[0].strip()
                                    if name:
                                        self.failed_test_names.append(name)

                        # Category detection: works at any verbosity level.
                        # -v:      "tests/smoke/test_foo.py::test PASSED"
                        # default: "tests/smoke/test_foo.py .....       [ 10%]"
                        # Only fires for multi-category runs (show_progress=True).
                        if show_progress and "tests/" in line:
                            try:
                                path_part = line.split("tests/")[1].split("/")[0]
                                detected = self._DIR_TO_CATEGORY.get(path_part)
                                # Only announce categories in the declared groups so
                                # marker-based runs don't overflow the progress bar denominator.
                                pytest_groups_set = set(pytest_groups) if pytest_groups else set()
                                if (
                                    detected
                                    and detected not in categories_seen
                                    and detected in pytest_groups_set
                                ):
                                    categories_seen.add(detected)
                                    elapsed = time.time() - pytest_start_time
                                    progress_chars = [
                                        "=" if c in categories_seen else " " for c in pytest_groups
                                    ]
                                    n, total = len(categories_seen), len(pytest_groups)
                                    if tui.is_active:
                                        tui.on_category(categories_seen, test_count)
                                    else:
                                        print(
                                            f"\nCategory: {detected.upper()} | [{''.join(progress_chars)}] "
                                            f"{n}/{total} | Tests: {test_count} | {elapsed:.1f}s",
                                            flush=True,
                                        )
                            except (IndexError, AttributeError):
                                pass

                        if not tui.is_active and time.time() - last_progress_update > 3.0 and show_progress and sys.stdout.isatty():
                            elapsed = time.time() - pytest_start_time
                            progress_chars = ["=" if c in categories_seen else " " for c in pytest_groups]
                            print(
                                f"\r[{''.join(progress_chars)}] {len(categories_seen)}/{len(pytest_groups)} "
                                f"| {test_count} tests | {elapsed:.1f}s",
                                end="",
                                flush=True,
                            )
                            last_progress_update = time.time()

                    returncode = process.wait(
                        timeout=self._remaining_timeout(pytest_start_time)
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

                    # Write failure log only when there are failures or errors.
                    if not pytest_success:
                        self._save_failure_log(stdout_text + stderr_text, pytest_counts, source="pytest")

                    # Stop TUI (or clear the plain \r progress line)
                    tui.finish()
                    if not tui.is_active and show_progress and sys.stdout.isatty():
                        print("\r" + " " * 100 + "\r", end="")  # Clear progress line
                    print()
                    print("=" * 80)
                    status = f"{Glyph.PASS} PASSED" if pytest_success else f"{Glyph.FAIL} FAILED"
                    print(f"PYTEST TESTS: {status} ({pytest_duration:.2f}s)")
                    passed = pytest_counts.get("passed", 0)
                    failed = pytest_counts.get("failed", 0)
                    skipped = pytest_counts.get("skipped", 0)
                    err_suffix = (
                        f" | Errors: {pytest_counts.get('errors', 0)}" if pytest_counts.get("errors", 0) else ""
                    )
                    print(f"   Passed: {passed} | Failed: {failed} | Skipped: {skipped}{err_suffix}")
                    if not pytest_success:
                        failure_path = test_results_dir / f"failures_pytest_{self.timestamp}.log"
                        if failure_path.exists():
                            print(f"   Failure details: test-results/failures_pytest_{self.timestamp}.log")
                    html_path = test_results_dir / f"report_{self.timestamp}.html"
                    junit_path = test_results_dir / f"junit_{self.timestamp}.xml"
                    if html_path.exists():
                        print(f"   HTML report: test-results/report_{self.timestamp}.html")
                    if junit_path.exists():
                        print(f"   JUnit XML: test-results/junit_{self.timestamp}.xml")
                    allure_dir = project_root / "allure-results"
                    if allure_dir.exists() and any(allure_dir.iterdir()):
                        print("   Allure report: allure serve allure-results")
                    print("=" * 80)

                except subprocess.TimeoutExpired:
                    if process is not None:
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
                        print(f"{Glyph.WARN}  --playwright-last-failed requires a previous Playwright run with failures.")
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
                    print("RUNNING PLAYWRIGHT TESTS")
                    if playwright_groups:
                        print(f"   Test Groups: {', '.join(playwright_groups)}")
                        print(f"   Progress: [{' ' * len(playwright_groups)}] 0/{len(playwright_groups)} groups")
                    print("=" * 80)
                    logger.info(f"Executing Playwright: {cmd_str}")
                    print()

                    process = None
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
                            if any(w in line.lower() for w in ["passed", "failed", "skipped"]):
                                pw_test_count += 1
                                # Capture failed Playwright test names
                                # List reporter: "  1) [chromium] > test.spec.ts:10:5 > suite > test name"
                                # or lines containing "failed" with a bracket project prefix
                                stripped = line.strip()
                                if "failed" in stripped.lower() and ("[" in stripped or ">>" in stripped):
                                    self.failed_test_names.append(f"[playwright] {stripped}")
                            if time.time() - pw_last_update > 3.0 and playwright_groups and sys.stdout.isatty():
                                elapsed = time.time() - playwright_start_time
                                est = min(len(playwright_groups), max(1, pw_test_count // 5))
                                bar = "=" * est + " " * (len(playwright_groups) - est)
                                msg = f"\r[{bar}] {est}/{len(playwright_groups)} | {pw_test_count} | {elapsed:.1f}s"
                                print(msg, end="", flush=True)
                                pw_last_update = time.time()

                        returncode = process.wait(
                            timeout=self._remaining_timeout(playwright_start_time)
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
                        if playwright_groups and sys.stdout.isatty():
                            print("\r" + " " * 100 + "\r", end="")  # Clear progress line
                        print()
                        print("=" * 80)
                        status = f"{Glyph.PASS} PASSED" if playwright_success else f"{Glyph.FAIL} FAILED"
                        print(f"PLAYWRIGHT TESTS: {status} ({playwright_duration:.2f}s)")
                        pp, pf, ps = (
                            playwright_counts.get("passed", 0),
                            playwright_counts.get("failed", 0),
                            playwright_counts.get("skipped", 0),
                        )
                        print(f"   Passed: {pp} | Failed: {pf} | Skipped: {ps}")
                        if not playwright_success:
                            self._save_failure_log(stdout_text + stderr_text, playwright_counts, source="playwright")
                            pw_failure_path = test_results_dir / f"failures_playwright_{self.timestamp}.log"
                            if pw_failure_path.exists():
                                print(f"   Failure details: test-results/failures_playwright_{self.timestamp}.log")
                        print("=" * 80)

                    except subprocess.TimeoutExpired:
                        if process is not None:
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
            (r"(\d+)\s+failed\b(?=\s*,|\s+in\b)", "failed"),
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

    def _build_dry_run_env(self) -> dict[str, str]:
        """Return the env vars this runner would inject, without mutating os.environ.

        Mirrors the env-setup logic in run_tests() so --dry-run output reflects
        the exact vars the live run would set.
        """
        env: dict[str, str] = {}
        env["APP_ENV"] = "test"

        td = os.environ.get("TEST_DATABASE_URL") or build_test_database_url(asyncpg=True)
        if td:
            env["TEST_DATABASE_URL"] = td

        _api_collecting_runs = (
            RunTestType.API,
            RunTestType.SECURITY,
            RunTestType.REGRESSION,
            RunTestType.ALL,
            RunTestType.ALL_NO_UI,
            RunTestType.COVERAGE,
        )
        if self.config.test_type in _api_collecting_runs:
            env["USE_ASGI_CLIENT"] = "1"
            env["REDIS_URL"] = "redis://localhost:6379/0"
        else:
            redis_port = os.getenv("REDIS_TEST_PORT", "6380")
            env["REDIS_URL"] = os.environ.get("REDIS_URL", f"redis://localhost:{redis_port}/0")

        env.update(self._get_agent_config_exclude_env())

        if self.config.test_type == RunTestType.UI_FULL:
            env["CTI_INCLUDE_QUARANTINE"] = "1"

        return env

    def _remaining_timeout(self, started_at: float) -> float | None:
        """Return seconds left before config.timeout expires, clamped to at least 0.1s."""
        if not self.config.timeout:
            return None
        return max(0.1, self.config.timeout - (time.time() - started_at))

    def _save_failure_log(self, output: str, counts: dict[str, int], source: str = "pytest") -> None:
        """Save failure details to a log file.

        Args:
            output: Combined stdout/stderr from the test runner.
            counts: Parsed pass/fail/skip counts.
            source: Runner that produced the output ("pytest" or "playwright").
                    Used in the filename to avoid overwrites when both fail.
        """
        from datetime import datetime

        # Ensure test-results directory exists (project_root-relative, matching pytest cwd)
        test_results_dir = project_root / "test-results"
        test_results_dir.mkdir(exist_ok=True)

        # Include source + timestamp so pytest and playwright never clobber each other
        failure_log_path = test_results_dir / f"failures_{source}_{self.timestamp}.log"

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
        total_duration = time.time() - self.start_time

        print("\n" + "=" * 60)
        print(f"Test Execution Report ({total_duration:.2f}s)")
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
                print(f"\nTest execution only: {test_only_duration:.2f}s")
            print(f"Total (including setup): {total_duration:.2f}s")
            return

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
        print(f"Test Type: {self.config.test_type.value}")
        print(f"Context: {self.config.context.value}")
        print(f"Debug Mode: {'Yes' if self.config.debug else 'No'}")
        print(f"Coverage: {'Yes' if self.config.coverage else 'No'}")

        # Test Groups Summary
        print("\n" + "=" * 80)
        print("TEST EXECUTION SUMMARY")
        print("=" * 80)

        if self.test_groups_executed:
            print(f"\n{Glyph.PASS} Test Groups Executed:")
            # Group by framework
            pytest_groups = [g.replace("pytest:", "") for g in self.test_groups_executed if g.startswith("pytest:")]
            playwright_groups = [
                g.replace("playwright:", "") for g in self.test_groups_executed if g.startswith("playwright:")
            ]

            if pytest_groups:
                print("  Pytest:")
                for group in sorted(set(pytest_groups)):
                    print(f"     - {group}")

            if playwright_groups:
                print("  Playwright:")
                for group in sorted(set(playwright_groups)):
                    print(f"     - {group}")
        else:
            print(f"\n{Glyph.WARN}  No test groups tracked")

        # Results summary
        if self.results:
            print("\nTest Results:")
            for test_type, result in self.results.items():
                if isinstance(result, dict) and "success" in result:
                    status = f"{Glyph.PASS} PASS" if result["success"] else f"{Glyph.FAIL} FAIL"
                    duration = result.get("duration", 0)
                    print(f"  {test_type}: {status} ({duration:.2f}s)")

                    # Show pytest/playwright breakdown if available
                    if "pytest" in result or "playwright" in result:
                        if "pytest" in result and result["pytest"] is not None:
                            pytest_status = Glyph.PASS if result["pytest"] else Glyph.FAIL
                            pytest_duration = self.results.get("pytest", {}).get("duration", 0)
                            print(f"    - pytest: {pytest_status} ({pytest_duration:.2f}s)")
                        if "playwright" in result and result["playwright"] is not None:
                            pw_status = Glyph.PASS if result["playwright"] else Glyph.FAIL
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
            print(f"\nTest execution only: {test_only_duration:.2f}s")
        print(f"Total (including setup): {total_duration:.2f}s")

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

        overall_label = f"{Glyph.PASS} ALL TESTS PASSED" if overall_success else f"{Glyph.FAIL} SOME TESTS FAILED"
        print(f"Overall Status: {overall_label}")

        # Report locations
        print("\nGenerated Reports:")

        # Test results
        test_results_dir = Path("test-results")
        if test_results_dir.exists():
            print(f"  Test Results: {test_results_dir.absolute()}")

            # Allure results
            allure_results = Path("allure-results")
            if allure_results.exists():
                print(f"  Allure Results: {allure_results.absolute()}")
                print("    Tip: Run 'allure serve allure-results' for interactive reports")

            # Report log (timestamped, generated by pytest-reportlog)
            report_log = test_results_dir / f"reportlog_{self.timestamp}.jsonl"
            if report_log.exists():
                print(f"  Report Log: {report_log.absolute()}")

        # Coverage report
        coverage_dir = Path("htmlcov")
        if coverage_dir.exists():
            index_file = coverage_dir / "index.html"
            if index_file.exists():
                print(f"  Coverage Report: {index_file.absolute()}")

        # Available test categories
        print("\nAvailable Test Categories:")
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
            print(f"  - {category:<15} {description}")

        # Usage examples
        print("\nUsage Examples:")
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
        print("\nNew Test Infrastructure:")
        print("  - Test containers: make test-up / make test-down")
        print("  - Test environment guards prevent production DB access")
        print("  - Stateful tests require test containers (auto-started if needed)")
        print("  - See docs/TESTING_STRATEGY.md for details")


