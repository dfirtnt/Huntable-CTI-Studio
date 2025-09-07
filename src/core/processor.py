"""Content processor with deduplication, normalization, and quality filtering."""

import asyncio
from typing import List, Dict, Set, Optional, Tuple, Any
from datetime import datetime, timedelta
import logging
import hashlib

from src.models.article import Article, ArticleCreate
from src.models.source import Source
from src.utils.content import (
    ContentCleaner, DateExtractor, QualityScorer, 
    validate_content, MetadataExtractor
)

logger = logging.getLogger(__name__)


class DeduplicationResult:
    """Result of deduplication process."""
    
    def __init__(
        self,
        unique_articles: List[ArticleCreate],
        duplicates: List[Tuple[ArticleCreate, str]],  # (article, reason)
        stats: Dict[str, int]
    ):
        self.unique_articles = unique_articles
        self.duplicates = duplicates
        self.stats = stats


class ContentProcessor:
    """Content processor for deduplication, normalization, and quality filtering."""
    
    def __init__(
        self,
        similarity_threshold: float = 0.85,
        max_age_days: int = 90,
        enable_content_enhancement: bool = True
    ):
        self.similarity_threshold = similarity_threshold
        self.max_age_days = max_age_days
        self.enable_content_enhancement = enable_content_enhancement
        
        # Deduplication tracking
        self.seen_hashes: Set[str] = set()
        self.seen_urls: Set[str] = set()
        self.seen_url_titles: Set[str] = set()  # url||title combinations
        self.content_fingerprints: Dict[str, str] = {}  # fingerprint -> content_hash
        
        # Processing statistics
        self.stats = {
            'total_processed': 0,
            'duplicates_removed': 0,
            'quality_filtered': 0,
            'enhanced_articles': 0,
            'validation_failures': 0
        }
    
    async def process_articles(
        self,
        articles: List[ArticleCreate],
        existing_hashes: Optional[Set[str]] = None,
        existing_urls: Optional[Set[str]] = None
    ) -> DeduplicationResult:
        """
        Process articles with deduplication, normalization, and quality filtering.
        
        Args:
            articles: List of articles to process
            existing_hashes: Set of existing content hashes to check against
            existing_urls: Set of existing URLs to check against
            
        Returns:
            DeduplicationResult with unique articles and statistics
        """
        if not articles:
            return DeduplicationResult([], [], {'total': 0, 'processed': 0})
        
        logger.info(f"Processing {len(articles)} articles")
        
        # Initialize existing hashes and URLs if provided
        if existing_hashes:
            self.seen_hashes.update(existing_hashes)
        if existing_urls:
            # Normalize existing URLs for consistent comparison
            normalized_existing_urls = {self._normalize_url(url) for url in existing_urls if url}
            self.seen_urls.update(normalized_existing_urls)
        
        # Process each article
        unique_articles = []
        duplicates = []
        
        for article in articles:
            try:
                # Normalize and enhance article
                processed_article = await self._process_single_article(article)
                
                if not processed_article:
                    continue
                
                # Check for duplicates
                duplicate_reason = self._check_duplicates(processed_article)
                
                if duplicate_reason:
                    duplicates.append((processed_article, duplicate_reason))
                    self.stats['duplicates_removed'] += 1
                else:
                    # Quality filtering
                    if self._passes_quality_filter(processed_article):
                        unique_articles.append(processed_article)
                        self._record_article(processed_article)
                    else:
                        duplicates.append((processed_article, "quality_filter"))
                        self.stats['quality_filtered'] += 1
                
                self.stats['total_processed'] += 1
                
            except Exception as e:
                logger.error(f"Failed to process article '{article.title[:50]}...': {e}")
                self.stats['validation_failures'] += 1
                continue
        
        # Create result
        result_stats = {
            'total': len(articles),
            'unique': len(unique_articles),
            'duplicates': len(duplicates),
            'quality_filtered': sum(1 for _, reason in duplicates if reason == "quality_filter"),
            'hash_duplicates': sum(1 for _, reason in duplicates if reason == "content_hash"),
            'url_duplicates': sum(1 for _, reason in duplicates if reason == "url"),
            'similarity_duplicates': sum(1 for _, reason in duplicates if reason == "content_similarity")
        }
        
        logger.info(f"Processing complete: {len(unique_articles)} unique articles from {len(articles)} input")
        
        return DeduplicationResult(unique_articles, duplicates, result_stats)
    
    async def _process_single_article(self, article: ArticleCreate) -> Optional[ArticleCreate]:
        """
        Process and normalize a single article.
        
        Args:
            article: Article to process
            
        Returns:
            Processed article or None if processing fails
        """
        try:
            # Validate required fields
            validation_issues = validate_content(article.title, article.content, article.canonical_url)
            if validation_issues:
                logger.debug(f"Article validation failed: {validation_issues}")
                return None
            
            # Content type detection
            content_type = self._detect_content_type(article)
            if content_type == 'podcast' and len(article.content) < 500:
                logger.info(f"Detected podcast entry: {article.title[:50]}...")
                # For podcast entries, we'll keep them but flag them
                article.metadata['content_type'] = 'podcast'
                article.metadata['is_short_content'] = True
            elif len(article.content) < 200:
                logger.warning(f"Very short content detected: {article.title[:50]}... ({len(article.content)} chars)")
                article.metadata['is_short_content'] = True
                # Don't reject, but flag for review
            
            # Normalize content
            normalized_title = ContentCleaner.normalize_whitespace(article.title)
            normalized_content = ContentCleaner.clean_html(article.content)
            
            # Generate or update content hash
            content_hash = ContentCleaner.calculate_content_hash(normalized_title, normalized_content)
            
            # Extract/enhance metadata if enabled
            enhanced_metadata = article.metadata.copy()
            enhanced_metadata.update({
                'content_type': content_type,
                'word_count': len(normalized_content.split()),
                'content_length': len(normalized_content),
                'processing_timestamp': datetime.utcnow().isoformat()
            })
            
            if self.enable_content_enhancement:
                enhanced_metadata.update(await self._enhance_metadata(article))
                self.stats['enhanced_articles'] += 1
            
            # Generate summary if missing
            summary = article.summary
            if not summary:
                summary = ContentCleaner.extract_summary(normalized_content)
            
            # Create processed article with content hash
            processed_article = ArticleCreate(
                source_id=article.source_id,
                canonical_url=article.canonical_url.strip(),
                title=normalized_title,
                published_at=article.published_at,
                modified_at=article.modified_at,
                authors=self._normalize_authors(article.authors),
                tags=self._normalize_tags(article.tags),
                summary=summary,
                content=normalized_content,
                content_hash=content_hash,  # Set hash during creation
                metadata=enhanced_metadata
            )
            
            return processed_article
            
        except Exception as e:
            logger.error(f"Error processing article: {e}")
            return None
    
    async def _enhance_metadata(self, article: ArticleCreate) -> Dict[str, Any]:
        """Enhance article metadata with additional information."""
        enhanced = {}
        
        try:
            # Calculate quality score
            quality_score = QualityScorer.score_article(
                article.title,
                article.content,
                article.metadata
            )
            enhanced['quality_score'] = quality_score
            
            # Extract additional metadata from content
            if '<' in article.content:  # HTML content
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(article.content, 'lxml')
                
                # Extract word count
                text_content = ContentCleaner.html_to_text(article.content)
                enhanced['word_count'] = len(text_content.split())
                
                # Extract reading time estimate (average 200 words per minute)
                enhanced['reading_time_minutes'] = max(1, enhanced['word_count'] // 200)
                
                # Extract image count
                images = soup.find_all('img')
                enhanced['image_count'] = len(images)
                
                # Extract link count
                links = soup.find_all('a', href=True)
                enhanced['link_count'] = len(links)
                
                # Extract headings structure
                headings = []
                for level in range(1, 7):
                    h_tags = soup.find_all(f'h{level}')
                    if h_tags:
                        headings.extend([tag.get_text(strip=True) for tag in h_tags])
                enhanced['headings'] = headings[:10]  # Limit to 10 headings
            
            # Extract date information
            if article.published_at:
                enhanced['publication_day_of_week'] = article.published_at.strftime('%A')
                enhanced['publication_month'] = article.published_at.strftime('%B')
                enhanced['publication_year'] = article.published_at.year
                
                # Calculate age - handle timezone differences
                try:
                    if article.published_at.tzinfo is not None:
                        # If published_at is timezone-aware, make current time timezone-aware too
                        current_time = datetime.now(article.published_at.tzinfo)
                    else:
                        # If published_at is naive, use naive current time
                        current_time = datetime.utcnow()
                    
                    age_days = (current_time - article.published_at).days
                    enhanced['age_days'] = age_days
                except Exception as e:
                    # Fallback: just use days from utcnow, ignoring timezone
                    enhanced['age_days'] = 0
            
            # Content analysis
            text_content = ContentCleaner.html_to_text(article.content).lower()
            
            # Extract potential threat indicators (basic keyword analysis)
            threat_keywords = [
                'malware', 'ransomware', 'phishing', 'apt', 'attack', 'vulnerability',
                'exploit', 'breach', 'campaign', 'threat', 'security', 'incident',
                'botnet', 'trojan', 'backdoor', 'spyware', 'rootkit', 'zero-day'
            ]
            
            found_keywords = [kw for kw in threat_keywords if kw in text_content]
            enhanced['threat_keywords'] = found_keywords
            enhanced['threat_keyword_count'] = len(found_keywords)
            
            # Processing timestamp
            enhanced['processed_at'] = datetime.utcnow().isoformat()
            
        except Exception as e:
            logger.warning(f"Error enhancing metadata: {e}")
        
        return enhanced
    
    def _normalize_url(self, url: str) -> str:
        """Normalize URL for consistent duplicate detection."""
        if not url:
            return ""
        
        # Remove trailing slashes, fragments, and common tracking parameters
        normalized = url.strip().rstrip('/')
        
        # Remove common tracking parameters
        if '?' in normalized:
            base_url, params = normalized.split('?', 1)
            # Keep only essential parameters, remove tracking ones
            param_pairs = params.split('&')
            essential_params = []
            tracking_params = {
                'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content', 
                'fbclid', 'gclid', 'ref', 'source', '_ga', '_gid', 'mc_cid', 'mc_eid',
                'si', 's', 'fb_action_ids', 'fb_action_types', 'fb_source', 'fb_ref',
                'campaign', 'email', 'newsletter', 'social', 'share', 'click'
            }
            
            for param in param_pairs:
                if '=' in param:
                    key = param.split('=')[0].lower()
                    if key not in tracking_params:
                        essential_params.append(param)
            
            if essential_params:
                normalized = f"{base_url}?{'&'.join(essential_params)}"
            else:
                normalized = base_url
        
        # Remove fragments
        if '#' in normalized:
            normalized = normalized.split('#')[0]
        
        # Normalize to lowercase
        normalized = normalized.lower()
        
        # Remove www. prefix for consistency
        if normalized.startswith('www.'):
            normalized = normalized[4:]
        
        return normalized
    
    def _get_minimum_content_length(self, url: str) -> int:
        """Get minimum content length based on source domain."""
        if not url:
            return 100  # Default minimum
        
        try:
            from urllib.parse import urlparse
            domain = urlparse(url).netloc.lower()
            
            # Source-specific minimum content lengths
            min_lengths = {
                'msrc.microsoft.com': 1000,  # Microsoft Security Response Center articles should be substantial
                'microsoft.com': 800,        # Other Microsoft articles
                'sans.edu': 500,             # SANS articles are usually detailed
                'isc.sans.edu': 500,         # ISC diary entries
                'unit42.paloaltonetworks.com': 1200,  # Unit 42 reports are comprehensive
                'paloaltonetworks.com': 800, # Other PAN articles
                'fireeye.com': 1000,         # FireEye threat intelligence
                'mandiant.com': 1000,        # Mandiant reports
                'crowdstrike.com': 800,      # CrowdStrike blogs
                'krebsonsecurity.com': 600,  # Brian Krebs articles
                'threatpost.com': 500,       # Threatpost articles
                'darkreading.com': 500,      # Dark Reading articles
                'bleepingcomputer.com': 400, # BleepingComputer news
                'securityweek.com': 400,     # Security Week news
            }
            
            # Check for exact domain match first
            if domain in min_lengths:
                return min_lengths[domain]
            
            # Check for subdomain matches
            for source_domain, min_len in min_lengths.items():
                if domain.endswith(f".{source_domain}"):
                    return min_len
            
            # Default minimum for unknown sources
            return 200
            
        except Exception as e:
            logger.warning(f"Error determining minimum content length for {url}: {e}")
            return 100  # Safe default
    
    def _check_duplicates(self, article: ArticleCreate) -> Optional[str]:
        """
        Check for duplicates using multiple strategies.
        
        Returns:
            Duplicate reason string or None if not a duplicate
        """
        # Normalize URL for better duplicate detection
        normalized_url = self._normalize_url(article.canonical_url)
        
        # Check URL first (strongest signal)
        if normalized_url in self.seen_urls:
            logger.debug(f"URL duplicate detected: {normalized_url}")
            return "url"
        
        # Check content hash (ensure we have one)
        if hasattr(article, 'content_hash') and article.content_hash:
            if article.content_hash in self.seen_hashes:
                logger.debug(f"Content hash duplicate detected: {article.content_hash[:10]}...")
                return "content_hash"
        
        # Check URL + title combination for RSS feeds that might change content
        url_title_key = f"{normalized_url}||{article.title.strip()}"
        if hasattr(self, 'seen_url_titles') and url_title_key in self.seen_url_titles:
            logger.debug(f"URL+title duplicate detected: {url_title_key[:50]}...")
            return "url_title"
        
        # Check content similarity using fingerprinting
        fingerprint = self._generate_content_fingerprint(article)
        if fingerprint in self.content_fingerprints:
            logger.debug(f"Content similarity duplicate detected: {fingerprint[:10]}...")
            return "content_similarity"
        
        return None
    
    def _generate_content_fingerprint(self, article: ArticleCreate) -> str:
        """Generate a fingerprint for content similarity detection."""
        # Create fingerprint from normalized title and first paragraph
        title_words = set(article.title.lower().split())
        
        # Extract first paragraph from content
        text_content = ContentCleaner.html_to_text(article.content)
        first_paragraph = text_content.split('\n')[0] if text_content else ""
        paragraph_words = set(first_paragraph.lower().split())
        
        # Combine significant words (length > 3)
        significant_words = {w for w in (title_words | paragraph_words) if len(w) > 3}
        
        # Create fingerprint from sorted words
        fingerprint_text = ' '.join(sorted(list(significant_words)[:20]))  # Top 20 words
        return hashlib.md5(fingerprint_text.encode('utf-8')).hexdigest()
    
    def _passes_quality_filter(self, article: ArticleCreate) -> bool:
        """Check if article passes quality filter."""
        # Check age filter
        if article.published_at:
            try:
                if article.published_at.tzinfo is not None:
                    # If published_at is timezone-aware, make current time timezone-aware too
                    current_time = datetime.now(article.published_at.tzinfo)
                else:
                    # If published_at is naive, use naive current time
                    current_time = datetime.utcnow()
                
                age_days = (current_time - article.published_at).days
                if age_days > self.max_age_days:
                    return False
            except Exception:
                # If there's any datetime issue, don't filter by age
                pass
        
        # Check content length with source-specific requirements
        text_content = ContentCleaner.html_to_text(article.content)
        min_length = self._get_minimum_content_length(article.canonical_url)
        
        content_length = len(text_content.strip())
        if content_length < min_length:
            logger.warning(f"Article '{article.title[:50]}...' content too short: {content_length} chars (min: {min_length})")
            return False
        
        # Check title length
        if len(article.title.strip()) < 10:
            return False
        
        return True
    
    def _record_article(self, article: ArticleCreate):
        """Record article in deduplication tracking."""
        # Normalize URL for consistent tracking
        normalized_url = self._normalize_url(article.canonical_url)
        self.seen_urls.add(normalized_url)
        
        # Track URL + title combination
        if not hasattr(self, 'seen_url_titles'):
            self.seen_url_titles = set()
        url_title_key = f"{normalized_url}||{article.title.strip()}"
        self.seen_url_titles.add(url_title_key)
        
        # Only add hash if we have one
        if hasattr(article, 'content_hash') and article.content_hash:
            self.seen_hashes.add(article.content_hash)
            
            fingerprint = self._generate_content_fingerprint(article)
            self.content_fingerprints[fingerprint] = article.content_hash
    
    def _detect_content_type(self, article: ArticleCreate) -> str:
        """Detect the type of content based on title, content, and metadata."""
        title_lower = article.title.lower()
        content_lower = article.content.lower()
        
        # Podcast detection
        if any(keyword in title_lower for keyword in ['stormcast', 'podcast', 'episode']):
            return 'podcast'
        
        # Announcement detection
        if any(keyword in title_lower for keyword in ['announcement', 'update', 'release', 'bounty']):
            return 'announcement'
        
        # Analysis detection
        if any(keyword in title_lower for keyword in ['analysis', 'research', 'investigation', 'report']):
            return 'analysis'
        
        # Default to article
        return 'article'
    
    def _normalize_authors(self, authors: List[str]) -> List[str]:
        """Normalize author names."""
        normalized = []
        
        for author in authors:
            # Clean whitespace
            author = ContentCleaner.normalize_whitespace(author)
            
            # Remove common prefixes/suffixes
            author = re.sub(r'^(by|author:?)\s+', '', author, flags=re.IGNORECASE)
            author = re.sub(r'\s+(writer|author)$', '', author, flags=re.IGNORECASE)
            
            # Basic name validation
            if len(author) > 2 and len(author) < 100:
                normalized.append(author)
        
        return normalized[:5]  # Limit to 5 authors
    
    def _normalize_tags(self, tags: List[str]) -> List[str]:
        """Normalize tags/categories."""
        normalized = set()
        
        for tag in tags:
            # Clean and normalize
            tag = ContentCleaner.normalize_whitespace(tag)
            tag = tag.lower().strip()
            
            # Remove empty or very short tags
            if len(tag) < 2 or len(tag) > 50:
                continue
            
            # Remove special characters except hyphens and underscores
            import re
            tag = re.sub(r'[^\w\s\-_]', '', tag)
            
            if tag:
                normalized.add(tag)
        
        return sorted(list(normalized))[:10]  # Limit to 10 tags
    
    def get_statistics(self) -> Dict[str, int]:
        """Get processing statistics."""
        return self.stats.copy()
    
    def reset_statistics(self):
        """Reset processing statistics."""
        for key in self.stats:
            self.stats[key] = 0
    
    def clear_deduplication_cache(self):
        """Clear deduplication cache."""
        self.seen_hashes.clear()
        self.seen_urls.clear()
        self.content_fingerprints.clear()
    
    def get_cache_size(self) -> Dict[str, int]:
        """Get current cache sizes."""
        return {
            'content_hashes': len(self.seen_hashes),
            'urls': len(self.seen_urls),
            'fingerprints': len(self.content_fingerprints)
        }


class BatchProcessor:
    """Utility for processing articles in batches."""
    
    def __init__(
        self,
        processor: ContentProcessor,
        batch_size: int = 100,
        max_concurrent: int = 3
    ):
        self.processor = processor
        self.batch_size = batch_size
        self.max_concurrent = max_concurrent
    
    async def process_batches(
        self,
        articles: List[ArticleCreate],
        existing_hashes: Optional[Set[str]] = None,
        existing_urls: Optional[Set[str]] = None
    ) -> DeduplicationResult:
        """
        Process articles in batches for better memory management.
        
        Args:
            articles: List of articles to process
            existing_hashes: Set of existing content hashes
            existing_urls: Set of existing URLs
            
        Returns:
            Combined DeduplicationResult
        """
        if not articles:
            return DeduplicationResult([], [], {'total': 0, 'processed': 0})
        
        logger.info(f"Processing {len(articles)} articles in batches of {self.batch_size}")
        
        # Split into batches
        batches = [
            articles[i:i + self.batch_size]
            for i in range(0, len(articles), self.batch_size)
        ]
        
        # Process batches with limited concurrency
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        async def process_batch(batch):
            async with semaphore:
                return await self.processor.process_articles(batch, existing_hashes, existing_urls)
        
        # Process all batches
        batch_results = await asyncio.gather(*[process_batch(batch) for batch in batches])
        
        # Combine results
        all_unique = []
        all_duplicates = []
        combined_stats = {'total': 0, 'unique': 0, 'duplicates': 0}
        
        for result in batch_results:
            all_unique.extend(result.unique_articles)
            all_duplicates.extend(result.duplicates)
            
            for key in combined_stats:
                combined_stats[key] += result.stats.get(key, 0)
        
        logger.info(f"Batch processing complete: {len(all_unique)} unique articles")
        
        return DeduplicationResult(all_unique, all_duplicates, combined_stats)


# Add missing import
import re
