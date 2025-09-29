"""
Pytest configuration and fixtures for CTI Scraper testing.
"""
import pytest
import pytest_asyncio
import asyncio
import httpx
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

# Test configuration
TEST_BASE_URL = "http://localhost:8000"
TEST_DB_URL = "sqlite:///test.db"

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Async HTTP client for testing."""
    async with httpx.AsyncClient(base_url=TEST_BASE_URL, timeout=30.0) as client:
        yield client

@pytest.fixture
def mock_db_manager():
    """Mock database manager for unit tests."""
    mock = AsyncMock()
    
    # Mock article data
    mock_article = MagicMock()
    mock_article.id = 1
    mock_article.title = "Test Article"
    mock_article.content = "This is test content with TTP indicators."
    mock_article.url = "https://example.com/test"
    mock_article.source_id = 1
    mock_article.published_date = "2024-01-01"
    
    mock.list_articles.return_value = [mock_article]
    mock.get_article.return_value = mock_article
    mock.get_database_stats.return_value = {
        "total_articles": 1,
        "total_sources": 1,
        "last_update": "2024-01-01T00:00:00"
    }
    
    return mock

@pytest.fixture
def sample_ttp_data():
    """Sample TTP analysis data for testing."""
    return {
        "total_techniques": 3,
        "overall_confidence": 0.85,
        "hunting_priority": "High",
        "techniques_by_category": {
            "MITRE ATT&CK": [
                {
                    "technique_name": "T1055",
                    "hunting_guidance": "Monitor process creation",
                    "confidence": 0.9,
                    "matched_text": "process injection"
                }
            ]
        }
    }

@pytest.fixture
def sample_quality_data():
    """Sample quality assessment data for testing."""
    return {
        "ttp_score": 65,
        "llm_score": 72,
        "combined_score": 68.5,
        "quality_level": "Good",
        "tactical_score": 85,
        "strategic_score": 45,
        "classification": "Tactical",
        "hunting_priority": "High",
        "structure_score": 20,
        "technical_score": 18,
        "intelligence_score": 22,
        "recommendations": ["Add more technical details", "Include IOCs"]
    }

@pytest.fixture
def test_environment():
    """Test environment configuration."""
    return {
        "base_url": TEST_BASE_URL,
        "timeout": 30,
        "retry_attempts": 3,
        "headless": True
    }
