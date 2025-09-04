"""Modern web scraper with JSON-LD and structured data extraction."""

import asyncio
import re
from typing import List, Optional, Dict, Any, Set
from urllib.parse import urljoin, urlparse
from datetime import datetime
import logging
from bs4 import BeautifulSoup
import extruct

from src.models.article import ArticleCreate
from src.models.source import Source
from src.utils.http import HTTPClient, normalize_url, is_same_domain
from src.utils.content import (
    ContentCleaner, DateExtractor, MetadataExtractor, 
    QualityScorer, validate_content
)

logger = logging.getLogger(__name__)


class URLDiscovery:
    """URL discovery strategies for modern scraping."""
    
    def __init__(self, http_client: HTTPClient):
        self.http_client = http_client
    
    async def discover_urls(self, source: Source) -> List[str]:
        """
        Discover article URLs using configured strategies.
        
        Args:
            source: Source configuration with discovery settings
            
        Returns:
            List of discovered article URLs
        """
        discovered_urls = set()
        
        discovery_config = source.config.discovery
        strategies = discovery_config.get('strategies', []) if isinstance(discovery_config, dict) else []
        
        for strategy in strategies:
            try:
                if 'listing' in strategy:
                    urls = await self._discover_from_listing(strategy['listing'], source)
                    discovered_urls.update(urls)
                
                elif 'sitemap' in strategy:
                    urls = await self._discover_from_sitemap(strategy['sitemap'], source)
                    discovered_urls.update(urls)
                    
            except Exception as e:
                logger.error(f"Discovery strategy failed for {source.name}: {e}")
                continue
        
        # Filter by scope
        filtered_urls = self._filter_by_scope(list(discovered_urls), source)
        
        logger.info(f"Discovered {len(filtered_urls)} URLs for {source.name}")
        return filtered_urls
    
    async def _discover_from_listing(self, config: Dict[str, Any], source: Source) -> List[str]:
        """Discover URLs from listing pages."""
        urls = set()
        
        listing_urls = config.get('urls', []) if isinstance(config, dict) else []
        post_link_selector = config.get('post_link_selector', '') if isinstance(config, dict) else ''
        next_selector = config.get('next_selector', '') if isinstance(config, dict) else ''
        max_pages = config.get('max_pages', 3) if isinstance(config, dict) else 3
        
        if not listing_urls or not post_link_selector:
            return []
        
        for listing_url in listing_urls:
            try:
                page_count = 0
                current_url = listing_url
                
                while current_url and page_count < max_pages:
                    logger.debug(f"Scraping listing page {page_count + 1}: {current_url}")
                    
                    response = await self.http_client.get(current_url, source_id=source.identifier)
                    response.raise_for_status()
                    
                    soup = BeautifulSoup(self.http_client.get_text_with_encoding_fallback(response), 'lxml')
                    
                    # Extract post links
                    post_links = soup.select(post_link_selector)
                    for link in post_links:
                        href = link.get('href')
                        if href:
                            full_url = urljoin(current_url, href)
                            urls.add(normalize_url(full_url))
                    
                    # Find next page
                    current_url = None
                    if next_selector:
                        next_link = soup.select_one(next_selector)
                        if next_link:
                            next_href = next_link.get('href')
                            if next_href:
                                current_url = urljoin(listing_url, next_href)
                    
                    page_count += 1
                    
                    # Respect rate limiting
                    await asyncio.sleep(1)
                    
            except Exception as e:
                logger.error(f"Failed to scrape listing {listing_url}: {e}")
                continue
        
        return list(urls)
    
    async def _discover_from_sitemap(self, config: Dict[str, Any], source: Source) -> List[str]:
        """Discover URLs from sitemap."""
        urls = set()
        
        sitemap_urls = config.get('urls', []) if isinstance(config, dict) else []
        
        for sitemap_url in sitemap_urls:
            try:
                logger.debug(f"Parsing sitemap: {sitemap_url}")
                
                response = await self.http_client.get(sitemap_url, source_id=source.identifier)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'xml')
                
                # Extract URLs from sitemap
                for loc in soup.find_all('loc'):
                    url = loc.get_text().strip()
                    if url:
                        urls.add(normalize_url(url))
                
                # Handle sitemap index files
                for sitemap in soup.find_all('sitemap'):
                    sitemap_loc = sitemap.find('loc')
                    if sitemap_loc:
                        sub_sitemap_url = sitemap_loc.get_text().strip()
                        if sub_sitemap_url:
                            # Recursively parse sub-sitemaps (limit depth)
                            try:
                                sub_response = await self.http_client.get(sub_sitemap_url, source_id=source.identifier)
                                sub_response.raise_for_status()
                                sub_soup = BeautifulSoup(sub_response.text, 'xml')
                                
                                for sub_loc in sub_soup.find_all('loc'):
                                    sub_url = sub_loc.get_text().strip()
                                    if sub_url:
                                        urls.add(normalize_url(sub_url))
                                        
                            except Exception as e:
                                logger.warning(f"Failed to parse sub-sitemap {sub_sitemap_url}: {e}")
                
            except Exception as e:
                logger.error(f"Failed to parse sitemap {sitemap_url}: {e}")
                continue
        
        return list(urls)
    
    def _filter_by_scope(self, urls: List[str], source: Source) -> List[str]:
        """Filter URLs by source scope configuration."""
        filtered = []
        
        scope_config = source.config
        allowed_domains = scope_config.get('allow', []) if isinstance(scope_config, dict) else []
        post_url_patterns = scope_config.get('post_url_regex', []) if isinstance(scope_config, dict) else []
        
        for url in urls:
            try:
                # Check domain allowlist
                if allowed_domains:
                    domain = urlparse(url).netloc.lower()
                    if not any(allowed_domain in domain for allowed_domain in allowed_domains):
                        continue
                
                # Check URL patterns
                if post_url_patterns:
                    if not any(re.match(pattern, url) for pattern in post_url_patterns):
                        continue
                
                filtered.append(url)
                
            except Exception as e:
                logger.debug(f"Error filtering URL {url}: {e}")
                continue
        
        return filtered


class StructuredDataExtractor:
    """Extract structured data from web pages."""
    
    @staticmethod
    def extract_structured_data(html: str, base_url: str) -> Dict[str, Any]:
        """
        Extract all structured data from HTML.
        
        Args:
            html: HTML content
            base_url: Base URL for resolving relative URLs
            
        Returns:
            Dictionary with extracted structured data
        """
        try:
            # Use extruct to extract structured data
            data = extruct.extract(
                html,
                base_url=base_url,
                syntaxes=['json-ld', 'opengraph', 'microdata', 'microformat'],
                uniform=True
            )
            
            return data
            
        except Exception as e:
            logger.warning(f"Failed to extract structured data: {e}")
            return {}
    
    @staticmethod
    def find_article_jsonld(structured_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find Article or BlogPosting JSON-LD data."""
        json_ld_items = structured_data.get('json-ld', [])
        
        for item in json_ld_items:
            if isinstance(item, dict):
                item_type = item.get('@type', '')
                if isinstance(item_type, str):
                    if item_type in ['Article', 'BlogPosting', 'NewsArticle']:
                        return item
                elif isinstance(item_type, list):
                    if any(t in ['Article', 'BlogPosting', 'NewsArticle'] for t in item_type):
                        return item
        
        return None
    
    @staticmethod
    def extract_from_jsonld(jsonld_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract article data from JSON-LD."""
        extracted = {}
        
        # Title
        headline = jsonld_data.get('headline') or jsonld_data.get('name')
        if headline:
            extracted['title'] = headline
        
        # Content
        article_body = jsonld_data.get('articleBody')
        if article_body:
            extracted['content'] = article_body
        
        # Date published
        date_published = jsonld_data.get('datePublished')
        if date_published:
            extracted['published_at'] = DateExtractor.parse_date(date_published)
        
        # Date modified
        date_modified = jsonld_data.get('dateModified')
        if date_modified:
            extracted['modified_at'] = DateExtractor.parse_date(date_modified)
        
        # Authors
        authors = []
        author_data = jsonld_data.get('author', [])
        if not isinstance(author_data, list):
            author_data = [author_data]
        
        for author in author_data:
            if isinstance(author, dict):
                name = author.get('name')
                if name:
                    authors.append(name)
            elif isinstance(author, str):
                authors.append(author)
        
        if authors:
            extracted['authors'] = authors
        
        # Keywords/tags
        keywords = jsonld_data.get('keywords')
        if keywords:
            if isinstance(keywords, str):
                tags = [k.strip() for k in keywords.split(',')]
            elif isinstance(keywords, list):
                tags = [str(k) for k in keywords]
            else:
                tags = [str(keywords)]
            extracted['tags'] = tags
        
        # Description/summary
        description = jsonld_data.get('description')
        if description:
            extracted['summary'] = description
        
        # URL
        url = jsonld_data.get('url') or jsonld_data.get('@id')
        if url:
            extracted['canonical_url'] = url
        
        return extracted


class ModernScraper:
    """Modern web scraper with structured data extraction."""
    
    def __init__(self, http_client: HTTPClient):
        self.http_client = http_client
        self.url_discovery = URLDiscovery(http_client)
        self.structured_extractor = StructuredDataExtractor()
    
    async def scrape_source(self, source: Source) -> List[ArticleCreate]:
        """
        Scrape articles from source using modern techniques.
        
        Args:
            source: Source configuration
            
        Returns:
            List of ArticleCreate objects
        """
        logger.info(f"Starting modern scraping for {source.name}")
        
        # Phase 1: URL Discovery
        urls = await self.url_discovery.discover_urls(source)
        
        if not urls:
            logger.warning(f"No URLs discovered for {source.name}")
            return []
        
        # Phase 2: Article Extraction
        articles = []
        for url in urls[:50]:  # Limit to prevent overwhelming
            try:
                article = await self._extract_article(url, source)
                if article:
                    articles.append(article)
                
                # Rate limiting between articles
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Failed to extract article from {url}: {e}")
                continue
        
        logger.info(f"Extracted {len(articles)} articles from {source.name}")
        return articles
    
    async def _extract_article(self, url: str, source: Source) -> Optional[ArticleCreate]:
        """
        Extract article from URL using structured data and selectors.
        
        Args:
            url: Article URL
            source: Source configuration
            
        Returns:
            ArticleCreate object or None if extraction fails
        """
        try:
            # Fetch page with conditional headers
            response = await self.http_client.get(url, use_conditional=True, source_id=source.identifier)
            
            # Handle 304 Not Modified
            if response.status_code == 304:
                logger.debug(f"Article not modified: {url}")
                return None
            
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(self.http_client.get_text_with_encoding_fallback(response), 'lxml')
            
            # Extract structured data
            structured_data = self.structured_extractor.extract_structured_data(
                self.http_client.get_text_with_encoding_fallback(response), url
            )
            
            # Try JSON-LD extraction first
            article_data = {}
            jsonld_article = self.structured_extractor.find_article_jsonld(structured_data)
            
            if jsonld_article and source.config.extract.get('prefer_jsonld', True):
                article_data = self.structured_extractor.extract_from_jsonld(jsonld_article)
                logger.debug(f"Extracted data from JSON-LD for {url}")
            
            # Fallback to selector-based extraction
            if not article_data.get('title') or not article_data.get('content'):
                selector_data = self._extract_with_selectors(soup, source, url)
                
                # Merge data, preferring JSON-LD when available
                for key, value in selector_data.items():
                    if not article_data.get(key):
                        article_data[key] = value
            
            # Ensure we have required fields
            if not article_data.get('title') or not article_data.get('content'):
                logger.warning(f"Missing required fields for {url}")
                return None
            
            # Validate content
            issues = validate_content(
                article_data['title'],
                article_data['content'],
                url
            )
            
            if issues:
                logger.warning(f"Content validation issues for {url}: {issues}")
                # Continue anyway unless critical issues
            
            # Build article
            article = ArticleCreate(
                source_id=source.id,
                canonical_url=article_data.get('canonical_url', url),
                title=article_data['title'],
                published_at=article_data.get('published_at') or datetime.utcnow(),
                modified_at=article_data.get('modified_at'),
                authors=article_data.get('authors', []),
                tags=article_data.get('tags', []),
                summary=article_data.get('summary'),
                content=article_data['content'],
                metadata={
                    'structured_data': structured_data,
                    'extraction_method': 'modern_scraping',
                    'jsonld_available': bool(jsonld_article),
                    'quality_score': QualityScorer.score_article(
                        article_data['title'],
                        article_data['content'],
                        article_data
                    )
                }
            )
            
            return article
            
        except Exception as e:
            logger.error(f"Failed to extract article from {url}: {e}")
            return None
    
    def _extract_with_selectors(self, soup: BeautifulSoup, source: Source, url: str) -> Dict[str, Any]:
        """Extract article data using configured CSS selectors."""
        data = {}
        extract_config = source.config.extract
        
        # Extract title
        title_selectors = extract_config.get('title_selectors', ['h1']) if isinstance(extract_config, dict) else ['h1']
        title = self._extract_with_selector_list(soup, title_selectors)
        if title:
            data['title'] = ContentCleaner.normalize_whitespace(title)
        
        # Extract publication date
        date_selectors = extract_config.get('date_selectors', []) if isinstance(extract_config, dict) else []
        published_at = None
        for selector in date_selectors:
            date_text = self._extract_with_selector_list(soup, [selector])
            if date_text:
                published_at = DateExtractor.parse_date(date_text)
                if published_at:
                    break
        
        if not published_at:
            # Try to extract from URL
            published_at = DateExtractor.extract_date_from_url(url)
        
        if published_at:
            data['published_at'] = published_at
        
        # Extract content
        body_selectors = extract_config.get('body_selectors', ['article', 'main']) if isinstance(extract_config, dict) else ['article', 'main']
        content_html = None
        for selector in body_selectors:
            content_elem = soup.select_one(selector)
            if content_elem:
                content_html = str(content_elem)
                if len(ContentCleaner.html_to_text(content_html).strip()) > 100:
                    break
        
        if content_html:
            data['content'] = ContentCleaner.clean_html(content_html)
        
        # Extract authors
        author_selectors = extract_config.get('author_selectors', []) if isinstance(extract_config, dict) else []
        if author_selectors:
            authors = []
            for selector in author_selectors:
                author_text = self._extract_with_selector_list(soup, [selector])
                if author_text:
                    authors.append(author_text.strip())
            if authors:
                data['authors'] = authors[:3]  # Limit to 3 authors
        
        # Fallback extractions using utility functions
        if not data.get('authors'):
            data['authors'] = MetadataExtractor.extract_authors(soup)
        
        if not data.get('tags'):
            data['tags'] = MetadataExtractor.extract_tags(soup)
        
        # Extract canonical URL
        canonical_url = MetadataExtractor.extract_canonical_url(soup)
        if canonical_url:
            data['canonical_url'] = canonical_url
        
        # Extract OpenGraph/meta description for summary
        meta_data = MetadataExtractor.extract_meta_tags(soup)
        og_data = MetadataExtractor.extract_opengraph(soup)
        
        if not data.get('summary'):
            summary = (
                og_data.get('description') or 
                meta_data.get('description') or
                meta_data.get('og:description')
            )
            if summary:
                data['summary'] = ContentCleaner.normalize_whitespace(summary)
        
        return data
    
    def _extract_with_selector_list(self, soup: BeautifulSoup, selectors: List[str]) -> Optional[str]:
        """Extract text using list of selectors, trying each until one works."""
        for selector in selectors:
            try:
                # Handle attribute extraction (e.g., "meta[name='author']::attr(content)")
                if '::attr(' in selector:
                    selector_part, attr_part = selector.split('::attr(')
                    attr_name = attr_part.rstrip(')')
                    
                    elem = soup.select_one(selector_part)
                    if elem:
                        value = elem.get(attr_name)
                        if value:
                            return str(value).strip()
                else:
                    # Regular text extraction
                    elem = soup.select_one(selector)
                    if elem:
                        text = elem.get_text(strip=True)
                        if text:
                            return text
                            
            except Exception as e:
                logger.debug(f"Selector '{selector}' failed: {e}")
                continue
        
        return None


class LegacyScraper:
    """Legacy HTML scraper for sources without modern structured data."""
    
    def __init__(self, http_client: HTTPClient):
        self.http_client = http_client
    
    async def scrape_source(self, source: Source) -> List[ArticleCreate]:
        """
        Scrape source using legacy HTML parsing.
        
        Args:
            source: Source configuration
            
        Returns:
            List of ArticleCreate objects
        """
        logger.info(f"Starting legacy scraping for {source.name}")
        
        content_selector = getattr(source.config, 'content_selector', 'article')
        
        try:
            # Fetch main page
            response = await self.http_client.get(source.url, source_id=source.identifier)
            response.raise_for_status()
            
            soup = BeautifulSoup(self.http_client.get_text_with_encoding_fallback(response), 'lxml')
            
            # Extract basic content
            content_elem = soup.select_one(content_selector)
            if not content_elem:
                logger.warning(f"No content found with selector '{content_selector}' for {source.name}")
                return []
            
            # Build basic article
            title = self._extract_title(soup)
            content = ContentCleaner.clean_html(str(content_elem))
            
            if not title or not content:
                logger.warning(f"Missing title or content for {source.name}")
                return []
            
            article = ArticleCreate(
                source_id=source.id,
                canonical_url=source.url,
                title=title,
                published_at=datetime.utcnow(),  # No date available
                content=content,
                metadata={
                    'extraction_method': 'legacy_scraping',
                    'content_selector': content_selector
                }
            )
            
            return [article]
            
        except Exception as e:
            logger.error(f"Legacy scraping failed for {source.name}: {e}")
            return []
    
    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract title from page."""
        # Try different title sources
        title_selectors = ['h1', 'title', 'meta[property="og:title"]']
        
        for selector in title_selectors:
            if selector.startswith('meta'):
                elem = soup.select_one(selector)
                if elem:
                    title = elem.get('content')
                    if title:
                        return ContentCleaner.normalize_whitespace(title)
            else:
                elem = soup.select_one(selector)
                if elem:
                    title = elem.get_text(strip=True)
                    if title:
                        return ContentCleaner.normalize_whitespace(title)
        
        return None
