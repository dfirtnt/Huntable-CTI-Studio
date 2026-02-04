"""
Smoke test runner script for CTI Scraper.

This script provides a dedicated runner for smoke tests with proper
configuration and reporting.
"""

#!/usr/bin/env python3
"""
Dedicated smoke test runner for CTI Scraper.

Usage:
    python tests/smoke/run_smoke_tests.py
    python tests/smoke/run_smoke_tests.py --docker
    python tests/smoke/run_smoke_tests.py --verbose
"""
import argparse
import subprocess
import sys
import time


def run_smoke_tests(docker_mode: bool = False, verbose: bool = False) -> bool:
    """Run smoke tests with proper configuration."""
    print("🔥 CTI Scraper Smoke Test Runner")
    print("=" * 50)

    # Build pytest command
    cmd_parts = []

    if docker_mode:
        cmd_parts.append("docker exec cti_web")

    cmd_parts.extend(
        [
            "python",
            "-m",
            "pytest",
            "tests/smoke/",
            "-m",
            "smoke",
            "--tb=short",
            "--maxfail=5",  # Stop after 5 failures
        ]
    )

    if verbose:
        cmd_parts.append("-v")
    else:
        cmd_parts.append("-q")

    cmd = " ".join(cmd_parts)

    print(f"Running: {cmd}")
    print("Timeout: 30 seconds per test")
    print("Max failures: 5")
    print()

    start_time = time.time()

    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        end_time = time.time()

        print("✅ Smoke tests completed successfully!")
        print(f"Duration: {end_time - start_time:.2f} seconds")

        if verbose and result.stdout:
            print("\nTest Output:")
            print(result.stdout)

        return True

    except subprocess.CalledProcessError as e:
        end_time = time.time()

        print("❌ Smoke tests failed!")
        print(f"Duration: {end_time - start_time:.2f} seconds")

        if e.stdout:
            print("\nTest Output:")
            print(e.stdout)

        if e.stderr:
            print("\nError Output:")
            print(e.stderr)

        return False


def check_prerequisites() -> bool:
    """Check if prerequisites are met."""
    print("🔍 Checking prerequisites...")

    # Check if app is running
    try:
        import asyncio

        import httpx

        async def check():
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get("http://localhost:8001/health")
                return response.status_code == 200

        if asyncio.run(check()):
            print("✅ CTI Scraper app is running")
            return True
        print("❌ CTI Scraper app is not responding")
        return False

    except Exception as e:
        print(f"❌ Error checking app status: {e}")
        return False


def main():
    """Main smoke test runner."""
    parser = argparse.ArgumentParser(
        description="CTI Scraper Smoke Test Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python tests/smoke/run_smoke_tests.py              # Run smoke tests locally
    python tests/smoke/run_smoke_tests.py --docker     # Run smoke tests in Docker
    python tests/smoke/run_smoke_tests.py --verbose   # Verbose output
        """,
    )

    parser.add_argument("--docker", action="store_true", help="Run tests in Docker container")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--skip-prereq", action="store_true", help="Skip prerequisite checks")

    args = parser.parse_args()

    # Check prerequisites unless skipped
    if not args.skip_prereq and not check_prerequisites():
        print("\n💡 Start the app first with: ./start.sh")
        return False

    # Run smoke tests
    success = run_smoke_tests(args.docker, args.verbose)

    if success:
        print("\n🎉 All smoke tests passed! System is healthy.")
    else:
        print("\n💥 Smoke tests failed! Check system health.")

    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
