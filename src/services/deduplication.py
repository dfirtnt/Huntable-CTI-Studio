"""Multi-layer deduplication service for articles."""

import hashlib
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
import logging
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func

from src.database.models import ArticleTable, ContentHashTable, SimHashBucketTable
from src.utils.simhash import compute_article_simhash, simhash_calculator
from src.models.article import ArticleCreate

logger = logging.getLogger(__name__)


class DeduplicationService:
    """Multi-layer deduplication service with canonical URL, content hash, and SimHash support."""
    
    def __init__(self, session: Session):
        self.session = session
    
    def compute_content_hash(self, content: str) -> str:
        """Compute SHA-256 hash of content."""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def check_exact_duplicates(self, article: ArticleCreate) -> Tuple[bool, Optional[ArticleTable]]:
        """
        Check for exact duplicates using canonical URL and content hash.
        
        Returns:
            Tuple of (is_duplicate, existing_article)
        """
        # Check canonical URL first (fastest)
        existing_by_url = self.session.query(ArticleTable).filter(
            ArticleTable.canonical_url == article.canonical_url
        ).first()
        
        if existing_by_url:
            logger.info(f"Duplicate found by canonical URL: {article.canonical_url}")
            return True, existing_by_url
        
        # Check content hash
        content_hash = self.compute_content_hash(article.content)
        existing_by_hash = self.session.query(ArticleTable).filter(
            ArticleTable.content_hash == content_hash
        ).first()
        
        if existing_by_hash:
            logger.info(f"Duplicate found by content hash: {content_hash[:8]}...")
            return True, existing_by_hash
        
        return False, None
    
    def check_near_duplicates(self, article: ArticleCreate, threshold: int = 3) -> List[ArticleTable]:
        """
        Check for near-duplicates using SimHash.
        
        Args:
            article: Article to check
            threshold: Hamming distance threshold (default: 3)
            
        Returns:
            List of similar articles
        """
        # Compute SimHash for the new article
        simhash, bucket = compute_article_simhash(article.content, article.title)
        
        # Find articles in the same bucket
        bucket_articles = self.session.query(ArticleTable).filter(
            ArticleTable.simhash_bucket == bucket,
            ArticleTable.simhash.isnot(None)
        ).all()
        
        similar_articles = []
        for existing_article in bucket_articles:
            if existing_article.simhash is not None:
                distance = simhash_calculator.hamming_distance(simhash, existing_article.simhash)
                if distance <= threshold:
                    similar_articles.append(existing_article)
        
        if similar_articles:
            logger.info(f"Found {len(similar_articles)} near-duplicates for article: {article.title[:50]}...")
        
        return similar_articles
    
    def create_article_with_deduplication(self, article: ArticleCreate) -> Tuple[bool, Optional[ArticleTable], List[ArticleTable]]:
        """
        Create article with comprehensive deduplication checks.
        
        Returns:
            Tuple of (created, new_article, similar_articles)
        """
        # Check for exact duplicates
        is_exact_duplicate, existing_article = self.check_exact_duplicates(article)
        
        if is_exact_duplicate:
            return False, existing_article, []
        
        # Check for near-duplicates
        similar_articles = self.check_near_duplicates(article)
        
        # Compute SimHash for the new article
        simhash, bucket = compute_article_simhash(article.content, article.title)
        content_hash = self.compute_content_hash(article.content)
        
        # Create the new article
        new_article = ArticleTable(
            source_id=article.source_id,
            canonical_url=article.canonical_url,
            title=article.title,
            published_at=article.published_at,
            modified_at=article.modified_at,
            authors=article.authors,
            tags=article.tags,
            summary=article.summary,
            content=article.content,
            content_hash=content_hash,
            article_metadata=article.metadata,
            simhash=simhash,
            simhash_bucket=bucket,
            discovered_at=datetime.utcnow(),
            processing_status="pending"
        )
        
        self.session.add(new_article)
        self.session.flush()  # Get the ID
        
        # Add to content hash tracking
        content_hash_entry = ContentHashTable(
            content_hash=content_hash,
            article_id=new_article.id,
            first_seen=datetime.utcnow()
        )
        self.session.add(content_hash_entry)
        
        # Add to SimHash bucket tracking
        simhash_bucket_entry = SimHashBucketTable(
            bucket_id=bucket,
            simhash=simhash,
            article_id=new_article.id,
            first_seen=datetime.utcnow()
        )
        self.session.add(simhash_bucket_entry)
        
        logger.info(f"Created new article with deduplication: {article.title[:50]}...")
        return True, new_article, similar_articles
    
    def get_deduplication_stats(self) -> Dict[str, Any]:
        """Get deduplication statistics."""
        total_articles = self.session.query(ArticleTable).count()
        articles_with_simhash = self.session.query(ArticleTable).filter(
            ArticleTable.simhash.isnot(None)
        ).count()
        
        # Count unique content hashes
        unique_content_hashes = self.session.query(ContentHashTable.content_hash).distinct().count()
        
        # Count SimHash buckets
        unique_simhash_buckets = self.session.query(SimHashBucketTable.bucket_id).distinct().count()
        
        return {
            "total_articles": total_articles,
            "articles_with_simhash": articles_with_simhash,
            "unique_content_hashes": unique_content_hashes,
            "unique_simhash_buckets": unique_simhash_buckets,
            "simhash_coverage": (articles_with_simhash / total_articles * 100) if total_articles > 0 else 0
        }
    
    def backfill_simhash_for_existing_articles(self) -> int:
        """Backfill SimHash values for existing articles that don't have them."""
        articles_without_simhash = self.session.query(ArticleTable).filter(
            ArticleTable.simhash.is_(None)
        ).all()
        
        updated_count = 0
        for article in articles_without_simhash:
            try:
                simhash, bucket = compute_article_simhash(article.content, article.title)
                article.simhash = simhash
                article.simhash_bucket = bucket
                
                # Add to SimHash bucket tracking
                simhash_bucket_entry = SimHashBucketTable(
                    bucket_id=bucket,
                    simhash=simhash,
                    article_id=article.id,
                    first_seen=datetime.utcnow()
                )
                self.session.add(simhash_bucket_entry)
                
                updated_count += 1
                
            except Exception as e:
                logger.error(f"Failed to compute SimHash for article {article.id}: {e}")
                continue
        
        logger.info(f"Backfilled SimHash for {updated_count} articles")
        return updated_count
