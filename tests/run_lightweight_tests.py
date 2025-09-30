#!/usr/bin/env python3
"""
Test runner for lightweight integration tests.

This script provides convenient commands to run different test suites
with appropriate markers and configurations.
"""
import subprocess
import sys
import argparse
from pathlib import Path


def run_command(cmd: list, description: str) -> int:
    """Run a command and return the exit code."""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'='*60}")
    
    result = subprocess.run(cmd, cwd=Path(__file__).parent.parent)
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description="Run CTI Scraper test suites")
    parser.add_argument(
        "suite",
        choices=["light", "full", "unit", "all", "critical"],
        help="Test suite to run"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    parser.add_argument(
        "--coverage", "-c",
        action="store_true",
        help="Generate coverage report"
    )
    parser.add_argument(
        "--parallel", "-p",
        type=int,
        default=1,
        help="Number of parallel workers"
    )
    
    args = parser.parse_args()
    
    # Base pytest command
    base_cmd = ["python3", "-m", "pytest"]
    
    # Add common options
    if args.verbose:
        base_cmd.append("-v")
    
    if args.coverage:
        base_cmd.extend([
            "--cov=src",
            "--cov-report=html:htmlcov",
            "--cov-report=term-missing"
        ])
    
    if args.parallel > 1:
        base_cmd.extend(["-n", str(args.parallel)])
    
    # Test suite configurations
    suites = {
        "light": {
            "cmd": base_cmd + ["-m", "integration_light", "tests/integration/test_lightweight_integration.py"],
            "description": "Lightweight Integration Tests (mocked dependencies)"
        },
        "full": {
            "cmd": base_cmd + ["-m", "integration_full", "tests/integration/"],
            "description": "Full Integration Tests (requires Docker environment)"
        },
        "unit": {
            "cmd": base_cmd + ["-m", "unit", "tests/"],
            "description": "Unit Tests"
        },
        "critical": {
            "cmd": base_cmd + ["-m", "integration_light", "tests/integration/test_lightweight_integration.py::TestCriticalPathIntegration"],
            "description": "Critical Path Integration Tests (lightweight)"
        },
        "all": {
            "cmd": base_cmd + ["tests/"],
            "description": "All Tests"
        }
    }
    
    # Run the selected suite
    suite_config = suites[args.suite]
    exit_code = run_command(suite_config["cmd"], suite_config["description"])
    
    if exit_code == 0:
        print(f"\n✅ {suite_config['description']} completed successfully!")
    else:
        print(f"\n❌ {suite_config['description']} failed with exit code {exit_code}")
    
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
