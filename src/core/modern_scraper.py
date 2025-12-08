"""Web scraper with basic JSON-LD parsing and CSS selector extraction."""

import asyncio
import re
from typing import List, Optional, Dict, Any, Set
from urllib.parse import urljoin, urlparse
from datetime import datetime
import logging
from bs4 import BeautifulSoup

from src.models.article import ArticleCreate
from src.models.source import Source
from src.utils.http import HTTPClient, normalize_url, is_same_domain
from src.utils.content import (
    ContentCleaner, DateExtractor, MetadataExtractor, 
    validate_content
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
        
        discovery_config = source.config.get('discovery') if isinstance(source.config, dict) else getattr(source.config, 'discovery', None)
        strategies = discovery_config.get('strategies', []) if isinstance(discovery_config, dict) else []
        
        # If no discovery strategies configured, use fallback: scrape base URL for links
        if not strategies:
            logger.debug(f"No discovery strategies configured for {source.name}, using fallback: scraping base URL")
            urls = await self._discover_from_base_url(source)
            discovered_urls.update(urls)
        else:
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
                    
                    soup = BeautifulSoup(response.text, 'lxml')
                    
                    # Extract post links
                    post_links = soup.select(post_link_selector)
                    for link in post_links:
                        href = link.get('href')
                        if href:
                            full_url = urljoin(current_url, href)
                            urls.add(normalize_url(full_url))
                    
                    # Find next page - prefer "Next" link, fallback to next page number
                    current_url = None
                    if next_selector:
                        # Try to find "Next" link first
                        next_links = soup.select(next_selector)
                        for link in next_links:
                            link_text = link.get_text().strip().lower()
                            next_href = link.get('href')
                            if next_href and ('next' in link_text or link_text.isdigit()):
                                # Make sure it's not the current page
                                current_page_match = re.search(r'[?&]p=(\d+)', current_url or listing_url)
                                next_page_match = re.search(r'[?&]p=(\d+)', next_href)
                                if next_page_match:
                                    next_page_num = int(next_page_match.group(1))
                                    if not current_page_match or next_page_num > int(current_page_match.group(1)):
                                        current_url = urljoin(current_url or listing_url, next_href)
                                        break
                                elif 'next' in link_text:
                                    # "Next" link found, use it
                                    current_url = urljoin(current_url or listing_url, next_href)
                                    break
                        
                        # If no next link found, try to increment page number
                        if not current_url:
                            current_page_match = re.search(r'[?&]p=(\d+)', current_url or listing_url)
                            if current_page_match:
                                current_page = int(current_page_match.group(1))
                                next_page = current_page + 1
                                base_url = re.sub(r'[?&]p=\d+', '', current_url or listing_url)
                                separator = '&' if '?' in base_url else '?'
                                current_url = f"{base_url}{separator}p={next_page}"
                    
                    page_count += 1
                    
                    # Respect rate limiting
                    await asyncio.sleep(1)
                    
            except Exception as e:
                logger.error(f"Failed to scrape listing {listing_url}: {e}")
                continue
        
        return list(urls)
    
    async def _discover_from_base_url(self, source: Source) -> List[str]:
        """Fallback: Discover URLs by scraping the source's base URL for links matching post_url_regex."""
        urls = set()
        
        try:
            logger.debug(f"Scraping base URL for {source.name}: {source.url}")
            
            response = await self.http_client.get(source.url, source_id=source.identifier)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'lxml')
            
            # Get post_url_regex patterns from config
            post_url_regex = source.config.get('post_url_regex', []) if isinstance(source.config, dict) else []
            if not post_url_regex:
                logger.warning(f"No post_url_regex configured for {source.name}, cannot filter URLs")
                return []
            
            # Compile regex patterns
            patterns = [re.compile(pattern) for pattern in post_url_regex]
            
            # Find all links
            links = soup.find_all('a', href=True)
            for link in links:
                href = link.get('href')
                if href:
                    # Resolve relative URLs
                    full_url = urljoin(source.url, href)
                    normalized_url = normalize_url(full_url)
                    
                    # Check if URL matches any pattern
                    for pattern in patterns:
                        if pattern.match(normalized_url):
                            urls.add(normalized_url)
                            break
            
            logger.info(f"Discovered {len(urls)} URLs from base URL for {source.name}")
            
        except Exception as e:
            logger.error(f"Failed to discover URLs from base URL for {source.name}: {e}")
        
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
                
                # Extract URLs from sitemap (handle namespaces)
                # BeautifulSoup's XML parser should handle namespaces, but try multiple approaches
                discovered_count = 0
                
                # Try standard find_all first
                for loc in soup.find_all('loc'):
                    url = loc.get_text().strip()
                    if url:
                        urls.add(normalize_url(url))
                        discovered_count += 1
                
                # If no URLs found, try namespace-aware search
                if discovered_count == 0:
                    logger.debug(f"No URLs found with find_all('loc'), trying namespace-aware parsing for {sitemap_url}")
                    # Try with explicit namespace
                    for loc in soup.find_all('loc', recursive=True):
                        url = loc.get_text().strip()
                        if url:
                            urls.add(normalize_url(url))
                            discovered_count += 1
                
                # If still no URLs, try regex-based extraction as fallback
                if discovered_count == 0:
                    logger.debug(f"No URLs found with BeautifulSoup, trying regex fallback for {sitemap_url}")
                    logger.debug(f"Response text length: {len(response.text)}, first 500 chars: {response.text[:500]}")
                    import re
                    loc_pattern = r'<loc>(.*?)</loc>'
                    matches = re.findall(loc_pattern, response.text)
                    logger.debug(f"Regex found {len(matches)} matches")
                    for url in matches:
                        url = url.strip()
                        if url:
                            urls.add(normalize_url(url))
                            discovered_count += 1
                
                logger.debug(f"Discovered {len(urls)} URLs from sitemap {sitemap_url}")
                
                # Log a sample of discovered URLs for debugging
                if urls:
                    sample_urls = list(urls)[:5]
                    logger.info(f"Sample URLs from sitemap {sitemap_url}: {sample_urls}")
                
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
        
        logger.info(f"Filtering {len(urls)} URLs for {source.name}: allowed_domains={allowed_domains}, patterns={post_url_patterns}")
        
        # Log first few URLs for debugging
        if urls:
            logger.info(f"Sample URLs to filter: {list(urls)[:3]}")
        
        for url in urls:
            try:
                # Check domain allowlist
                if allowed_domains:
                    domain = urlparse(url).netloc.lower()
                    if not any(allowed_domain in domain for allowed_domain in allowed_domains):
                        logger.debug(f"URL {url} filtered out by domain check")
                        continue
                
                # Check URL patterns
                if post_url_patterns:
                    matched = False
                    for pattern in post_url_patterns:
                        try:
                            # Handle escaped backslashes in patterns (from JSON storage)
                            # Pattern stored in DB as: "\\\\\\.\" -> when read from JSON becomes "\\\."
                            # Need to convert \\\. to \. (escaped dot for regex)
                            # Replace double backslash + dot: \\\. -> \.
                            pattern_normalized = pattern.replace('\\\\.', '\\.')
                            # Use re.compile to properly handle the pattern
                            compiled_pattern = re.compile(pattern_normalized)
                            if compiled_pattern.match(url):
                                matched = True
                                logger.info(f"✅ URL {url} matched pattern {pattern_normalized}")
                                break
                            else:
                                # Log first non-match for debugging
                                if not matched and len([u for u in urls if u == url]) == 1:  # First occurrence
                                    logger.debug(f"❌ URL {url} did NOT match pattern {pattern_normalized} (compiled: {compiled_pattern.pattern})")
                        except re.error as e:
                            logger.warning(f"Invalid regex pattern '{pattern}' for {source.name}: {e}")
                            continue
                    
                    if not matched:
                        logger.debug(f"URL {url} filtered out by pattern check (patterns: {post_url_patterns})")
                        continue
                
                filtered.append(url)
                
            except Exception as e:
                logger.debug(f"Error filtering URL {url}: {e}")
                continue
        
        logger.debug(f"Filtered to {len(filtered)} URLs for {source.name}")
        return filtered


class StructuredDataExtractor:
    """Basic structured data extraction using regex parsing (no extruct library)."""
    
    @staticmethod
    def extract_structured_data(html: str, base_url: str) -> Dict[str, Any]:
        """
        Extract basic structured data from HTML using regex parsing.
        Note: This is a simplified implementation without proper structured data libraries.
        
        Args:
            html: HTML content
            base_url: Base URL for resolving relative URLs
            
        Returns:
            Dictionary with extracted structured data
        """
        try:
            # Basic structured data extraction using regex (not production-grade)
            data = {
                'json-ld': [],
                'opengraph': [],
                'microdata': [],
                'microformat': []
            }
            
            # Basic JSON-LD extraction
            soup = BeautifulSoup(html, 'html.parser')
            json_ld_scripts = soup.find_all('script', type='application/ld+json')
            
            for script in json_ld_scripts:
                try:
                    import json
                    json_data = json.loads(script.string)
                    if isinstance(json_data, dict):
                        data['json-ld'].append(json_data)
                    elif isinstance(json_data, list):
                        data['json-ld'].extend(json_data)
                except Exception:
                    continue
            
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
    """Web scraper with basic structured data extraction and CSS selectors."""
    
    def __init__(self, http_client: HTTPClient):
        self.http_client = http_client
        self.url_discovery = URLDiscovery(http_client)
        self.structured_extractor = StructuredDataExtractor()
    
    async def scrape_source(self, source: Source) -> List[ArticleCreate]:
        """
        Scrape articles from source using CSS selectors and basic JSON-LD parsing.
        Note: This is a fallback method when RSS feeds are unavailable.

        Args:
            source: Source configuration

        Returns:
            List of ArticleCreate objects
        """
        logger.info(f"Starting modern scraping for {source.name}")

        # Configure robots.txt settings if available
        if isinstance(source.config, dict) and 'robots' in source.config:
            if hasattr(self.http_client, 'configure_source_robots'):
                self.http_client.configure_source_robots(source.identifier, source.config['robots'])

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
            soup = BeautifulSoup(response.text, 'lxml')
            
            # Extract structured data
            structured_data = self.structured_extractor.extract_structured_data(
                response.text, url
            )
            
            # Try JSON-LD extraction first
            article_data = {}
            jsonld_article = self.structured_extractor.find_article_jsonld(structured_data)
            
            extract_config = source.config.get('extract', {}) if isinstance(source.config, dict) else getattr(source.config, 'extract', {})
            if jsonld_article and extract_config.get('prefer_jsonld', True):
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
                logger.warning(f"Missing required fields for {url}: title={bool(article_data.get('title'))}, content={bool(article_data.get('content'))}")
                logger.debug(f"Article data keys: {list(article_data.keys())}")
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
            
            # Generate required fields
            from src.utils.content import ContentCleaner
            content_hash = ContentCleaner.calculate_content_hash(article_data['title'], article_data['content'])
            word_count = len(article_data['content'].split()) if article_data['content'] else 0
            collected_at = datetime.utcnow()
            
            # Build article
            article = ArticleCreate(
                source_id=source.id,
                url=url,
                canonical_url=article_data.get('canonical_url', url),
                title=article_data['title'],
                published_at=article_data.get('published_at') or datetime.utcnow(),
                content=article_data['content'],
                content_hash=content_hash,
                word_count=word_count,
                collected_at=collected_at
            )
            
            return article
            
        except Exception as e:
            logger.error(f"Failed to extract article from {url}: {e}")
            return None
    
    def _extract_with_selectors(self, soup: BeautifulSoup, source: Source, url: str) -> Dict[str, Any]:
        """Extract article data using configured CSS selectors."""
        data = {}
        extract_config = source.config.get('extract', {}) if isinstance(source.config, dict) else getattr(source.config, 'extract', {})
        
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
                # Get text length to verify it's substantial content
                text_length = len(ContentCleaner.html_to_text(str(content_elem)).strip())
                if text_length > 100:
                    content_html = str(content_elem)
                    logger.debug(f"Found content with selector '{selector}' for {url} ({text_length} chars)")
                    break
        
        if not content_html:
            # Fallback: try to find any substantial content block
            for fallback_selector in ['article', 'main', '[role="main"]', '.content', '.post-content', '.entry-content', '[class*="content"]', '[class*="post"]', '[class*="blog"]']:
                content_elem = soup.select_one(fallback_selector)
                if content_elem:
                    text_length = len(ContentCleaner.html_to_text(str(content_elem)).strip())
                    if text_length > 500:  # Substantial content
                        content_html = str(content_elem)
                        logger.debug(f"Found content with fallback selector '{fallback_selector}' for {url} ({text_length} chars)")
                        break
        
        # Last resort: find content near h1
        if not content_html:
            h1_elem = soup.select_one('h1')
            if h1_elem:
                # Try to find parent container with substantial content
                parent = h1_elem.parent
                for _ in range(5):  # Go up 5 levels
                    if parent:
                        text_length = len(ContentCleaner.html_to_text(str(parent)).strip())
                        if text_length > 500:  # Found substantial content
                            content_html = str(parent)
                            logger.debug(f"Found content near h1 for {url} ({text_length} chars)")
                            break
                        parent = parent.parent
        
        if content_html:
            cleaned_content = ContentCleaner.clean_html(content_html)
            # Check if cleaned content has substantial text
            text_length = len(cleaned_content.strip())
            if text_length > 100:
                data['content'] = cleaned_content
                logger.debug(f"Successfully extracted content for {url} ({text_length} chars)")
            else:
                logger.warning(f"Content too short after cleaning for {url} ({text_length} chars), may be mostly navigation/UI")
                # Try to find content near h1 as last resort
                h1_elem = soup.select_one('h1')
                if h1_elem:
                    parent = h1_elem.parent
                    for _ in range(5):
                        if parent:
                            parent_html = str(parent)
                            parent_text = ContentCleaner.html_to_text(parent_html).strip()
                            if len(parent_text) > 1000:
                                cleaned_parent = ContentCleaner.clean_html(parent_html)
                                if len(cleaned_parent.strip()) > 100:
                                    data['content'] = cleaned_parent
                                    logger.debug(f"Found content near h1 for {url} ({len(cleaned_parent.strip())} chars)")
                                    break
                            parent = parent.parent
        else:
            logger.warning(f"No content found for {url} with selectors: {body_selectors}")
        
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
    """Basic HTML scraper using CSS selectors (last resort fallback)."""
    
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

        # Configure robots.txt settings if available
        if isinstance(source.config, dict) and 'robots' in source.config:
            if hasattr(self.http_client, 'configure_source_robots'):
                self.http_client.configure_source_robots(source.identifier, source.config['robots'])

        content_selector = getattr(source.config, 'content_selector', 'article')
        
        try:
            # Fetch main page
            response = await self.http_client.get(source.url, source_id=source.identifier)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'lxml')
            
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
                url=source.url,
                canonical_url=source.url,
                title=title,
                published_at=datetime.utcnow(),  # No date available
                content=content
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
