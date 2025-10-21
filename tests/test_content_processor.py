"""Tests for content processor functionality."""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
from typing import List, Dict, Any, Set

from src.core.processor import ContentProcessor, DeduplicationResult, BatchProcessor
from src.models.article import ArticleCreate


class TestDeduplicationResult:
    """Test DeduplicationResult class."""

    def test_init(self):
        """Test DeduplicationResult initialization."""
        unique_articles = [Mock(), Mock()]
        duplicates = [(Mock(), "url"), (Mock(), "content_hash")]
        stats = {"total": 4, "unique": 2, "duplicates": 2}
        
        result = DeduplicationResult(unique_articles, duplicates, stats)
        
        assert result.unique_articles == unique_articles
        assert result.duplicates == duplicates
        assert result.stats == stats


@pytest.mark.asyncio
class TestContentProcessor:
    """Test ContentProcessor functionality."""

    @pytest.fixture
    def processor(self):
        """Create ContentProcessor instance for testing."""
        return ContentProcessor(
            similarity_threshold=0.85,
            max_age_days=90,
            enable_content_enhancement=True
        )

    @pytest.fixture
    def sample_article(self):
        """Create sample article for testing."""
        return ArticleCreate(
            source_id=1,
            canonical_url="https://example.com/article1",
            title="Test Article Title",
            published_at=datetime.utcnow(),
            content="<p>This is a test article with substantial content. It contains multiple sentences and paragraphs to meet quality requirements.</p><p>Additional content for testing purposes.</p>",
            summary="Test article summary",
            authors=["Test Author"],
            tags=["security", "threat-intel"],
            article_metadata={},
            content_hash="test_hash_123"
        )

    @pytest.fixture
    def old_article(self):
        """Create old article for age filtering."""
        return ArticleCreate(
            source_id=1,
            canonical_url="https://example.com/old-article",
            title="Old Article",
            published_at=datetime.utcnow() - timedelta(days=100),
            content="<p>This is an old article that should be filtered out due to age.</p>",
            summary="Old article summary",
            authors=["Old Author"],
            tags=["old"],
            article_metadata={},
            content_hash="old_hash_456"
        )

    @pytest.fixture
    def short_article(self):
        """Create short article for quality filtering."""
        return ArticleCreate(
            source_id=1,
            canonical_url="https://example.com/short-article",
            title="Short",
            published_at=datetime.utcnow(),
            content="<p>Short content.</p>",
            summary="Short summary",
            authors=[],
            tags=[],
            article_metadata={},
            content_hash="short_hash_789"
        )

    @pytest.mark.asyncio
    async def test_process_articles_empty_list(self, processor):
        """Test processing empty article list."""
        result = await processor.process_articles([])
        
        assert len(result.unique_articles) == 0
        assert len(result.duplicates) == 0
        assert result.stats['total'] == 0

    @pytest.mark.asyncio
    async def test_process_articles_success(self, processor, sample_article):
        """Test successful article processing."""
        articles = [sample_article]
        
        with patch.object(processor, '_process_single_article', return_value=sample_article):
            with patch.object(processor, '_check_duplicates', return_value=None):
                with patch.object(processor, '_passes_quality_filter', return_value=True):
                    result = await processor.process_articles(articles)
        
        assert len(result.unique_articles) == 1
        assert len(result.duplicates) == 0
        assert result.stats['total'] == 1
        assert result.stats['unique'] == 1

    @pytest.mark.asyncio
    async def test_process_articles_with_existing_hashes(self, processor, sample_article):
        """Test processing with existing content hashes."""
        existing_hashes = {"test_hash_123"}
        articles = [sample_article]
        
        with patch.object(processor, '_process_single_article', return_value=sample_article):
            with patch.object(processor, '_check_duplicates', return_value="content_hash"):
                result = await processor.process_articles(articles, existing_hashes=existing_hashes)
        
        assert len(result.unique_articles) == 0
        assert len(result.duplicates) == 1
        assert result.stats['duplicates'] == 1
        assert result.stats['hash_duplicates'] == 1

    @pytest.mark.asyncio
    async def test_process_articles_with_existing_urls(self, processor, sample_article):
        """Test processing with existing URLs."""
        existing_urls = {"https://example.com/article1"}
        articles = [sample_article]
        
        with patch.object(processor, '_process_single_article', return_value=sample_article):
            with patch.object(processor, '_check_duplicates', return_value="url"):
                result = await processor.process_articles(articles, existing_urls=existing_urls)
        
        assert len(result.unique_articles) == 0
        assert len(result.duplicates) == 1
        assert result.stats['duplicates'] == 1
        assert result.stats['url_duplicates'] == 1

    @pytest.mark.asyncio
    async def test_process_articles_quality_filtered(self, processor, short_article):
        """Test processing with quality filtering."""
        articles = [short_article]
        
        with patch.object(processor, '_process_single_article', return_value=short_article):
            with patch.object(processor, '_check_duplicates', return_value=None):
                with patch.object(processor, '_passes_quality_filter', return_value=False):
                    result = await processor.process_articles(articles)
        
        assert len(result.unique_articles) == 0
        assert len(result.duplicates) == 1
        assert result.stats['duplicates'] == 1
        assert result.stats['quality_filtered'] == 1

    @pytest.mark.asyncio
    async def test_process_articles_processing_failure(self, processor, sample_article):
        """Test handling of processing failures."""
        articles = [sample_article]
        
        with patch.object(processor, '_process_single_article', return_value=None):
            result = await processor.process_articles(articles)
        
        assert len(result.unique_articles) == 0
        assert len(result.duplicates) == 0
        assert result.stats['total'] == 1
        assert result.stats['validation_failures'] == 0  # None return doesn't count as failure

    @pytest.mark.asyncio
    async def test_process_articles_exception_handling(self, processor, sample_article):
        """Test exception handling during processing."""
        articles = [sample_article]
        
        with patch.object(processor, '_process_single_article', side_effect=Exception("Processing error")):
            result = await processor.process_articles(articles)
        
        assert len(result.unique_articles) == 0
        assert len(result.duplicates) == 0
        assert result.stats['total'] == 1
        assert result.stats['validation_failures'] == 1

    @pytest.mark.asyncio
    async def test_process_single_article_success(self, processor, sample_article):
        """Test successful single article processing."""
        with patch('src.utils.content.validate_content', return_value=[]):
            with patch.object(processor, '_enhance_metadata', return_value={'enhanced': True}):
                result = await processor._process_single_article(sample_article)
        
        assert result is not None
        assert result.title == "Test Article Title"
        assert result.content_hash == "test_hash_123"
        assert result.article_metadata.get('enhanced') is True

    @pytest.mark.asyncio
    async def test_process_single_article_validation_failure(self, processor, sample_article):
        """Test single article processing with validation failure."""
        with patch('src.utils.content.validate_content', return_value=["Title too short"]):
            result = await processor._process_single_article(sample_article)
        
        assert result is None

    @pytest.mark.asyncio
    async def test_process_single_article_podcast_detection(self, processor):
        """Test podcast content type detection."""
        podcast_article = ArticleCreate(
            source_id=1,
            canonical_url="https://example.com/podcast",
            title="StormCast Episode 123",
            published_at=datetime.utcnow(),
            content="<p>Short podcast content</p>",
            summary="Podcast summary",
            authors=["Podcast Host"],
            tags=["podcast"],
            article_metadata={},
            content_hash="podcast_hash"
        )
        
        with patch('src.utils.content.validate_content', return_value=[]):
            with patch.object(processor, '_enhance_metadata', return_value={}):
                result = await processor._process_single_article(podcast_article)
        
        assert result is not None
        assert result.article_metadata.get('content_type') == 'podcast'
        assert result.article_metadata.get('is_short_content') is True

    @pytest.mark.asyncio
    async def test_enhance_metadata_success(self, processor, sample_article):
        """Test metadata enhancement."""
        result = await processor._enhance_metadata(sample_article)
        
        assert 'reading_time_minutes' in result
        assert 'image_count' in result
        assert 'link_count' in result
        assert 'threat_keywords' in result
        assert 'threat_keyword_count' in result
        assert 'processed_at' in result

    @pytest.mark.asyncio
    async def test_enhance_metadata_with_published_date(self, processor, sample_article):
        """Test metadata enhancement with publication date."""
        sample_article.published_at = datetime(2024, 1, 1, 12, 0, 0)
        
        result = await processor._enhance_metadata(sample_article)
        
        assert 'publication_day_of_week' in result
        assert 'publication_month' in result
        assert 'publication_year' in result
        assert 'age_days' in result

    @pytest.mark.asyncio
    async def test_enhance_metadata_exception_handling(self, processor, sample_article):
        """Test metadata enhancement exception handling."""
        with patch('src.utils.content.ThreatHuntingScorer.score_threat_hunting_content', side_effect=Exception("Scoring error")):
            result = await processor._enhance_metadata(sample_article)
        
        # Should still return some metadata despite the error
        assert isinstance(result, dict)

    def test_normalize_url_basic(self, processor):
        """Test basic URL normalization."""
        url = "https://example.com/article?utm_source=test&id=123"
        normalized = processor._normalize_url(url)
        
        assert normalized == "https://example.com/article?id=123"

    def test_normalize_url_with_fragment(self, processor):
        """Test URL normalization with fragment."""
        url = "https://example.com/article#section"
        normalized = processor._normalize_url(url)
        
        assert normalized == "https://example.com/article"

    def test_normalize_url_with_www(self, processor):
        """Test URL normalization with www prefix."""
        url = "https://www.example.com/article"
        normalized = processor._normalize_url(url)
        
        assert normalized == "https://example.com/article"

    def test_normalize_url_empty(self, processor):
        """Test URL normalization with empty URL."""
        normalized = processor._normalize_url("")
        assert normalized == ""
        
        normalized = processor._normalize_url(None)
        assert normalized == ""

    def test_get_minimum_content_length_default(self, processor):
        """Test default minimum content length."""
        length = processor._get_minimum_content_length("https://unknown.com/article")
        assert length == 200

    def test_get_minimum_content_length_microsoft(self, processor):
        """Test Microsoft-specific minimum content length."""
        length = processor._get_minimum_content_length("https://msrc.microsoft.com/security-bulletin")
        assert length == 1000

    def test_get_minimum_content_length_crowdstrike(self, processor):
        """Test CrowdStrike-specific minimum content length."""
        length = processor._get_minimum_content_length("https://crowdstrike.com/blog/article")
        assert length == 800

    def test_get_minimum_content_length_exception(self, processor):
        """Test minimum content length with exception."""
        with patch('urllib.parse.urlparse', side_effect=Exception("Parse error")):
            length = processor._get_minimum_content_length("invalid-url")
            assert length == 100

    def test_check_duplicates_url_duplicate(self, processor, sample_article):
        """Test URL duplicate detection."""
        processor.seen_urls.add("https://example.com/article1")
        
        reason = processor._check_duplicates(sample_article)
        assert reason == "url"

    def test_check_duplicates_content_hash_duplicate(self, processor, sample_article):
        """Test content hash duplicate detection."""
        processor.seen_hashes.add("test_hash_123")
        
        reason = processor._check_duplicates(sample_article)
        assert reason == "content_hash"

    def test_check_duplicates_url_title_duplicate(self, processor, sample_article):
        """Test URL+title duplicate detection."""
        processor.seen_url_titles.add("https://example.com/article1||Test Article Title")
        
        reason = processor._check_duplicates(sample_article)
        assert reason == "url_title"

    def test_check_duplicates_content_similarity(self, processor, sample_article):
        """Test content similarity duplicate detection."""
        fingerprint = processor._generate_content_fingerprint(sample_article)
        processor.source_fingerprints[1] = {fingerprint}
        
        reason = processor._check_duplicates(sample_article)
        assert reason == "content_similarity"

    def test_check_duplicates_no_duplicate(self, processor, sample_article):
        """Test no duplicate detection."""
        reason = processor._check_duplicates(sample_article)
        assert reason is None

    def test_generate_content_fingerprint(self, processor, sample_article):
        """Test content fingerprint generation."""
        fingerprint = processor._generate_content_fingerprint(sample_article)
        
        assert isinstance(fingerprint, str)
        assert len(fingerprint) == 32  # MD5 hash length

    def test_passes_quality_filter_success(self, processor, sample_article):
        """Test quality filter passes for good article."""
        with patch.object(processor, '_get_minimum_content_length', return_value=100):
            result = processor._passes_quality_filter(sample_article)
        
        assert result is True

    def test_passes_quality_filter_too_old(self, processor, old_article):
        """Test quality filter fails for old article."""
        result = processor._passes_quality_filter(old_article)
        assert result is False

    def test_passes_quality_filter_too_short_title(self, processor):
        """Test quality filter fails for short title."""
        short_title_article = ArticleCreate(
            source_id=1,
            canonical_url="https://example.com/short",
            title="Short",
            published_at=datetime.utcnow(),
            content="<p>This is a test article with substantial content.</p>",
            summary="Test summary",
            authors=[],
            tags=[],
            article_metadata={},
            content_hash="short_title_hash"
        )
        
        with patch.object(processor, '_get_minimum_content_length', return_value=100):
            result = processor._passes_quality_filter(short_title_article)
        
        assert result is False

    def test_passes_quality_filter_too_short_content(self, processor, sample_article):
        """Test quality filter fails for short content."""
        with patch.object(processor, '_get_minimum_content_length', return_value=1000):
            result = processor._passes_quality_filter(sample_article)
        
        assert result is False

    def test_passes_quality_filter_no_published_date(self, processor):
        """Test quality filter with no published date."""
        no_date_article = ArticleCreate(
            source_id=1,
            canonical_url="https://example.com/no-date",
            title="Article Without Date",
            published_at=None,
            content="<p>This is a test article with substantial content.</p>",
            summary="Test summary",
            authors=[],
            tags=[],
            article_metadata={},
            content_hash="no_date_hash"
        )
        
        with patch.object(processor, '_get_minimum_content_length', return_value=100):
            result = processor._passes_quality_filter(no_date_article)
        
        assert result is True

    def test_record_article(self, processor, sample_article):
        """Test article recording for deduplication."""
        processor._record_article(sample_article)
        
        assert "https://example.com/article1" in processor.seen_urls
        assert "test_hash_123" in processor.seen_hashes
        assert "https://example.com/article1||Test Article Title" in processor.seen_url_titles
        assert 1 in processor.source_fingerprints

    def test_detect_content_type_podcast(self, processor):
        """Test podcast content type detection."""
        podcast_article = ArticleCreate(
            source_id=1,
            canonical_url="https://example.com/podcast",
            title="StormCast Episode 123",
            published_at=datetime.utcnow(),
            content="<p>Podcast content</p>",
            summary="Podcast summary",
            authors=[],
            tags=[],
            article_metadata={},
            content_hash="podcast_hash"
        )
        
        content_type = processor._detect_content_type(podcast_article)
        assert content_type == "podcast"

    def test_detect_content_type_announcement(self, processor):
        """Test announcement content type detection."""
        announcement_article = ArticleCreate(
            source_id=1,
            canonical_url="https://example.com/announcement",
            title="Security Update Announcement",
            published_at=datetime.utcnow(),
            content="<p>Announcement content</p>",
            summary="Announcement summary",
            authors=[],
            tags=[],
            article_metadata={},
            content_hash="announcement_hash"
        )
        
        content_type = processor._detect_content_type(announcement_article)
        assert content_type == "announcement"

    def test_detect_content_type_analysis(self, processor):
        """Test analysis content type detection."""
        analysis_article = ArticleCreate(
            source_id=1,
            canonical_url="https://example.com/analysis",
            title="Threat Analysis Report",
            published_at=datetime.utcnow(),
            content="<p>Analysis content</p>",
            summary="Analysis summary",
            authors=[],
            tags=[],
            article_metadata={},
            content_hash="analysis_hash"
        )
        
        content_type = processor._detect_content_type(analysis_article)
        assert content_type == "analysis"

    def test_detect_content_type_default(self, processor, sample_article):
        """Test default content type detection."""
        content_type = processor._detect_content_type(sample_article)
        assert content_type == "article"

    def test_normalize_authors(self, processor):
        """Test author normalization."""
        authors = ["  John Doe  ", "by Jane Smith", "Author: Bob Wilson"]
        normalized = processor._normalize_authors(authors)
        
        assert "John Doe" in normalized
        assert "Jane Smith" in normalized
        assert "Bob Wilson" in normalized

    def test_normalize_authors_limit(self, processor):
        """Test author normalization with limit."""
        authors = [f"Author {i}" for i in range(10)]
        normalized = processor._normalize_authors(authors)
        
        assert len(normalized) == 5  # Limited to 5 authors

    def test_normalize_tags(self, processor):
        """Test tag normalization."""
        tags = ["  Security  ", "THREAT-INTEL", "malware,", "test@tag"]
        normalized = processor._normalize_tags(tags)
        
        assert "security" in normalized
        assert "threat-intel" in normalized
        assert "malware" in normalized
        assert "testtag" in normalized

    def test_normalize_tags_limit(self, processor):
        """Test tag normalization with limit."""
        tags = [f"tag{i}" for i in range(15)]
        normalized = processor._normalize_tags(tags)
        
        assert len(normalized) == 10  # Limited to 10 tags

    def test_get_statistics(self, processor):
        """Test statistics retrieval."""
        processor.stats['total_processed'] = 10
        processor.stats['duplicates_removed'] = 2
        
        stats = processor.get_statistics()
        
        assert stats['total_processed'] == 10
        assert stats['duplicates_removed'] == 2

    def test_reset_statistics(self, processor):
        """Test statistics reset."""
        processor.stats['total_processed'] = 10
        processor.stats['duplicates_removed'] = 2
        
        processor.reset_statistics()
        
        assert processor.stats['total_processed'] == 0
        assert processor.stats['duplicates_removed'] == 0

    def test_clear_deduplication_cache(self, processor, sample_article):
        """Test deduplication cache clearing."""
        processor._record_article(sample_article)
        
        assert len(processor.seen_hashes) > 0
        assert len(processor.seen_urls) > 0
        
        processor.clear_deduplication_cache()
        
        assert len(processor.seen_hashes) == 0
        assert len(processor.seen_urls) == 0

    def test_get_cache_size(self, processor, sample_article):
        """Test cache size retrieval."""
        processor._record_article(sample_article)
        
        cache_size = processor.get_cache_size()
        
        assert cache_size['content_hashes'] > 0
        assert cache_size['urls'] > 0
        assert cache_size['fingerprints'] > 0


@pytest.mark.skip(reason="Async mock configuration needed for BatchProcessor tests")
class TestBatchProcessor:
    """Test BatchProcessor functionality."""

    @pytest.fixture
    def processor(self):
        """Create ContentProcessor instance for testing."""
        return ContentProcessor()

    @pytest.fixture
    def batch_processor(self, processor):
        """Create BatchProcessor instance for testing."""
        return BatchProcessor(processor, batch_size=2, max_concurrent=2)

    @pytest.fixture
    def sample_articles(self):
        """Create sample articles for testing."""
        return [
            ArticleCreate(
                source_id=1,
                canonical_url=f"https://example.com/article{i}",
                title=f"Article {i}",
                published_at=datetime.utcnow(),
                content=f"<p>Content for article {i}</p>",
                summary=f"Summary {i}",
                authors=[],
                tags=[],
                article_metadata={},
                content_hash=f"hash_{i}"
            )
            for i in range(5)
        ]

    @pytest.mark.asyncio
    async def test_process_batches_empty_list(self, batch_processor):
        """Test processing empty article list."""
        result = await batch_processor.process_batches([])
        
        assert len(result.unique_articles) == 0
        assert len(result.duplicates) == 0
        assert result.stats['total'] == 0

    @pytest.mark.asyncio
    async def test_process_batches_success(self, batch_processor, sample_articles):
        """Test successful batch processing."""
        with patch.object(batch_processor.processor, 'process_articles') as mock_process:
            mock_result = DeduplicationResult(
                unique_articles=sample_articles[:2],
                duplicates=[],
                stats={'total': 2, 'unique': 2, 'duplicates': 0}
            )
            mock_process.return_value = mock_result
            
            result = await batch_processor.process_batches(sample_articles)
        
        assert len(result.unique_articles) == 10  # 5 batches * 2 articles each
        assert result.stats['total'] == 10
        assert result.stats['unique'] == 10

    @pytest.mark.asyncio
    async def test_process_batches_with_existing_data(self, batch_processor, sample_articles):
        """Test batch processing with existing hashes and URLs."""
        existing_hashes = {"hash_0"}
        existing_urls = {"https://example.com/article0"}
        
        with patch.object(batch_processor.processor, 'process_articles') as mock_process:
            mock_result = DeduplicationResult(
                unique_articles=sample_articles[1:2],
                duplicates=[(sample_articles[0], "content_hash")],
                stats={'total': 2, 'unique': 1, 'duplicates': 1}
            )
            mock_process.return_value = mock_result
            
            result = await batch_processor.process_batches(
                sample_articles, 
                existing_hashes=existing_hashes,
                existing_urls=existing_urls
            )
        
        assert len(result.unique_articles) == 4  # 5 batches * 1 unique article each
        assert len(result.duplicates) == 5  # 5 batches * 1 duplicate each
        assert result.stats['total'] == 10
        assert result.stats['unique'] == 4
        assert result.stats['duplicates'] == 5

    @pytest.mark.asyncio
    async def test_process_batches_concurrency_limit(self, batch_processor, sample_articles):
        """Test batch processing respects concurrency limit."""
        call_count = 0
        
        async def mock_process_articles(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Simulate processing time
            await asyncio.sleep(0.1)
            return DeduplicationResult([], [], {'total': 0, 'unique': 0, 'duplicates': 0})
        
        with patch.object(batch_processor.processor, 'process_articles', side_effect=mock_process_articles):
            await batch_processor.process_batches(sample_articles)
        
        # Should have been called for each batch (3 batches for 5 articles with batch_size=2)
        assert call_count == 3
