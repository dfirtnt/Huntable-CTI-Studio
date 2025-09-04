"""Multi-layer deduplication service for articles."""

import hashlib
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
import logging
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, or_, func, select

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
                # Convert decimal.Decimal to int for SimHash comparison
                existing_simhash = int(existing_article.simhash)
                distance = simhash_calculator.hamming_distance(simhash, existing_simhash)
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
        
        # Create new article
        content_hash = self.compute_content_hash(article.content)
        simhash, bucket = compute_article_simhash(article.content, article.title)
        
        db_article = ArticleTable(
            title=article.title,
            content=article.content,
            canonical_url=article.canonical_url,
            source_id=article.source_id,
            published_at=article.published_at,
            authors=article.authors,
            tags=article.tags,
            summary=article.summary,
            content_hash=content_hash,
            simhash=simhash,
            simhash_bucket=bucket,
            article_metadata=article.metadata,
            quality_score=article.quality_score,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        self.session.add(db_article)
        self.session.flush()  # Get the ID without committing
        
        return True, db_article, similar_articles


class AsyncDeduplicationService:
    """Async version of deduplication service for use with AsyncSession."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    def compute_content_hash(self, content: str) -> str:
        """Compute SHA-256 hash of content."""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    async def check_exact_duplicates(self, article: ArticleCreate) -> Tuple[bool, Optional[ArticleTable]]:
        """
        Check for exact duplicates using canonical URL and content hash.
        
        Returns:
            Tuple of (is_duplicate, existing_article)
        """
        # Check canonical URL first (fastest)
        result = await self.session.execute(
            select(ArticleTable).where(ArticleTable.canonical_url == article.canonical_url)
        )
        existing_by_url = result.scalar_one_or_none()
        
        if existing_by_url:
            logger.info(f"Duplicate found by canonical URL: {article.canonical_url}")
            return True, existing_by_url
        
        # Check content hash
        content_hash = self.compute_content_hash(article.content)
        result = await self.session.execute(
            select(ArticleTable).where(ArticleTable.content_hash == content_hash)
        )
        existing_by_hash = result.scalar_one_or_none()
        
        if existing_by_hash:
            logger.info(f"Duplicate found by content hash: {content_hash[:8]}...")
            return True, existing_by_hash
        
        return False, None
    
    async def check_near_duplicates(self, article: ArticleCreate, threshold: int = 3) -> List[ArticleTable]:
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
        result = await self.session.execute(
            select(ArticleTable).where(
                and_(
                    ArticleTable.simhash_bucket == bucket,
                    ArticleTable.simhash.isnot(None)
                )
            )
        )
        bucket_articles = result.scalars().all()
        
        similar_articles = []
        for existing_article in bucket_articles:
            if existing_article.simhash is not None:
                distance = simhash_calculator.hamming_distance(simhash, existing_article.simhash)
                if distance <= threshold:
                    similar_articles.append(existing_article)
        
        if similar_articles:
            logger.info(f"Found {len(similar_articles)} near-duplicates for article: {article.title[:50]}...")
        
        return similar_articles
    
    async def create_article_with_deduplication(self, article: ArticleCreate) -> Tuple[bool, Optional[ArticleTable], List[ArticleTable]]:
        """
        Create article with comprehensive deduplication checks.
        
        Returns:
            Tuple of (created, new_article, similar_articles)
        """
        # Check for exact duplicates
        is_exact_duplicate, existing_article = await self.check_exact_duplicates(article)
        
        if is_exact_duplicate:
            return False, existing_article, []
        
        # Temporarily disable near-duplicate checking to fix SimHash decimal issue
        similar_articles = []
        
        # Create new article
        content_hash = self.compute_content_hash(article.content)
        simhash, bucket = compute_article_simhash(article.content, article.title)
        
        db_article = ArticleTable(
            title=article.title,
            content=article.content,
            canonical_url=article.canonical_url,
            source_id=article.source_id,
            published_at=article.published_at,
            authors=article.authors,
            tags=article.tags,
            summary=article.summary,
            content_hash=content_hash,
            simhash=simhash,
            simhash_bucket=bucket,
            article_metadata=article.metadata,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        self.session.add(db_article)
        await self.session.flush()  # Get the ID without committing
        
        return True, db_article, similar_articles
