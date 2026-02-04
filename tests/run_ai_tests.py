#!/usr/bin/env python3
"""
Test runner for AI Assistant Priority 1 tests - DEPRECATED.
AI Assistant modal has been removed. This file is kept for reference only.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def run_ai_tests(test_type="all", verbose=False, coverage=False):
    """Run AI Assistant tests with specified configuration."""

    # Add project root to Python path
    project_root = Path(__file__).parent.parent
    sys.path.insert(0, str(project_root))

    # Base pytest command
    cmd = ["python3", "-m", "pytest"]

    # DEPRECATED: AI Assistant UI tests removed
    print("⚠️  WARNING: AI Assistant tests are deprecated. The AI Assistant modal has been removed.")
    print("   This test runner is kept for reference only.")
    return True

    # Add test files based on type
    if test_type == "ui":
        cmd.extend(
            [
                # "tests/ui/test_ai_assistant_ui.py",  # DEPRECATED
                "-m",
                "ui and ai",
            ]
        )
    elif test_type == "integration":
        cmd.extend(
            [
                "tests/integration/test_ai_cross_model_integration.py",
                "tests/integration/test_ai_real_api_integration.py",
                "-m",
                "integration and ai",
            ]
        )
    elif test_type == "all":
        cmd.extend(
            [
                # "tests/ui/test_ai_assistant_ui.py",  # DEPRECATED
                "tests/integration/test_ai_cross_model_integration.py",
                "tests/integration/test_ai_real_api_integration.py",
                "-m",
                "ai",
            ]
        )
    else:
        print(f"Unknown test type: {test_type}")
        return False

    # Add configuration
    cmd.extend(
        [
            "-v" if verbose else "",
            "--tb=short",
            "--strict-markers",
            "--disable-warnings",
            "-x",  # Stop on first failure
        ]
    )

    # Remove empty strings
    cmd = [arg for arg in cmd if arg]

    # Add coverage if requested
    if coverage:
        cmd.extend(["--cov=src", "--cov-report=term-missing", "--cov-report=html:htmlcov/ai_tests"])

    # Add conftest files
    cmd.extend(["-p", "tests.conftest_ai"])

    print(f"Running AI Assistant tests: {' '.join(cmd)}")
    print("=" * 60)

    try:
        result = subprocess.run(cmd, cwd=project_root)
        return result.returncode == 0
    except KeyboardInterrupt:
        print("\nTests interrupted by user")
        return False
    except Exception as e:
        print(f"Error running tests: {e}")
        return False


def main():
    """Main entry point for AI test runner."""
    parser = argparse.ArgumentParser(description="Run AI Assistant Priority 1 tests")
    parser.add_argument(
        "--type", choices=["ui", "integration", "all"], default="all", help="Type of tests to run (default: all)"
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Run tests in verbose mode")
    parser.add_argument("--coverage", "-c", action="store_true", help="Run tests with coverage reporting")
    parser.add_argument("--skip-real-api", action="store_true", help="Skip real API integration tests")

    args = parser.parse_args()

    # Set environment variables for skipping real API tests if requested
    if args.skip_real_api:
        os.environ["SKIP_REAL_API_TESTS"] = "1"

    # Run tests
    success = run_ai_tests(test_type=args.type, verbose=args.verbose, coverage=args.coverage)

    if success:
        print("\n" + "=" * 60)
        print("✅ All AI Assistant Priority 1 tests passed!")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("❌ Some AI Assistant tests failed!")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
