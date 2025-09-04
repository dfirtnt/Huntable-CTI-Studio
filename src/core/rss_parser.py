"""RSS/Atom feed parser for threat intelligence sources."""

import asyncio
from typing import List, Optional, Dict, Any
from datetime import datetime
import feedparser
import logging
from urllib.parse import urljoin

from src.models.article import Article, ArticleCreate
from src.models.source import Source
from src.utils.http import HTTPClient
from src.utils.content import DateExtractor, ContentCleaner, MetadataExtractor

logger = logging.getLogger(__name__)


class RSSParser:
    """RSS/Atom feed parser with enhanced content extraction."""
    
    def __init__(self, http_client: HTTPClient):
        self.http_client = http_client
    
    async def parse_feed(self, source: Source) -> List[ArticleCreate]:
        """
        Parse RSS/Atom feed and extract articles.
        
        Args:
            source: Source configuration with RSS URL
            
        Returns:
            List of ArticleCreate objects
            
        Raises:
            Exception: If feed cannot be fetched or parsed
        """
        if not source.rss_url:
            raise ValueError(f"Source {source.identifier} has no RSS URL")
        
        logger.info(f"Parsing RSS feed for {source.name}: {source.rss_url}")
        
        try:
            # Fetch RSS feed with source-specific robots configuration
            response = await self.http_client.get(
                source.rss_url, 
                source_id=source.identifier
            )
            response.raise_for_status()
            
            # Parse with feedparser
            feed_data = feedparser.parse(response.text)
            
            if feed_data.bozo and feed_data.bozo_exception:
                logger.warning(f"Feed parsing warning for {source.name}: {feed_data.bozo_exception}")
            
            # Extract articles
            articles = []
            for entry in feed_data.entries:
                try:
                    article = await self._parse_entry(entry, source)
                    if article:
                        articles.append(article)
                except Exception as e:
                    logger.error(f"Failed to parse entry in {source.name}: {e}")
                    continue
            
            logger.info(f"Extracted {len(articles)} articles from {source.name}")
            return articles
            
        except Exception as e:
            logger.error(f"Failed to parse RSS feed for {source.name}: {e}")
            raise
    
    async def _parse_entry(self, entry: Any, source: Source) -> Optional[ArticleCreate]:
        """
        Parse individual RSS entry into ArticleCreate.
        
        Args:
            entry: feedparser entry object
            source: Source configuration
            
        Returns:
            ArticleCreate object or None if parsing fails
        """
        try:
            # Extract basic fields
            title = self._extract_title(entry)
            url = self._extract_url(entry)
            published_at = await self._extract_date(entry, url)
            
            if not title or not url:
                logger.warning(f"Skipping entry with missing title or URL in {source.name}")
                return None
            
            # Extract content
            content = await self._extract_content(entry, url, source)
            if not content:
                logger.warning(f"No content extracted for {url}")
                return None
            
            # Extract metadata
            authors = self._extract_authors(entry)
            tags = self._extract_tags(entry)
            summary = self._extract_summary(entry, content)
            
            # Build article metadata
            metadata = {
                'feed_entry': {
                    'id': getattr(entry, 'id', ''),
                    'link': getattr(entry, 'link', ''),
                    'published': getattr(entry, 'published', ''),
                    'updated': getattr(entry, 'updated', ''),
                },
                'extraction_method': 'rss_with_modern_fallback' if hasattr(entry, '_used_modern_fallback') else 'rss'
            }
            
            # Quality scoring removed
            # metadata['quality_score'] = quality_score
            
            # Build article
            article = ArticleCreate(
                source_id=source.id,
                canonical_url=url,
                title=title,
                published_at=published_at or datetime.utcnow(),
                authors=authors,
                tags=tags,
                summary=summary,
                content=content,
                metadata=metadata
            )
            
            return article
            
        except Exception as e:
            logger.error(f"Error parsing RSS entry: {e}")
            return None
    
    def _extract_title(self, entry: Any) -> Optional[str]:
        """Extract title from RSS entry."""
        title = getattr(entry, 'title', '')
        if title:
            # Decode HTML entities (like &rsquo;)
            import html
            title = html.unescape(title)
            return ContentCleaner.normalize_whitespace(title)
        return None
    
    def _extract_url(self, entry: Any) -> Optional[str]:
        """Extract canonical URL from RSS entry."""
        # Try different URL fields
        url_fields = ['link', 'id', 'guid']
        
        for field in url_fields:
            url = getattr(entry, field, '')
            if url and url.startswith(('http://', 'https://')):
                return url
        
        # Handle guid that might not be a URL
        guid = getattr(entry, 'guid', '')
        if guid and not guid.startswith(('http://', 'https://')):
            # Some feeds use non-URL GUIDs, use link instead
            return getattr(entry, 'link', '')
        
        return None
    
    async def _extract_date(self, entry: Any, url: str = None) -> Optional[datetime]:
        """Extract publication date from RSS entry."""
        # Try different date fields
        date_fields = ['published', 'updated', 'created']
        
        for field in date_fields:
            date_str = getattr(entry, field, '')
            if date_str:
                parsed_date = DateExtractor.parse_date(date_str)
                if parsed_date and parsed_date.year > 1970:  # Skip epoch dates
                    return parsed_date
        
        # Try parsed date fields
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            try:
                import time
                timestamp = time.mktime(entry.published_parsed)
                parsed_date = datetime.fromtimestamp(timestamp)
                if parsed_date.year > 1970:  # Skip epoch dates
                    return parsed_date
            except Exception:
                pass
        
        if hasattr(entry, 'updated_parsed') and entry.updated_parsed:
            try:
                import time
                timestamp = time.mktime(entry.updated_parsed)
                parsed_date = datetime.fromtimestamp(timestamp)
                if parsed_date.year > 1970:  # Skip epoch dates
                    return parsed_date
            except Exception:
                pass
        
        # Fallback: try to extract date from article page metadata
        if url:
            try:
                date_from_page = await self._extract_date_from_page(url)
                if date_from_page:
                    return date_from_page
            except Exception as e:
                logger.warning(f"Failed to extract date from page {url}: {e}")
        
        return None
    
    async def _extract_date_from_page(self, url: str) -> Optional[datetime]:
        """Extract publication date from article page metadata."""
        try:
            # Fetch the article page
            response = await self.http_client.get(url)
            response.raise_for_status()
            
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(self.http_client.get_text_with_encoding_fallback(response), 'lxml')
            
            # Try different meta tags for publication date
            date_selectors = [
                'meta[name="published-date"]',
                'meta[name="article:published_time"]',
                'meta[property="article:published_time"]',
                'meta[name="date"]',
                'meta[name="pubdate"]',
                'meta[name="publishdate"]',
                'meta[name="publication_date"]',
                'meta[name="og:published_time"]',
                'meta[property="og:published_time"]',
                'time[datetime]',
                'time[pubdate]'
            ]
            
            for selector in date_selectors:
                element = soup.select_one(selector)
                if element:
                    date_str = element.get('content') or element.get('datetime')
                    if date_str:
                        parsed_date = DateExtractor.parse_date(date_str)
                        if parsed_date and parsed_date.year > 1970:
                            logger.info(f"Extracted date from page metadata: {date_str} -> {parsed_date}")
                            return parsed_date
            
            # Try to extract date from URL patterns
            url_date = DateExtractor.extract_date_from_url(url)
            if url_date and url_date.year > 1970:
                logger.info(f"Extracted date from URL pattern: {url_date}")
                return url_date
            
            return None
            
        except Exception as e:
            logger.warning(f"Failed to extract date from page {url}: {e}")
            return None
    
    async def _extract_content(self, entry: Any, url: str, source: Source) -> Optional[str]:
        """
        Extract content from RSS entry.
        
        Priority:
        1. Full content from feed
        2. Summary/description from feed
        3. If RSS content < 500 chars, try modern scraping
        4. Fetch full article from URL (with Red Canary protection)
        """
        # Try to get full content from feed first
        content = self._get_feed_content(entry)
        
        if content and len(ContentCleaner.html_to_text(content).strip()) > 1000:
            # We have substantial content from the feed (at least 1000 chars)
            return ContentCleaner.clean_html(content)
        
        # Check if RSS content is too short (< 500 chars) and try modern scraping
        if content:
            cleaned_rss_content = ContentCleaner.clean_html(content)
            rss_text_length = len(ContentCleaner.html_to_text(cleaned_rss_content).strip())
            
            if rss_text_length < 500:
                logger.info(f"RSS content too short ({rss_text_length} chars) for {url}, trying modern scraping")
                try:
                    # Try modern scraping to get full content
                    modern_content = await self._extract_with_modern_scraping(url, source)
                    if modern_content:
                        modern_text_length = len(ContentCleaner.html_to_text(modern_content).strip())
                        if modern_text_length > rss_text_length:
                            logger.info(f"Modern scraping successful: {modern_text_length} chars vs {rss_text_length} chars from RSS")
                            # Mark that modern scraping was used
                            entry._used_modern_fallback = True
                            return modern_content
                        else:
                            logger.info(f"Modern scraping didn't improve content length: {modern_text_length} vs {rss_text_length}")
                    else:
                        logger.info(f"Modern scraping failed for {url}, using RSS content")
                except Exception as e:
                    logger.warning(f"Modern scraping failed for {url}: {e}, falling back to RSS content")
        
        # Special handling for Red Canary - avoid compressed content issues
        if 'redcanary.com' in url.lower():
            logger.info(f"Red Canary URL detected, skipping due to compression issues: {url}")
            # Return None to indicate extraction failure - this article will be rejected
            return None
        
        # Special handling for The Hacker News - try modern scraping first, fallback to RSS
        if 'thehackernews.com' in url.lower():
            logger.info(f"The Hacker News URL detected, trying modern scraping first: {url}")
            try:
                # Try modern scraping to get full content
                modern_content = await self._extract_with_modern_scraping(url, source)
                if modern_content:
                    modern_text_length = len(ContentCleaner.html_to_text(modern_content).strip())
                    if modern_text_length > 1000:  # Ensure we got substantial content
                        logger.info(f"Modern scraping successful for The Hacker News: {modern_text_length} chars")
                        return modern_content
                    else:
                        logger.info(f"Modern scraping didn't provide substantial content: {modern_text_length} chars")
                else:
                    logger.info(f"Modern scraping failed for The Hacker News, using RSS content")
            except Exception as e:
                logger.warning(f"Modern scraping failed for The Hacker News {url}: {e}")
            
            # Fallback to RSS content if modern scraping fails
            if content and len(ContentCleaner.html_to_text(content).strip()) > 100:
                logger.info(f"Using RSS content for The Hacker News: {len(ContentCleaner.html_to_text(content).strip())} chars")
                return ContentCleaner.clean_html(content)
            return None
        
        # If feed content is insufficient, fetch from URL with retry strategies
        try:
            response = None
            for attempt in range(2):  # Try twice with different approaches
                try:
                    # First attempt: standard request with any pre-configured headers
                    # Second attempt: with additional headers to appear more like a browser
                    attempt_headers = extra_headers.copy() if extra_headers else {}
                    if attempt == 1:
                        attempt_headers.update({
                            'Referer': f"https://{url.split('/')[2]}/",
                            'Sec-Fetch-User': '?1',
                            'Sec-Ch-Ua': '"Google Chrome";v="120", "Chromium";v="120", "Not A(Brand";v="99"',
                            'Sec-Ch-Ua-Mobile': '?0',
                            'Sec-Ch-Ua-Platform': '"macOS"'
                        })
                        logger.info(f"Retry attempt {attempt + 1} with enhanced headers for {url}")
                    
                    response = await self.http_client.get(url, headers=attempt_headers)
                    response.raise_for_status()
                    break  # Success, exit retry loop
                    
                except Exception as e:
                    logger.warning(f"Attempt {attempt + 1} failed for {url}: {e}")
                    if attempt == 1:  # Last attempt failed
                        raise e
                    # Wait before retry
                    import asyncio
                    await asyncio.sleep(1)
            
            # Use basic content extraction
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(self.http_client.get_text_with_encoding_fallback(response), 'lxml')
            
            # Try comprehensive content selectors (prioritized by likelihood)
            content_selectors = [
                # The Hacker News specific (prioritized)
                '.post-body', '.entry-content', '.post-content', '.article-content',
                '.post-body .entry-content', '.entry-content .post-body',
                # CrowdStrike specific (prioritized)
                '.blog-post-content', '.blog-content', '.post-content', '.article-content',
                '.blog-post-body', '.post-body', '.article-body',
                # Unit 42 specific
                '.blog-post-content', '.post-content', '.entry-content',
                # Modern blog platforms
                '.blog-post-content', '.post-body', '.article-body', '.entry-body',
                # Medium/modern platforms
                'article', '[data-testid="storyContent"]', '.story-content',
                # WordPress/common CMS
                '.entry-content', '.post-content', '.content-area',
                # Generic content containers
                '.content', 'main', '#main-content', '#content',
                # Fallback containers
                '.container .content', '.page-content', '.site-content'
            ]
            
            for selector in content_selectors:
                content_elem = soup.select_one(selector)
                if content_elem:
                    extracted_content = str(content_elem)
                    clean_text = ContentCleaner.html_to_text(extracted_content).strip()
                    
                    # Enhanced content quality validation
                    if self._is_quality_content(clean_text, url):
                        logger.info(f"Successful content extraction using selector '{selector}' for {url}")
                        cleaned_content = ContentCleaner.clean_html(extracted_content)
                        
                        # Special cleaning for CrowdStrike articles
                        if 'crowdstrike.com' in url.lower():
                            cleaned_content = self._clean_crowdstrike_content(cleaned_content)
                        
                        return cleaned_content
            
            # Fallback: get body content
            body = soup.find('body')
            if body:
                return ContentCleaner.clean_html(str(body))
                
        except Exception as e:
            logger.warning(f"Failed to fetch full content from {url}: {e}")
        
        # Return feed content even if short
        if content:
            cleaned_content = ContentCleaner.clean_html(content)
            # Special cleaning for CrowdStrike articles
            if 'crowdstrike.com' in url.lower():
                cleaned_content = self._clean_crowdstrike_content(cleaned_content)
            return cleaned_content
        return None
    
    async def _extract_with_modern_scraping(self, url: str, source: Source) -> Optional[str]:
        """
        Extract content using modern scraping techniques (simplified version).
        
        Args:
            url: Article URL
            source: Source configuration
            
        Returns:
            Extracted content or None if extraction fails
        """
        try:
            # Fetch the article page
            response = await self.http_client.get(url, source_id=source.identifier)
            response.raise_for_status()
            
            # Parse HTML
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(self.http_client.get_text_with_encoding_fallback(response), 'lxml')
            
            # Try comprehensive content selectors (prioritized by likelihood)
            content_selectors = [
                # The Hacker News specific (prioritized)
                '.post-body', '.entry-content', '.post-content', '.article-content',
                '.post-body .entry-content', '.entry-content .post-body',
                # Modern blog platforms
                '.blog-post-content', '.post-body', '.article-body', '.entry-body',
                # Medium/modern platforms
                'article', '[data-testid="storyContent"]', '.story-content',
                # WordPress/common CMS
                '.entry-content', '.post-content', '.content-area',
                # Generic content containers
                '.content', 'main', '#main-content', '#content',
                # Fallback containers
                '.container .content', '.page-content', '.site-content'
            ]
            
            for selector in content_selectors:
                content_elem = soup.select_one(selector)
                if content_elem:
                    extracted_content = str(content_elem)
                    clean_text = ContentCleaner.html_to_text(extracted_content).strip()
                    
                    # Enhanced content quality validation
                    if self._is_quality_content(clean_text, url):
                        logger.info(f"Successful modern content extraction using selector '{selector}' for {url}")
                        return ContentCleaner.clean_html(extracted_content)
            
            # Fallback: get body content
            body = soup.find('body')
            if body:
                body_content = ContentCleaner.clean_html(str(body))
                clean_text = ContentCleaner.html_to_text(body_content).strip()
                if self._is_quality_content(clean_text, url):
                    return body_content
                
        except Exception as e:
            logger.warning(f"Failed to extract modern content from {url}: {e}")
        
        return None
    
    def _is_quality_content(self, text: str, url: str) -> bool:
        """Validate if extracted content is high quality and not blocked/error content."""
        if not text or len(text) < 100:
            return False
        
        # Check for anti-bot/error messages
        anti_bot_indicators = [
            'access denied', 'blocked', 'bot detected', 'captcha',
            'please enable javascript', 'javascript is required',
            'cloudflare', 'security check', 'rate limit',
            'temporarily unavailable', '403 forbidden', '404 not found'
        ]
        
        text_lower = text.lower()
        for indicator in anti_bot_indicators:
            if indicator in text_lower:
                logger.warning(f"Anti-bot content detected for {url}: {indicator}")
                return False
        
        # Ensure sufficient content length and word count
        words = text.split()
        if len(words) < 30:  # Reduced from 50 to 30 words
            return False
        
        # Check for reasonable content structure (paragraphs, sentences)
        sentences = text.count('.') + text.count('!') + text.count('?')
        if sentences < 2:  # Reduced from 3 to 2 sentences
            return False
        
        logger.debug(f"Quality content validated: {len(text)} chars, {len(words)} words, {sentences} sentences")
        return True
    
    def _get_feed_content(self, entry: Any) -> Optional[str]:
        """Extract content from feed entry."""
        # Try content field first (Atom)
        if hasattr(entry, 'content') and entry.content:
            if isinstance(entry.content, list) and entry.content:
                return entry.content[0].get('value', '')
            return str(entry.content)
        
        # Try description (RSS)
        if hasattr(entry, 'description') and entry.description:
            return entry.description
        
        # Try summary
        if hasattr(entry, 'summary') and entry.summary:
            return entry.summary
        
        return None
    
    def _extract_authors(self, entry: Any) -> List[str]:
        """Extract authors from RSS entry."""
        authors = []
        
        # Try author field
        if hasattr(entry, 'author') and entry.author:
            authors.append(entry.author)
        
        # Try authors list (some feeds have multiple authors)
        if hasattr(entry, 'authors') and entry.authors:
            for author in entry.authors:
                if isinstance(author, dict):
                    name = author.get('name', '')
                    if name:
                        authors.append(name)
                else:
                    authors.append(str(author))
        
        # Clean and deduplicate
        cleaned_authors = []
        for author in authors:
            author = author.strip()
            if author and author not in cleaned_authors:
                cleaned_authors.append(author)
        
        return cleaned_authors
    
    def _extract_tags(self, entry: Any) -> List[str]:
        """Extract tags/categories from RSS entry."""
        tags = set()
        
        # Try tags field
        if hasattr(entry, 'tags') and entry.tags:
            for tag in entry.tags:
                if isinstance(tag, dict):
                    term = tag.get('term', '')
                    if term:
                        tags.add(term)
                else:
                    tags.add(str(tag))
        
        # Try categories
        if hasattr(entry, 'category') and entry.category:
            tags.add(entry.category)
        
        # Convert to sorted list
        return sorted(list(tags))
    
    def _extract_summary(self, entry: Any, content: str) -> Optional[str]:
        """Extract or generate summary from RSS entry."""
        # Try summary from feed first
        if hasattr(entry, 'summary') and entry.summary:
            summary = ContentCleaner.html_to_text(entry.summary)
            summary = ContentCleaner.normalize_whitespace(summary)
            if len(summary) > 20:  # Ensure it's substantial
                return summary
        
        # Generate from content
        if content:
            return ContentCleaner.extract_summary(content)
        
        return None
    
    def _clean_crowdstrike_content(self, content: str) -> str:
        """Clean CrowdStrike article content by removing navigation and footer elements."""
        if not content:
            return content
        
        lines = content.split('\n')
        cleaned_lines = []
        
        # Skip navigation elements at the beginning
        skip_patterns = [
            'BLOG Featured',
            'Recent CrowdStrike',
            'CrowdStrike Named a Leader',
            'CrowdStrike to Acquire',
            'MURKY PANDA',
            'Recent'
        ]
        
        # Stop when we hit footer elements
        footer_patterns = [
            'Sign Up',
            'See CrowdStrike Falcon',
            'See Demo',
            'Copyright',
            'Privacy',
            'Contact Us',
            '1.888.512.8906',
            'Accessibility'
        ]
        
        in_content = False
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Check if we've found the start of actual content
            if any(keyword in line.lower() for keyword in ['machine learning', 'data splitting', 'evaluation', 'model', 'training', 'validation', 'approach', 'method']):
                in_content = True
            
            # Skip navigation elements at the beginning
            if not in_content and any(pattern in line for pattern in skip_patterns):
                continue
            
            # Stop when we hit footer elements
            if any(pattern in line for pattern in footer_patterns):
                break
            
            if in_content or len(cleaned_lines) > 0:
                cleaned_lines.append(line)
        
        # Join the cleaned content
        cleaned_content = '\n\n'.join(cleaned_lines)
        
        # Ensure we have substantial content
        if len(cleaned_content.strip()) < 100:
            # If cleaning was too aggressive, return original content
            return content
        
        return cleaned_content


class FeedValidator:
    """Utility class for validating RSS/Atom feeds."""
    
    @staticmethod
    async def validate_feed(url: str, http_client: HTTPClient) -> Dict[str, Any]:
        """
        Validate RSS/Atom feed and return metadata.
        
        Returns:
            Dictionary with validation results and feed metadata
        """
        result = {
            'valid': False,
            'feed_type': None,
            'title': None,
            'description': None,
            'entry_count': 0,
            'last_updated': None,
            'errors': []
        }
        
        try:
            # Fetch feed
            response = await http_client.get(url)
            response.raise_for_status()
            
            # Parse with feedparser
            feed_data = feedparser.parse(response.text)
            
            # Check for parsing errors
            if feed_data.bozo and feed_data.bozo_exception:
                result['errors'].append(f"Feed parsing warning: {feed_data.bozo_exception}")
            
            # Check if we have a valid feed
            if not hasattr(feed_data, 'feed') or not feed_data.entries:
                result['errors'].append("No valid feed structure or entries found")
                return result
            
            # Extract feed metadata
            feed_info = feed_data.feed
            result['valid'] = True
            result['feed_type'] = getattr(feed_info, 'version', 'unknown')
            result['title'] = getattr(feed_info, 'title', '')
            result['description'] = getattr(feed_info, 'description', '')
            result['entry_count'] = len(feed_data.entries)
            
            # Extract last updated
            if hasattr(feed_info, 'updated'):
                result['last_updated'] = DateExtractor.parse_date(feed_info.updated)
            
            # Validate entries
            valid_entries = 0
            for entry in feed_data.entries[:5]:  # Check first 5 entries
                if hasattr(entry, 'title') and hasattr(entry, 'link'):
                    valid_entries += 1
            
            if valid_entries == 0:
                result['errors'].append("No valid entries found with title and link")
                result['valid'] = False
            
        except Exception as e:
            result['errors'].append(f"Failed to fetch or parse feed: {e}")
        
        return result
