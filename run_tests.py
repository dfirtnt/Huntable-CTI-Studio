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
  * test-results/failures_pytest_YYYYMMDD_HHMMSS.log - Pytest failure summary
  * test-results/failures_playwright_YYYYMMDD_HHMMSS.log - Playwright failure summary
  * test-results/junit_YYYYMMDD_HHMMSS.xml - Machine-readable XML format
  * test-results/report_YYYYMMDD_HHMMSS.html - Interactive HTML report (if pytest-html available)
  * test-results/reportlog_YYYYMMDD_HHMMSS.jsonl - JSONL report log (if pytest-reportlog available)
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

import logging
import os
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Augment PATH so subprocesses can find tools (e.g. Docker Desktop CLI on macOS)
# installed outside the default non-login shell PATH.
_EXTRA_PATH_DIRS = ["/usr/local/bin", "/opt/homebrew/bin", "/opt/homebrew/sbin"]
_current_path = os.environ.get("PATH", "")
_path_parts = _current_path.split(os.pathsep)
for _d in reversed(_EXTRA_PATH_DIRS):
    if _d not in _path_parts:
        os.environ["PATH"] = _d + os.pathsep + os.environ.get("PATH", "")
del _EXTRA_PATH_DIRS, _current_path, _path_parts
try:
    del _d
except NameError:
    pass

from tests_runner.env import in_ci as _in_ci_fn, load_dotenv as _load_dotenv_fn, strip_cloud_llm_keys as _strip_cloud_llm_keys_fn  # noqa: E402

# Backward-compatible local aliases used throughout this file
def _strip_cloud_llm_keys() -> None:
    _strip_cloud_llm_keys_fn()

def _load_dotenv() -> None:
    _load_dotenv_fn(project_root)


# Import test environment utilities
try:
    import tests.utils.database_connections  # noqa: F401
except ImportError:
    pass

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

from tests_runner.cli import main  # noqa: E402

def _in_ci() -> bool:
    """Return True when running inside a CI environment (GitHub Actions or generic CI)."""
    return _in_ci_fn()

if __name__ == "__main__":
    import asyncio
    raise SystemExit(asyncio.run(main()))
