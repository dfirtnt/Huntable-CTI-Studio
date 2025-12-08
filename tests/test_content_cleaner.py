"""Tests for content cleaner functionality."""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock, patch, AsyncMock
from typing import List, Dict, Any, Optional

from src.utils.content import ContentCleaner, ContentExtractor, TextNormalizer


class TestContentCleaner:
    """Test ContentCleaner functionality."""

    @pytest.fixture
    def content_cleaner(self):
        """Create ContentCleaner instance for testing."""
        return ContentCleaner()

    def test_init(self, content_cleaner):
        """Test ContentCleaner initialization."""
        assert content_cleaner is not None
        assert hasattr(content_cleaner, 'clean_html')
        assert hasattr(content_cleaner, 'enhanced_html_clean')
        assert hasattr(content_cleaner, 'html_to_text')

    def test_clean_html_basic(self, content_cleaner):
        """Test basic HTML cleaning."""
        html = """
        <html>
            <head><title>Test Page</title></head>
            <body>
                <h1>Main Title</h1>
                <p>This is a paragraph with <strong>bold text</strong>.</p>
                <div>Some content in a div.</div>
            </body>
        </html>
        """
        
        cleaned = content_cleaner.clean_html(html)
        
        assert isinstance(cleaned, str)
        assert "Main Title" in cleaned
        assert "This is a paragraph with bold text" in cleaned
        assert "Some content in a div" in cleaned
        assert "<html>" not in cleaned
        assert "<head>" not in cleaned
        assert "<body>" not in cleaned

    def test_clean_html_with_scripts(self, content_cleaner):
        """Test HTML cleaning with scripts and styles."""
        html = """
        <html>
            <head>
                <script>alert('xss');</script>
                <style>body { color: red; }</style>
            </head>
            <body>
                <h1>Content</h1>
                <p>This is the actual content.</p>
                <script>console.log('test');</script>
            </body>
        </html>
        """
        
        cleaned = content_cleaner.clean_html(html)
        
        assert "Content" in cleaned
        assert "This is the actual content" in cleaned
        assert "alert('xss')" not in cleaned
        assert "console.log('test')" not in cleaned
        assert "body { color: red; }" not in cleaned

    def test_clean_html_with_navigation(self, content_cleaner):
        """Test HTML cleaning with navigation elements."""
        html = """
        <html>
            <body>
                <nav>
                    <ul>
                        <li><a href="/home">Home</a></li>
                        <li><a href="/about">About</a></li>
                    </ul>
                </nav>
                <header>
                    <h1>Site Title</h1>
                </header>
                <main>
                    <article>
                        <h2>Article Title</h2>
                        <p>This is the main article content.</p>
                    </article>
                </main>
                <footer>
                    <p>Copyright 2024</p>
                </footer>
            </body>
        </html>
        """
        
        cleaned = content_cleaner.clean_html(html)
        
        assert "Article Title" in cleaned
        assert "This is the main article content" in cleaned
        assert "Home" not in cleaned
        assert "About" not in cleaned
        assert "Site Title" not in cleaned
        assert "Copyright 2024" not in cleaned

    def test_clean_html_with_ads(self, content_cleaner):
        """Test HTML cleaning with advertisement elements."""
        html = """
        <html>
            <body>
                <div class="advertisement">
                    <p>Buy our product!</p>
                </div>
                <div class="banner">
                    <p>Special offer!</p>
                </div>
                <article>
                    <h1>Real Content</h1>
                    <p>This is the actual article content.</p>
                </article>
                <div class="popup">
                    <p>Click here!</p>
                </div>
            </body>
        </html>
        """
        
        cleaned = content_cleaner.clean_html(html)
        
        assert "Real Content" in cleaned
        assert "This is the actual article content" in cleaned
        assert "Buy our product!" not in cleaned
        assert "Special offer!" not in cleaned
        assert "Click here!" not in cleaned

    def test_clean_html_with_comments(self, content_cleaner):
        """Test HTML cleaning with comments and social elements."""
        html = """
        <html>
            <body>
                <div class="comments">
                    <p>User comment 1</p>
                    <p>User comment 2</p>
                </div>
                <div class="social">
                    <a href="#">Share on Facebook</a>
                    <a href="#">Tweet this</a>
                </div>
                <article>
                    <h1>Article Content</h1>
                    <p>This is the main article.</p>
                </article>
                <div class="related">
                    <p>Related articles</p>
                </div>
            </body>
        </html>
        """
        
        cleaned = content_cleaner.clean_html(html)
        
        assert "Article Content" in cleaned
        assert "This is the main article" in cleaned
        assert "User comment 1" not in cleaned
        assert "User comment 2" not in cleaned
        assert "Share on Facebook" not in cleaned
        assert "Tweet this" not in cleaned
        assert "Related articles" not in cleaned

    def test_enhanced_html_clean(self, content_cleaner):
        """Test enhanced HTML cleaning."""
        html = """
        <html>
            <body>
                <div class="sidebar">
                    <p>Sidebar content</p>
                </div>
                <div class="widget">
                    <p>Widget content</p>
                </div>
                <main>
                    <article>
                        <h1>Main Article</h1>
                        <p>This is the main content of the article.</p>
                        <p>Another paragraph with more content.</p>
                    </article>
                </main>
                <div class="promo">
                    <p>Promotional content</p>
                </div>
            </body>
        </html>
        """
        
        cleaned = content_cleaner.enhanced_html_clean(html)
        
        assert "Main Article" in cleaned
        assert "This is the main content of the article" in cleaned
        assert "Another paragraph with more content" in cleaned
        assert "Sidebar content" not in cleaned
        assert "Widget content" not in cleaned
        assert "Promotional content" not in cleaned

    def test_html_to_text(self, content_cleaner):
        """Test HTML to text conversion."""
        html = """
        <html>
            <body>
                <h1>Article Title</h1>
                <p>This is a paragraph with <strong>bold text</strong> and <em>italic text</em>.</p>
                <ul>
                    <li>List item 1</li>
                    <li>List item 2</li>
                </ul>
                <p>Another paragraph with <a href="https://example.com">a link</a>.</p>
            </body>
        </html>
        """
        
        text = content_cleaner.html_to_text(html)
        
        assert "Article Title" in text
        assert "This is a paragraph with bold text and italic text" in text
        assert "List item 1" in text
        assert "List item 2" in text
        assert "Another paragraph with a link" in text
        assert "<h1>" not in text
        assert "<p>" not in text
        assert "<strong>" not in text
        assert "<em>" not in text

    def test_clean_html_empty_input(self, content_cleaner):
        """Test HTML cleaning with empty input."""
        # Empty string
        result = content_cleaner.clean_html("")
        assert result == ""

        # None input
        result = content_cleaner.clean_html(None)
        assert result == ""

        # Whitespace only
        result = content_cleaner.clean_html("   \n\t   ")
        assert result.strip() == ""

    def test_clean_html_malformed_html(self, content_cleaner):
        """Test HTML cleaning with malformed HTML."""
        malformed_html = """
        <html>
            <body>
                <h1>Unclosed tag
                <p>This is a paragraph</p>
                <div>Unclosed div
                <p>Another paragraph</p>
            </body>
        </html>
        """
        
        cleaned = content_cleaner.clean_html(malformed_html)
        
        assert "Unclosed tag" in cleaned
        assert "This is a paragraph" in cleaned
        assert "Another paragraph" in cleaned

    def test_clean_html_with_tables(self, content_cleaner):
        """Test HTML cleaning with tables."""
        html = """
        <html>
            <body>
                <table>
                    <thead>
                        <tr>
                            <th>Header 1</th>
                            <th>Header 2</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td>Cell 1</td>
                            <td>Cell 2</td>
                        </tr>
                    </tbody>
                </table>
                <p>Content after table</p>
            </body>
        </html>
        """
        
        cleaned = content_cleaner.clean_html(html)
        
        assert "Header 1" in cleaned
        assert "Header 2" in cleaned
        assert "Cell 1" in cleaned
        assert "Cell 2" in cleaned
        assert "Content after table" in cleaned

    def test_clean_html_with_forms(self, content_cleaner):
        """Test HTML cleaning with forms."""
        html = """
        <html>
            <body>
                <form>
                    <input type="text" name="username" placeholder="Username">
                    <input type="password" name="password" placeholder="Password">
                    <button type="submit">Submit</button>
                </form>
                <p>Content after form</p>
            </body>
        </html>
        """
        
        cleaned = content_cleaner.clean_html(html)
        
        assert "Content after form" in cleaned
        assert "Username" not in cleaned
        assert "Password" not in cleaned
        assert "Submit" not in cleaned

    def test_clean_html_performance(self, content_cleaner):
        """Test HTML cleaning performance."""
        import time
        
        # Create large HTML document
        html = """
        <html>
            <body>
                <h1>Large Document</h1>
        """
        
        for i in range(1000):
            html += f"<p>Paragraph {i} with some content.</p>"
        
        html += """
            </body>
        </html>
        """
        
        start_time = time.time()
        cleaned = content_cleaner.clean_html(html)
        end_time = time.time()
        
        processing_time = end_time - start_time
        
        # Should process large HTML in reasonable time
        assert processing_time < 1.0  # Less than 1 second
        assert processing_time > 0.0
        assert len(cleaned) > 0


class TestContentExtractor:
    """Test ContentExtractor functionality."""

    @pytest.fixture
    def content_extractor(self):
        """Create ContentExtractor instance for testing."""
        return ContentExtractor()

    def test_init(self, content_extractor):
        """Test ContentExtractor initialization."""
        assert content_extractor is not None
        assert hasattr(content_extractor, 'extract_title')
        assert hasattr(content_extractor, 'extract_meta_description')
        assert hasattr(content_extractor, 'extract_keywords')

    def test_extract_title(self, content_extractor):
        """Test title extraction."""
        html = """
        <html>
            <head>
                <title>Page Title</title>
            </head>
            <body>
                <h1>Main Heading</h1>
                <p>Content</p>
            </body>
        </html>
        """
        
        title = content_extractor.extract_title(html)
        
        assert title == "Page Title"

    def test_extract_title_from_h1(self, content_extractor):
        """Test title extraction from h1 when title tag is missing."""
        html = """
        <html>
            <head>
            </head>
            <body>
                <h1>Main Heading</h1>
                <p>Content</p>
            </body>
        </html>
        """
        
        title = content_extractor.extract_title(html)
        
        assert title == "Main Heading"

    def test_extract_meta_description(self, content_extractor):
        """Test meta description extraction."""
        html = """
        <html>
            <head>
                <meta name="description" content="This is a meta description">
            </head>
            <body>
                <p>Content</p>
            </body>
        </html>
        """
        
        description = content_extractor.extract_meta_description(html)
        
        assert description == "This is a meta description"

    def test_extract_keywords(self, content_extractor):
        """Test keywords extraction."""
        html = """
        <html>
            <head>
                <meta name="keywords" content="keyword1, keyword2, keyword3">
            </head>
            <body>
                <p>Content</p>
            </body>
        </html>
        """
        
        keywords = content_extractor.extract_keywords(html)
        
        assert keywords == ["keyword1", "keyword2", "keyword3"]

    def test_extract_author(self, content_extractor):
        """Test author extraction."""
        html = """
        <html>
            <head>
                <meta name="author" content="John Doe">
            </head>
            <body>
                <p>Content</p>
            </body>
        </html>
        """
        
        author = content_extractor.extract_author(html)
        
        assert author == "John Doe"

    def test_extract_published_date(self, content_extractor):
        """Test published date extraction."""
        html = """
        <html>
            <head>
                <meta name="article:published_time" content="2024-01-15T10:30:00Z">
            </head>
            <body>
                <p>Content</p>
            </body>
        </html>
        """
        
        date = content_extractor.extract_published_date(html)
        
        assert date == "2024-01-15T10:30:00Z"

    def test_extract_canonical_url(self, content_extractor):
        """Test canonical URL extraction."""
        html = """
        <html>
            <head>
                <link rel="canonical" href="https://example.com/canonical-url">
            </head>
            <body>
                <p>Content</p>
            </body>
        </html>
        """
        
        url = content_extractor.extract_canonical_url(html)
        
        assert url == "https://example.com/canonical-url"

    def test_extract_all_metadata(self, content_extractor):
        """Test extracting all metadata at once."""
        html = """
        <html>
            <head>
                <title>Article Title</title>
                <meta name="description" content="Article description">
                <meta name="keywords" content="keyword1, keyword2">
                <meta name="author" content="John Doe">
                <meta name="article:published_time" content="2024-01-15T10:30:00Z">
                <link rel="canonical" href="https://example.com/article">
            </head>
            <body>
                <p>Content</p>
            </body>
        </html>
        """
        
        metadata = content_extractor.extract_all_metadata(html)
        
        assert metadata['title'] == "Article Title"
        assert metadata['description'] == "Article description"
        assert metadata['keywords'] == ["keyword1", "keyword2"]
        assert metadata['author'] == "John Doe"
        assert metadata['published_date'] == "2024-01-15T10:30:00Z"
        assert metadata['canonical_url'] == "https://example.com/article"


class TestTextNormalizer:
    """Test TextNormalizer functionality."""

    @pytest.fixture
    def text_normalizer(self):
        """Create TextNormalizer instance for testing."""
        return TextNormalizer()

    def test_init(self, text_normalizer):
        """Test TextNormalizer initialization."""
        assert text_normalizer is not None
        assert hasattr(text_normalizer, 'normalize_whitespace')
        assert hasattr(text_normalizer, 'normalize_unicode')
        assert hasattr(text_normalizer, 'normalize_case')

    def test_normalize_whitespace(self, text_normalizer):
        """Test whitespace normalization."""
        text = "This   has    multiple    spaces   and\n\nnewlines\t\tand\ttabs."
        
        normalized = text_normalizer.normalize_whitespace(text)
        
        assert normalized == "This has multiple spaces and newlines and tabs."

    def test_normalize_unicode(self, text_normalizer):
        """Test Unicode normalization."""
        text = "Café naïve résumé"
        
        normalized = text_normalizer.normalize_unicode(text)
        
        assert normalized == "Cafe naive resume"

    def test_normalize_case(self, text_normalizer):
        """Test case normalization."""
        text = "This Is A Mixed Case String"
        
        normalized = text_normalizer.normalize_case(text)
        
        assert normalized == "this is a mixed case string"

    def test_remove_special_characters(self, text_normalizer):
        """Test removal of special characters."""
        text = "This has @#$%^&*() special characters!"
        
        cleaned = text_normalizer.remove_special_characters(text)
        
        assert cleaned == "This has special characters"

    def test_normalize_text_comprehensive(self, text_normalizer):
        """Test comprehensive text normalization."""
        text = "  This   is   a   MIXED   case   text   with   special   chars   @#$%   and   unicode   café   naïve  "
        
        normalized = text_normalizer.normalize_text(text)
        
        assert normalized == "this is a mixed case text with special chars and unicode cafe naive"

    def test_normalize_text_empty_input(self, text_normalizer):
        """Test text normalization with empty input."""
        # Empty string
        result = text_normalizer.normalize_text("")
        assert result == ""

        # None input
        result = text_normalizer.normalize_text(None)
        assert result == ""

        # Whitespace only
        result = text_normalizer.normalize_text("   \n\t   ")
        assert result == ""

    def test_normalize_text_performance(self, text_normalizer):
        """Test text normalization performance."""
        import time
        
        # Create large text
        text = "This is a test text. " * 1000
        
        start_time = time.time()
        normalized = text_normalizer.normalize_text(text)
        end_time = time.time()
        
        processing_time = end_time - start_time
        
        # Should process large text in reasonable time
        assert processing_time < 1.0  # Less than 1 second
        assert processing_time > 0.0
        assert len(normalized) > 0
