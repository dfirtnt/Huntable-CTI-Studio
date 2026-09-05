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
        return AsyncMockHTTPClient()

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


class TestHuntersLedgerDiscoveryShape:
    """Pin the config semantics the hunters_ledger stanza relies on (2026-09-02).

    The detections index links omit the trailing slash, the index itself must be excluded
    by the ``[href!=...]`` selector, and the widened ``post_url_regex`` must accept the
    no-slash detections URL while rejecting the bare index and off-domain links.
    """

    _REGEX = [
        "^https://the-hunters-ledger\\.com/reports/.+",
        "^https://the-hunters-ledger\\.com/hunting-detections/.+",
    ]
    _SELECTOR = 'a[href^="/hunting-detections/"][href!="/hunting-detections/"]'
    _INDEX_HTML = (
        "<html><body><nav><a href='/hunting-detections/'>Detection Library</a><a href='/reports/'>Reports</a></nav>"
        "<main>"
        "<a href='/hunting-detections/PULSAR-RAT-detections'>PULSAR RAT</a>"
        "<a href='/hunting-detections/agent-exe-detections'>agent.exe</a>"
        "<a href='/hunting-detections/'>All detections</a>"
        "<a href='https://hunt.io'>Sponsor</a>"
        "</main></body></html>"
    )

    def _source(self):
        return create_test_source(
            id=42,
            identifier="hunters_ledger",
            name="The Hunter's Ledger",
            url="https://the-hunters-ledger.com/",
            rss_url="https://the-hunters-ledger.com/feed.xml",
            active=True,
            config={
                "allow": ["the-hunters-ledger.com"],
                "post_url_regex": list(self._REGEX),
                "discovery": {
                    "strategies": [
                        {
                            "listing": {
                                "urls": ["https://the-hunters-ledger.com/hunting-detections/"],
                                "max_pages": 1,
                                "post_link_selector": self._SELECTOR,
                            }
                        }
                    ]
                },
            },
        )

    def test_scope_regex_accepts_detections_pages_and_rejects_index(self):
        discovery = URLDiscovery(Mock(spec=HTTPClient))
        urls = [
            "https://the-hunters-ledger.com/hunting-detections/PULSAR-RAT-detections",  # no trailing slash
            "https://the-hunters-ledger.com/hunting-detections/agent-exe-detections/",  # with slash
            "https://the-hunters-ledger.com/reports/cloudsync-assembler-toolkit/",
            "https://the-hunters-ledger.com/hunting-detections/",  # the index itself
            "https://the-hunters-ledger.com/wire/",
            "https://hunt.io/hunting-detections/x",
        ]
        kept = discovery._filter_by_scope(urls, self._source())
        assert kept == [
            "https://the-hunters-ledger.com/hunting-detections/PULSAR-RAT-detections",
            "https://the-hunters-ledger.com/hunting-detections/agent-exe-detections/",
            "https://the-hunters-ledger.com/reports/cloudsync-assembler-toolkit/",
        ]

    def test_listing_selector_excludes_the_index_link(self):
        """soupsieve supports the non-standard ``[attr!=value]``; the index link must not match."""
        from bs4 import BeautifulSoup

        hrefs = [a["href"] for a in BeautifulSoup(self._INDEX_HTML, "lxml").select(self._SELECTOR)]
        assert hrefs == ["/hunting-detections/PULSAR-RAT-detections", "/hunting-detections/agent-exe-detections"]

    @pytest.mark.asyncio
    async def test_listing_discovery_yields_absolute_detections_urls_only(self):
        client = Mock(spec=HTTPClient)
        response = create_async_mock_response(text=self._INDEX_HTML, status_code=200)
        response.raise_for_status = Mock()
        client.get = AsyncMock(return_value=response)
        discovery = URLDiscovery(client)

        with patch("src.core.modern_scraper.asyncio.sleep", new=AsyncMock()):
            urls = await discovery.discover_urls(self._source())

        assert sorted(urls) == [
            "https://the-hunters-ledger.com/hunting-detections/PULSAR-RAT-detections",
            "https://the-hunters-ledger.com/hunting-detections/agent-exe-detections",
        ]
        client.get.assert_awaited_once()


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


class TestStructuredDataExtractorDateFallback:
    """Tests for the datePublished extraction path used by PlaywrightScraper's JSON-LD fallback.

    These tests cover the three-method chain:
      extract_structured_data -> find_article_jsonld -> extract_from_jsonld
    as it is called in playwright_scraper.py when CSS selectors fail to find a date.
    """

    # ------------------------------------------------------------------
    # extract_structured_data
    # ------------------------------------------------------------------

    def test_extract_blogposting_with_date_published(self):
        """BlogPosting block with datePublished is parsed and date is accessible."""
        html = """
        <html>
          <head>
            <script type="application/ld+json">
            {
              "@context": "https://schema.org",
              "@type": "BlogPosting",
              "headline": "Threat Intel Post",
              "datePublished": "2025-03-15T09:00:00Z"
            }
            </script>
          </head>
          <body>content</body>
        </html>
        """
        structured = StructuredDataExtractor.extract_structured_data(html, "https://blog.example.com")
        article = StructuredDataExtractor.find_article_jsonld(structured)
        extracted = StructuredDataExtractor.extract_from_jsonld(article)

        assert article is not None
        assert article["@type"] == "BlogPosting"
        assert "published_at" in extracted
        assert extracted["published_at"] is not None

    def test_extract_structured_data_no_jsonld_returns_empty_list(self):
        """HTML with no JSON-LD script blocks returns an empty json-ld list, not None."""
        html = "<html><head><title>No structured data here</title></head><body></body></html>"
        structured = StructuredDataExtractor.extract_structured_data(html, "https://example.com")

        assert isinstance(structured, dict)
        assert structured.get("json-ld", []) == []

    def test_find_article_jsonld_on_empty_structured_data_returns_none(self):
        """find_article_jsonld gracefully returns None when json-ld list is empty."""
        structured = {"json-ld": []}
        result = StructuredDataExtractor.find_article_jsonld(structured)
        assert result is None

    # ------------------------------------------------------------------
    # @type matching
    # ------------------------------------------------------------------

    def test_find_article_jsonld_matches_article_type(self):
        """@type 'Article' is recognised as an article block."""
        structured = {"json-ld": [{"@type": "Article", "headline": "A", "datePublished": "2025-01-01"}]}
        article = StructuredDataExtractor.find_article_jsonld(structured)
        assert article is not None
        assert article["@type"] == "Article"

    def test_find_article_jsonld_matches_newsarticle_type(self):
        """@type 'NewsArticle' is recognised as an article block."""
        structured = {"json-ld": [{"@type": "NewsArticle", "headline": "B", "datePublished": "2025-02-01"}]}
        article = StructuredDataExtractor.find_article_jsonld(structured)
        assert article is not None
        assert article["@type"] == "NewsArticle"

    def test_find_article_jsonld_matches_blogposting_type(self):
        """@type 'BlogPosting' is recognised as an article block."""
        structured = {"json-ld": [{"@type": "BlogPosting", "headline": "C", "datePublished": "2025-03-01"}]}
        article = StructuredDataExtractor.find_article_jsonld(structured)
        assert article is not None
        assert article["@type"] == "BlogPosting"

    def test_find_article_jsonld_matches_list_type_containing_newsarticle(self):
        """@type as a list that includes 'NewsArticle' is still matched."""
        structured = {"json-ld": [{"@type": ["Thing", "NewsArticle"], "headline": "D"}]}
        article = StructuredDataExtractor.find_article_jsonld(structured)
        assert article is not None

    def test_find_article_jsonld_matches_techarticle_type(self):
        """@type 'TechArticle' (common on security-research sites) is recognised as an article block."""
        structured = {"json-ld": [{"@type": "TechArticle", "headline": "E", "datePublished": "2025-04-01"}]}
        article = StructuredDataExtractor.find_article_jsonld(structured)
        assert article is not None
        assert article["@type"] == "TechArticle"

    @pytest.mark.parametrize("item_type", ["ScholarlyArticle", "Report"])
    def test_find_article_jsonld_matches_other_article_types(self, item_type):
        structured = {"json-ld": [{"@type": item_type, "headline": "F"}]}
        assert StructuredDataExtractor.find_article_jsonld(structured) is not None

    # ------------------------------------------------------------------
    # multi-block preference (The Hunter's Ledger shape, 2026-09-02)
    # ------------------------------------------------------------------

    def test_find_article_jsonld_prefers_block_with_author(self):
        """BlogPosting without author followed by TechArticle with author -> the TechArticle wins."""
        structured = {
            "json-ld": [
                {"@type": "BlogPosting", "headline": "CloudSync Assembler Toolkit", "datePublished": "2026-09-01"},
                {
                    "@type": "TechArticle",
                    "headline": "CloudSync Assembler Toolkit",
                    "author": {"@type": "Person", "name": "Joseph Harrison"},
                },
            ]
        }
        article = StructuredDataExtractor.find_article_jsonld(structured)
        assert article is not None
        assert article["@type"] == "TechArticle"
        assert StructuredDataExtractor.extract_from_jsonld(article)["authors"] == ["Joseph Harrison"]

    def test_find_article_jsonld_author_preference_is_order_independent(self):
        """The authored block wins even when it comes first."""
        structured = {
            "json-ld": [
                {"@type": "TechArticle", "headline": "X", "author": "Jane Analyst"},
                {"@type": "BlogPosting", "headline": "X", "articleBody": "body"},
            ]
        }
        assert StructuredDataExtractor.find_article_jsonld(structured)["@type"] == "TechArticle"

    def test_find_article_jsonld_prefers_article_body_when_no_author(self):
        structured = {
            "json-ld": [
                {"@type": "BlogPosting", "headline": "Y"},
                {"@type": "Article", "headline": "Y", "articleBody": "full text"},
            ]
        }
        assert StructuredDataExtractor.find_article_jsonld(structured)["@type"] == "Article"

    def test_find_article_jsonld_falls_back_to_document_order(self):
        """No author and no body anywhere -> first article-typed block, as before."""
        structured = {
            "json-ld": [
                {"@type": "Person", "name": "Someone"},
                {"@type": "BlogPosting", "headline": "first"},
                {"@type": "NewsArticle", "headline": "second"},
            ]
        }
        assert StructuredDataExtractor.find_article_jsonld(structured)["headline"] == "first"

    @pytest.mark.parametrize("empty_author", [[], {}, "", {"@type": "Person"}, [{"@type": "Organization"}]])
    def test_find_article_jsonld_empty_author_does_not_count(self, empty_author):
        """An author field with no usable name must not outrank a block that has one."""
        structured = {
            "json-ld": [
                {"@type": "BlogPosting", "headline": "Z", "author": empty_author},
                {"@type": "TechArticle", "headline": "Z", "author": {"name": "Real Author"}},
            ]
        }
        assert StructuredDataExtractor.find_article_jsonld(structured)["@type"] == "TechArticle"

    def test_find_article_jsonld_single_block_without_author_unchanged(self):
        """Single-block pages behave exactly as before: the lone article block is returned."""
        structured = {"json-ld": [{"@type": "BlogPosting", "headline": "solo"}, {"@type": "WebPage"}]}
        article = StructuredDataExtractor.find_article_jsonld(structured)
        assert article is not None
        assert article["headline"] == "solo"

    # ------------------------------------------------------------------
    # extract_from_jsonld date field logic
    # ------------------------------------------------------------------

    def test_extract_from_jsonld_date_published_is_parsed(self):
        """datePublished string is converted to a datetime object in published_at."""
        from datetime import datetime

        jsonld_data = {
            "@type": "Article",
            "headline": "Dated Article",
            "datePublished": "2025-06-01T14:30:00Z",
        }
        extracted = StructuredDataExtractor.extract_from_jsonld(jsonld_data)

        assert "published_at" in extracted
        assert isinstance(extracted["published_at"], datetime)
        assert extracted["published_at"].year == 2025

    def test_extract_from_jsonld_missing_date_published_yields_no_published_at(self):
        """When datePublished is absent but dateModified is present, published_at is not set."""
        jsonld_data = {
            "@type": "Article",
            "headline": "Modified But Not Published",
            "dateModified": "2025-05-10T00:00:00Z",
        }
        extracted = StructuredDataExtractor.extract_from_jsonld(jsonld_data)

        assert "published_at" not in extracted
        # dateModified should still be extracted as modified_at
        assert "modified_at" in extracted

    def test_extract_from_jsonld_no_dates_at_all_yields_no_published_at(self):
        """JSON-LD block with no date fields produces no published_at key."""
        jsonld_data = {"@type": "BlogPosting", "headline": "No Dates"}
        extracted = StructuredDataExtractor.extract_from_jsonld(jsonld_data)
        assert "published_at" not in extracted

    # ------------------------------------------------------------------
    # Malformed JSON resilience
    # ------------------------------------------------------------------

    def test_malformed_jsonld_script_does_not_crash_extraction(self):
        """A script tag with broken JSON is silently skipped; valid blocks still parse."""
        html = """
        <html>
          <head>
            <script type="application/ld+json">{ this is not valid json }</script>
            <script type="application/ld+json">
            {"@type": "Article", "headline": "Valid", "datePublished": "2025-01-15"}
            </script>
          </head>
        </html>
        """
        structured = StructuredDataExtractor.extract_structured_data(html, "https://example.com")

        # Only the valid block should be present
        assert len(structured["json-ld"]) == 1
        assert structured["json-ld"][0]["headline"] == "Valid"

    def test_completely_empty_script_tag_does_not_crash(self):
        """An empty ld+json script tag is handled without raising."""
        html = '<html><head><script type="application/ld+json"></script></head></html>'
        structured = StructuredDataExtractor.extract_structured_data(html, "https://example.com")
        assert structured.get("json-ld", []) == []

    # ------------------------------------------------------------------
    # End-to-end: full three-method chain
    # ------------------------------------------------------------------

    def test_full_chain_blogposting_with_date_published(self):
        """Full chain: HTML -> extract_structured_data -> find_article_jsonld -> extract_from_jsonld returns date."""
        from datetime import datetime

        html = """
        <html>
          <head>
            <script type="application/ld+json">
            {
              "@context": "https://schema.org",
              "@type": "BlogPosting",
              "headline": "Red Team Tactics 2025",
              "datePublished": "2025-04-01T08:00:00Z",
              "author": {"@type": "Person", "name": "Analyst One"}
            }
            </script>
          </head>
          <body>Article body here.</body>
        </html>
        """
        structured = StructuredDataExtractor.extract_structured_data(html, "https://blog.example.com")
        article = StructuredDataExtractor.find_article_jsonld(structured)
        assert article is not None

        extracted = StructuredDataExtractor.extract_from_jsonld(article)
        assert "published_at" in extracted
        assert isinstance(extracted["published_at"], datetime)
        assert extracted["title"] == "Red Team Tactics 2025"

    def test_full_chain_no_jsonld_returns_none_article(self):
        """Full chain: HTML with no JSON-LD -> find_article_jsonld returns None (no crash)."""
        html = "<html><body><p>Plain page, no structured data.</p></body></html>"
        structured = StructuredDataExtractor.extract_structured_data(html, "https://example.com")
        article = StructuredDataExtractor.find_article_jsonld(structured)
        assert article is None


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

        with (
            patch.object(
                modern_scraper.structured_extractor, "extract_structured_data", return_value={"json-ld": [jsonld_data]}
            ),
            patch.object(modern_scraper.structured_extractor, "find_article_jsonld", return_value=jsonld_data),
        ):
            with patch.object(
                modern_scraper.structured_extractor,
                "extract_from_jsonld",
                return_value={"title": "JSON-LD Article", "content": "JSON-LD content"},
            ):
                with patch("src.utils.content.validate_content", return_value=[]):  # Empty list = no validation issues
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


class TestExtractArticleCarriesMetadata:
    """``_extract_article`` must not drop authors/tags/summary it extracted (2026-09-02).

    Before the fix the ArticleCreate was built without them, so every discovery-path
    article on every source was stored with ``authors == []``.
    """

    _BODY = "Detection engineering write-up body text. " * 12

    @staticmethod
    def _scraper_with(html):
        client = Mock(spec=HTTPClient)
        client.configure_source_robots = Mock()
        response = create_async_mock_response(text=html, status_code=200)
        response.raise_for_status = Mock()
        client.get = AsyncMock(return_value=response)
        return ModernScraper(client)

    @staticmethod
    def _source(author_selectors):
        return create_test_source(
            id=42,
            identifier="hunters_ledger",
            name="The Hunter's Ledger",
            url="https://the-hunters-ledger.com/",
            rss_url=None,
            active=True,
            config={
                "extract": {
                    "prefer_jsonld": True,
                    "title_selectors": ["h1"],
                    "body_selectors": ["article"],
                    "author_selectors": author_selectors,
                }
            },
        )

    @pytest.mark.asyncio
    async def test_jsonld_author_tags_and_summary_reach_article_create(self):
        html = f"""<html><head>
        <script type="application/ld+json">{{"@type":"BlogPosting","headline":"CloudSync Report"}}</script>
        <script type="application/ld+json">{{"@type":"TechArticle","headline":"CloudSync Report",
          "author":{{"@type":"Person","name":"Joseph Harrison"}},"keywords":"cloudsync, rat",
          "description":"An intrusion tool write-up","datePublished":"2026-08-02T20:00:00Z",
          "url":"https://the-hunters-ledger.com/reports/cloudsync/"}}</script>
        </head><body><h1>CloudSync Report</h1><article>{self._BODY}</article></body></html>"""
        scraper = self._scraper_with(html)

        article = await scraper._extract_article("https://the-hunters-ledger.com/reports/cloudsync", self._source([]))

        assert article is not None
        assert article.authors == ["Joseph Harrison"]
        assert article.tags == ["cloudsync", "rat"]
        assert article.summary == "An intrusion tool write-up"
        assert article.canonical_url == "https://the-hunters-ledger.com/reports/cloudsync/"

    @pytest.mark.asyncio
    async def test_selector_fallback_author_when_jsonld_has_none(self):
        """Detections pages: JSON-LD BlogPosting without author -> og:site_name selector fallback."""
        html = f"""<html><head>
        <meta property="og:site_name" content="The Hunter's Ledger">
        <script type="application/ld+json">{{"@type":"BlogPosting","headline":"Detection Rules: PULSAR RAT",
          "url":"https://the-hunters-ledger.com/hunting-detections/PULSAR-RAT-detections/"}}</script>
        </head><body><h1>Detection Rules: PULSAR RAT</h1><article>{self._BODY}</article></body></html>"""
        scraper = self._scraper_with(html)
        source = self._source(["meta[name='author']::attr(content)", "meta[property='og:site_name']::attr(content)"])

        article = await scraper._extract_article(
            "https://the-hunters-ledger.com/hunting-detections/PULSAR-RAT-detections", source
        )

        assert article is not None
        assert article.authors == ["The Hunter's Ledger"]
        # Canonical comes from JSON-LD with the trailing slash even though discovery had none.
        assert article.canonical_url == "https://the-hunters-ledger.com/hunting-detections/PULSAR-RAT-detections/"

    @pytest.mark.asyncio
    async def test_no_author_anywhere_stays_empty_list(self):
        html = f"<html><body><h1>Plain Page</h1><article>{self._BODY}</article></body></html>"
        scraper = self._scraper_with(html)

        article = await scraper._extract_article("https://example.com/plain", self._source([]))

        assert article is not None
        assert article.authors == []
        assert article.tags == []


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
