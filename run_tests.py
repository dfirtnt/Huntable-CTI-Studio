#!/usr/bin/env python3
"""
Unified test runner for CTI Scraper.

This is the primary interface for all testing operations.
Supports multiple execution contexts: localhost, Docker, and CI/CD.

Usage:
    python run_tests.py --help                    # Show all options
    python run_tests.py --smoke                   # Quick health check
    python run_tests.py --all                     # Full test suite
    python run_tests.py --docker                  # Docker-based testing
    python run_tests.py --coverage                # With coverage report
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

def run_unit_tests(docker_mode: bool = False) -> bool:
    """Run unit tests."""
    if docker_mode:
        return run_command(
            "docker exec cti_web python -m pytest tests/ -m 'not (ui or integration)' -v --tb=short",
            "Running unit tests in Docker"
        )
    return run_command(
        "python3 -m pytest tests/ -m 'not (ui or integration)' -v --tb=short",
        "Running unit tests"
    )

def run_api_tests(docker_mode: bool = False) -> bool:
    """Run API tests."""
    if docker_mode:
        return run_command(
            "docker exec cti_web python -m pytest tests/api/ -v --tb=short",
            "Running API tests in Docker"
        )
    return run_command(
        "python3 -m pytest tests/api/ -v --tb=short",
        "Running API tests"
    )

def run_integration_tests(docker_mode: bool = False) -> bool:
    """Run integration tests."""
    if docker_mode:
        return run_command(
            "docker exec cti_web python -m pytest tests/integration/ -v --tb=short",
            "Running integration tests in Docker"
        )
    return run_command(
        "python3 -m pytest tests/integration/ -v --tb=short",
        "Running integration tests"
    )

def run_ui_tests(docker_mode: bool = False) -> bool:
    """Run UI tests with Playwright."""
    if docker_mode:
        return run_command(
            "docker exec cti_web python -m pytest tests/ui/ -v --tb=short",
            "Running UI tests in Docker"
        )
    return run_command(
        "python3 -m pytest tests/ui/ -v --tb=short",
        "Running UI tests with Playwright"
    )

def run_smoke_tests(docker_mode: bool = False) -> bool:
    """Run smoke tests."""
    if docker_mode:
        return run_command(
            "docker exec cti_web python -m pytest tests/ -m smoke -v --tb=short",
            "Running smoke tests in Docker"
        )
    return run_command(
        "python3 -m pytest tests/ -m smoke -v --tb=short",
        "Running smoke tests"
    )

def run_all_tests(docker_mode: bool = False) -> bool:
    """Run all tests with enhanced visual reporting."""
    if docker_mode:
        return run_command(
            "docker exec cti_web python -m pytest tests/ -v --tb=short --report-log=test-results/reportlog.jsonl --alluredir=allure-results",
            "Running all tests in Docker with enhanced visual reporting"
        )
    return run_command(
        "python3 -m pytest tests/ -v --tb=short --report-log=test-results/reportlog.jsonl --alluredir=allure-results",
        "Running all tests with enhanced visual reporting"
    )

def run_coverage_tests(docker_mode: bool = False) -> bool:
    """Run tests with coverage."""
    if docker_mode:
        return run_command(
            "docker exec cti_web python -m pytest tests/ --cov=src --cov-report=html --cov-report=term-missing",
            "Running tests with coverage in Docker"
        )
    return run_command(
        "python3 -m pytest tests/ --cov=src --cov-report=html --cov-report=term-missing",
        "Running tests with coverage report"
    )

def run_performance_tests(docker_mode: bool = False) -> bool:
    """Run performance tests."""
    if docker_mode:
        return run_command(
            "docker exec cti_web python -m pytest tests/ -m slow -v --tb=short",
            "Running performance tests in Docker"
        )
    return run_command(
        "python3 -m pytest tests/ -m slow -v --tb=short",
        "Running performance tests"
    )

def run_ai_tests(docker_mode: bool = False, skip_real_api: bool = False) -> bool:
    """Run all AI Assistant tests."""
    if docker_mode:
        cmd = "docker exec cti_web python -m pytest tests/ui/test_ai_assistant_ui.py tests/integration/test_ai_cross_model_integration.py tests/integration/test_ai_real_api_integration.py -m ai -v --tb=short"
        if skip_real_api:
            cmd += " -e SKIP_REAL_API_TESTS=1"
        return run_command(cmd, "Running all AI Assistant tests in Docker")
    
    cmd = "python3 -m pytest tests/ui/test_ai_assistant_ui.py tests/integration/test_ai_cross_model_integration.py tests/integration/test_ai_real_api_integration.py -m ai -v --tb=short"
    if skip_real_api:
        cmd += " -e SKIP_REAL_API_TESTS=1"
    return run_command(cmd, "Running all AI Assistant tests")

def run_ai_ui_tests(docker_mode: bool = False) -> bool:
    """Run AI UI tests only."""
    if docker_mode:
        return run_command(
            "docker exec cti_web python -m pytest tests/ui/test_ai_assistant_ui.py -m 'ui and ai' -v --tb=short",
            "Running AI UI tests in Docker"
        )
    return run_command(
        "python3 -m pytest tests/ui/test_ai_assistant_ui.py -m 'ui and ai' -v --tb=short",
        "Running AI UI tests"
    )

def run_ai_integration_tests(docker_mode: bool = False, skip_real_api: bool = False) -> bool:
    """Run AI integration tests only."""
    if docker_mode:
        cmd = "docker exec cti_web python -m pytest tests/integration/test_ai_cross_model_integration.py tests/integration/test_ai_real_api_integration.py -m 'integration and ai' -v --tb=short"
        if skip_real_api:
            cmd += " -e SKIP_REAL_API_TESTS=1"
        return run_command(cmd, "Running AI integration tests in Docker")
    
    cmd = "python3 -m pytest tests/integration/test_ai_cross_model_integration.py tests/integration/test_ai_real_api_integration.py -m 'integration and ai' -v --tb=short"
    if skip_real_api:
        cmd += " -e SKIP_REAL_API_TESTS=1"
    return run_command(cmd, "Running AI integration tests")

def generate_test_report() -> None:
    """Generate a test summary report with visual tracking information."""
    print("\n📊 Test Summary Report")
    print("=" * 50)
    
    # Check if test results exist
    test_results_dir = Path("test-results")
    if test_results_dir.exists():
                # Allure results
                allure_results = Path("allure-results")
                if allure_results.exists():
                    print(f"📊 Allure Results: {allure_results.absolute()}")
                    print(f"💡 Run './manage_allure.sh start' for containerized reports (recommended)")
                    print(f"💡 Run 'allure serve allure-results' for host-based reports")
        
        # Report log for analysis
        report_log = test_results_dir / "reportlog.jsonl"
        if report_log.exists():
            print(f"📊 Report Log: {report_log.absolute()}")
            print(f"💡 Use Allure Reports for comprehensive visual analysis")
    
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
    print("  • AI Assistant Tests: tests/ui/test_ai_assistant_ui.py + tests/integration/test_ai_*.py")
    print("  • All Tests: tests/")
    print("  • Coverage: tests/ --cov=src")
    
            print("\n🔍 Visual Tracking Features:")
            print("  • Allure Reports: Rich visual analytics with pie charts, bar charts, and trends")
            print("  • Containerized Reports: Dedicated Docker container for reliable access")
            print("  • Enhanced HTML Reports: Rich reporting with better debugging info")
            print("  • Performance Analytics: Track test execution trends over time")
            print("  • ML/AI Debugging: Detailed visualization for AI inference tests")

def main():
    """Main test runner."""
    parser = argparse.ArgumentParser(
        description="CTI Scraper Unified Test Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Execution Contexts:
  localhost    Run tests locally using virtual environment (default)
  docker       Run tests inside Docker containers
  ci           Run tests in CI/CD environment

Test Categories:
  smoke        Quick health check (~30s)
  unit         Unit tests only (~1m)
  api          API endpoint tests (~2m)
  integration  System integration tests (~3m)
  ui           Web interface tests (~5m)
  ai           AI Assistant tests (~3m)
  ai-ui        AI UI tests only (~1m)
  ai-integration AI integration tests (~2m)
  all          Complete test suite (~8m)

Examples:
  python run_tests.py --smoke                    # Quick health check
  python run_tests.py --all --coverage           # Full suite with coverage
  python run_tests.py --docker --integration     # Docker-based integration tests
  python run_tests.py --ai                       # All AI Assistant tests
  python run_tests.py --ai-ui --coverage         # AI UI tests with coverage
  python run_tests.py --ai-skip-real-api         # AI tests without real API calls
  python run_tests.py --install                  # Install test dependencies
        """
    )
    
    # Execution context
    parser.add_argument("--docker", action="store_true", help="Run tests in Docker containers")
    parser.add_argument("--ci", action="store_true", help="Run tests in CI/CD mode")
    
    # Test categories
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
    
    # AI Assistant test categories
    parser.add_argument("--ai", action="store_true", help="Run all AI Assistant tests")
    parser.add_argument("--ai-ui", action="store_true", help="Run AI UI tests only")
    parser.add_argument("--ai-integration", action="store_true", help="Run AI integration tests only")
    parser.add_argument("--ai-skip-real-api", action="store_true", help="Skip real API tests (cost/rate limiting)")
    
    args = parser.parse_args()
    
    print("🚀 CTI Scraper Unified Test Runner")
    print("=" * 50)
    
    # Determine execution context
    if args.docker:
        print("🐳 Execution Context: Docker containers")
    elif args.ci:
        print("🔄 Execution Context: CI/CD environment")
    else:
        print("💻 Execution Context: Localhost (virtual environment)")
    
    # Check if app is running (only for localhost and docker contexts)
    if not args.ci and (args.check_app or not args.install):
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
    docker_mode = args.docker
    
    if args.unit:
        success &= run_unit_tests(docker_mode)
    
    if args.api:
        success &= run_api_tests(docker_mode)
    
    if args.integration:
        success &= run_integration_tests(docker_mode)
    
    if args.ui:
        success &= run_ui_tests(docker_mode)
    
    if args.smoke:
        success &= run_smoke_tests(docker_mode)
    
    if args.performance:
        success &= run_performance_tests(docker_mode)
    
    if args.coverage:
        success &= run_coverage_tests(docker_mode)
    
    if args.all:
        success &= run_all_tests(docker_mode)
    
    # AI Assistant test categories
    if args.ai:
        success &= run_ai_tests(docker_mode, args.ai_skip_real_api)
    
    if args.ai_ui:
        success &= run_ai_ui_tests(docker_mode)
    
    if args.ai_integration:
        success &= run_ai_integration_tests(docker_mode, args.ai_skip_real_api)
    
    # If no specific tests specified, run smoke tests
    if not any([args.unit, args.api, args.integration, args.ui, args.smoke, args.performance, args.coverage, args.all, args.ai, args.ai_ui, args.ai_integration]):
        print("\n🎯 No specific tests specified, running smoke tests...")
        success &= run_smoke_tests(docker_mode)
    
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
