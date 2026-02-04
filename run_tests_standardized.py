#!/usr/bin/env python3
"""
Standardized test runner for CTI Scraper.

This script provides a unified interface for running tests across different
environments (localhost, Docker, CI/CD) with proper environment configuration.
"""

import argparse
import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from tests.utils.test_environment import TestEnvironmentManager, TestEnvironmentValidator

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class TestRunner:
    """Standardized test runner with environment management."""

    def __init__(self, config_file: str | None = None):
        self.config_file = config_file
        self.validator = TestEnvironmentValidator()
        self.config = None
        self.manager = None

    async def setup_environment(self) -> bool:
        """Set up test environment."""
        logger.info("Setting up test environment...")

        # Load configuration
        self.config = self.validator.load_test_config(self.config_file)
        logger.info(f"Test context: {self.config.context.value}")

        # Validate environment
        validation_results = await self.validator.validate_environment()
        if not all(validation_results.values()):
            logger.error("Environment validation failed")
            return False

        # Set up environment manager
        self.manager = TestEnvironmentManager(self.config)
        await self.manager.setup_test_environment()

        logger.info("Test environment setup completed")
        return True

    async def teardown_environment(self):
        """Tear down test environment."""
        if self.manager:
            await self.manager.teardown_test_environment()
            logger.info("Test environment teardown completed")

    def run_tests(
        self,
        test_paths: list[str],
        markers: list[str] | None = None,
        exclude_markers: list[str] | None = None,
        parallel: bool = False,
        coverage: bool = False,
        verbose: bool = False,
        **kwargs,
    ) -> int:
        """Run tests with specified parameters."""

        # Build pytest command
        cmd = ["python", "-m", "pytest"]

        # Add test paths
        cmd.extend(test_paths)

        # Add markers
        if markers:
            marker_expr = " or ".join(markers)
            cmd.extend(["-m", marker_expr])

        # Exclude markers
        if exclude_markers:
            exclude_expr = " and ".join([f"not {marker}" for marker in exclude_markers])
            if markers:
                cmd.extend(["-m", f"({marker_expr}) and ({exclude_expr})"])
            else:
                cmd.extend(["-m", exclude_expr])

        # Add parallel execution
        if parallel:
            cmd.extend(["-n", "auto"])

        # Add coverage
        if coverage:
            cmd.extend(
                ["--cov=src", "--cov-report=html:htmlcov", "--cov-report=xml:coverage.xml", "--cov-report=term-missing"]
            )

        # Add verbosity
        if verbose:
            cmd.append("-v")
        else:
            cmd.append("-q")

        # Add additional options
        for key, value in kwargs.items():
            if value is True:
                cmd.append(f"--{key}")
            elif value is not False:
                cmd.append(f"--{key}={value}")

        # Set environment variables
        env = os.environ.copy()
        env.update(
            {
                "DATABASE_URL": self.config.database_url,
                "REDIS_URL": self.config.redis_url,
                "TESTING": "true",
                "ENVIRONMENT": "test",
            }
        )

        logger.info(f"Running command: {' '.join(cmd)}")

        # Run tests
        try:
            result = subprocess.run(cmd, env=env, cwd=project_root)
            return result.returncode
        except KeyboardInterrupt:
            logger.info("Test execution interrupted by user")
            return 1
        except Exception as e:
            logger.error(f"Test execution failed: {e}")
            return 1

    def run_smoke_tests(self, verbose: bool = False) -> int:
        """Run smoke tests."""
        logger.info("Running smoke tests...")
        return self.run_tests(test_paths=["tests/smoke/"], verbose=verbose)

    def run_unit_tests(self, verbose: bool = False, coverage: bool = False) -> int:
        """Run unit tests."""
        logger.info("Running unit tests...")
        return self.run_tests(
            test_paths=["tests/"],
            exclude_markers=["smoke", "integration", "api", "performance", "e2e"],
            verbose=verbose,
            coverage=coverage,
        )

    def run_integration_tests(self, verbose: bool = False) -> int:
        """Run integration tests."""
        logger.info("Running integration tests...")
        return self.run_tests(test_paths=["tests/integration/"], verbose=verbose)

    def run_api_tests(self, verbose: bool = False) -> int:
        """Run API tests."""
        logger.info("Running API tests...")
        return self.run_tests(test_paths=["tests/api/"], verbose=verbose)

    def run_performance_tests(self, verbose: bool = False) -> int:
        """Run performance tests."""
        logger.info("Running performance tests...")
        return self.run_tests(test_paths=["tests/"], markers=["performance"], verbose=verbose)

    def run_e2e_tests(self, verbose: bool = False) -> int:
        """Run end-to-end tests."""
        logger.info("Running end-to-end tests...")
        return self.run_tests(test_paths=["tests/e2e/"], verbose=verbose)

    def run_all_tests(self, verbose: bool = False, coverage: bool = False, parallel: bool = False) -> int:
        """Run all tests."""
        logger.info("Running all tests...")
        return self.run_tests(test_paths=["tests/"], verbose=verbose, coverage=coverage, parallel=parallel)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="CTI Scraper Test Runner")

    # Environment options
    parser.add_argument("--config", help="Path to test configuration file")
    parser.add_argument("--validate-only", action="store_true", help="Only validate environment")
    parser.add_argument("--setup-only", action="store_true", help="Only setup environment")

    # Test selection
    parser.add_argument("--smoke", action="store_true", help="Run smoke tests")
    parser.add_argument("--unit", action="store_true", help="Run unit tests")
    parser.add_argument("--integration", action="store_true", help="Run integration tests")
    parser.add_argument("--api", action="store_true", help="Run API tests")
    parser.add_argument("--performance", action="store_true", help="Run performance tests")
    parser.add_argument("--e2e", action="store_true", help="Run end-to-end tests")
    parser.add_argument("--all", action="store_true", help="Run all tests")

    # Test execution options
    parser.add_argument("--parallel", action="store_true", help="Run tests in parallel")
    parser.add_argument("--coverage", action="store_true", help="Generate coverage report")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--markers", help="Comma-separated list of test markers")
    parser.add_argument("--exclude-markers", help="Comma-separated list of markers to exclude")

    # Test paths
    parser.add_argument("test_paths", nargs="*", help="Specific test paths to run")

    args = parser.parse_args()

    async def run():
        """Async main function."""
        runner = TestRunner(args.config)

        # Setup environment
        if not await runner.setup_environment():
            logger.error("Failed to setup test environment")
            return 1

        try:
            # Validate only
            if args.validate_only:
                logger.info("Environment validation completed successfully")
                return 0

            # Setup only
            if args.setup_only:
                logger.info("Test environment setup completed successfully")
                return 0

            # Determine which tests to run
            exit_code = 0

            if args.test_paths:
                # Run specific test paths
                exit_code = runner.run_tests(
                    test_paths=args.test_paths,
                    markers=args.markers.split(",") if args.markers else None,
                    exclude_markers=args.exclude_markers.split(",") if args.exclude_markers else None,
                    parallel=args.parallel,
                    coverage=args.coverage,
                    verbose=args.verbose,
                )
            elif args.smoke:
                exit_code = runner.run_smoke_tests(args.verbose)
            elif args.unit:
                exit_code = runner.run_unit_tests(args.verbose, args.coverage)
            elif args.integration:
                exit_code = runner.run_integration_tests(args.verbose)
            elif args.api:
                exit_code = runner.run_api_tests(args.verbose)
            elif args.performance:
                exit_code = runner.run_performance_tests(args.verbose)
            elif args.e2e:
                exit_code = runner.run_e2e_tests(args.verbose)
            elif args.all:
                exit_code = runner.run_all_tests(args.verbose, args.coverage, args.parallel)
            else:
                # Default: run smoke tests
                exit_code = runner.run_smoke_tests(args.verbose)

            return exit_code

        finally:
            # Teardown environment
            await runner.teardown_environment()

    # Run async main function
    try:
        exit_code = asyncio.run(run())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("Test execution interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Test runner failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
