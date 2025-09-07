"""Content processing utilities."""

import re
from typing import List, Optional, Dict, Any
from datetime import datetime
from dateutil import parser as date_parser
import hashlib
from bs4 import BeautifulSoup, Tag
from readability import Document
import logging

logger = logging.getLogger(__name__)


class ContentCleaner:
    """Utility class for cleaning and normalizing content."""
    
    @staticmethod
    def clean_html(html: str) -> str:
        """Clean HTML content and extract readable text."""
        try:
            # First try readability for article extraction
            doc = Document(html)
            cleaned_html = doc.content()
            # Convert to clean text
            return ContentCleaner.html_to_text(cleaned_html)
        except Exception as e:
            logger.warning(f"Readability failed, using enhanced cleaning: {e}")
            return ContentCleaner.enhanced_html_clean(html)
    
    @staticmethod
    def enhanced_html_clean(html: str) -> str:
        """Enhanced HTML cleaning that extracts clean text."""
        soup = BeautifulSoup(html, 'lxml')
        
        # Remove unwanted elements completely
        unwanted_tags = [
            "script", "style", "nav", "header", "footer", "aside", 
            "advertisement", "menu", "sidebar", "breadcrumb", "pagination",
            "social", "share", "comment", "related", "widget", "promo",
            "banner", "ad", "popup", "modal", "overlay", "tracking"
        ]
        
        for tag_name in unwanted_tags:
            for tag in soup.find_all(tag_name):
                tag.decompose()
        
        # Remove elements by class/id patterns (common navigation/UI elements)
        unwanted_patterns = [
            'nav', 'menu', 'sidebar', 'header', 'footer', 'breadcrumb',
            'pagination', 'social', 'share', 'comment', 'related', 'widget',
            'promo', 'banner', 'ad', 'popup', 'modal', 'overlay', 'tracking',
            'subscribe', 'newsletter', 'follow', 'like', 'tweet', 'facebook'
        ]
        
        for pattern in unwanted_patterns:
            for element in soup.find_all(attrs={'class': lambda x: x and any(pattern.lower() in str(x).lower() for pattern in unwanted_patterns)}):
                element.decompose()
            for element in soup.find_all(attrs={'id': lambda x: x and any(pattern.lower() in str(x).lower() for pattern in unwanted_patterns)}):
                element.decompose()
        
        # Find main content area
        content_selectors = [
            'article', '[role="main"]', 'main', '.content', '.post-content',
            '.entry-content', '.blog-content', '.article-content', '#content'
        ]
        
        main_content = None
        for selector in content_selectors:
            main_content = soup.select_one(selector)
            if main_content and len(main_content.get_text(strip=True)) > 100:
                break
        
        if main_content:
            # Extract clean text from main content
            return ContentCleaner.html_to_text(str(main_content))
        else:
            # Fallback: extract from body but clean aggressively
            return ContentCleaner.html_to_text(html)
    
    @staticmethod
    def basic_html_clean(html: str) -> str:
        """Basic HTML cleaning without readability (deprecated - use enhanced_html_clean)."""
        soup = BeautifulSoup(html, 'lxml')
        
        # Remove unwanted elements
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "advertisement"]):
            tag.decompose()
        
        # Remove attributes that might cause issues
        for tag in soup.find_all():
            tag.attrs = {k: v for k, v in tag.attrs.items() 
                        if k in ['href', 'src', 'alt', 'title']}
        
        return str(soup)
    
    @staticmethod
    def html_to_text(html: str) -> str:
        """Convert HTML to clean text with better formatting."""
        try:
            # Ensure we have clean text input
            if isinstance(html, bytes):
                html = html.decode('utf-8', errors='ignore')
            
            soup = BeautifulSoup(html, 'lxml')
            
            # Add line breaks for block elements before extracting text
            for tag in soup.find_all(['p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'br']):
                tag.insert_after('\n')
            
            # Extract text
            text = soup.get_text(separator=' ', strip=True)
            
            # Clean up whitespace and normalize
            text = ContentCleaner.normalize_whitespace(text)
            
            # Remove non-printable characters
            text = ContentCleaner.clean_text_characters(text)
            
            return text
        except Exception as e:
            logger.warning(f"Error in html_to_text: {e}")
            # Fallback to simple text extraction
            return ContentCleaner.normalize_whitespace(str(html))
    
    @staticmethod
    def normalize_whitespace(text: str) -> str:
        """Normalize whitespace in text."""
        # Replace multiple whitespace characters with single space
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    @staticmethod
    def clean_text_characters(text: str) -> str:
        """Clean text by removing non-printable and control characters."""
        try:
            # Remove control characters and other problematic characters
            # Keep only printable ASCII and common Unicode characters
            cleaned = ''.join(char for char in text if (
                char.isprintable() or char.isspace()
            ) and ord(char) < 65536)  # Basic Multilingual Plane
            
            # Remove any remaining problematic sequences
            cleaned = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', cleaned)
            
            return cleaned
        except Exception as e:
            logger.warning(f"Error cleaning text characters: {e}")
            # Fallback: remove only null bytes and common control chars
            return re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
    
    @staticmethod
    def extract_summary(content: str, max_length: int = 500) -> str:
        """Extract summary from content."""
        # Convert HTML to text if needed
        if '<' in content and '>' in content:
            text = ContentCleaner.html_to_text(content)
        else:
            text = content
        
        # Normalize whitespace
        text = ContentCleaner.normalize_whitespace(text)
        
        # Find first complete sentence that doesn't exceed max_length
        sentences = re.split(r'[.!?]+', text)
        summary = ""
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            
            test_summary = f"{summary} {sentence}".strip()
            if len(test_summary) <= max_length:
                summary = test_summary
            else:
                break
        
        # If no complete sentences fit, truncate at word boundary
        if not summary:
            words = text.split()
            summary = ""
            for word in words:
                test_summary = f"{summary} {word}".strip()
                if len(test_summary) <= max_length - 3:  # Leave room for "..."
                    summary = test_summary
                else:
                    break
            summary += "..."
        
        return summary
    
    @staticmethod
    def calculate_content_hash(title: str, content: str) -> str:
        """Calculate SHA256 hash of content for deduplication."""
        # Normalize content for hashing
        normalized_title = ContentCleaner.normalize_whitespace(title.lower())
        normalized_content = ContentCleaner.normalize_whitespace(
            ContentCleaner.html_to_text(content).lower()
        )
        
        combined = f"{normalized_title}\n{normalized_content}".encode('utf-8')
        return hashlib.sha256(combined).hexdigest()


class DateExtractor:
    """Utility class for extracting and parsing dates."""
    
    @staticmethod
    def parse_date(date_str: str) -> Optional[datetime]:
        """Parse date string to datetime object."""
        if not date_str:
            return None
        
        try:
            # Handle common date formats
            date_str = date_str.strip()
            
            # ISO format with timezone
            if 'T' in date_str or '+' in date_str or 'Z' in date_str:
                return date_parser.parse(date_str)
            
            # Try dateutil parser
            return date_parser.parse(date_str)
            
        except Exception as e:
            logger.debug(f"Failed to parse date '{date_str}': {e}")
            return None
    
    @staticmethod
    def extract_date_from_url(url: str) -> Optional[datetime]:
        """Extract date from URL path if possible."""
        # Look for YYYY/MM/DD or YYYY-MM-DD patterns
        date_patterns = [
            r'(\d{4})/(\d{1,2})/(\d{1,2})',  # 2024/01/15
            r'(\d{4})-(\d{1,2})-(\d{1,2})',  # 2024-01-15
            r'(\d{4})(\d{2})(\d{2})',        # 20240115
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, url)
            if match:
                try:
                    year, month, day = map(int, match.groups())
                    return datetime(year, month, day)
                except ValueError:
                    continue
        
        return None


class MetadataExtractor:
    """Utility class for extracting metadata from HTML."""
    
    @staticmethod
    def extract_meta_tags(soup: BeautifulSoup) -> Dict[str, str]:
        """Extract all meta tag content."""
        meta_data = {}
        
        # Standard meta tags
        for meta in soup.find_all('meta'):
            name = meta.get('name') or meta.get('property') or meta.get('http-equiv')
            content = meta.get('content')
            
            if name and content:
                meta_data[name.lower()] = content
        
        return meta_data
    
    @staticmethod
    def extract_opengraph(soup: BeautifulSoup) -> Dict[str, str]:
        """Extract OpenGraph metadata."""
        og_data = {}
        
        for meta in soup.find_all('meta'):
            property_name = meta.get('property', '')
            if property_name.startswith('og:'):
                content = meta.get('content')
                if content:
                    key = property_name[3:]  # Remove 'og:' prefix
                    og_data[key] = content
        
        return og_data
    
    @staticmethod
    def extract_twitter_cards(soup: BeautifulSoup) -> Dict[str, str]:
        """Extract Twitter Card metadata."""
        twitter_data = {}
        
        for meta in soup.find_all('meta'):
            name = meta.get('name', '')
            if name.startswith('twitter:'):
                content = meta.get('content')
                if content:
                    key = name[8:]  # Remove 'twitter:' prefix
                    twitter_data[key] = content
        
        return twitter_data
    
    @staticmethod
    def extract_canonical_url(soup: BeautifulSoup) -> Optional[str]:
        """Extract canonical URL from link tag."""
        canonical = soup.find('link', {'rel': 'canonical'})
        if canonical:
            return canonical.get('href')
        return None
    
    @staticmethod
    def extract_authors(soup: BeautifulSoup) -> List[str]:
        """Extract author information from various sources."""
        authors = []
        
        # Try meta tags first
        author_meta = soup.find('meta', {'name': 'author'})
        if author_meta:
            content = author_meta.get('content', '')
            if content:
                # Split on common delimiters
                for delimiter in [',', ';', '&', ' and ']:
                    if delimiter in content:
                        authors.extend([a.strip() for a in content.split(delimiter)])
                        break
                else:
                    authors.append(content.strip())
        
        # Try OpenGraph
        if not authors:
            og_author = soup.find('meta', {'property': 'article:author'})
            if og_author:
                content = og_author.get('content', '').strip()
                if content:
                    authors.append(content)
        
        # Try structured data (basic)
        if not authors:
            # Look for author in JSON-LD or microdata
            author_elements = soup.find_all(attrs={'itemprop': 'author'})
            for elem in author_elements:
                if elem.string:
                    authors.append(elem.string.strip())
        
        # Clean and deduplicate
        cleaned_authors = []
        for author in authors:
            author = author.strip()
            if author and author not in cleaned_authors:
                cleaned_authors.append(author)
        
        return cleaned_authors[:5]  # Limit to 5 authors
    
    @staticmethod
    def extract_tags(soup: BeautifulSoup) -> List[str]:
        """Extract tags/categories from various sources."""
        tags = set()
        
        # Meta keywords
        keywords_meta = soup.find('meta', {'name': 'keywords'})
        if keywords_meta:
            content = keywords_meta.get('content', '')
            if content:
                tags.update([tag.strip() for tag in content.split(',') if tag.strip()])
        
        # OpenGraph tags
        og_tags = soup.find_all('meta', {'property': 'article:tag'})
        for tag_meta in og_tags:
            content = tag_meta.get('content', '').strip()
            if content:
                tags.add(content)
        
        # Category meta
        category_meta = soup.find('meta', {'name': 'category'})
        if category_meta:
            content = category_meta.get('content', '').strip()
            if content:
                tags.add(content)
        
        # Convert to sorted list and limit
        return sorted(list(tags))[:10]  # Limit to 10 tags


class QualityScorer:
    """Utility class for scoring content quality."""
    
    @staticmethod
    def score_article(title: str, content: str, metadata: Dict[str, Any]) -> float:
        """
        Score article quality from 0.0 to 1.0.
        
        Factors:
        - Title length and quality
        - Content length and structure
        - Metadata completeness
        - Date presence
        - Author information
        """
        score = 0.0
        
        # Title scoring (0.2 max)
        if title:
            title_len = len(title.strip())
            if 10 <= title_len <= 200:
                score += 0.2
            elif title_len > 5:
                score += 0.1
        
        # Content scoring (0.4 max)
        if content:
            text_content = ContentCleaner.html_to_text(content)
            content_len = len(text_content.strip())
            
            if content_len >= 500:
                score += 0.4
            elif content_len >= 200:
                score += 0.3
            elif content_len >= 50:
                score += 0.2
            elif content_len > 0:
                score += 0.1
            
            # Bonus for structured content
            if '<p>' in content or '<div>' in content:
                score += 0.05
        
        # Metadata scoring (0.2 max)
        meta_score = 0.0
        
        # Author presence
        if metadata.get('authors'):
            meta_score += 0.05
        
        # Publication date
        if metadata.get('published_at'):
            meta_score += 0.05
        
        # Tags/categories
        if metadata.get('tags'):
            meta_score += 0.05
        
        # Summary/description
        if metadata.get('summary') or metadata.get('description'):
            meta_score += 0.05
        
        score += meta_score
        
        # Deduction for obvious issues
        if not title or not content:
            score *= 0.5
        
        # Ensure score is between 0 and 1
        return max(0.0, min(1.0, score))


def validate_content(title: str, content: str, url: str) -> List[str]:
    """
    Validate content and return list of issues.
    
    Returns:
        List of validation issues (empty if valid)
    """
    issues = []
    
    if not title or not title.strip():
        issues.append("Missing or empty title")
    elif len(title.strip()) < 5:
        issues.append("Title too short")
    elif len(title.strip()) > 500:
        issues.append("Title too long")
    
    if not content or not content.strip():
        issues.append("Missing or empty content")
    else:
        # Check for garbage content patterns
        if _is_garbage_content(content):
            issues.append("Content appears to be garbage/compressed data")
        
        # Check for compression failure messages
        if _has_compression_failure_indicators(content):
            issues.append("Content indicates extraction failure")
        
        text_content = ContentCleaner.html_to_text(content)
        if len(text_content.strip()) < 50:
            issues.append("Content too short")
    
    if not url or not url.strip():
        issues.append("Missing URL")
    elif not url.startswith(('http://', 'https://')):
        issues.append("Invalid URL format")
    
    return issues

def _is_garbage_content(content: str) -> bool:
    """
    Detect if content is garbage/compressed data.
    
    Returns:
        True if content appears to be garbage
    """
    if not content:
        return False
    
    # Convert to lowercase for analysis
    content_lower = content.lower()
    
    # Check for high ratio of problematic characters
    problematic_chars = sum(1 for c in content if c in '[]{}|\\')
    total_chars = len(content)
    
    if total_chars > 0:
        problematic_ratio = problematic_chars / total_chars
        if problematic_ratio > 0.08:  # More than 8% problematic characters
            return True
    
    # Check for specific garbage patterns
    if '`E9 UI=' in content or 'cwCz _9hvtYfL' in content:
        return True
    
    # Check for consecutive problematic characters
    consecutive_count = 0
    max_consecutive = 0
    for char in content:
        if char in '[]{}|\\':
            consecutive_count += 1
            max_consecutive = max(max_consecutive, consecutive_count)
        else:
            consecutive_count = 0
    
    # Check final sequence
    if consecutive_count >= 3:
        max_consecutive = max(max_consecutive, consecutive_count)
    
    if max_consecutive >= 3:  # 3 or more consecutive problematic chars
        return True
    
    # Check for binary-like patterns
    binary_patterns = [
        r'[^\w\s]{3,}',      # Multiple consecutive special chars
    ]
    
    import re
    for pattern in binary_patterns:
        if re.search(pattern, content):
            return True
    
    # Check for compression artifacts
    compression_indicators = [
        'compression issues',
        'website compression',
        'content extraction failed',
        'failed due to website',
        'compression failed',
        'extraction disabled'
    ]
    
    if any(indicator in content_lower for indicator in compression_indicators):
        return True
    
    return False

def _has_compression_failure_indicators(content: str) -> bool:
    """
    Check if content contains indicators of extraction failure.
    
    Returns:
        True if content suggests extraction failed
    """
    if not content:
        return False
    
    content_lower = content.lower()
    
    # Patterns that indicate extraction failure
    failure_patterns = [
        'content extraction failed',
        'failed due to website compression',
        'extraction is disabled',
        'please visit the original article',
        'compression issues',
        'website compression issues',
        'full content extraction is disabled'
    ]
    
    return any(pattern in content_lower for pattern in failure_patterns)
