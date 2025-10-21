"""
Test configuration and fixtures for CTI Scraper tests.
"""

import os
import sys
import pytest
import pytest_asyncio
import httpx
import asyncio
import tempfile
import shutil
import logging
from typing import AsyncGenerator, Generator
from pathlib import Path
from playwright.sync_api import sync_playwright
from unittest.mock import AsyncMock, MagicMock

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import test environment utilities
from tests.utils.test_environment import (
    TestEnvironmentValidator,
    TestEnvironmentManager,
    TestContext,
    get_test_config,
    validate_test_environment,
    setup_test_environment
)

# Enhanced debugging imports
from tests.utils.test_failure_analyzer import TestFailureReporter, analyze_test_failure
from tests.utils.async_debug_utils import AsyncDebugger, debug_async_test
from tests.utils.test_isolation import TestIsolationManager, test_isolation
from tests.utils.performance_profiler import PerformanceProfiler, profile_test
from tests.utils.test_output_formatter import TestOutputFormatter, print_test_result, print_test_failure

# Load test configuration
test_config = get_test_config()

# Set up logging for tests
logging.basicConfig(
    level=os.getenv("TEST_LOG_LEVEL", "DEBUG"),
    format=os.getenv("TEST_LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def test_environment_config():
    """Provide test environment configuration."""
    return test_config


@pytest.fixture(scope="session")
async def test_environment_manager(test_environment_config):
    """Set up and manage test environment."""
    manager = TestEnvironmentManager(test_environment_config)
    await manager.setup_test_environment()
    yield manager
    await manager.teardown_test_environment()


@pytest.fixture(scope="session")
async def test_environment_validation():
    """Validate test environment before running tests."""
    is_valid = await validate_test_environment()
    if not is_valid:
        pytest.exit("Test environment validation failed")
    return is_valid


@pytest_asyncio.fixture
async def async_client(test_environment_config) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Async HTTP client for API testing."""
    base_url = f"http://127.0.0.1:{test_environment_config.test_port}"
    timeout = httpx.Timeout(60.0)  # Increased timeout for RAG operations
    async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
        yield client


@pytest.fixture
def api_headers():
    """Default API headers."""
    return {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }


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
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    
    engine = create_async_engine(
        test_environment_config.database_url,
        pool_size=test_environment_config.db_pool_size if hasattr(test_environment_config, 'db_pool_size') else 5,
        max_overflow=test_environment_config.db_max_overflow if hasattr(test_environment_config, 'db_max_overflow') else 10,
        pool_pre_ping=True,
        pool_recycle=1800
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
            socket_timeout=5
        )
    else:
        client = redis.Redis(
            host=test_environment_config.redis_host,
            port=test_environment_config.redis_port,
            db=test_environment_config.redis_db,
            socket_timeout=5
        )
    
    yield client
    await client.close()


# Mock Fixtures for Database and Service Testing
@pytest.fixture
def mock_async_session():
    """Create a properly configured async database session mock."""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.add = MagicMock()
    session.delete = MagicMock()
    session.merge = MagicMock()
    session.refresh = AsyncMock()
    session.scalar = AsyncMock()
    session.scalars = AsyncMock()
    session.get = AsyncMock()
    return session


@pytest.fixture
def mock_async_engine():
    """Create a properly configured async database engine mock."""
    engine = AsyncMock()
    engine.begin = AsyncMock()
    engine.__aenter__ = AsyncMock(return_value=engine)
    engine.__aexit__ = AsyncMock(return_value=None)
    engine.connect = AsyncMock()
    engine.dispose = AsyncMock()
    return engine


@pytest.fixture
def mock_async_http_client():
    """Create a properly configured async HTTP client mock."""
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
            "height": int(os.getenv("BROWSER_HEIGHT", "720"))
        },
        "ignore_https_errors": os.getenv("BROWSER_IGNORE_HTTPS", "true").lower() == "true",
        "record_video_dir": os.getenv("PLAYWRIGHT_VIDEO_DIR", "test-results/videos/"),
        "record_video_size": {
            "width": int(os.getenv("BROWSER_WIDTH", "1280")),
            "height": int(os.getenv("BROWSER_HEIGHT", "720"))
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
def playwright_context():
    """Playwright context for session-scoped tests"""
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def browser(playwright_context, browser_type_launch_args):
    """Browser instance for session-scoped tests"""
    browser = playwright_context.chromium.launch(**browser_type_launch_args)
    yield browser
    browser.close()


@pytest.fixture(scope="session")
def context(browser, browser_context_args):
    """Browser context for session-scoped tests"""
    context = browser.new_context(**browser_context_args)
    yield context
    context.close()


@pytest.fixture
def page(context):
    """Page instance for each test"""
    page = context.new_page()
    yield page
    page.close()


# Test isolation fixtures
@pytest.fixture(autouse=True)
async def test_isolation(test_environment_config, test_environment_manager):
    """Ensure test isolation between tests."""
    if not test_environment_config.test_isolation:
        return
    
    # Set up isolation before test
    await test_environment_manager._setup_test_isolation()
    
    yield
    
    # Clean up after test
    await test_environment_manager._cleanup_test_data()


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


# Enhanced debugging fixtures
@pytest.fixture
def failure_reporter():
    """Provide test failure reporter."""
    return TestFailureReporter()


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
    return TestOutputFormatter()


@pytest.fixture
def isolation_manager():
    """Provide test isolation manager."""
    return TestIsolationManager()


def pytest_configure(config):
    """Register custom markers to satisfy strict marker checks."""
    config.addinivalue_line("markers", "ui: UI tests")
    config.addinivalue_line("markers", "ai: AI assistant and summarization tests")
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
    if report.when == "call":
        if report.outcome == "failed":
            # Generate failure report
            try:
                from tests.utils.test_failure_analyzer import generate_failure_report
                
                # Extract test information
                test_name = report.nodeid
                exc_info = report.longrepr
                
                # Generate failure report
                failure_context = generate_failure_report(
                    test_name=test_name,
                    exc_info=(Exception, Exception(str(exc_info)), None),
                    test_duration=report.duration,
                    environment_info={"test_file": report.fspath}
                )
                
                logger.error(f"Test failure analyzed: {test_name}")
                
            except Exception as e:
                logger.error(f"Failed to generate failure report: {e}")
        
        elif report.outcome == "passed":
            # Log successful test with timing
            logger.info(f"Test passed: {report.nodeid} ({report.duration:.3f}s)")
        
        elif report.outcome == "skipped":
            # Log skipped test
            logger.warning(f"Test skipped: {report.nodeid}")


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
            from tests.utils.performance_profiler import stop_performance_monitoring, save_performance_report
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
