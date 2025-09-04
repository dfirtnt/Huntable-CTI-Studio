"""Content processing utilities for threat intelligence articles."""

import re
import hashlib
from datetime import datetime
from typing import List, Optional, Dict, Any
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)


class ContentCleaner:
    """Utilities for cleaning and normalizing content."""
    
    @staticmethod
    def normalize_whitespace(text: str) -> str:
        """Normalize whitespace in text."""
        if not text:
            return ""
        # Replace multiple whitespace with single space
        text = re.sub(r'\s+', ' ', text.strip())
        return text
    
    @staticmethod
    def clean_html(html_content: str) -> str:
        """Clean HTML content while preserving structure."""
        if not html_content:
            return ""
        
        # Parse with BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
        
        # Get text content
        text = soup.get_text()
        
        # Clean up whitespace
        text = ContentCleaner.normalize_whitespace(text)
        
        return text
    
    @staticmethod
    def html_to_text(html_content: str) -> str:
        """Convert HTML to plain text."""
        if not html_content:
            return ""
        
        # Parse with BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
        
        # Get text content
        text = soup.get_text()
        
        # Clean up whitespace
        text = ContentCleaner.normalize_whitespace(text)
        
        return text
    
    @staticmethod
    def extract_summary(content: str, max_length: int = 300) -> str:
        """Extract a summary from content."""
        if not content:
            return ""
        
        # Clean the content
        clean_content = ContentCleaner.html_to_text(content)
        
        # Take first max_length characters
        if len(clean_content) <= max_length:
            return clean_content
        
        # Try to break at sentence boundary
        summary = clean_content[:max_length]
        last_period = summary.rfind('.')
        last_exclamation = summary.rfind('!')
        last_question = summary.rfind('?')
        
        # Find the last sentence ending
        last_sentence = max(last_period, last_exclamation, last_question)
        
        if last_sentence > max_length * 0.7:  # If we have a good sentence break
            summary = summary[:last_sentence + 1]
        
        return summary.strip()
    
    @staticmethod
    def calculate_content_hash(title: str, content: str) -> str:
        """Calculate SHA256 hash of title and content."""
        combined = f"{title}\n{content}".encode('utf-8')
        return hashlib.sha256(combined).hexdigest()


class DateExtractor:
    """Utilities for extracting and parsing dates."""
    
    # Common date patterns
    DATE_PATTERNS = [
        r'(\d{4}-\d{2}-\d{2})',  # YYYY-MM-DD
        r'(\d{2}/\d{2}/\d{4})',  # MM/DD/YYYY
        r'(\d{2}-\d{2}-\d{4})',  # MM-DD-YYYY
        r'(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4})',  # DD MMM YYYY
        r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})',  # ISO format
        r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)',  # ISO format with Z
        r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+\d{2}:\d{2})',  # ISO format with timezone
    ]
    
    @staticmethod
    def parse_date(date_str: str) -> Optional[datetime]:
        """Parse date string to datetime object."""
        if not date_str:
            return None
        
        try:
            # Try parsing with feedparser's date parser
            import feedparser
            parsed = feedparser._parse_date(date_str)
            if parsed:
                return datetime(*parsed[:6])
        except Exception:
            pass
        
        # Try common formats
        for pattern in DateExtractor.DATE_PATTERNS:
            match = re.search(pattern, date_str)
            if match:
                try:
                    date_part = match.group(1)
                    # Try different parsing approaches
                    for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%m-%d-%Y', '%d %b %Y', '%Y-%m-%dT%H:%M:%S']:
                        try:
                            return datetime.strptime(date_part, fmt)
                        except ValueError:
                            continue
                except Exception:
                    continue
        
        logger.warning(f"Could not parse date: {date_str}")
        return None
    
    @staticmethod
    def extract_date_from_url(url: str) -> Optional[datetime]:
        """Extract date from URL patterns."""
        if not url:
            return None
        
        # Common URL date patterns
        url_patterns = [
            r'/(\d{4})/(\d{2})/(\d{2})/',  # /YYYY/MM/DD/
            r'/(\d{4})-(\d{2})-(\d{2})/',  # /YYYY-MM-DD/
            r'(\d{4})_(\d{2})_(\d{2})',    # YYYY_MM_DD
        ]
        
        for pattern in url_patterns:
            match = re.search(pattern, url)
            if match:
                try:
                    year, month, day = match.groups()
                    return datetime(int(year), int(month), int(day))
                except (ValueError, TypeError):
                    continue
        
        return None


class MetadataExtractor:
    """Utilities for extracting metadata from HTML."""
    
    @staticmethod
    def extract_authors(soup: BeautifulSoup) -> List[str]:
        """Extract authors from HTML."""
        authors = []
        
        # Common author selectors
        author_selectors = [
            '.author', '.byline', '.author-name', '.writer',
            '[rel="author"]', '.post-author', '.entry-author',
            'meta[name="author"]', 'meta[property="article:author"]'
        ]
        
        for selector in author_selectors:
            elements = soup.select(selector)
            for element in elements:
                if element.name == 'meta':
                    content = element.get('content', '')
                else:
                    content = element.get_text()
                
                if content:
                    author = ContentCleaner.normalize_whitespace(content)
                    if author and author not in authors:
                        authors.append(author)
        
        return authors
    
    @staticmethod
    def extract_tags(soup: BeautifulSoup) -> List[str]:
        """Extract tags/categories from HTML."""
        tags = []
        
        # Common tag selectors
        tag_selectors = [
            '.tags', '.categories', '.tag', '.category',
            '.post-tags', '.entry-tags', '.article-tags'
        ]
        
        for selector in tag_selectors:
            elements = soup.select(selector)
            for element in elements:
                links = element.find_all('a')
                for link in links:
                    tag = ContentCleaner.normalize_whitespace(link.get_text())
                    if tag and tag not in tags:
                        tags.append(tag)
        
        return tags
    
    @staticmethod
    def extract_canonical_url(soup: BeautifulSoup) -> Optional[str]:
        """Extract canonical URL from HTML."""
        canonical = soup.find('link', rel='canonical')
        if canonical:
            return canonical.get('href')
        
        # Try Open Graph URL
        og_url = soup.find('meta', property='og:url')
        if og_url:
            return og_url.get('content')
        
        return None
    
    @staticmethod
    def extract_meta_tags(soup: BeautifulSoup) -> Dict[str, str]:
        """Extract meta tags from HTML."""
        meta_data = {}
        
        meta_tags = soup.find_all('meta')
        for tag in meta_tags:
            name = tag.get('name') or tag.get('property')
            content = tag.get('content')
            
            if name and content:
                meta_data[name] = content
        
        return meta_data
    
    @staticmethod
    def extract_opengraph(soup: BeautifulSoup) -> Dict[str, str]:
        """Extract Open Graph data from HTML."""
        og_data = {}
        
        og_tags = soup.find_all('meta', property=re.compile(r'^og:'))
        for tag in og_tags:
            property_name = tag.get('property', '')
            content = tag.get('content', '')
            
            if property_name and content:
                og_data[property_name] = content
        
        return og_data


class QualityScorer:
    """Utilities for scoring article quality."""
    
    @staticmethod
    def score_article(title: str, content: str, metadata: Dict[str, Any]) -> float:
        """Score article quality based on various factors."""
        score = 50.0  # Base score
        
        try:
            # Title quality (0-20 points)
            if title:
                title_length = len(title.strip())
                if 10 <= title_length <= 100:
                    score += 10
                elif 5 <= title_length <= 150:
                    score += 5
                
                # Check for common spam indicators
                spam_indicators = ['click here', 'buy now', 'limited time', 'act now']
                if not any(indicator in title.lower() for indicator in spam_indicators):
                    score += 10
            
            # Content quality (0-30 points)
            if content:
                content_length = len(ContentCleaner.html_to_text(content))
                if content_length >= 500:
                    score += 15
                elif content_length >= 200:
                    score += 10
                elif content_length >= 100:
                    score += 5
                
                # Check for structured content
                if '<h' in content or '<p>' in content:
                    score += 10
                
                # Check for links (but not too many)
                link_count = content.count('<a href')
                if 1 <= link_count <= 10:
                    score += 5
            
            # Metadata quality (0-20 points)
            if metadata:
                # Check for author information
                if metadata.get('authors'):
                    score += 10
                
                # Check for tags/categories
                if metadata.get('tags'):
                    score += 5
                
                # Check for publication date
                if metadata.get('published_at'):
                    score += 5
            
            # Cap score at 100
            score = min(score, 100.0)
            
        except Exception as e:
            logger.warning(f"Error scoring article: {e}")
            score = 50.0  # Default score on error
        
        return round(score, 1)


def validate_content(title: str, content: str, url: str) -> List[str]:
    """Validate content and return list of issues."""
    issues = []
    
    try:
        # Title validation
        if not title or len(title.strip()) < 5:
            issues.append("Title too short or missing")
        elif len(title.strip()) > 200:
            issues.append("Title too long")
        
        # Content validation
        if not content or len(content.strip()) < 50:
            issues.append("Content too short or missing")
        elif len(content.strip()) > 50000:
            issues.append("Content too long")
        
        # URL validation
        if not url or not url.startswith(('http://', 'https://')):
            issues.append("Invalid URL format")
        
        # Check for obvious spam indicators
        spam_indicators = ['click here', 'buy now', 'limited time', 'act now', 'make money fast']
        text_content = ContentCleaner.html_to_text(content).lower()
        if any(indicator in text_content for indicator in spam_indicators):
            issues.append("Contains spam indicators")
        
        # Check for excessive links
        link_count = content.count('<a href')
        if link_count > 20:
            issues.append("Too many links")
        
    except Exception as e:
        logger.warning(f"Error validating content: {e}")
        issues.append("Validation error")
    
    return issues
