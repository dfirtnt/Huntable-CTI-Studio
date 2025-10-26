"""
Enhanced conftest for integration workflow tests.
Provides fixtures for Celery workers, test database with rollback, and external API preference handling.
"""

import pytest
import pytest_asyncio
import asyncio
import subprocess
import time
import os
from typing import AsyncGenerator, Dict, Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture(scope="session")
def integration_test_marker():
    """Marker to identify integration workflow tests."""
    pytest.mark.integration_workflow


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def celery_worker_available():
    """Check if Celery worker is running in Docker."""
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=cti_worker", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return "cti_worker" in result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        return False


@pytest_asyncio.fixture(scope="session")
async def test_database_with_rollback(celery_worker_available):
    """Test database fixture with transaction rollback for isolation."""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    import os
    
    # Database URL from environment
    db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://cti_user:cti_pass@localhost:5432/cti_scraper_test")
    
    engine = create_async_engine(
        db_url,
        pool_pre_ping=True,
        echo=False
    )
    
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Begin transaction
        await session.begin()
        yield session
        # Rollback to clean state
        await session.rollback()
    
    await engine.dispose()


@pytest.fixture
def test_database_manager(test_database_with_rollback):
    """Provide test database manager with transaction rollback."""
    from src.database.async_manager import AsyncDatabaseManager
    
    # Create manager with test session
    manager = AsyncDatabaseManager()
    # Use the test session with rollback
    return manager


@pytest.fixture
async def external_api_preference():
    """
    Prompt user for external API testing preference and API keys.
    Returns: 'mock' or 'real'
    """
    import sys
    
    # Check for API keys and prompt if missing
    openai_key = os.getenv('OPENAI_API_KEY')
    anthropic_key = os.getenv('ANTHROPIC_API_KEY')
    
    if not openai_key and not anthropic_key:
        print("\n⚠️  No AI API keys found in environment.")
        print("For tests that use OpenAI or Anthropic:")
        print("  - Set OPENAI_API_KEY environment variable for OpenAI tests")
        print("  - Set ANTHROPIC_API_KEY environment variable for Anthropic tests")
        print("  - Or they will be prompted during test execution")
    
    # Check environment variable first
    preference = os.getenv("EXTERNAL_API_TEST_MODE", "").lower()
    
    if preference in ['mock', 'real']:
        return preference
    
    # Prompt user for preference (non-interactive in CI)
    if os.getenv("CI") == "true":
        return 'mock'  # Default to mock in CI
    
    # In interactive mode, ask user
    print("\n" + "="*60)
    print("External API Testing Preference")
    print("="*60)
    print("How should external APIs (OpenAI, Anthropic) be tested?")
    print("  [m] Mock (fast, no cost, no external calls)")
    print("  [r] Real (slow, costs money, makes actual API calls)")
    print("="*60)
    
    while True:
        choice = input("Enter choice [m/r]: ").strip().lower()
        if choice in ['m', 'mock']:
            return 'mock'
        elif choice in ['r', 'real']:
            print("⚠️  WARNING: Real API tests will make actual API calls and incur costs!")
            confirm = input("Continue with real API tests? [y/N]: ").strip().lower()
            if confirm == 'y':
                return 'real'
            continue
        else:
            print("Invalid choice. Please enter 'm' or 'r'")
    
    return 'mock'  # Default fallback


@pytest.fixture
def mock_llm_service(external_api_preference):
    """Mock LLM service based on user preference."""
    if external_api_preference == 'mock':
        service = AsyncMock()
        service.generate_response = AsyncMock(return_value="Mock LLM response")
        service.summarize_content = AsyncMock(return_value="Mock summary")
        service.extract_entities = AsyncMock(return_value=["entity1", "entity2"])
        return service
    # For real API tests, return None to use actual service
    return None


@pytest.fixture
def mock_celery_app():
    """Mock Celery app for tests that don't need real worker."""
    from src.worker.celery_app import celery_app
    return celery_app


@pytest_asyncio.fixture
async def wait_for_celery_task():
    """Helper to wait for Celery task completion."""
    async def _wait_for_task(task_result, timeout=30):
        """Wait for task with timeout."""
        start_time = time.time()
        while not task_result.ready():
            if time.time() - start_time > timeout:
                raise TimeoutError(f"Task not completed within {timeout}s")
            await asyncio.sleep(0.1)
        return task_result
    return _wait_for_task


@pytest.fixture
def celery_task_cleanup():
    """Cleanup fixture for Celery tasks."""
    tasks_to_cleanup = []
    
    yield tasks_to_cleanup
    
    # Cleanup registered tasks
    for task in tasks_to_cleanup:
        try:
            if hasattr(task, 'revoke'):
                task.revoke(terminate=True)
        except Exception:
            pass


@pytest.fixture
def mock_rss_feed():
    """Mock RSS feed data for testing."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
    <channel>
        <title>Test Security Blog</title>
        <link>https://test.example.com</link>
        <description>Test feed for integration tests</description>
        <item>
            <title>APT29 Uses Rundll32 for Persistence</title>
            <link>https://test.example.com/apt29-persistence</link>
            <guid isPermaLink="true">https://test.example.com/apt29-persistence</guid>
            <pubDate>Wed, 01 Jan 2025 12:00:00 GMT</pubDate>
            <description>Threat actors used rundll32.exe to execute malicious DLL at C:\\Windows\\System32\\evil.dll</description>
        </item>
        <item>
            <title>Malware Campaign Analysis</title>
            <link>https://test.example.com/malware-campaign</link>
            <guid isPermaLink="true">https://test.example.com/malware-campaign</guid>
            <pubDate>Wed, 01 Jan 2025 13:00:00 GMT</pubDate>
            <description>Analysis of recent malware campaign with IOCs and TTPs</description>
        </item>
    </channel>
</rss>"""


@pytest.fixture
def test_source_config():
    """Test source configuration."""
    return {
        "identifier": "test-source-integration",
        "name": "Test Integration Source",
        "url": "https://test.example.com",
        "rss_url": "https://test.example.com/feed.xml",
        "check_frequency": 3600,
        "lookback_days": 180,
        "active": True,
        "config": {
            "collection_method": "rss",
            "fallback_to_scraping": True
        }
    }


@pytest.fixture
def sample_article_data():
    """Sample article data for testing."""
    return {
        "title": "Test Threat Intelligence Article",
        "content": "Sample content with rundll32.exe, WINDIR, appdata references and threat hunting indicators",
        "canonical_url": "https://test.example.com/test-article",
        "published_date": datetime.now(),
        "source_id": 1,
        "content_hash": "test-hash-123",
        "collected_at": datetime.now(),
        "discovered_at": datetime.now()
    }


@pytest.fixture
def annotation_test_data():
    """Test data for annotation feedback loop."""
    return {
        "annotation_type": "huntable",
        "selected_text": "This is a long text " * 50,  # ~1000 chars to meet validation
        "start_position": 0,
        "end_position": 1000,
        "article_id": 1
    }


@pytest.fixture
def chunk_feedback_test_data():
    """Test data for chunk classification feedback."""
    return {
        "article_id": 1,
        "chunk_id": 0,
        "chunk_text": "Sample chunk text for classification feedback",
        "model_classification": "Huntable",
        "model_confidence": 0.85,
        "is_correct": True,
        "user_classification": None
    }


@pytest.fixture
async def test_redis_client():
    """Test Redis client fixture."""
    import redis.asyncio as redis
    import os
    
    client = await redis.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        db=int(os.getenv("REDIS_DB", "1")),  # Use different DB for tests
        decode_responses=True
    )
    
    yield client
    
    # Cleanup test data
    await client.flushdb()
    await client.close()


# Register custom markers
def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "integration_workflow: Integration workflow tests")
    config.addinivalue_line("markers", "celery_task: Celery task integration tests")
    config.addinivalue_line("markers", "scoring_system: Scoring system integration tests")
    config.addinivalue_line("markers", "annotation_feedback: Annotation feedback loop tests")
    config.addinivalue_line("markers", "content_pipeline: Content processing pipeline tests")
    config.addinivalue_line("markers", "source_management: Source management workflow tests")
    config.addinivalue_line("markers", "rag_conversation: RAG chat conversation tests")
    config.addinivalue_line("markers", "error_recovery: Error recovery and resilience tests")
    config.addinivalue_line("markers", "export_backup: Export and backup workflow tests")
    config.addinivalue_line("markers", "external_api: Tests requiring external APIs")

