#!/usr/bin/env python3
"""
Comprehensive test runner for CTI Scraper.
"""
import os
import sys
import subprocess
import argparse
import time
from pathlib import Path

def run_command(cmd: str, description: str) -> bool:
    """Run a command and return success status."""
    print(f"\n🔄 {description}")
    print(f"Running: {cmd}")
    
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {description} completed successfully")
        if result.stdout:
            print(f"Output: {result.stdout}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed")
        print(f"Error: {e}")
        if e.stdout:
            print(f"Stdout: {e.stdout}")
        if e.stderr:
            print(f"Stderr: {e.stderr}")
        return False

def check_app_running() -> bool:
    """Check if the CTI Scraper app is running."""
    try:
        import httpx
        import asyncio
        
        async def check():
            base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{base_url}/health")
                return response.status_code == 200
        
        result = asyncio.run(check())
        return result
    except Exception:
        return False

def install_test_dependencies() -> bool:
    """Install test dependencies."""
    print("\n📦 Installing test dependencies...")
    
    # Install Python test dependencies
    if not run_command("pip install -r requirements-test.txt", "Installing Python test dependencies"):
        return False
    
    # Install Playwright browsers
    if not run_command("playwright install", "Installing Playwright browsers"):
        return False
    
    return True

def run_unit_tests() -> bool:
    """Run unit tests."""
    return run_command(
        "python3 -m pytest tests/ -m 'not (ui or integration)' -v --tb=short",
        "Running unit tests"
    )

def run_api_tests() -> bool:
    """Run API tests."""
    return run_command(
        "python3 -m pytest tests/api/ -v --tb=short",
        "Running API tests"
    )

def run_integration_tests() -> bool:
    """Run integration tests."""
    return run_command(
        "python3 -m pytest tests/integration/ -v --tb=short",
        "Running integration tests"
    )

def run_ui_tests() -> bool:
    """Run UI tests with Playwright."""
    return run_command(
        "python3 -m pytest tests/ui/ -v --tb=short",
        "Running UI tests with Playwright"
    )

def run_smoke_tests() -> bool:
    """Run smoke tests."""
    return run_command(
        "python3 -m pytest tests/ -m smoke -v --tb=short",
        "Running smoke tests"
    )

def run_all_tests() -> bool:
    """Run all tests."""
    return run_command(
        "python3 -m pytest tests/ -v --tb=short --html=test-results/report.html --self-contained-html",
        "Running all tests with HTML report"
    )

def run_coverage_tests() -> bool:
    """Run tests with coverage."""
    return run_command(
        "python3 -m pytest tests/ --cov=src --cov-report=html --cov-report=term-missing",
        "Running tests with coverage report"
    )

def run_performance_tests() -> bool:
    """Run performance tests."""
    return run_command(
        "python3 -m pytest tests/ -m slow -v --tb=short",
        "Running performance tests"
    )

def generate_test_report() -> None:
    """Generate a test summary report."""
    print("\n📊 Test Summary Report")
    print("=" * 50)
    
    # Check if test results exist
    test_results_dir = Path("test-results")
    if test_results_dir.exists():
        html_report = test_results_dir / "report.html"
        if html_report.exists():
            print(f"📄 HTML Report: {html_report.absolute()}")
    
    coverage_dir = Path("htmlcov")
    if coverage_dir.exists():
        index_file = coverage_dir / "index.html"
        if index_file.exists():
            print(f"📊 Coverage Report: {index_file.absolute()}")
    
    print("\n🎯 Test Categories Available:")
    print("  • Unit Tests: tests/ -m 'not (ui or integration)'")
    print("  • API Tests: tests/api/")
    print("  • Integration Tests: tests/integration/")
    print("  • UI Tests: tests/ui/")
    print("  • Smoke Tests: tests/ -m smoke")
    print("  • Performance Tests: tests/ -m slow")
    print("  • All Tests: tests/")
    print("  • Coverage: tests/ --cov=src")

def main():
    """Main test runner."""
    parser = argparse.ArgumentParser(description="CTI Scraper Test Runner")
    parser.add_argument("--install", action="store_true", help="Install test dependencies")
    parser.add_argument("--unit", action="store_true", help="Run unit tests only")
    parser.add_argument("--api", action="store_true", help="Run API tests only")
    parser.add_argument("--integration", action="store_true", help="Run integration tests only")
    parser.add_argument("--ui", action="store_true", help="Run UI tests only")
    parser.add_argument("--smoke", action="store_true", help="Run smoke tests only")
    parser.add_argument("--performance", action="store_true", help="Run performance tests only")
    parser.add_argument("--coverage", action="store_true", help="Run tests with coverage")
    parser.add_argument("--all", action="store_true", help="Run all tests")
    parser.add_argument("--check-app", action="store_true", help="Check if app is running")
    
    args = parser.parse_args()
    
    print("🚀 CTI Scraper Test Runner")
    print("=" * 50)
    
    # Check if app is running
    if args.check_app or not args.install:
        print("\n🔍 Checking if CTI Scraper app is running...")
        if check_app_running():
            print("✅ CTI Scraper app is running on http://localhost:8001")
        else:
            print("❌ CTI Scraper app is not running")
            print("💡 Start the app first with: ./start.sh")
            if not args.install:
                return False
    
    # Install dependencies if requested
    if args.install:
        if not install_test_dependencies():
            print("❌ Failed to install test dependencies")
            return False
    
    # Run specific test categories
    success = True
    
    if args.unit:
        success &= run_unit_tests()
    
    if args.api:
        success &= run_api_tests()
    
    if args.integration:
        success &= run_integration_tests()
    
    if args.ui:
        success &= run_ui_tests()
    
    if args.smoke:
        success &= run_smoke_tests()
    
    if args.performance:
        success &= run_performance_tests()
    
    if args.coverage:
        success &= run_coverage_tests()
    
    if args.all:
        success &= run_all_tests()
    
    # If no specific tests specified, run smoke tests
    if not any([args.unit, args.api, args.integration, args.ui, args.smoke, args.performance, args.coverage, args.all]):
        print("\n🎯 No specific tests specified, running smoke tests...")
        success &= run_smoke_tests()
    
    # Generate report
    generate_test_report()
    
    # Final result
    if success:
        print("\n🎉 All tests completed successfully!")
        return True
    else:
        print("\n💥 Some tests failed. Check the output above for details.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
