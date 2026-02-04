"""Tests for modern scraper functionality.

These are unit tests using mocks - no real infrastructure required.
"""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.core.modern_scraper import LegacyScraper, ModernScraper, StructuredDataExtractor, URLDiscovery
from src.models.article import ArticleCreate
from src.models.source import Source
from src.utils.http import HTTPClient
from tests.utils.async_mocks import AsyncMockHTTPClient, create_async_mock_response

# Mark all tests in this file as unit tests (use mocks, no real infrastructure)
pytestmark = pytest.mark.unit


def create_test_source(**kwargs) -> Source:
    """Helper to create a Source with all required fields."""
    now = datetime.now()
    defaults = {
        "check_frequency": 3600,
        "lookback_days": 180,
        "consecutive_failures": 0,
        "total_articles": 0,
        "average_response_time": 0.0,
        "created_at": now,
        "updated_at": now,
        "config": {},
    }
    defaults.update(kwargs)
    return Source(**defaults)


@pytest.mark.asyncio
class TestURLDiscovery:
    """Test URLDiscovery functionality."""

    @pytest.fixture
    def mock_http_client(self):
        """Create mock HTTP client."""
        client = AsyncMockHTTPClient()
        return client

    @pytest.fixture
    def url_discovery(self, mock_http_client):
        """Create URLDiscovery instance."""
        return URLDiscovery(mock_http_client)

    @pytest.fixture
    def sample_source(self):
        """Create sample source for testing."""
        return create_test_source(
            id=1,
            identifier="test-source",
            name="Test Source",
            url="https://example.com",
            rss_url="https://example.com/feed.xml",
            active=True,
            config={
                "discovery": {
                    "strategies": [
                        {
                            "listing": {
                                "urls": ["https://example.com/articles"],  # Note: 'urls' (plural), not 'url'
                                "post_link_selector": "a.article-link",  # Note: 'post_link_selector', not 'selectors'
                            }
                        }
                    ]
                }
            },
        )

    @pytest.mark.asyncio
    async def test_discover_urls_listing_strategy(self, url_discovery, sample_source, mock_http_client):
        """Test URL discovery using listing strategy."""
        # Mock HTTP response
        html_content = """
        <html>
            <body>
                <a href="/article1" class="article-link">Article 1</a>
                <a href="/article2" class="article-link">Article 2</a>
                <a href="/other" class="other-link">Other Link</a>
            </body>
        </html>
        """
        mock_response = create_async_mock_response(text=html_content)
        mock_http_client.get.return_value = mock_response

        urls = await url_discovery.discover_urls(sample_source)

        assert len(urls) == 2
        assert "https://example.com/article1" in urls
        assert "https://example.com/article2" in urls
        assert "https://example.com/other" not in urls

    @pytest.mark.asyncio
    async def test_discover_urls_sitemap_strategy(self, url_discovery, mock_http_client):
        """Test URL discovery using sitemap strategy."""
        source = create_test_source(
            id=1,
            identifier="test-source",
            name="Test Source",
            url="https://example.com",
            rss_url="https://example.com/feed.xml",
            active=True,
            config={
                "discovery": {
                    "strategies": [
                        {
                            "sitemap": {
                                "urls": ["https://example.com/sitemap.xml"]  # Note: 'urls' (plural), not 'url'
                            }
                        }
                    ]
                }
            },
        )

        # Mock sitemap response
        sitemap_xml = """
        <?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url>
                <loc>https://example.com/article1</loc>
                <lastmod>2024-01-01</lastmod>
            </url>
            <url>
                <loc>https://example.com/article2</loc>
                <lastmod>2024-01-02</lastmod>
            </url>
        </urlset>
        """
        mock_response = create_async_mock_response(text=sitemap_xml)
        mock_http_client.get.return_value = mock_response

        urls = await url_discovery.discover_urls(source)

        assert len(urls) == 2
        assert "https://example.com/article1" in urls
        assert "https://example.com/article2" in urls

    @pytest.mark.asyncio
    async def test_discover_urls_no_strategies(self, url_discovery, mock_http_client):
        """Test URL discovery with no strategies configured."""
        source = create_test_source(
            id=1,
            identifier="test-source",
            name="Test Source",
            url="https://example.com",
            rss_url="https://example.com/feed.xml",
            active=True,
        )

        urls = await url_discovery.discover_urls(source)

        assert urls == []

    @pytest.mark.asyncio
    async def test_discover_urls_strategy_failure(self, url_discovery, sample_source, mock_http_client):
        """Test URL discovery with strategy failure."""
        # Mock HTTP error
        mock_http_client.get = AsyncMock(side_effect=Exception("HTTP Error"))

        urls = await url_discovery.discover_urls(sample_source)

        assert urls == []

    @pytest.mark.asyncio
    async def test_discover_urls_scope_filtering(self, url_discovery, mock_http_client):
        """Test URL discovery with scope filtering."""
        source = create_test_source(
            id=1,
            identifier="test-source",
            name="Test Source",
            url="https://example.com",
            rss_url="https://example.com/feed.xml",
            active=True,
            config={
                "discovery": {
                    "strategies": [{"listing": {"urls": ["https://example.com/articles"], "post_link_selector": "a"}}]
                },
                # Scope filtering uses post_url_regex at top level
                "post_url_regex": ["^https://example\\.com/article/"],
            },
        )

        # Mock HTTP response
        html_content = """
        <html>
            <body>
                <a href="/article/1">Article 1</a>
                <a href="/article/2">Article 2</a>
                <a href="/admin/panel">Admin Panel</a>
                <a href="/login">Login</a>
                <a href="/other">Other</a>
            </body>
        </html>
        """
        mock_response = create_async_mock_response(text=html_content)
        mock_http_client.get.return_value = mock_response

        urls = await url_discovery.discover_urls(source)

        assert len(urls) == 2
        assert "https://example.com/article/1" in urls
        assert "https://example.com/article/2" in urls
        assert "https://example.com/admin/panel" not in urls
        assert "https://example.com/login" not in urls
        assert "https://example.com/other" not in urls


class TestStructuredDataExtractor:
    """Test StructuredDataExtractor functionality."""

    def test_extract_structured_data_basic(self):
        """Test basic structured data extraction."""
        html = """
        <html>
            <head>
                <script type="application/ld+json">
                {
                    "@context": "https://schema.org",
                    "@type": "Article",
                    "headline": "Test Article",
                    "author": {"@type": "Person", "name": "Test Author"},
                    "datePublished": "2024-01-01T12:00:00Z"
                }
                </script>
            </head>
            <body>Content</body>
        </html>
        """

        data = StructuredDataExtractor.extract_structured_data(html, "https://example.com")

        assert "json-ld" in data
        assert len(data["json-ld"]) == 1
        assert data["json-ld"][0]["@type"] == "Article"
        assert data["json-ld"][0]["headline"] == "Test Article"

    def test_extract_structured_data_multiple_jsonld(self):
        """Test extraction with multiple JSON-LD scripts."""
        html = """
        <html>
            <head>
                <script type="application/ld+json">
                {"@type": "Article", "headline": "Article 1"}
                </script>
                <script type="application/ld+json">
                {"@type": "Person", "name": "Author"}
                </script>
            </head>
            <body>Content</body>
        </html>
        """

        data = StructuredDataExtractor.extract_structured_data(html, "https://example.com")

        assert len(data["json-ld"]) == 2
        assert data["json-ld"][0]["@type"] == "Article"
        assert data["json-ld"][1]["@type"] == "Person"

    def test_extract_structured_data_invalid_json(self):
        """Test extraction with invalid JSON-LD."""
        html = """
        <html>
            <head>
                <script type="application/ld+json">
                {"@type": "Article", "headline": "Test Article"
                </script>
            </head>
            <body>Content</body>
        </html>
        """

        data = StructuredDataExtractor.extract_structured_data(html, "https://example.com")

        assert len(data["json-ld"]) == 0

    def test_extract_structured_data_no_jsonld(self):
        """Test extraction with no JSON-LD."""
        html = """
        <html>
            <head>
                <title>Test Page</title>
            </head>
            <body>Content</body>
        </html>
        """

        data = StructuredDataExtractor.extract_structured_data(html, "https://example.com")

        assert len(data["json-ld"]) == 0

    def test_find_article_jsonld(self):
        """Test finding article JSON-LD."""
        structured_data = {
            "json-ld": [
                {"@type": "Article", "headline": "Test Article"},
                {"@type": "Person", "name": "Author"},
                {"@type": "WebPage", "name": "Page"},
            ]
        }

        article = StructuredDataExtractor.find_article_jsonld(structured_data)

        assert article is not None
        assert article["@type"] == "Article"
        assert article["headline"] == "Test Article"

    def test_find_article_jsonld_no_article(self):
        """Test finding article JSON-LD when none exists."""
        structured_data = {"json-ld": [{"@type": "Person", "name": "Author"}, {"@type": "WebPage", "name": "Page"}]}

        article = StructuredDataExtractor.find_article_jsonld(structured_data)

        assert article is None

    def test_extract_from_jsonld(self):
        """Test extraction from JSON-LD data."""
        jsonld_data = {
            "@type": "Article",
            "headline": "Test Article",
            "author": {"@type": "Person", "name": "Test Author"},
            "datePublished": "2024-01-01T12:00:00Z",
            "articleBody": "This is the article content.",
            "url": "https://example.com/article",
        }

        extracted = StructuredDataExtractor.extract_from_jsonld(jsonld_data)

        assert extracted["title"] == "Test Article"
        assert extracted["authors"] == ["Test Author"]
        assert extracted["content"] == "This is the article content."
        assert extracted["canonical_url"] == "https://example.com/article"

    def test_extract_from_jsonld_minimal(self):
        """Test extraction from minimal JSON-LD data."""
        jsonld_data = {"@type": "Article", "headline": "Test Article"}

        extracted = StructuredDataExtractor.extract_from_jsonld(jsonld_data)

        assert extracted["title"] == "Test Article"
        # Authors key may not exist if no authors found
        assert extracted.get("authors", []) == []
        # Content and canonical_url may not exist if not in JSON-LD
        assert extracted.get("content", "") == ""
        assert extracted.get("canonical_url", "") == ""


class TestModernScraper:
    """Test ModernScraper functionality."""

    @pytest.fixture
    def mock_http_client(self):
        """Create mock HTTP client."""
        client = Mock(spec=HTTPClient)
        client.get = AsyncMock()
        client.configure_source_robots = Mock()
        client.get_text_with_encoding_fallback = Mock(return_value="<html>Test content</html>")
        return client

    @pytest.fixture
    def modern_scraper(self, mock_http_client):
        """Create ModernScraper instance."""
        return ModernScraper(mock_http_client)

    @pytest.fixture
    def sample_source(self):
        """Create sample source for testing."""
        return create_test_source(
            id=1,
            identifier="test-source",
            name="Test Source",
            url="https://example.com",
            rss_url="https://example.com/feed.xml",
            active=True,
            config={
                "discovery": {
                    "strategies": [
                        {"listing": {"url": "https://example.com/articles", "selectors": ["a.article-link"]}}
                    ]
                },
                "extract": {"title_selectors": ["h1"], "body_selectors": ["article", "main"], "prefer_jsonld": True},
            },
        )

    @pytest.mark.asyncio
    async def test_scrape_source_success(self, modern_scraper, sample_source, mock_http_client):
        """Test successful source scraping."""
        # Mock URL discovery
        with patch.object(modern_scraper.url_discovery, "discover_urls", return_value=["https://example.com/article1"]):
            # Mock article extraction
            with patch.object(modern_scraper, "_extract_article", return_value=Mock(spec=ArticleCreate)):
                articles = await modern_scraper.scrape_source(sample_source)

        assert len(articles) == 1

    @pytest.mark.asyncio
    async def test_scrape_source_no_urls(self, modern_scraper, sample_source, mock_http_client):
        """Test scraping with no discovered URLs."""
        with patch.object(modern_scraper.url_discovery, "discover_urls", return_value=[]):
            articles = await modern_scraper.scrape_source(sample_source)

        assert articles == []

    @pytest.mark.asyncio
    async def test_scrape_source_extraction_failure(self, modern_scraper, sample_source, mock_http_client):
        """Test scraping with article extraction failure."""
        with patch.object(modern_scraper.url_discovery, "discover_urls", return_value=["https://example.com/article1"]):
            with patch.object(modern_scraper, "_extract_article", return_value=None):
                articles = await modern_scraper.scrape_source(sample_source)

        assert articles == []

    @pytest.mark.asyncio
    async def test_extract_article_success(self, modern_scraper, sample_source, mock_http_client):
        """Test successful article extraction."""
        # Mock HTTP response with text content
        html_content = "<html><body><h1>Test Article</h1><article>This is test content.</article></body></html>"
        mock_response = create_async_mock_response(text=html_content, status_code=200)
        mock_response.raise_for_status = AsyncMock()
        mock_http_client.get.return_value = mock_response

        # Mock structured data extraction
        with patch.object(modern_scraper.structured_extractor, "extract_structured_data", return_value={"json-ld": []}):
            with patch.object(modern_scraper.structured_extractor, "find_article_jsonld", return_value=None):
                with patch.object(
                    modern_scraper,
                    "_extract_with_selectors",
                    return_value={
                        "title": "Test Article",
                        "content": "This is test content.",
                        "published_at": datetime.now(),
                    },
                ):
                    with patch("src.utils.content.validate_content", return_value=True):
                        article = await modern_scraper._extract_article("https://example.com/article", sample_source)

        assert article is not None
        assert article.title == "Test Article"
        assert article.content == "This is test content."

    @pytest.mark.asyncio
    async def test_extract_article_not_modified(self, modern_scraper, sample_source, mock_http_client):
        """Test article extraction with 304 Not Modified."""
        # Mock HTTP response
        mock_response = create_async_mock_response(status_code=304)
        mock_http_client.get.return_value = mock_response

        article = await modern_scraper._extract_article("https://example.com/article", sample_source)

        assert article is None

    @pytest.mark.asyncio
    async def test_extract_article_http_error(self, modern_scraper, sample_source, mock_http_client):
        """Test article extraction with HTTP error."""
        # Mock HTTP error
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = Exception("HTTP Error")
        mock_http_client.get.return_value = mock_response

        article = await modern_scraper._extract_article("https://example.com/article", sample_source)

        assert article is None

    @pytest.mark.asyncio
    async def test_extract_article_jsonld_preference(self, modern_scraper, sample_source, mock_http_client):
        """Test article extraction with JSON-LD preference."""
        # Mock HTTP response with text content
        html_content = '<html><head><script type="application/ld+json">{"@type":"Article","headline":"JSON-LD Article","articleBody":"JSON-LD content"}</script></head><body></body></html>'
        mock_response = create_async_mock_response(text=html_content, status_code=200)
        mock_response.raise_for_status = AsyncMock()
        mock_http_client.get.return_value = mock_response

        # Mock JSON-LD data
        jsonld_data = {"@type": "Article", "headline": "JSON-LD Article", "articleBody": "JSON-LD content"}

        with patch.object(
            modern_scraper.structured_extractor, "extract_structured_data", return_value={"json-ld": [jsonld_data]}
        ):
            with patch.object(modern_scraper.structured_extractor, "find_article_jsonld", return_value=jsonld_data):
                with patch.object(
                    modern_scraper.structured_extractor,
                    "extract_from_jsonld",
                    return_value={"title": "JSON-LD Article", "content": "JSON-LD content"},
                ):
                    with patch(
                        "src.utils.content.validate_content", return_value=[]
                    ):  # Empty list = no validation issues
                        article = await modern_scraper._extract_article("https://example.com/article", sample_source)

        assert article is not None
        assert article.title == "JSON-LD Article"
        assert article.content == "JSON-LD content"

    def test_extract_with_selectors_basic(self, modern_scraper, sample_source):
        """Test selector-based extraction."""
        from bs4 import BeautifulSoup

        html = (
            """
        <html>
            <head>
                <title>Test Page</title>
                <meta name="author" content="Test Author">
            </head>
            <body>
                <h1>Test Article Title</h1>
                <article>
                    <p>This is the article content. """
            + "More content. " * 20
            + """</p>
                </article>
            </body>
        </html>
        """
        )

        soup = BeautifulSoup(html, "html.parser")

        with patch("src.utils.content.DateExtractor.parse_date", return_value=datetime.now()):
            with patch("src.utils.content.MetadataExtractor.extract_authors", return_value=["Test Author"]):
                with patch("src.utils.content.MetadataExtractor.extract_tags", return_value=["test"]):
                    with patch(
                        "src.utils.content.MetadataExtractor.extract_canonical_url",
                        return_value="https://example.com/article",
                    ):
                        with patch(
                            "src.utils.content.MetadataExtractor.extract_meta_tags",
                            return_value={"description": "Test description"},
                        ):
                            with patch("src.utils.content.MetadataExtractor.extract_opengraph", return_value={}):
                                data = modern_scraper._extract_with_selectors(
                                    soup, sample_source, "https://example.com/article"
                                )

        assert data["title"] == "Test Article Title"
        assert "This is the article content." in data["content"]
        assert data["authors"] == ["Test Author"]
        assert data["tags"] == ["test"]
        assert data["canonical_url"] == "https://example.com/article"
        assert data["summary"] == "Test description"

    def test_extract_with_selector_list_success(self, modern_scraper):
        """Test selector list extraction success."""
        from bs4 import BeautifulSoup

        html = """
        <html>
            <body>
                <h1>Main Title</h1>
                <h2>Secondary Title</h2>
            </body>
        </html>
        """

        soup = BeautifulSoup(html, "html.parser")
        selectors = ["h1", "h2", "h3"]

        result = modern_scraper._extract_with_selector_list(soup, selectors)

        assert result == "Main Title"

    def test_extract_with_selector_list_attr_extraction(self, modern_scraper):
        """Test selector list with attribute extraction."""
        from bs4 import BeautifulSoup

        html = """
        <html>
            <head>
                <meta name="author" content="Test Author">
            </head>
        </html>
        """

        soup = BeautifulSoup(html, "html.parser")
        selectors = ["meta[name='author']::attr(content)"]

        result = modern_scraper._extract_with_selector_list(soup, selectors)

        assert result == "Test Author"

    def test_extract_with_selector_list_failure(self, modern_scraper):
        """Test selector list extraction failure."""
        from bs4 import BeautifulSoup

        html = """
        <html>
            <body>
                <p>Some content</p>
            </body>
        </html>
        """

        soup = BeautifulSoup(html, "html.parser")
        selectors = ["h1", "h2", "h3"]

        result = modern_scraper._extract_with_selector_list(soup, selectors)

        assert result is None


class TestLegacyScraper:
    """Test LegacyScraper functionality."""

    @pytest.fixture
    def mock_http_client(self):
        """Create mock HTTP client."""
        client = Mock(spec=HTTPClient)
        client.get = AsyncMock()
        client.configure_source_robots = Mock()
        client.get_text_with_encoding_fallback = Mock(return_value="<html>Test content</html>")
        return client

    @pytest.fixture
    def legacy_scraper(self, mock_http_client):
        """Create LegacyScraper instance."""
        return LegacyScraper(mock_http_client)

    @pytest.fixture
    def sample_source(self):
        """Create sample source for testing."""
        return create_test_source(
            id=1,
            identifier="test-source",
            name="Test Source",
            url="https://example.com",
            rss_url="https://example.com/feed.xml",
            active=True,
            config={"content_selector": "article"},
        )

    @pytest.mark.asyncio
    async def test_scrape_source_success(self, legacy_scraper, sample_source, mock_http_client):
        """Test successful legacy scraping."""
        # Mock HTTP response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_http_client.get.return_value = mock_response

        with patch("src.utils.content.validate_content", return_value=[]):
            articles = await legacy_scraper.scrape_source(sample_source)

        assert isinstance(articles, list)

    @pytest.mark.asyncio
    async def test_scrape_source_http_error(self, legacy_scraper, sample_source, mock_http_client):
        """Test legacy scraping with HTTP error."""
        # Mock HTTP error
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = Exception("HTTP Error")
        mock_http_client.get.return_value = mock_response

        articles = await legacy_scraper.scrape_source(sample_source)

        assert articles == []
