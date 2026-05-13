"""Test runner configuration types.

Defines the enums and dataclass that describe *what* to run and *how*.
These are pure data -- no I/O, no subprocess calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RunTestType(Enum):
    """Test execution types."""

    SMOKE = "smoke"
    UNIT = "unit"
    API = "api"
    INTEGRATION = "integration"
    UI = "ui"
    UI_SMOKE = "ui-smoke"  # Tier 1: <2 min  (pytest smoke + ui_smoke markers, no Playwright)
    UI_FAST = "ui-fast"  # Tier 3: ~10-15 min  (full UI minus @slow, parallel)
    UI_FULL = "ui-full"  # Tier 4: ~40-45 min  (everything including slow)
    E2E = "e2e"
    ALL_NO_UI = "all-no-ui"
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
    serial: bool = False
    playwright_project: str | None = None  # --area: pin Playwright to one feature project
    coverage: bool = False
    cov_append: bool = False  # True for 2nd+ coverage run in a multi-type invocation
    install_deps: bool = False
    run_teardown: bool = True
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
    dry_run: bool = False
    tui: str = "auto"  # "auto" | "rich" | "plain"
