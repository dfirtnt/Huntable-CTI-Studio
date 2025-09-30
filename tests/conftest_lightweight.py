"""
Lightweight test configuration and fixtures for integration tests with minimal dependencies.

This conftest provides mocked fixtures for testing critical paths without requiring
full Docker environment setup.
"""
import pytest
import pytest_asyncio
import asyncio
from unittest.mock import AsyncMock, MagicMock
from typing import AsyncGenerator, Dict, Any, List
from datetime import datetime, timedelta

from src.models.article import Article, ArticleCreate
from src.models.source import Source, SourceCreate
from src.database.async_manager import AsyncDatabaseManager
from src.utils.http import HTTPClient
from src.core.processor import ContentProcessor


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_database_manager():
    """Mock database manager for lightweight integration tests."""
    mock_db = AsyncMock(spec=AsyncDatabaseManager)
    
    # Mock article data
    mock_article = Article(
        id=1,
        title="Test Threat Intelligence Article",
        content="This is test content with TTP indicators and threat intelligence data.",
        canonical_url="https://example.com/test",
        source_id=1,
        published_at=datetime.now(),
        content_hash="test-hash-123",
        collected_at=datetime.now(),
        discovered_at=datetime.now(),
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    
    # Configure mock responses
    mock_db.list_articles.return_value = [mock_article]
    mock_db.get_article.return_value = mock_article
    mock_db.create_article.return_value = mock_article
    mock_db.get_existing_content_hashes.return_value = set()
    mock_db.get_database_stats.return_value = {
        "total_articles": 1,
        "total_sources": 1,
        "last_update": datetime.now().isoformat()
    }
    
    # Mock source data
    mock_source = Source(
        id=1,
        identifier="test-source",
        name="Test Security Blog",
        url="https://example.com",
        rss_url="https://example.com/feed.xml",
        check_frequency=3600,
        lookback_days=180,
        active=True,
        config={}
    )
    
    mock_db.list_sources.return_value = [mock_source]
    mock_db.get_source.return_value = mock_source
    mock_db.create_source.return_value = mock_source
    
    return mock_db


@pytest.fixture
def mock_http_client():
    """Mock HTTP client for lightweight integration tests."""
    mock_client = AsyncMock(spec=HTTPClient)
    
    # Mock RSS feed response
    mock_response = MagicMock()
    mock_response.text = """
    <?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
        <channel>
            <title>Test Security Blog</title>
            <item>
                <title>Test Threat Intelligence Article</title>
                <link>https://example.com/article1</link>
                <description>This is a test article about threat intelligence with TTP indicators.</description>
                <pubDate>Wed, 01 Jan 2024 12:00:00 GMT</pubDate>
            </item>
            <item>
                <title>Malware Analysis Report</title>
                <link>https://example.com/article2</link>
                <description>Detailed analysis of recent malware campaign with IOCs.</description>
                <pubDate>Wed, 01 Jan 2024 13:00:00 GMT</pubDate>
            </item>
        </channel>
    </rss>
    """
    mock_response.raise_for_status.return_value = None
    
    mock_client.get.return_value = mock_response
    mock_client.configure_source_robots.return_value = None
    
    return mock_client


@pytest.fixture
def mock_content_processor():
    """Mock content processor for lightweight integration tests."""
    mock_processor = AsyncMock(spec=ContentProcessor)
    
    # Mock processing result
    mock_result = MagicMock()
    mock_result.unique_articles = [
        ArticleCreate(
            title="Test Threat Intelligence Article",
            content="This is a test article about threat intelligence with TTP indicators.",
            url="https://example.com/article1",
            source_id=1,
            published_date=datetime.now()
        ),
        ArticleCreate(
            title="Malware Analysis Report",
            content="Detailed analysis of recent malware campaign with IOCs.",
            url="https://example.com/article2",
            source_id=1,
            published_date=datetime.now()
        )
    ]
    mock_result.duplicates = []
    
    mock_processor.process_articles.return_value = mock_result
    
    return mock_processor


@pytest.fixture
def sample_articles():
    """Sample articles for testing."""
        return [
            Article(
                id=1,
                title="APT29 Campaign Analysis",
                content="Detailed analysis of APT29 techniques including process injection and lateral movement.",
                canonical_url="https://example.com/apt29",
                source_id=1,
                published_at=datetime.now(),
                content_hash="apt29-hash",
                collected_at=datetime.now(),
                discovered_at=datetime.now(),
                created_at=datetime.now(),
                updated_at=datetime.now()
            ),
            Article(
                id=2,
                title="Malware Detection Techniques",
                content="Overview of modern malware detection and analysis methods.",
                canonical_url="https://example.com/malware-detection",
                source_id=1,
                published_at=datetime.now(),
                content_hash="malware-hash",
                collected_at=datetime.now(),
                discovered_at=datetime.now(),
                created_at=datetime.now(),
                updated_at=datetime.now()
            ),
            Article(
                id=3,
                title="Threat Hunting Guide",
                content="Comprehensive guide to threat hunting methodologies and tools.",
                canonical_url="https://example.com/threat-hunting",
                source_id=1,
                published_at=datetime.now(),
                content_hash="hunting-hash",
                collected_at=datetime.now(),
                discovered_at=datetime.now(),
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
        ]


@pytest.fixture
def sample_sources():
    """Sample sources for testing."""
    return [
        Source(
            id=1,
            identifier="test-source-1",
            name="Test Security Blog",
            url="https://example.com",
            rss_url="https://example.com/feed.xml",
            check_frequency=3600,
            lookback_days=180,
            active=True,
            config={}
        ),
        Source(
            id=2,
            identifier="test-source-2",
            name="Security Research Lab",
            url="https://research.example.com",
            rss_url="https://research.example.com/feed.xml",
            check_frequency=7200,
            lookback_days=90,
            active=True,
            config={}
        )
    ]


@pytest.fixture
def mock_content_processor():
    """Mock content processor for lightweight integration tests."""
    mock_processor = AsyncMock()
    
    # Mock processing results
    mock_processor.process_articles.return_value = MagicMock(
        unique_articles=[],
        duplicates=[],
        stats={"total": 0, "unique": 0, "duplicates": 0}
    )
    
    return mock_processor


@pytest.fixture
def mock_source_manager():
    """Mock source manager for lightweight integration tests."""
    mock_manager = AsyncMock()
    
    # Mock source loading
    mock_source = Source(
        id=1,
        identifier="test-source",
        name="Test Security Blog",
        url="https://example.com",
        rss_url="https://example.com/feed.xml",
        check_frequency=3600,
        lookback_days=180,
        active=True,
        config={}
    )
    
    mock_manager.load_sources_from_config.return_value = [mock_source]
    mock_manager.get_sources_due_for_check.return_value = [mock_source]
    mock_manager.validate_source_config.return_value = {
        "valid": True,
        "sources_count": 1,
        "errors": [],
        "warnings": []
    }
    
    return mock_manager


@pytest.fixture
def mock_environment():
    """Mock complete environment for integration testing."""
    return {
        "database": AsyncMock(spec=AsyncDatabaseManager),
        "http_client": AsyncMock(spec=HTTPClient),
        "source_manager": AsyncMock(),
        "content_processor": AsyncMock(spec=ContentProcessor),
        "quality_assessor": AsyncMock()
    }


@pytest.fixture
def test_config():
    """Test configuration for lightweight integration tests."""
    return {
        "base_url": "http://localhost:8001",
        "timeout": 30,
        "retry_attempts": 3,
        "headless": True,
        "mock_mode": True
    }


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
                },
                {
                    "technique_name": "T1021",
                    "hunting_guidance": "Monitor remote services",
                    "confidence": 0.8,
                    "matched_text": "lateral movement"
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
def mock_fastapi_app():
    """Mock FastAPI application for testing."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    
    app = FastAPI()
    
    @app.get("/")
    async def root():
        return {"message": "CTI Scraper API", "status": "healthy"}
    
    @app.get("/api/articles")
    async def get_articles():
        return {
            "articles": [
                {
                    "id": 1,
                    "title": "Test Article",
                    "content": "Test content with threat intelligence",
                    "url": "https://example.com/test",
                    "source_id": 1,
                    "published_date": datetime.now().isoformat()
                }
            ],
            "total": 1
        }
    
    @app.get("/api/sources")
    async def get_sources():
        return {
            "sources": [
                {
                    "id": 1,
                    "identifier": "test-source",
                    "name": "Test Security Blog",
                    "url": "https://example.com",
                    "active": True
                }
            ],
            "total": 1
        }
    
    @app.get("/analysis")
    async def get_analysis():
        return {
            "quality_distribution": {
                "excellent": 10,
                "good": 25,
                "fair": 15,
                "poor": 5
            },
            "tactical_vs_strategic": {
                "tactical": 30,
                "strategic": 20
            }
        }
    
    return TestClient(app)


# Performance testing fixtures
@pytest.fixture
def large_article_set():
    """Large set of articles for performance testing."""
        return [
            ArticleCreate(
                title=f"Article {i}",
                content=f"Content {i} with threat intelligence data " * 100,  # ~1KB content
                canonical_url=f"https://example.com/{i}",
                source_id=1,
                published_at=datetime.now() - timedelta(days=i),
                content_hash=f"large-hash-{i}"
            )
            for i in range(1000)
        ]


@pytest.fixture
def concurrent_test_config():
    """Configuration for concurrent testing."""
    return {
        "concurrent_requests": 10,
        "timeout_per_request": 5.0,
        "max_total_time": 30.0
    }
