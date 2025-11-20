#!/usr/bin/env python3
"""
CTI Scraper Unified Test Runner

This is the single entry point for all test execution needs across different contexts.
Consolidates functionality from run_tests.py, run_tests.sh, and run_tests_standardized.py.

Features:
- Context-aware execution (localhost, Docker, CI/CD)
- Standardized environment management
- Enhanced error reporting and debugging
- Comprehensive test discovery and execution
- Rich output formatting and reporting
- Backward compatibility with existing interfaces

Usage:
    python run_tests.py --help                    # Show all options
    python run_tests.py smoke                     # Quick health check
    python run_tests.py all --coverage            # Full test suite with coverage
    python run_tests.py --docker integration      # Docker-based integration tests
    python run_tests.py --debug --verbose         # Debug mode with verbose output
"""

import os
import sys
import argparse
import asyncio
import subprocess
import time
import json
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Import test environment utilities
try:
    from tests.utils.test_environment import (
        TestEnvironmentValidator,
        TestEnvironmentManager,
        TestContext,
        get_test_config,
        validate_test_environment
    )
    from tests.utils.database_connections import (
        validate_database_connection,
        validate_redis_connection
    )
    ENVIRONMENT_UTILS_AVAILABLE = True
except ImportError:
    ENVIRONMENT_UTILS_AVAILABLE = False
    print("Warning: Test environment utilities not available. Some features may be limited.")

# Enhanced debugging imports
try:
    from tests.utils.test_failure_analyzer import TestFailureReporter
    from tests.utils.async_debug_utils import AsyncDebugger
    from tests.utils.test_isolation import TestIsolationManager
    from tests.utils.performance_profiler import PerformanceProfiler, start_performance_monitoring, stop_performance_monitoring
    from tests.utils.test_output_formatter import TestOutputFormatter, print_header, print_test_result, print_summary
    DEBUGGING_AVAILABLE = True
except ImportError as e:
    DEBUGGING_AVAILABLE = False
    print(f"Warning: Enhanced debugging utilities not available: {e}")
    print("Enhanced debugging features will not be available.")

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
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
    test_paths: Optional[List[str]] = None
    markers: Optional[List[str]] = None
    exclude_markers: Optional[List[str]] = None
    config_file: Optional[str] = None
    output_format: str = "progress"
    fail_fast: bool = False
    retry_count: int = 0
    timeout: Optional[int] = None


class TestRunner:
    """Unified test runner with enhanced functionality."""
    
    def __init__(self, config: TestConfig):
        self.config = config
        self.start_time = time.time()
        self.results = {}
        self.environment_manager = None
        
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
            subprocess.run(
                ["python3", "-m", "venv", venv_path],
                check=True,
                capture_output=True
            )
            logger.info("Virtual environment created")
        
        # Verify venv python exists
        if not os.path.exists(venv_python):
            logger.warning(f"Virtual environment Python not found at {venv_python}, falling back to system python3")
            return "python3"
        
        logger.info(f"Using virtual environment: {venv_python}")
        return venv_python
    
    async def setup_environment(self) -> bool:
        """Set up test environment."""
        if not ENVIRONMENT_UTILS_AVAILABLE:
            logger.warning("Environment utilities not available, skipping environment setup")
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
                if not all(validation_results.values()):
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
    
    def install_dependencies(self) -> bool:
        """Install test dependencies."""
        logger.info("Installing test dependencies...")
        
        # Virtual environment is already set up in __init__
        
        # Install from requirements files
        commands = [
            (f"{self.venv_pip} install --upgrade pip", "Upgrading pip"),
            (f"{self.venv_pip} install -r requirements.txt", "Installing project dependencies"),
        ]
        
        # Add test requirements if it exists (non-blocking)
        if os.path.exists("requirements-test.txt"):
            try:
                logger.info("Attempting to install test dependencies (may have conflicts, continuing if it fails)...")
                commands.append((f"{self.venv_pip} install -r requirements-test.txt", "Installing test dependencies"))
            except Exception:
                logger.warning("Test dependencies not installed, continuing without them")
        
        # Install Playwright if it's installed
        result = subprocess.run(
            [self.venv_python, "-c", "import playwright"],
            capture_output=True,
            check=False
        )
        if result.returncode == 0:
            commands.append((f"{self.venv_python} -m playwright install chromium", "Installing Playwright browser"))
        
        # Track which commands are optional
        optional_commands = ["Installing test dependencies"]
        
        for cmd, description in commands:
            result = self._run_command(cmd, description, capture_output=True)
            if not result and description not in optional_commands:
                logger.error(f"Failed to {description.lower()}")
                return False
            elif not result:
                logger.warning(f"Optional step failed: {description}")

        logger.info("Dependencies installed successfully")
        return True
    
    def _check_dependencies(self) -> bool:
        """Check if essential test dependencies are available in venv."""
        try:
            result = subprocess.run(
                [self.venv_python, "-c", "import pytest; import pytest_asyncio"],
                capture_output=True,
                check=False
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def _check_playwright_dependencies(self) -> bool:
        """Check if Playwright and npm dependencies are available."""
        try:
            # Check if npm/node is available
            result = subprocess.run(
                ["npm", "--version"],
                capture_output=True,
                check=False
            )
            if result.returncode != 0:
                return False
            
            # Check if package.json exists and has dependencies installed
            if not os.path.exists("package.json"):
                return False
            
            # Check if node_modules exists (dependencies installed)
            if not os.path.exists("node_modules"):
                return False
            
            # Check if allure-playwright is installed
            result = subprocess.run(
                ["npm", "list", "allure-playwright"],
                capture_output=True,
                check=False
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def _build_playwright_command(self) -> List[str]:
        """Build Playwright test command based on configuration."""
        cmd = ["npx", "playwright", "test"]
        
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
                timeout=self.config.timeout
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
    
    def _build_pytest_command(self) -> List[str]:
        """Build pytest command based on configuration."""
        cmd = ["python3", "-m", "pytest"]
        
        # Add test paths
        if self.config.test_paths:
            cmd.extend(self.config.test_paths)
        else:
            # Default test paths based on test type
            test_path_map = {
                TestType.SMOKE: ["tests/", "-m", "smoke"],
                TestType.UNIT: ["tests/", "-m", "not (smoke or integration or api or ui or e2e or performance)"],
                TestType.API: ["tests/api/"],
                TestType.INTEGRATION: ["tests/integration/", "-m", "integration_workflow"],
                TestType.UI: ["tests/ui/"],
                TestType.E2E: ["tests/e2e/"],
                TestType.PERFORMANCE: ["tests/", "-m", "performance"],
                TestType.AI: ["tests/ui/test_ai_assistant_ui.py", "tests/integration/test_ai_*.py", "-m", "ai"],
                TestType.AI_UI: ["tests/ui/test_ai_assistant_ui.py", "-m", "ui and ai"],
                TestType.AI_INTEGRATION: ["tests/integration/test_ai_*.py", "-m", "integration and ai"],
                TestType.ALL: ["tests/"],
                TestType.COVERAGE: ["tests/", "--cov=src"]
            }
            
            if self.config.test_type in test_path_map:
                cmd.extend(test_path_map[self.config.test_type])
            else:
                cmd.append("tests/")
        
        # Add markers
        if self.config.markers:
            marker_expr = " or ".join(self.config.markers)
            cmd.extend(["-m", marker_expr])
        
        # Exclude markers
        if self.config.exclude_markers:
            exclude_expr = " and ".join([f"not {marker}" for marker in self.config.exclude_markers])
            if self.config.markers:
                cmd.extend(["-m", f"({marker_expr}) and ({exclude_expr})"])
            else:
                cmd.extend(["-m", exclude_expr])
        
        # Use virtual environment python (always set to venv)
        cmd[0] = self.venv_python
        
        # Add execution context specific options
        if self.config.context == ExecutionContext.DOCKER:
            cmd = ["docker", "exec", "cti_web"] + cmd
        
        # Add parallel execution
        if self.config.parallel:
            logger.warning("Parallel execution requires pytest-xdist. Install with: pip install pytest-xdist")
            cmd.extend(["-n", "auto"])
        
        # Add coverage
        if self.config.coverage:
            cmd.extend([
                "--cov=src",
                "--cov-report=html:htmlcov",
                "--cov-report=xml:coverage.xml",
                "--cov-report=term-missing"
            ])
        
        # Add output format
        if self.config.output_format == "progress":
            cmd.append("-q" if not self.config.verbose else "-v")
        elif self.config.output_format == "verbose":
            cmd.append("-v")
        elif self.config.output_format == "quiet":
            cmd.append("-q")
        
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
        
        # Add timeout
        if self.config.timeout:
            cmd.extend(["--timeout", str(self.config.timeout)])
        
        # Add reporting (only if allure is available in venv)
        try:
            result = subprocess.run(
                [self.venv_python, "-c", "import allure"],
                capture_output=True,
                check=False
            )
            if result.returncode == 0:
                cmd.extend(["--alluredir=allure-results"])
        except Exception:
            pass
        
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
            if ENVIRONMENT_UTILS_AVAILABLE:
                try:
                    validator = TestEnvironmentValidator()
                    test_config = validator.load_test_config(self.config.config_file)
                    env.update({
                        "DATABASE_URL": test_config.database_url,
                        "REDIS_URL": test_config.redis_url,
                        "TESTING": "true",
                        "ENVIRONMENT": "test"
                    })
                except Exception as e:
                    logger.warning(f"Could not set environment variables: {e}")
            
            # Add skip real API flag
            if self.config.skip_real_api:
                env["SKIP_REAL_API_TESTS"] = "1"
            
            # Run pytest tests (always run pytest, except when only Playwright tests are needed)
            pytest_success = True
            pytest_start_time = time.time()
            
            # Build and run pytest command
            cmd = self._build_pytest_command()
            cmd_str = " ".join(cmd)
            
            logger.info(f"Executing pytest: {cmd_str}")
            
            try:
                result = subprocess.run(
                    cmd,
                    env=env,
                    cwd=project_root,
                    timeout=self.config.timeout
                )
                
                pytest_success = result.returncode == 0
                self.results["pytest"] = {
                    "success": pytest_success,
                    "returncode": result.returncode,
                    "duration": time.time() - pytest_start_time
                }
                
            except subprocess.TimeoutExpired:
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
                
                logger.info(f"Executing Playwright: {cmd_str}")
                
                try:
                    result = subprocess.run(
                        playwright_cmd,
                        env=env,
                        cwd=project_root,
                        timeout=self.config.timeout
                    )
                    
                    playwright_success = result.returncode == 0
                    self.results["playwright"] = {
                        "success": playwright_success,
                        "returncode": result.returncode,
                        "duration": time.time() - playwright_start_time
                    }
                    
                except subprocess.TimeoutExpired:
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
                "duration": time.time() - self.start_time
            }
            
            return overall_success
                
        finally:
            # Stop debugging components
            self.stop_debugging()
    
    def _install_playwright_dependencies(self) -> bool:
        """Install Playwright and npm dependencies."""
        try:
            # Install npm dependencies
            logger.info("Installing npm dependencies...")
            result = subprocess.run(
                ["npm", "install"],
                cwd=project_root,
                capture_output=True,
                check=False
            )
            if result.returncode != 0:
                logger.warning(f"npm install failed: {result.stderr}")
                return False
            
            # Install Playwright browsers
            logger.info("Installing Playwright browsers...")
            result = subprocess.run(
                ["npx", "playwright", "install", "chromium"],
                cwd=project_root,
                capture_output=True,
                check=False
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
        
        print("\n" + "="*60)
        print("📊 CTI Scraper Test Execution Report")
        print("="*60)
    
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
            return
        
        # Calculate duration
        duration = time.time() - self.start_time
        
        # Print enhanced summary
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
                            print(f"    - pytest: {pytest_status}")
                        if "playwright" in result and result["playwright"] is not None:
                            pw_status = "✅" if result["playwright"] else "❌"
                            print(f"    - playwright: {pw_status}")
        
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
                print(f"    💡 Run 'allure serve allure-results' for interactive reports")
        
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
            ("ai", "AI Assistant tests (~3m)"),
            ("ai-ui", "AI UI tests only (~1m)"),
            ("ai-integration", "AI integration tests (~2m)"),
            ("all", "Complete test suite (~8m)"),
            ("coverage", "Tests with coverage report")
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
            "python run_tests.py unit --fail-fast"
        ]
        
        for example in examples:
            print(f"  $ {example}")


def parse_arguments() -> TestConfig:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="CTI Scraper Unified Test Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Execution Contexts:
  localhost    Run tests locally using virtual environment (default)
  docker       Run tests inside Docker containers
  ci           Run tests in CI/CD environment

Test Types:
  smoke        Quick health check (~30s)
  unit         Unit tests only (~1m)
  api          API endpoint tests (~2m)
  integration  System integration tests (~3m)
  ui           Web interface tests (~5m)
  e2e          End-to-end tests (~3m)
  performance  Performance tests (~2m)
  ai           AI Assistant tests (~3m)
  ai-ui        AI UI tests only (~1m)
  ai-integration AI integration tests (~2m)
  all          Complete test suite (~8m)
  coverage     Tests with coverage report

Examples:
  python run_tests.py smoke                    # Quick health check
  python run_tests.py all --coverage           # Full suite with coverage
  python run_tests.py --docker integration     # Docker-based integration tests
  python run_tests.py --debug --verbose        # Debug mode with verbose output
  python run_tests.py unit --fail-fast         # Unit tests with fail-fast
        """
    )
    
    # Test type (positional argument)
    parser.add_argument(
        "test_type",
        nargs="?",
        default="smoke",
        choices=[t.value for t in TestType],
        help="Type of tests to run"
    )
    
    # Execution context
    parser.add_argument(
        "--context",
        choices=[c.value for c in ExecutionContext],
        default="localhost",
        help="Execution context"
    )
    parser.add_argument("--docker", action="store_true", help="Run tests in Docker containers")
    parser.add_argument("--ci", action="store_true", help="Run tests in CI/CD mode")
    
    # Test execution options
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--debug", action="store_true", help="Debug mode with detailed output")
    parser.add_argument("--parallel", action="store_true", help="Run tests in parallel (requires pytest-xdist)")
    parser.add_argument("--coverage", action="store_true", help="Generate coverage report")
    parser.add_argument("--install", action="store_true", help="Install test dependencies")
    parser.add_argument("--no-validate", action="store_true", help="Skip environment validation")
    
    # Test filtering
    parser.add_argument("--paths", nargs="+", help="Specific test paths to run")
    parser.add_argument("--markers", nargs="+", help="Test markers to include")
    parser.add_argument("--exclude-markers", nargs="+", help="Test markers to exclude")
    parser.add_argument("--skip-real-api", action="store_true", help="Skip real API tests")
    
    # Output and reporting
    parser.add_argument("--output-format", choices=["progress", "verbose", "quiet"], default="progress", help="Output format")
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
        timeout=args.timeout
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