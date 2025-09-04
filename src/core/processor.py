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
    validate_content, MetadataExtractor, ThreatHuntingScorer
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
        # Quality scoring removed
        self.similarity_threshold = similarity_threshold
        self.max_age_days = max_age_days
        self.enable_content_enhancement = enable_content_enhancement
        
        # Deduplication tracking
        self.seen_hashes: Set[str] = set()
        self.seen_urls: Set[str] = set()
        self.content_fingerprints: Dict[str, str] = {}  # fingerprint -> content_hash
        
        # Processing statistics
        self.stats = {
            'total_processed': 0,
            'duplicates_removed': 0,
            'enhanced_articles': 0,
            'validation_failures': 0
        }
    
    async def process_articles(
        self,
        articles: List[ArticleCreate],
        existing_hashes: Optional[Set[str]] = None
    ) -> DeduplicationResult:
        """
        Process articles with deduplication, normalization, and quality filtering.
        
        Args:
            articles: List of articles to process
            existing_hashes: Set of existing content hashes to check against
            
        Returns:
            DeduplicationResult with unique articles and statistics
        """
        if not articles:
            return DeduplicationResult([], [], {'total': 0, 'processed': 0})
        
        logger.info(f"Processing {len(articles)} articles")
        
        # Initialize existing hashes if provided
        if existing_hashes:
            self.seen_hashes.update(existing_hashes)
        
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
                    # Quality filtering removed - accept all articles
                    unique_articles.append(processed_article)
                    self._record_article(processed_article)
                
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
            
            # Normalize content
            normalized_title = ContentCleaner.normalize_whitespace(article.title)
            normalized_content = ContentCleaner.clean_html(article.content)
            
            # Generate or update content hash
            content_hash = ContentCleaner.calculate_content_hash(normalized_title, normalized_content)
            
            # Extract/enhance metadata if enabled
            enhanced_metadata = article.metadata.copy()
            
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
            
            # Enhanced threat hunting scoring using Windows malware keywords
            threat_hunting_analysis = ThreatHuntingScorer.score_threat_hunting_content(
                article.title, article.content
            )
            enhanced.update(threat_hunting_analysis)
            
            # Processing timestamp
            enhanced['processed_at'] = datetime.utcnow().isoformat()
            
        except Exception as e:
            logger.warning(f"Error enhancing metadata: {e}")
        
        return enhanced
    
    def _check_duplicates(self, article: ArticleCreate) -> Optional[str]:
        """
        Check for duplicates using multiple strategies.
        
        Returns:
            Duplicate reason string or None if not a duplicate
        """
        # Check content hash (ensure we have one)
        if hasattr(article, 'content_hash') and article.content_hash:
            if article.content_hash in self.seen_hashes:
                return "content_hash"
        
        # Check URL
        if article.canonical_url in self.seen_urls:
            return "url"
        
        # Check content similarity using fingerprinting
        fingerprint = self._generate_content_fingerprint(article)
        if fingerprint in self.content_fingerprints:
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
    
    # Quality filter method removed
    
    def _record_article(self, article: ArticleCreate):
        """Record article in deduplication tracking."""
        # Only add hash if we have one
        if hasattr(article, 'content_hash') and article.content_hash:
            self.seen_hashes.add(article.content_hash)
            
            fingerprint = self._generate_content_fingerprint(article)
            self.content_fingerprints[fingerprint] = article.content_hash
        
        self.seen_urls.add(article.canonical_url)
    
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
        existing_hashes: Optional[Set[str]] = None
    ) -> DeduplicationResult:
        """
        Process articles in batches for better memory management.
        
        Args:
            articles: List of articles to process
            existing_hashes: Set of existing content hashes
            
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
                return await self.processor.process_articles(batch, existing_hashes)
        
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
