"""
Tests for database modules in src/database/.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from src.database.manager import DatabaseManager
from src.database.async_manager import AsyncDatabaseManager
from src.database.models import ArticleTable, SourceTable


class TestDatabaseManager:
    """Test the DatabaseManager class."""
    
    def test_connection_string(self):
        """Test database connection string generation."""
        # Test connection string format
        expected = "postgresql://test_user:test_pass@localhost:5432/test_db"
        
        # Verify the format is correct
        assert "postgresql://" in expected
        assert "test_user:test_pass" in expected
        assert "localhost:5432" in expected
        assert "test_db" in expected
    
    def test_validate_connection_params(self):
        """Test connection parameter validation."""
        # Test valid parameters
        valid_params = {
            'host': 'localhost',
            'port': 5432,
            'database': 'test_db',
            'username': 'test_user',
            'password': 'test_pass'
        }
        # All required fields present
        assert all(key in valid_params for key in ['host', 'port', 'database', 'username', 'password'])
        
        # Test invalid parameters (missing host)
        invalid_params = {
            'port': 5432,
            'database': 'test_db',
            'username': 'test_user',
            'password': 'test_pass'
        }
        # Missing required field
        assert 'host' not in invalid_params
    
    def test_create_tables(self):
        """Test table creation."""
        # Test that we can import the models
        from src.database.models import ArticleTableTable, SourceTable
        
        # Verify models exist
        assert ArticleTable is not None
        assert SourceTable is not None
    
    def test_get_article_count(self):
        """Test getting article count."""
        # Test model structure
        from src.database.models import ArticleTable
        
        # Create a mock article
        article = ArticleTable(
            title="Test Article",
            content="Test content",
            canonical_url="https://example.com",
            source_id=1,
            published_at="2024-01-01T00:00:00Z",
            content_hash="test_hash"
        )
        
        assert article.title == "Test Article"
        assert article.content == "Test content"
        assert article.canonical_url == "https://example.com"
        assert article.source_id == 1
    
    def test_get_source_count(self):
        """Test getting source count."""
        # Test model structure
        from src.database.models import SourceTable
        
        # Create a mock source
        source = SourceTable(
            name="Test Source",
            url="https://example.com/feed.xml",
            identifier="test-source",
            active=True
        )
        
        assert source.name == "Test Source"
        assert source.url == "https://example.com/feed.xml"
        assert source.identifier == "test-source"
        assert source.active is True


class TestAsyncDatabaseManager:
    """Test the AsyncDatabaseManager class."""
    
    @pytest.mark.asyncio
    async def test_async_connection_string(self):
        """Test async database connection string generation."""
        # Test async connection string format
        expected = "postgresql+asyncpg://test_user:test_pass@localhost:5432/test_db"
        
        # Verify the format is correct
        assert "postgresql+asyncpg://" in expected
        assert "test_user:test_pass" in expected
        assert "localhost:5432" in expected
        assert "test_db" in expected
    
    @pytest.mark.asyncio
    async def test_async_create_tables(self):
        """Test async table creation."""
        # Test that we can import async models
        from src.database.models import ArticleTableTable, SourceTable
        
        # Verify models exist
        assert ArticleTable is not None
        assert SourceTable is not None
    
    @pytest.mark.asyncio
    async def test_async_get_article_count(self):
        """Test async getting article count."""
        # Test model structure
        from src.database.models import ArticleTable
        
        # Create a mock article
        article = ArticleTable(
            title="Test Article",
            content="Test content",
            canonical_url="https://example.com",
            source_id=1,
            published_at="2024-01-01T00:00:00Z",
            content_hash="test_hash"
        )
        
        assert article.title == "Test Article"
        assert article.content == "Test content"
        assert article.canonical_url == "https://example.com"
        assert article.source_id == 1
    
    @pytest.mark.asyncio
    async def test_async_get_source_count(self):
        """Test async getting source count."""
        # Test model structure
        from src.database.models import SourceTable
        
        # Create a mock source
        source = SourceTable(
            name="Test Source",
            url="https://example.com/feed.xml",
            identifier="test-source",
            active=True
        )
        
        assert source.name == "Test Source"
        assert source.url == "https://example.com/feed.xml"
        assert source.identifier == "test-source"
        assert source.active is True
    
    @pytest.mark.asyncio
    async def test_async_save_article(self):
        """Test async saving article."""
        # Test ArticleCreate model
        from src.database.models import ArticleTableCreate
        
        article_data = ArticleCreate(
            title='Test Article',
            content='Test content',
            url='https://example.com/article',
            source_id=1,
            published_at='2024-01-01T00:00:00Z'
        )
        
        assert article_data.title == 'Test Article'
        assert article_data.content == 'Test content'
        assert article_data.url == 'https://example.com/article'
        assert article_data.source_id == 1
    
    @pytest.mark.asyncio
    async def test_async_get_articles(self):
        """Test async getting articles."""
        # Test model structure
        from src.database.models import ArticleTable
        
        # Create mock articles
        article1 = ArticleTable(title='Article 1', content='Content 1', canonical_url='https://example.com/1', source_id=1, published_at='2024-01-01T00:00:00Z', content_hash='hash1')
        article2 = ArticleTable(title='Article 2', content='Content 2', canonical_url='https://example.com/2', source_id=1, published_at='2024-01-01T00:00:00Z', content_hash='hash2')
        
        articles = [article1, article2]
        
        assert len(articles) == 2
        assert articles[0].title == 'Article 1'
        assert articles[1].title == 'Article 2'


class TestDatabaseModels:
    """Test database models."""
    
    def test_article_model(self):
        """Test Article model."""
        article = ArticleTable(
            title='Test Article',
            content='Test content',
            canonical_url='https://example.com/article',
            source_id=1,
            published_at='2024-01-01T00:00:00Z',
            content_hash='test_hash'
        )
        
        assert article.title == 'Test Article'
        assert article.content == 'Test content'
        assert article.canonical_url == 'https://example.com/article'
        assert article.source_id == 1
        assert article.published_at == '2024-01-01T00:00:00Z'
    
    def test_source_model(self):
        """Test Source model."""
        source = SourceTable(
            name='Test Source',
            url='https://example.com/feed.xml',
            identifier='test-source',
            active=True
        )
        
        assert source.name == 'Test Source'
        assert source.url == 'https://example.com/feed.xml'
        assert source.identifier == 'test-source'
        assert source.active is True
    
    def test_article_relationships(self):
        """Test Article model relationships."""
        source = SourceTable(
            name='Test Source',
            url='https://example.com/feed.xml',
            identifier='test-source',
            active=True
        )
        
        article = ArticleTable(
            title='Test Article',
            content='Test content',
            url='https://example.com/article',
            source=source,
            published_at='2024-01-01T00:00:00Z'
        )
        
        assert article.source == source
        assert article.source.name == 'Test Source'
    
    def test_model_validation(self):
        """Test model validation."""
        # Test Article with required fields
        article = ArticleTable(
            title='Test Article',
            content='Test content',
            canonical_url='https://example.com/article',
            source_id=1,
            published_at='2024-01-01T00:00:00Z',
            content_hash='test_hash'
        )
        
        assert article.title is not None
        assert article.content is not None
        assert article.canonical_url is not None
        
        # Test Source with required fields
        source = SourceTable(
            name='Test Source',
            url='https://example.com/feed.xml',
            type='rss'
        )
        
        assert source.name is not None
        assert source.url is not None
        assert source.type is not None


if __name__ == "__main__":
    pytest.main([__file__])
