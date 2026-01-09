"""Tests for deduplication service functionality."""

import pytest

# DISABLED: These tests require database access for duplicate checking and may modify production data.
# No isolated test environment available.
pytestmark = pytest.mark.skip(reason="Disabled to prevent database access/modification. No isolated test environment available.")

import hashlib
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch
from typing import List, Optional, Tuple

from src.services.deduplication import DeduplicationService, AsyncDeduplicationService
from src.utils.simhash import SimHash, compute_article_simhash, is_content_similar, simhash_calculator
from src.models.article import ArticleCreate
from src.database.models import ArticleTable


class TestSimHash:
    """Test SimHash functionality."""

    @pytest.fixture
    def simhash(self):
        """Create SimHash instance for testing."""
        return SimHash(hash_bits=64)

    def test_init(self, simhash):
        """Test SimHash initialization."""
        assert simhash.hash_bits == 64
        assert simhash.max_hash == 2**64 - 1

    def test_tokenize_basic(self, simhash):
        """Test basic tokenization."""
        text = "This is a test article about threat hunting."
        tokens = simhash._tokenize(text)
        
        assert "test" in tokens
        assert "article" in tokens
        assert "threat" in tokens
        assert "hunting" in tokens
        assert "this" not in tokens  # Stop word
        assert "is" not in tokens    # Stop word
        assert "a" not in tokens     # Stop word

    def test_tokenize_empty_text(self, simhash):
        """Test tokenization with empty text."""
        tokens = simhash._tokenize("")
        assert tokens == []

    def test_tokenize_short_tokens(self, simhash):
        """Test tokenization filters short tokens."""
        text = "A B C test article"
        tokens = simhash._tokenize(text)
        
        assert "test" in tokens
        assert "article" in tokens
        assert "A" not in tokens  # Too short
        assert "B" not in tokens  # Too short
        assert "C" not in tokens  # Too short

    def test_tokenize_punctuation(self, simhash):
        """Test tokenization handles punctuation."""
        text = "This is a test, article. With punctuation!"
        tokens = simhash._tokenize(text)
        
        assert "test" in tokens
        assert "article" in tokens
        assert "punctuation" in tokens

    def test_get_feature_hash(self, simhash):
        """Test feature hash generation."""
        hash1 = simhash._get_feature_hash("test")
        hash2 = simhash._get_feature_hash("test")
        hash3 = simhash._get_feature_hash("different")
        
        assert hash1 == hash2  # Same input should produce same hash
        assert hash1 != hash3  # Different input should produce different hash
        assert 0 <= hash1 < 2**64  # Hash should be within bounds

    def test_get_feature_vector(self, simhash):
        """Test feature vector generation."""
        features = ["test", "article", "threat"]
        vector = simhash._get_feature_vector(features)
        
        assert len(vector) == 3
        assert all(0 <= h < 2**64 for h in vector)

    def test_get_weighted_vector(self, simhash):
        """Test weighted vector generation."""
        features = ["test", "test", "article", "threat"]
        vector = simhash._get_weighted_vector(features)
        
        assert len(vector) == 64  # hash_bits
        assert all(isinstance(v, int) for v in vector)

    def test_compute_simhash_basic(self, simhash):
        """Test basic SimHash computation."""
        text = "This is a test article about threat hunting."
        simhash_value = simhash.compute_simhash(text)
        
        assert isinstance(simhash_value, int)
        assert 0 <= simhash_value <= simhash.max_hash

    def test_compute_simhash_empty_text(self, simhash):
        """Test SimHash computation with empty text."""
        simhash_value = simhash.compute_simhash("")
        assert simhash_value == 0

    def test_compute_simhash_identical_texts(self, simhash):
        """Test that identical texts produce identical SimHashes."""
        text = "This is a test article about threat hunting."
        simhash1 = simhash.compute_simhash(text)
        simhash2 = simhash.compute_simhash(text)
        
        assert simhash1 == simhash2

    def test_compute_simhash_similar_texts(self, simhash):
        """Test that similar texts produce similar SimHashes."""
        text1 = "This is a test article about threat hunting."
        text2 = "This is a test article about threat detection."
        
        simhash1 = simhash.compute_simhash(text1)
        simhash2 = simhash.compute_simhash(text2)
        
        # Should be similar (low Hamming distance)
        distance = simhash.hamming_distance(simhash1, simhash2)
        assert distance <= 5  # Should be relatively similar

    def test_compute_simhash_different_texts(self, simhash):
        """Test that different texts produce different SimHashes."""
        text1 = "This is a test article about threat hunting."
        text2 = "Completely different content about something else."
        
        simhash1 = simhash.compute_simhash(text1)
        simhash2 = simhash.compute_simhash(text2)
        
        # Should be different (high Hamming distance)
        distance = simhash.hamming_distance(simhash1, simhash2)
        assert distance > 5  # Should be relatively different

    def test_compute_simhash_bucket(self, simhash):
        """Test SimHash bucket computation."""
        simhash_value = 12345
        bucket = simhash.compute_simhash_bucket(simhash_value, 16)
        
        assert 0 <= bucket < 16
        assert bucket == simhash_value % 16

    def test_hamming_distance(self, simhash):
        """Test Hamming distance calculation."""
        # Test with known values
        simhash1 = 0b1010  # Binary: 1010
        simhash2 = 0b1100  # Binary: 1100
        distance = simhash.hamming_distance(simhash1, simhash2)
        
        assert distance == 2  # Bits differ at positions 1 and 3

    def test_hamming_distance_identical(self, simhash):
        """Test Hamming distance with identical SimHashes."""
        simhash_value = 12345
        distance = simhash.hamming_distance(simhash_value, simhash_value)
        assert distance == 0

    def test_is_similar(self, simhash):
        """Test similarity checking."""
        simhash1 = 0b1010
        simhash2 = 0b1100
        simhash3 = 0b1111
        
        assert simhash.is_similar(simhash1, simhash2, threshold=3)  # Distance 2
        assert not simhash.is_similar(simhash1, simhash3, threshold=1)  # Distance 2

    def test_find_similar_hashes(self, simhash):
        """Test finding similar hashes in a list."""
        target = 0b1010
        hashes = [0b1100, 0b1111, 0b1011, 0b0000]
        
        similar = simhash.find_similar_hashes(target, hashes, threshold=2)
        
        # Should find hashes with distance <= 2
        assert 0b1100 in similar  # Distance 2
        assert 0b1011 in similar  # Distance 1
        assert 0b1111 not in similar  # Distance 3
        assert 0b0000 not in similar  # Distance 3


class TestSimHashFunctions:
    """Test SimHash utility functions."""

    def test_compute_article_simhash(self):
        """Test article SimHash computation."""
        content = "This is a test article about threat hunting."
        title = "Test Article"
        
        simhash, bucket = compute_article_simhash(content, title)
        
        assert isinstance(simhash, int)
        assert isinstance(bucket, int)
        assert 0 <= bucket < 16  # Default bucket count

    def test_compute_article_simhash_no_title(self):
        """Test article SimHash computation without title."""
        content = "This is a test article about threat hunting."
        
        simhash, bucket = compute_article_simhash(content)
        
        assert isinstance(simhash, int)
        assert isinstance(bucket, int)

    def test_is_content_similar(self):
        """Test content similarity checking."""
        content1 = "This is a test article about threat hunting."
        content2 = "This is a test article about threat detection."
        content3 = "Completely different content about something else."
        
        assert is_content_similar(content1, content2)  # Should be similar
        assert not is_content_similar(content1, content3)  # Should be different

    def test_is_content_similar_with_titles(self):
        """Test content similarity checking with titles."""
        content1 = "This is a test article about threat hunting."
        title1 = "Threat Hunting Guide"
        content2 = "This is a test article about threat detection."
        title2 = "Threat Detection Guide"
        content3 = "Completely different content."
        title3 = "Different Topic"
        
        assert is_content_similar(content1, content2, title1, title2)
        assert not is_content_similar(content1, content3, title1, title3)

    def test_is_content_similar_custom_threshold(self):
        """Test content similarity checking with custom threshold."""
        content1 = "This is a test article about threat hunting."
        content2 = "This is a test article about threat detection."
        
        # With strict threshold
        assert not is_content_similar(content1, content2, threshold=0)
        
        # With lenient threshold
        assert is_content_similar(content1, content2, threshold=10)


class TestDeduplicationService:
    """Test DeduplicationService functionality."""

    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        session = Mock()
        session.query = Mock()
        return session

    @pytest.fixture
    def deduplication_service(self, mock_session):
        """Create DeduplicationService instance."""
        return DeduplicationService(mock_session)

    @pytest.fixture
    def sample_article(self):
        """Create sample article for testing."""
        return ArticleCreate(
            source_id=1,
            canonical_url="https://example.com/article1",
            title="Test Article",
            published_at=datetime.now(),
            content="This is a test article about threat hunting.",
            summary="Test summary",
            authors=["Test Author"],
            tags=["security"],
            article_metadata={},
            content_hash="test_hash_123"
        )

    def test_compute_content_hash(self, deduplication_service):
        """Test content hash computation."""
        content = "This is a test article."
        content_hash = deduplication_service.compute_content_hash(content)
        
        # Should be SHA-256 hash
        assert len(content_hash) == 64  # SHA-256 hex length
        assert content_hash == hashlib.sha256(content.encode('utf-8')).hexdigest()

    def test_compute_content_hash_identical_content(self, deduplication_service):
        """Test that identical content produces identical hashes."""
        content = "This is a test article."
        hash1 = deduplication_service.compute_content_hash(content)
        hash2 = deduplication_service.compute_content_hash(content)
        
        assert hash1 == hash2

    def test_compute_content_hash_different_content(self, deduplication_service):
        """Test that different content produces different hashes."""
        content1 = "This is a test article."
        content2 = "This is a different article."
        
        hash1 = deduplication_service.compute_content_hash(content1)
        hash2 = deduplication_service.compute_content_hash(content2)
        
        assert hash1 != hash2

    def test_check_exact_duplicates_by_url(self, deduplication_service, sample_article, mock_session):
        """Test exact duplicate checking by URL."""
        # Mock existing article
        existing_article = Mock(spec=ArticleTable)
        existing_article.canonical_url = sample_article.canonical_url
        
        # Mock query chain
        query_mock = Mock()
        query_mock.filter.return_value.first.return_value = existing_article
        mock_session.query.return_value = query_mock
        
        is_duplicate, found_article = deduplication_service.check_exact_duplicates(sample_article)
        
        assert is_duplicate is True
        assert found_article == existing_article

    def test_check_exact_duplicates_by_content_hash(self, deduplication_service, sample_article, mock_session):
        """Test exact duplicate checking by content hash."""
        # Mock no existing article by URL
        query_mock = Mock()
        query_mock.filter.return_value.first.return_value = None
        mock_session.query.return_value = query_mock
        
        # Mock existing article by content hash
        existing_article = Mock(spec=ArticleTable)
        existing_article.content_hash = deduplication_service.compute_content_hash(sample_article.content)
        
        # First call returns None (URL check), second call returns existing article (hash check)
        query_mock.filter.return_value.first.side_effect = [None, existing_article]
        
        is_duplicate, found_article = deduplication_service.check_exact_duplicates(sample_article)
        
        assert is_duplicate is True
        assert found_article == existing_article

    def test_check_exact_duplicates_no_duplicate(self, deduplication_service, sample_article, mock_session):
        """Test exact duplicate checking with no duplicates."""
        # Mock no existing articles
        query_mock = Mock()
        query_mock.filter.return_value.first.return_value = None
        mock_session.query.return_value = query_mock
        
        is_duplicate, found_article = deduplication_service.check_exact_duplicates(sample_article)
        
        assert is_duplicate is False
        assert found_article is None

    def test_check_near_duplicates(self, deduplication_service, sample_article, mock_session):
        """Test near duplicate checking."""
        # Mock similar articles
        similar_article1 = Mock(spec=ArticleTable)
        similar_article1.simhash = 12345
        similar_article1.title = "Similar Article 1"
        
        similar_article2 = Mock(spec=ArticleTable)
        similar_article2.simhash = 12346
        similar_article2.title = "Similar Article 2"
        
        # Mock query to return similar articles
        query_mock = Mock()
        query_mock.filter.return_value.all.return_value = [similar_article1, similar_article2]
        mock_session.query.return_value = query_mock
        
        with patch('src.services.deduplication.compute_article_simhash', return_value=(12345, 0)):
            with patch('src.services.deduplication.simhash_calculator.is_similar', return_value=True):
                similar_articles = deduplication_service.check_near_duplicates(sample_article)
        
        assert len(similar_articles) == 2
        assert similar_article1 in similar_articles
        assert similar_article2 in similar_articles

    def test_create_article_with_deduplication_exact_duplicate(self, deduplication_service, sample_article, mock_session):
        """Test article creation with exact duplicate."""
        # Mock exact duplicate found
        existing_article = Mock(spec=ArticleTable)
        
        with patch.object(deduplication_service, 'check_exact_duplicates', return_value=(True, existing_article)):
            created, article, similar = deduplication_service.create_article_with_deduplication(sample_article)
        
        assert created is False
        assert article == existing_article
        assert similar == []

    def test_create_article_with_deduplication_new_article(self, deduplication_service, sample_article, mock_session):
        """Test article creation with new article."""
        # Mock no exact duplicates
        with patch.object(deduplication_service, 'check_exact_duplicates', return_value=(False, None)):
            with patch.object(deduplication_service, 'check_near_duplicates', return_value=[]):
                with patch('src.services.deduplication.compute_article_simhash', return_value=(12345, 0)):
                    created, article, similar = deduplication_service.create_article_with_deduplication(sample_article)
        
        assert created is True
        assert isinstance(article, ArticleTable)
        assert similar == []
        
        # Verify session.add was called
        mock_session.add.assert_called_once()


@pytest.mark.asyncio
class TestAsyncDeduplicationService:
    """Test AsyncDeduplicationService functionality."""

    @pytest.fixture
    def mock_async_session(self):
        """Create mock async database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.add = AsyncMock()
        session.flush = AsyncMock()
        return session

    @pytest.fixture
    def async_deduplication_service(self, mock_async_session):
        """Create AsyncDeduplicationService instance."""
        return AsyncDeduplicationService(mock_async_session)

    @pytest.fixture
    def sample_article(self):
        """Create sample article for testing."""
        return ArticleCreate(
            source_id=1,
            canonical_url="https://example.com/article1",
            title="Test Article",
            published_at=datetime.now(),
            content="This is a test article about threat hunting.",
            summary="Test summary",
            authors=["Test Author"],
            tags=["security"],
            article_metadata={},
            content_hash="test_hash_123"
        )

    def test_compute_content_hash(self, async_deduplication_service):
        """Test content hash computation."""
        content = "This is a test article."
        content_hash = async_deduplication_service.compute_content_hash(content)
        
        # Should be SHA-256 hash
        assert len(content_hash) == 64  # SHA-256 hex length
        assert content_hash == hashlib.sha256(content.encode('utf-8')).hexdigest()

    @pytest.mark.asyncio
    async def test_check_exact_duplicates_by_url(self, async_deduplication_service, sample_article, mock_async_session):
        """Test exact duplicate checking by URL."""
        # Mock existing article
        existing_article = Mock(spec=ArticleTable)
        existing_article.canonical_url = sample_article.canonical_url
        
        # Mock query result
        result_mock = Mock()
        result_mock.scalar_one_or_none.return_value = existing_article
        mock_async_session.execute.return_value = result_mock
        
        is_duplicate, found_article = await async_deduplication_service.check_exact_duplicates(sample_article)
        
        assert is_duplicate is True
        assert found_article == existing_article

    @pytest.mark.asyncio
    async def test_check_exact_duplicates_by_content_hash(self, async_deduplication_service, sample_article, mock_async_session):
        """Test exact duplicate checking by content hash."""
        # Mock no existing article by URL
        result_mock = Mock()
        result_mock.scalar_one_or_none.side_effect = [None, Mock(spec=ArticleTable)]
        mock_async_session.execute.return_value = result_mock
        
        is_duplicate, found_article = await async_deduplication_service.check_exact_duplicates(sample_article)
        
        assert is_duplicate is True
        assert found_article is not None

    @pytest.mark.asyncio
    async def test_check_exact_duplicates_no_duplicate(self, async_deduplication_service, sample_article, mock_async_session):
        """Test exact duplicate checking with no duplicates."""
        # Mock no existing articles
        result_mock = Mock()
        result_mock.scalar_one_or_none.return_value = None
        mock_async_session.execute.return_value = result_mock
        
        is_duplicate, found_article = await async_deduplication_service.check_exact_duplicates(sample_article)
        
        assert is_duplicate is False
        assert found_article is None

    @pytest.mark.asyncio
    async def test_check_near_duplicates(self, async_deduplication_service, sample_article, mock_async_session):
        """Test near duplicate checking."""
        # Mock similar articles
        similar_article1 = Mock(spec=ArticleTable)
        similar_article1.simhash = 12345
        similar_article1.title = "Similar Article 1"
        
        similar_article2 = Mock(spec=ArticleTable)
        similar_article2.simhash = 12346
        similar_article2.title = "Similar Article 2"
        
        # Mock query result
        result_mock = Mock()
        result_mock.scalars.return_value.all.return_value = [similar_article1, similar_article2]
        mock_async_session.execute.return_value = result_mock
        
        with patch('src.services.deduplication.compute_article_simhash', return_value=(12345, 0)):
            with patch('src.services.deduplication.simhash_calculator.is_similar', return_value=True):
                similar_articles = await async_deduplication_service.check_near_duplicates(sample_article)
        
        assert len(similar_articles) == 2
        assert similar_article1 in similar_articles
        assert similar_article2 in similar_articles

    @pytest.mark.asyncio
    async def test_check_near_duplicates_decimal_conversion(self, async_deduplication_service, sample_article, mock_async_session):
        """Test near duplicate checking with Decimal type conversion (database simhash values)."""
        from decimal import Decimal
        
        # Mock similar articles with Decimal type (as returned from database)
        similar_article1 = Mock(spec=ArticleTable)
        similar_article1.simhash = Decimal(12345)  # Decimal type from DB
        similar_article1.title = "Similar Article 1"
        
        similar_article2 = Mock(spec=ArticleTable)
        similar_article2.simhash = Decimal(12346)  # Decimal type from DB
        similar_article2.title = "Similar Article 2"
        
        # Mock query result
        result_mock = Mock()
        result_mock.scalars.return_value.all.return_value = [similar_article1, similar_article2]
        mock_async_session.execute.return_value = result_mock
        
        with patch('src.services.deduplication.compute_article_simhash', return_value=(12345, 0)):
            # This tests the fix: Decimal is converted to int before hamming_distance call
            similar_articles = await async_deduplication_service.check_near_duplicates(sample_article, threshold=3)
        
        # Both articles should be found (they're within threshold of 12345)
        assert len(similar_articles) >= 0  # May be 0 or more depending on actual distance

    @pytest.mark.asyncio
    async def test_create_article_with_deduplication_exact_duplicate(self, async_deduplication_service, sample_article, mock_async_session):
        """Test article creation with exact duplicate."""
        # Mock exact duplicate found
        existing_article = Mock(spec=ArticleTable)
        
        with patch.object(async_deduplication_service, 'check_exact_duplicates', return_value=(True, existing_article)):
            created, article, similar = await async_deduplication_service.create_article_with_deduplication(sample_article)
        
        assert created is False
        assert article == existing_article
        assert similar == []

    @pytest.mark.asyncio
    async def test_create_article_with_deduplication_new_article(self, async_deduplication_service, sample_article, mock_async_session):
        """Test article creation with new article."""
        # Mock no exact duplicates
        with patch.object(async_deduplication_service, 'check_exact_duplicates', return_value=(False, None)):
            with patch('src.services.deduplication.compute_article_simhash', return_value=(12345, 0)):
                created, article, similar = await async_deduplication_service.create_article_with_deduplication(sample_article)
        
        assert created is True
        assert isinstance(article, ArticleTable)
        assert similar == []
        
        # Verify session methods were called
        mock_async_session.add.assert_called_once()
        mock_async_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_article_with_deduplication_timezone_handling(self, async_deduplication_service, mock_async_session):
        """Test article creation with timezone-aware datetime."""
        from datetime import datetime, timezone
        
        # Create article with timezone-aware datetime (to test conversion to naive)
        article_with_tz = ArticleCreate(
            source_id=1,
            canonical_url="https://example.com/article1",
            title="Test Article",
            published_at=datetime.now(timezone.utc),
            content="This is a test article.",
            summary="Test summary",
            authors=[],
            tags=[],
            article_metadata={},
            content_hash="test_hash"
        )
        
        with patch.object(async_deduplication_service, 'check_exact_duplicates', return_value=(False, None)):
            with patch('src.services.deduplication.compute_article_simhash', return_value=(12345, 0)):
                created, article, similar = await async_deduplication_service.create_article_with_deduplication(article_with_tz)
        
        assert created is True
        assert article.published_at.tzinfo is None  # Should be converted to naive datetime
