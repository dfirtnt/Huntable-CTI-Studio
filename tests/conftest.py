"""
Test configuration and fixtures for CTI Scraper tests.
"""

import os
import sys
import warnings

# Ensure transformers modules have names they use but do not import (LRScheduler, nn).
# Resolve values at install time to avoid re-entrant imports during hook execution.
def _install_transformers_compat_hooks():
    import importlib.abc
    import importlib.machinery
    import importlib.util

    _lrs_val = None
    _nn_val = None
    try:
        m = importlib.import_module("torch.optim.lr_scheduler")
        _lrs_val = getattr(m, "LRScheduler", None) or getattr(m, "_LRScheduler", None)
    except Exception:
        pass
    try:
        _torch = importlib.import_module("torch")
        _nn_val = _torch.nn
        # torch.uint16/32/64 added in 2.3; older builds lack them — alias so imports succeed
        for u, i in [("uint16", "int16"), ("uint32", "int32"), ("uint64", "int64")]:
            if not hasattr(_torch, u):
                setattr(_torch, u, getattr(_torch, i, None))
    except Exception:
        _torch = None
        _nn_val = None

    def _make_hook(target_name, inject_pairs):
        # inject_pairs: list of (name, value); value can be None if not yet resolved
        class _LoaderWrapper:
            def __init__(self, original_loader):
                self._loader = original_loader
                self._pairs = inject_pairs

            def create_module(self, spec):
                return self._loader.create_module(spec)

            def exec_module(self, module):
                for name, val in self._pairs:
                    if val is not None:
                        module.__dict__[name] = val
                self._loader.exec_module(module)

        class _Finder(importlib.abc.MetaPathFinder):
            def find_spec(self, name, path=None, target=None):
                if name != target_name:
                    return None
                sys.meta_path.remove(self)
                try:
                    real_spec = importlib.util.find_spec(name)
                finally:
                    sys.meta_path.insert(0, self)
                if real_spec is None or real_spec.loader is None:
                    return None
                wrapped = _LoaderWrapper(real_spec.loader)
                return importlib.machinery.ModuleSpec(
                    name, wrapped, origin=real_spec.origin, is_package=False
                )

        return _Finder()

    if _lrs_val is not None:
        sys.meta_path.insert(0, _make_hook("transformers.trainer_pt_utils", [("LRScheduler", _lrs_val)]))
    if _nn_val is not None and _torch is not None:
        # Any transformers.integrations.* module may use torch/nn in annotations
        def _make_integrations_hook():
            pairs = [("nn", _nn_val), ("torch", _torch)]

            class _LoaderWrapper:
                def __init__(self, original_loader):
                    self._loader = original_loader
                    self._pairs = pairs

                def create_module(self, spec):
                    return self._loader.create_module(spec)

                def exec_module(self, module):
                    for name, val in self._pairs:
                        if val is not None:
                            module.__dict__[name] = val
                    self._loader.exec_module(module)

            class _Finder(importlib.abc.MetaPathFinder):
                def find_spec(self, name, path=None, target=None):
                    if not name.startswith("transformers.integrations.") or name == "transformers.integrations":
                        return None
                    sys.meta_path.remove(self)
                    try:
                        real_spec = importlib.util.find_spec(name)
                    finally:
                        sys.meta_path.insert(0, self)
                    if real_spec is None or real_spec.loader is None:
                        return None
                    wrapped = _LoaderWrapper(real_spec.loader)
                    return importlib.machinery.ModuleSpec(
                        name, wrapped, origin=real_spec.origin, is_package=False
                    )

            return _Finder()

        sys.meta_path.insert(0, _make_integrations_hook())
_install_transformers_compat_hooks()

import pydantic.warnings
import pytest
import pytest_asyncio

try:
    import pytest_asyncio
except ImportError:  # Allow running targeted tests without pytest-asyncio

    class _PytestAsyncioStub:
        def fixture(self, *args, **kwargs):
            return pytest.fixture(*args, **kwargs)

    pytest_asyncio = _PytestAsyncioStub()
    warnings.warn(
        "pytest-asyncio not installed; async fixtures will behave as regular fixtures.",
        RuntimeWarning,
        stacklevel=2,
    )
import logging
import shutil
from collections.abc import AsyncGenerator
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
from playwright.sync_api import sync_playwright

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Silence known pydantic v2 config deprecation from third-party models
warnings.filterwarnings(
    "ignore",
    category=pydantic.warnings.PydanticDeprecatedSince20,
)

# Import AI test fixtures
try:
    from tests.conftest_ai import ai_test_config
except ImportError:
    pass  # AI fixtures not required for all tests

# Import test environment guard (required)
try:
    from tests.utils.test_environment import assert_test_environment

    TEST_ENV_GUARD_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Test environment guard not available: {e}")
    TEST_ENV_GUARD_AVAILABLE = False

# Import test environment utilities (optional)
try:
    from tests.utils.async_debug_utils import AsyncDebugger, debug_async_test
    from tests.utils.performance_profiler import PerformanceProfiler, profile_test
    from tests.utils.test_environment import (
        TestContext,
        TestEnvironmentManager,
        TestEnvironmentValidator,
        get_test_config,
        setup_test_environment,
        validate_test_environment,
    )

    # Load test configuration
    test_config = get_test_config()
    ENVIRONMENT_UTILS_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Test environment utilities not available: {e}")
    ENVIRONMENT_UTILS_AVAILABLE = False
    test_config = None

# Optional: failure analyzer (missing module must not break conftest or teardown)
try:
    from tests.utils.test_failure_analyzer import (
        TestFailureReporter,
        analyze_test_failure,
        generate_failure_report,
    )

    FAILURE_ANALYZER_AVAILABLE = True
except ImportError:
    FAILURE_ANALYZER_AVAILABLE = False
    TestFailureReporter = None
    analyze_test_failure = None
    generate_failure_report = None

# Optional: test isolation
try:
    from tests.utils.test_isolation import TestIsolationManager, test_isolation

    ISOLATION_AVAILABLE = True
except ImportError:
    ISOLATION_AVAILABLE = False
    TestIsolationManager = None
    test_isolation = None

# Optional: test output formatter
try:
    from tests.utils.test_output_formatter import (
        TestOutputFormatter,
        print_test_failure,
        print_test_result,
    )

    OUTPUT_FORMATTER_AVAILABLE = True
except ImportError:
    OUTPUT_FORMATTER_AVAILABLE = False
    TestOutputFormatter = None
    print_test_failure = None
    print_test_result = None

# Set up logging for tests
logging.basicConfig(
    level=os.getenv("TEST_LOG_LEVEL", "DEBUG"),
    format=os.getenv("TEST_LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
)
logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def test_environment_config():
    """Provide test environment configuration."""
    if not ENVIRONMENT_UTILS_AVAILABLE:
        # Return None instead of skipping - allows tests that don't need it to run
        return None
    return test_config


# Temporarily disable async fixtures to fix hanging tests
# @pytest.fixture(scope="session")
# async def test_environment_manager(test_environment_config):
#     """Set up and manage test environment."""
#     manager = TestEnvironmentManager(test_environment_config)
#     await manager.setup_test_environment()
#     yield manager
#     await manager.teardown_test_environment()


@pytest.fixture(scope="session")
async def test_environment_validation():
    """Validate test environment before running tests."""
    if not ENVIRONMENT_UTILS_AVAILABLE:
        # Skip validation if utilities not available - allows tests to run
        return True
    is_valid = await validate_test_environment()
    if not is_valid:
        pytest.exit("Test environment validation failed")
    return is_valid


def _use_asgi_client() -> bool:
    """Use in-process ASGI client instead of live server (no server on 127.0.0.1 needed)."""
    return os.getenv("USE_ASGI_CLIENT", "").lower() in ("1", "true", "yes")


@pytest_asyncio.fixture
async def async_client(test_environment_config) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Async HTTP client for API testing. With USE_ASGI_CLIENT=1 uses in-process app (no live server)."""
    timeout = httpx.Timeout(60.0)  # Increased timeout for RAG operations
    if _use_asgi_client():
        from httpx import ASGITransport

        from src.web.modern_main import app

        transport = ASGITransport(app=app, raise_app_exceptions=False)
        client = httpx.AsyncClient(transport=transport, base_url="http://testserver", timeout=timeout)
    else:
        port = (
            int(os.getenv("TEST_PORT", "8001"))
            if test_environment_config is None
            else getattr(test_environment_config, "test_port", 8001)
        )
        base_url = f"http://127.0.0.1:{port}"
        client = httpx.AsyncClient(base_url=base_url, timeout=timeout)
    try:
        yield client
    finally:
        try:
            await client.aclose()
        except RuntimeError:
            pass


@pytest.fixture
def api_headers():
    """Default API headers."""
    return {"Content-Type": "application/json", "Accept": "application/json"}


@pytest.fixture
def test_data_dir():
    """Provide test data directory."""
    test_data_path = Path("test-data")
    test_data_path.mkdir(exist_ok=True)
    yield test_data_path
    # Cleanup if needed
    if os.getenv("TEST_FILE_CLEANUP", "true").lower() == "true":
        shutil.rmtree(test_data_path, ignore_errors=True)


@pytest.fixture
def test_temp_dir():
    """Provide temporary directory for tests."""
    temp_dir = Path("test-results/temp")
    temp_dir.mkdir(parents=True, exist_ok=True)
    yield temp_dir
    # Cleanup
    if os.getenv("TEST_FILE_CLEANUP", "true").lower() == "true":
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def test_fixtures_dir():
    """Provide test fixtures directory."""
    fixtures_dir = Path("tests/fixtures")
    fixtures_dir.mkdir(exist_ok=True)
    return fixtures_dir


# Database Fixtures
@pytest_asyncio.fixture
async def test_database_session(test_environment_config):
    """Provide test database session."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_async_engine(
        test_environment_config.database_url,
        pool_size=test_environment_config.db_pool_size if hasattr(test_environment_config, "db_pool_size") else 5,
        max_overflow=test_environment_config.db_max_overflow
        if hasattr(test_environment_config, "db_max_overflow")
        else 10,
        pool_pre_ping=True,
        pool_recycle=1800,
    )

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def test_redis_client(test_environment_config):
    """Provide test Redis client."""
    import redis.asyncio as redis

    if test_environment_config.redis_password:
        client = redis.Redis(
            host=test_environment_config.redis_host,
            port=test_environment_config.redis_port,
            db=test_environment_config.redis_db,
            password=test_environment_config.redis_password,
            socket_timeout=5,
        )
    else:
        client = redis.Redis(
            host=test_environment_config.redis_host,
            port=test_environment_config.redis_port,
            db=test_environment_config.redis_db,
            socket_timeout=5,
        )

    yield client
    await client.close()


# Mock Fixtures for Database and Service Testing
@pytest.fixture
def mock_async_session():
    """Create a properly configured async database session mock with query chain support."""
    from tests.utils.async_mocks import AsyncMockSession, setup_transaction_mock

    session = AsyncMockSession()
    setup_transaction_mock(session)

    # Configure async query execution
    session.execute = AsyncMock()
    session.scalar = AsyncMock()
    session.scalars = AsyncMock()
    session.get = AsyncMock()

    return session


@pytest.fixture
def mock_async_engine():
    """Create a properly configured async database engine mock."""
    engine = AsyncMock()
    engine.begin = AsyncMock()
    engine.begin.return_value.__aenter__ = AsyncMock(return_value=engine.begin.return_value)
    engine.begin.return_value.__aexit__ = AsyncMock(return_value=None)
    engine.connect = AsyncMock()
    engine.connect.return_value.__aenter__ = AsyncMock(return_value=engine.connect.return_value)
    engine.connect.return_value.__aexit__ = AsyncMock(return_value=None)
    engine.dispose = AsyncMock()
    return engine


@pytest.fixture
def mock_async_http_client():
    """Create a properly configured async HTTP client mock."""
    from tests.utils.async_mocks import AsyncMockHTTPClient

    return AsyncMockHTTPClient()
    client = AsyncMock()
    client.get = AsyncMock()
    client.post = AsyncMock()
    client.put = AsyncMock()
    client.delete = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


@pytest.fixture
def mock_async_deduplication_service():
    """Create a properly configured async deduplication service mock."""
    service = AsyncMock()
    service.check_duplicate = AsyncMock()
    service.add_content_hash = AsyncMock()
    service.get_similar_content = AsyncMock()
    service.cleanup_old_hashes = AsyncMock()
    return service


@pytest.fixture
def mock_llm_service(test_environment_config):
    """Create mock LLM service if mocking is enabled."""
    if test_environment_config.mock_llm_responses:
        service = AsyncMock()
        service.generate_response = AsyncMock(return_value="Mock LLM response")
        service.summarize_content = AsyncMock(return_value="Mock summary")
        service.extract_entities = AsyncMock(return_value=["entity1", "entity2"])
        return service
    return None


# Playwright fixtures for UI testing
@pytest.fixture(scope="session")
def browser_context_args(test_environment_config):
    """Browser context arguments for Playwright tests"""
    return {
        "viewport": {
            "width": int(os.getenv("BROWSER_WIDTH", "1280")),
            "height": int(os.getenv("BROWSER_HEIGHT", "720")),
        },
        "ignore_https_errors": os.getenv("BROWSER_IGNORE_HTTPS", "true").lower() == "true",
        "record_video_dir": os.getenv("PLAYWRIGHT_VIDEO_DIR", "test-results/videos/"),
        "record_video_size": {
            "width": int(os.getenv("BROWSER_WIDTH", "1280")),
            "height": int(os.getenv("BROWSER_HEIGHT", "720")),
        },
    }


@pytest.fixture(scope="session")
def browser_type_launch_args():
    """Browser launch arguments"""
    return {
        "headless": os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true",
        "slow_mo": int(os.getenv("PLAYWRIGHT_SLOW_MO", "100")),
    }


@pytest.fixture(scope="session")
def _playwright_sync():
    """Sync Playwright instance for session-scoped browser (used by sync UI tests)."""
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def browser(_playwright_sync, browser_type_launch_args):
    """Browser instance for session-scoped tests (sync API for playwright.sync_api tests)."""
    try:
        b = _playwright_sync.chromium.launch(**browser_type_launch_args)
        yield b
        b.close()
    except Exception as e:
        error_str = str(e)
        if "Executable doesn't exist" in error_str or "playwright install" in error_str.lower():
            pytest.skip("Playwright browsers not installed. Run 'playwright install' in Docker container")
        raise


@pytest.fixture(scope="session")
def context(browser, browser_context_args):
    """Browser context for session-scoped tests (sync API)."""
    ctx = browser.new_context(**browser_context_args)
    yield ctx
    ctx.close()


@pytest.fixture
def page(context):
    """Page instance for each test (sync API for playwright.sync_api)."""
    p = context.new_page()
    yield p
    p.close()


# Test isolation fixtures
# Temporarily disable async fixtures to fix hanging tests
# @pytest.fixture(autouse=True)
# async def test_isolation(test_environment_config, test_environment_manager):
#     """Ensure test isolation between tests."""
#     if not test_environment_config.test_isolation:
#         return
#
#     # Set up isolation before test
#     await test_environment_manager._setup_test_isolation()
#
#     yield
#
#     # Clean up after test
#     await test_environment_manager._cleanup_test_data()


# Performance testing fixtures
@pytest.fixture
def performance_test_config(test_environment_config):
    """Provide performance test configuration."""
    return {
        "enabled": os.getenv("PERFORMANCE_TEST_ENABLED", "false").lower() == "true",
        "timeout": int(os.getenv("PERFORMANCE_TEST_TIMEOUT", "60")),
        "concurrent_users": int(os.getenv("PERFORMANCE_TEST_CONCURRENT_USERS", "10")),
        "duration": int(os.getenv("PERFORMANCE_TEST_DURATION", "30")),
    }


# Integration test fixtures
@pytest.fixture
def integration_test_config(test_environment_config):
    """Provide integration test configuration."""
    return {
        "enabled": os.getenv("INTEGRATION_TEST_ENABLED", "true").lower() == "true",
        "timeout": int(os.getenv("INTEGRATION_TEST_TIMEOUT", "120")),
        "retries": int(os.getenv("INTEGRATION_TEST_RETRIES", "3")),
        "mock_external_services": test_environment_config.mock_external_services,
    }


# No-op fallbacks when optional utils are missing
def _noop(*args, **kwargs):
    pass


class _NoOpReporter:
    __getattr__ = lambda self, _: _noop


# Enhanced debugging fixtures
@pytest.fixture
def failure_reporter():
    """Provide test failure reporter."""
    if FAILURE_ANALYZER_AVAILABLE and TestFailureReporter is not None:
        return TestFailureReporter()
    return _NoOpReporter()


@pytest.fixture
def async_debugger():
    """Provide async debugger."""
    return AsyncDebugger()


@pytest.fixture
def performance_profiler():
    """Provide performance profiler."""
    return PerformanceProfiler()


@pytest.fixture
def test_output_formatter():
    """Provide test output formatter."""
    if OUTPUT_FORMATTER_AVAILABLE and TestOutputFormatter is not None:
        return TestOutputFormatter()
    return _NoOpReporter()


@pytest.fixture
def isolation_manager():
    """Provide test isolation manager."""
    if ISOLATION_AVAILABLE and TestIsolationManager is not None:
        return TestIsolationManager()
    return _NoOpReporter()


def pytest_configure(config):
    """Register custom markers and validate test environment."""
    # Invoke test environment guard at pytest bootstrap
    if TEST_ENV_GUARD_AVAILABLE:
        try:
            assert_test_environment()
        except RuntimeError as e:
            pytest.exit(f"Test environment validation failed: {e}")

    # Register custom markers to satisfy strict marker checks
    config.addinivalue_line("markers", "ui: UI tests")
    config.addinivalue_line("markers", "ai: AI integration tests (AI Assistant UI deprecated)")
    config.addinivalue_line("markers", "e2e: End-to-end tests using Playwright")
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "integration_light: Lightweight integration tests with mocks")
    config.addinivalue_line("markers", "integration_full: Full integration tests requiring full environment")
    config.addinivalue_line("markers", "slow: Slow running tests")
    config.addinivalue_line("markers", "browser: Tests requiring browser")
    config.addinivalue_line("markers", "api: API endpoint tests")
    config.addinivalue_line("markers", "smoke: Smoke tests")
    config.addinivalue_line("markers", "asyncio: Async tests")
    config.addinivalue_line("markers", "dashboard: Dashboard-specific tests")
    config.addinivalue_line("markers", "performance: Performance and load tests")
    config.addinivalue_line("markers", "analytics: Analytics and metrics tests")
    config.addinivalue_line("markers", "priority_high: High priority E2E tests")
    config.addinivalue_line("markers", "priority_medium: Medium priority E2E tests")
    config.addinivalue_line("markers", "priority_low: Low priority E2E tests")
    config.addinivalue_line("markers", "quarantine: Quarantined tests that need fixes (tracked in SKIPPED_TESTS.md)")
    config.addinivalue_line("markers", "ui_smoke: UI smoke tests (reclassified Playwright tests)")


def pytest_collection_modifyitems(config, items):
    """Modify test collection based on environment."""
    # Skip performance tests if not enabled
    if os.getenv("PERFORMANCE_TEST_ENABLED", "false").lower() != "true":
        for item in items:
            if "performance" in item.keywords:
                item.add_marker(pytest.mark.skip(reason="Performance tests disabled"))

    # Skip integration tests if not enabled
    if os.getenv("INTEGRATION_TEST_ENABLED", "true").lower() != "true":
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(pytest.mark.skip(reason="Integration tests disabled"))

    # Always skip infrastructure and production data tests
    for item in items:
        if "infrastructure" in item.keywords:
            item.add_marker(pytest.mark.skip(reason="Infrastructure tests disabled - no test infra"))
        if "prod_data" in item.keywords or "production_data" in item.keywords:
            item.add_marker(pytest.mark.skip(reason="Production data tests disabled - no prod data access"))


def pytest_runtest_setup(item):
    """Set up test environment before each test."""
    # Log test start
    logger.info(f"Starting test: {item.name}")


def pytest_runtest_teardown(item, nextitem):
    """Clean up after each test."""
    # Log test completion
    logger.info(f"Completed test: {item.name}")


# Enhanced debugging hooks
def pytest_runtest_logreport(report):
    """Enhanced test reporting with debugging information."""
    if report.when != "call":
        return
    if report.outcome == "failed" and FAILURE_ANALYZER_AVAILABLE and generate_failure_report is not None:
        try:
            test_name = report.nodeid
            exc_info = report.longrepr
            generate_failure_report(
                test_name=test_name,
                exc_info=(Exception, Exception(str(exc_info)), None),
                test_duration=report.duration,
                environment_info={"test_file": report.fspath},
            )
            logger.error("Test failure analyzed: %s", test_name)
        except Exception as e:
            logger.error("Failed to generate failure report: %s", e)
    elif report.outcome == "passed":
        logger.info("Test passed: %s (%.3fs)", report.nodeid, report.duration)
    elif report.outcome == "skipped":
        logger.warning("Test skipped: %s", report.nodeid)


def pytest_runtest_setup(item):
    """Enhanced test setup with debugging."""
    # Start performance profiling if enabled
    if hasattr(item, "get_closest_marker") and item.get_closest_marker("performance"):
        try:
            from tests.utils.performance_profiler import start_performance_monitoring

            start_performance_monitoring()
        except Exception as e:
            logger.error(f"Failed to start performance monitoring: {e}")


def pytest_runtest_teardown(item):
    """Enhanced test teardown with debugging."""
    # Stop performance profiling if enabled
    if hasattr(item, "get_closest_marker") and item.get_closest_marker("performance"):
        try:
            from tests.utils.performance_profiler import save_performance_report, stop_performance_monitoring

            stop_performance_monitoring()
            save_performance_report()
        except Exception as e:
            logger.error(f"Failed to stop performance monitoring: {e}")


# Environment-specific test skipping utilities
# Note: These are utility functions, not pytest hooks
def skip_on_ci(reason="Test skipped in CI environment"):
    """Skip test in CI environment."""
    if test_config.context == TestContext.CI:
        pytest.skip(reason)


def skip_on_docker(reason="Test skipped in Docker environment"):
    """Skip test in Docker environment."""
    if test_config.context == TestContext.DOCKER:
        pytest.skip(reason)


def skip_on_localhost(reason="Test skipped on localhost"):
    """Skip test on localhost."""
    if test_config.context == TestContext.LOCALHOST:
        pytest.skip(reason)
