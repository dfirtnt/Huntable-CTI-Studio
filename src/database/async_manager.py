"""
Modern Async Database Manager for CTI Scraper

Uses PostgreSQL with SQLAlchemy async for production-grade performance.
"""

import os
import asyncio
import logging
from typing import List, Optional, Dict, Any, AsyncGenerator
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    create_async_engine, 
    AsyncSession, 
    async_sessionmaker,
    AsyncEngine
)
from sqlalchemy import select, update, delete, func, and_, or_, desc, text
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import selectinload

from src.database.models import Base, SourceTable, ArticleTable, SourceCheckTable
from src.models.source import Source, SourceCreate, SourceUpdate, SourceFilter
from src.models.article import Article, ArticleCreate, ArticleUpdate
from src.services.deduplication import AsyncDeduplicationService

logger = logging.getLogger(__name__)


class AsyncDatabaseManager:
    """Modern async database manager with connection pooling and proper transaction handling."""
    
    def __init__(
        self,
        database_url: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://cti_user:cti_password_2024@postgres:5432/cti_scraper"),
        echo: bool = False,
        pool_size: int = 20,
        max_overflow: int = 30,
        pool_pre_ping: bool = True,
        pool_recycle: int = 3600
    ) -> None:
        """
        Initialize the async database manager.
        
        Args:
            database_url: PostgreSQL connection string
            echo: Enable SQL query logging
            pool_size: Database connection pool size
            max_overflow: Maximum overflow connections
            pool_pre_ping: Enable connection health checks
            pool_recycle: Connection recycle time in seconds
        """
        self.database_url = database_url
        self.echo = echo
        
        # Create async engine with connection pooling
        self.engine: AsyncEngine = create_async_engine(
            database_url,
            echo=echo,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=pool_pre_ping,
            pool_recycle=pool_recycle,
            future=True
        )
        
        # Create async session factory
        self.AsyncSessionLocal = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False
        )
        
        logger.info(f"Initialized async database manager with pool size {pool_size}")
    
    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get an async database session with proper cleanup."""
        session = self.AsyncSessionLocal()
        try:
            yield session
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            await session.close()
    
    async def create_tables(self):
        """Create all database tables asynchronously."""
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Failed to create tables: {e}")
            raise
    
    async def get_database_stats(self) -> Dict[str, Any]:
        """Get comprehensive database statistics."""
        try:
            async with self.get_session() as session:
                # Count sources
                sources_result = await session.execute(
                    select(func.count(SourceTable.id))
                )
                total_sources = sources_result.scalar()
                
                # Count active sources
                active_sources_result = await session.execute(
                    select(func.count(SourceTable.id)).where(SourceTable.active == True)
                )
                active_sources = active_sources_result.scalar()
                
                # Count articles
                articles_result = await session.execute(
                    select(func.count(ArticleTable.id))
                )
                total_articles = articles_result.scalar()
                
                # Articles in last 24h
                yesterday = datetime.now() - timedelta(days=1)
                recent_articles_result = await session.execute(
                    select(func.count(ArticleTable.id)).where(
                        ArticleTable.discovered_at >= yesterday
                    )
                )
                articles_last_24h = recent_articles_result.scalar()
                
                # Database size (approximate)
                # Calculate size based on content length
                content_size_result = await session.execute(
                    select(func.sum(func.length(ArticleTable.content)))
                )
                total_content_bytes = content_size_result.scalar() or 0
                
                # Add estimated size for metadata, titles, etc. (roughly 20% overhead)
                estimated_total_bytes = int(total_content_bytes * 1.2)
                db_size_mb = round(estimated_total_bytes / (1024 * 1024), 2)
                
                return {
                    "total_sources": total_sources or 0,
                    "active_sources": active_sources or 0,
                    "total_articles": total_articles or 0,
                    "articles_last_24h": articles_last_24h or 0,
                    "database_size_mb": db_size_mb
                }
                
        except Exception as e:
            logger.error(f"Failed to get database stats: {e}")
            return {
                "total_sources": 0,
                "active_sources": 0,
                "total_articles": 0,
                "articles_last_24h": 0,
                "database_size_mb": 0.0
            }
    
    async def list_sources(self, filter_params: Optional[SourceFilter] = None) -> List[Source]:
        """List all sources with optional filtering."""
        try:
            async with self.get_session() as session:
                query = select(SourceTable)
                
                if filter_params:
                    if filter_params.tier:
                        query = query.where(SourceTable.tier == filter_params.tier)
                    if filter_params.active is not None:
                        query = query.where(SourceTable.active == filter_params.active)
                    if filter_params.identifier_contains:
                        query = query.where(
                            SourceTable.identifier.contains(filter_params.identifier_contains)
                        )
                    if filter_params.name_contains:
                        query = query.where(
                            SourceTable.name.contains(filter_params.name_contains)
                        )
                
                query = query.order_by(SourceTable.name)
                result = await session.execute(query)
                db_sources = result.scalars().all()
                
                return [self._db_source_to_model(db_source) for db_source in db_sources]
                
        except Exception as e:
            logger.error(f"Failed to list sources: {e}")
            return []
    
    async def create_source(self, source_data: SourceCreate) -> Optional[Source]:
        """Create a new source."""
        try:
            async with self.get_session() as session:
                # Convert SourceCreate to SourceTable
                db_source = SourceTable(
                    identifier=source_data.identifier,
                    name=source_data.name,
                    url=source_data.url,
                    rss_url=source_data.rss_url,
                    check_frequency=source_data.check_frequency,
                    active=source_data.active,
                    config=source_data.config.dict() if source_data.config else {},
                    created_at=datetime.now(),
                    updated_at=datetime.now()
                )
                
                session.add(db_source)
                await session.commit()
                await session.refresh(db_source)
                
                logger.info(f"Created source: {source_data.name}")
                return self._db_source_to_model(db_source)
                
        except Exception as e:
            logger.error(f"Failed to create source: {e}")
            return None
    
    async def get_source(self, source_id: int) -> Optional[Source]:
        """Get a specific source by ID."""
        try:
            async with self.get_session() as session:
                result = await session.execute(
                    select(SourceTable).where(SourceTable.id == source_id)
                )
                db_source = result.scalar_one_or_none()
                
                if db_source:
                    return self._db_source_to_model(db_source)
                return None
                
        except Exception as e:
            logger.error(f"Failed to get source {source_id}: {e}")
            return None
    
    async def update_source(self, source_id: int, update_data: SourceUpdate) -> Optional[Source]:
        """Update a source with proper transaction handling."""
        try:
            async with self.get_session() as session:
                # Get the source
                result = await session.execute(
                    select(SourceTable).where(SourceTable.id == source_id)
                )
                db_source = result.scalar_one_or_none()
                
                if not db_source:
                    return None
                
                # Update fields
                update_dict = update_data.dict(exclude_unset=True)
                for field, value in update_dict.items():
                    if field == 'config' and value:
                        setattr(db_source, field, value.dict())
                    else:
                        setattr(db_source, field, value)
                
                # Update timestamp
                db_source.updated_at = datetime.now()
                
                await session.commit()
                await session.refresh(db_source)
                
                logger.info(f"Successfully updated source: {db_source.identifier}")
                return self._db_source_to_model(db_source)
                
        except Exception as e:
            logger.error(f"Failed to update source {source_id}: {e}")
            raise
    
    async def toggle_source_status(self, source_id: int) -> Optional[Dict[str, Any]]:
        """Toggle source active status with proper transaction handling."""
        try:
            async with self.get_session() as session:
                # Get the source
                result = await session.execute(
                    select(SourceTable).where(SourceTable.id == source_id)
                )
                db_source = result.scalar_one_or_none()
                
                if not db_source:
                    return None
                
                # Toggle the status
                old_status = db_source.active
                new_status = not old_status
                db_source.active = new_status
                db_source.updated_at = datetime.now()
                
                # Commit the transaction
                await session.commit()
                await session.refresh(db_source)
                
                logger.info(f"Successfully toggled source {source_id} from {old_status} to {new_status}")
                
                return {
                    "source_id": source_id,
                    "source_name": db_source.name,
                    "old_status": old_status,
                    "new_status": new_status,
                    "success": True
                }
                
        except Exception as e:
            logger.error(f"Failed to toggle source {source_id}: {e}")
            raise
    
    async def update_source_health(self, source_id: int, success: bool, response_time: float = 0.0):
        """Update source health metrics."""
        try:
            async with self.get_session() as session:
                result = await session.execute(
                    select(SourceTable).where(SourceTable.id == source_id)
                )
                db_source = result.scalar_one_or_none()
                
                if not db_source:
                    return
                
                # Update metrics
                if success:
                    db_source.consecutive_failures = 0
                    db_source.last_success = datetime.utcnow()
                else:
                    db_source.consecutive_failures += 1
                
                db_source.last_check = datetime.utcnow()
                
                # Update average response time
                if db_source.average_response_time == 0.0:
                    db_source.average_response_time = response_time
                else:
                    db_source.average_response_time = (db_source.average_response_time + response_time) / 2
                
                await session.commit()
                
        except Exception as e:
            logger.error(f"Failed to update source health for {source_id}: {e}")
            raise
    
    async def update_source_article_count(self, source_id: int):
        """Update the total articles count for a source."""
        try:
            async with self.get_session() as session:
                # Count articles for this source
                result = await session.execute(
                    select(func.count(ArticleTable.id)).where(ArticleTable.source_id == source_id)
                )
                article_count = result.scalar()
                
                # Update the source's total_articles field
                await session.execute(
                    update(SourceTable)
                    .where(SourceTable.id == source_id)
                    .values(total_articles=article_count)
                )
                
                await session.commit()
                logger.info(f"Updated source {source_id} article count to {article_count}")
                
        except Exception as e:
            logger.error(f"Failed to update source article count for {source_id}: {e}")
            raise
    
    async def list_articles(self, limit: Optional[int] = None) -> List[Article]:
        """List articles with optional limit."""
        try:
            async with self.get_session() as session:
                query = select(ArticleTable).order_by(desc(ArticleTable.discovered_at))
                
                if limit:
                    query = query.limit(limit)
                
                result = await session.execute(query)
                db_articles = result.scalars().all()
                
                return [self._db_article_to_model(db_article) for db_article in db_articles]
                
        except Exception as e:
            logger.error(f"Failed to list articles: {e}")
            return []
    
    async def get_article(self, article_id: int) -> Optional[Article]:
        """Get a specific article by ID."""
        try:
            async with self.get_session() as session:
                result = await session.execute(
                    select(ArticleTable).where(ArticleTable.id == article_id)
                )
                db_article = result.scalar_one_or_none()
                
                if db_article:
                    return self._db_article_to_model(db_article)
                return None
                
        except Exception as e:
            logger.error(f"Failed to get article {article_id}: {e}")
            return None
    
    async def get_article_by_url(self, canonical_url: str) -> Optional[Article]:
        """Get a specific article by canonical URL."""
        try:
            async with self.get_session() as session:
                result = await session.execute(
                    select(ArticleTable).where(ArticleTable.canonical_url == canonical_url)
                )
                db_article = result.scalar_one_or_none()
                
                if db_article:
                    return self._db_article_to_model(db_article)
                return None
                
        except Exception as e:
            logger.error(f"Failed to get article by URL {canonical_url}: {e}")
            return None
    
    async def list_articles_by_source(self, source_id: int) -> List[Article]:
        """Get all articles for a specific source."""
        try:
            async with self.get_session() as session:
                query = select(ArticleTable).where(ArticleTable.source_id == source_id).order_by(desc(ArticleTable.discovered_at))
                result = await session.execute(query)
                db_articles = result.scalars().all()
                
                return [self._db_article_to_model(db_article) for db_article in db_articles]
                
        except Exception as e:
            logger.error(f"Failed to list articles by source {source_id}: {e}")
            return []
    
    async def create_article(self, article: ArticleCreate) -> Optional[Article]:
        """Create a new article in the database with deduplication."""
        try:
            async with self.get_session() as session:
                # Use deduplication service
                dedup_service = AsyncDeduplicationService(session)
                
                # Create article with deduplication checks
                created, new_article, similar_articles = await dedup_service.create_article_with_deduplication(article)
                
                if not created:
                    logger.info(f"Duplicate article detected: {article.title}")
                    # Return the existing article
                    return self._db_article_to_model(new_article)
                
                # Log similar articles if found
                if similar_articles:
                    logger.info(f"Created article with {len(similar_articles)} similar articles: {article.title}")
                
                await session.commit()
                await session.refresh(new_article)
                
                logger.info(f"Created article with deduplication: {article.title}")
                return self._db_article_to_model(new_article)
                
        except Exception as e:
            logger.error(f"Failed to create article: {e}")
            return None
    
    async def update_article(self, article_id: int, update_data: ArticleUpdate) -> Optional[Article]:
        """Update an existing article."""
        try:
            async with self.get_session() as session:
                # Get the article
                result = await session.execute(
                    select(ArticleTable).where(ArticleTable.id == article_id)
                )
                db_article = result.scalar_one_or_none()
                
                if not db_article:
                    return None
                
                # Update fields
                update_dict = update_data.dict(exclude_unset=True)
                for field, value in update_dict.items():
                    if field == 'metadata' and value:
                        setattr(db_article, 'article_metadata', value)
                    else:
                        setattr(db_article, field, value)
                
                # Update timestamp
                db_article.updated_at = datetime.utcnow()
                
                await session.commit()
                await session.refresh(db_article)
                
                logger.info(f"Updated article: {db_article.title}")
                return self._db_article_to_model(db_article)
                
        except Exception as e:
            logger.error(f"Failed to update article {article_id}: {e}")
            return None
    
    async def delete_article(self, article_id: int) -> bool:
        """Delete an article."""
        try:
            async with self.get_session() as session:
                # Get the article
                result = await session.execute(
                    select(ArticleTable).where(ArticleTable.id == article_id)
                )
                db_article = result.scalar_one_or_none()
                
                if not db_article:
                    return False
                
                # Delete the article
                await session.delete(db_article)
                await session.commit()
                
                logger.info(f"Deleted article: {db_article.title}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to delete article {article_id}: {e}")
            return False
    
    async def get_existing_content_hashes(self, limit: int = 10000) -> set:
        """Get existing content hashes for deduplication."""
        try:
            async with self.get_session() as session:
                result = await session.execute(
                    select(ArticleTable.content_hash).limit(limit)
                )
                hashes = result.scalars().all()
                return set(hashes)
                
        except Exception as e:
            logger.error(f"Failed to get existing content hashes: {e}")
            return set()
    
    async def get_source_quality_stats(self) -> List[Dict[str, Any]]:
        """Get quality statistics for all sources."""
        try:
            async with self.get_session() as session:
                # Raw SQL query for better performance
                query = """
                SELECT 
                    s.id,
                    s.name,
                    s.identifier,
                    s.active,
                    COUNT(a.id) as total_articles,
                    COUNT(CASE WHEN a.article_metadata->>'training_category' = 'rejected' THEN 1 END) as rejected_count,
                    COUNT(CASE WHEN a.article_metadata->>'training_category' = 'chosen' THEN 1 END) as chosen_count,
                    COUNT(CASE WHEN a.article_metadata->>'training_category' IS NULL OR a.article_metadata->>'training_category' = 'unclassified' THEN 1 END) as unclassified_count,
                    CASE 
                        WHEN COUNT(a.id) > 0 THEN 
                            ROUND(COUNT(CASE WHEN a.article_metadata->>'training_category' = 'rejected' THEN 1 END)::numeric / COUNT(a.id)::numeric * 100, 1)
                        ELSE 0 
                    END as rejection_rate,
                    CASE 
                        WHEN COUNT(a.id) > 0 THEN 
                            ROUND(COUNT(CASE WHEN a.article_metadata->>'training_category' = 'chosen' THEN 1 END)::numeric / COUNT(a.id)::numeric * 100, 1)
                        ELSE 0 
                    END as acceptance_rate
                FROM sources s 
                LEFT JOIN articles a ON s.id = a.source_id 
                GROUP BY s.id, s.name, s.identifier, s.active
                ORDER BY rejected_count DESC, rejection_rate DESC
                """
                
                result = await session.execute(text(query))
                rows = result.fetchall()
                
                return [
                    {
                        "source_id": row.id,
                        "name": row.name,
                        "identifier": row.identifier,
                        "active": row.active,
                        "total_articles": row.total_articles,
                        "rejected_count": row.rejected_count,
                        "chosen_count": row.chosen_count,
                        "unclassified_count": row.unclassified_count,
                        "rejection_rate": row.rejection_rate,
                        "acceptance_rate": row.acceptance_rate
                    }
                    for row in rows
                ]
                
        except Exception as e:
            logger.error(f"Failed to get source quality stats: {e}")
            return []
    
    def _db_source_to_model(self, db_source: SourceTable) -> Source:
        """Convert database source to Pydantic model."""
        from src.models.source import SourceConfig
        
        return Source(
            id=db_source.id,
            identifier=db_source.identifier,
            name=db_source.name,
            url=db_source.url,
            rss_url=db_source.rss_url,
            check_frequency=db_source.check_frequency,
            active=db_source.active,
            config=SourceConfig.parse_obj(db_source.config),
            last_check=db_source.last_check,
            last_success=db_source.last_success,
            consecutive_failures=db_source.consecutive_failures,
            total_articles=db_source.total_articles,
            success_rate=db_source.success_rate,
            average_response_time=db_source.average_response_time
        )
    
    def _db_article_to_model(self, db_article: ArticleTable) -> Article:
        """Convert database article to Pydantic model."""
        return Article(
            id=db_article.id,
            source_id=db_article.source_id,
            canonical_url=db_article.canonical_url,
            title=db_article.title,
            published_at=db_article.published_at,
            modified_at=db_article.modified_at,
            authors=db_article.authors,
            tags=db_article.tags,
            summary=db_article.summary,
            content=db_article.content,
            content_hash=db_article.content_hash,
            metadata=db_article.article_metadata,
            quality_score=db_article.quality_score,
            word_count=db_article.word_count,
            discovered_at=db_article.discovered_at,
            processing_status=db_article.processing_status
        )
    
    async def get_deduplication_stats(self) -> Dict[str, Any]:
        """Get deduplication system statistics."""
        try:
            async with self.get_session() as session:
                stats = {}
                
                # Content hash duplicates
                content_hash_query = """
                SELECT content_hash, COUNT(*) as count 
                FROM articles 
                GROUP BY content_hash 
                HAVING COUNT(*) > 1
                """
                result = await session.execute(text(content_hash_query))
                duplicate_hashes = result.fetchall()
                
                stats['content_hash_duplicates'] = len(duplicate_hashes)
                stats['duplicate_details'] = [
                    {'hash': row[0][:10] + '...', 'count': row[1]} 
                    for row in duplicate_hashes[:10]
                ]
                
                # SimHash coverage
                simhash_query = """
                SELECT 
                    COUNT(*) as total_articles,
                    COUNT(CASE WHEN simhash IS NOT NULL THEN 1 END) as simhash_articles
                FROM articles
                """
                result = await session.execute(text(simhash_query))
                row = result.fetchone()
                
                if row and row[0] > 0:
                    stats['simhash_coverage'] = round((row[1] / row[0]) * 100, 1)
                else:
                    stats['simhash_coverage'] = 0
                
                # Near duplicates (simhash buckets)
                bucket_query = """
                SELECT simhash_bucket, COUNT(*) as count
                FROM articles 
                WHERE simhash_bucket IS NOT NULL
                GROUP BY simhash_bucket
                ORDER BY count DESC
                LIMIT 10
                """
                result = await session.execute(text(bucket_query))
                buckets = result.fetchall()
                
                stats['bucket_distribution'] = [
                    {'bucket_id': row[0], 'articles_count': row[1]} 
                    for row in buckets
                ]
                
                if buckets:
                    stats['most_active_bucket'] = [buckets[0][0], buckets[0][1]]
                else:
                    stats['most_active_bucket'] = None
                
                # Potential near duplicates
                stats['near_duplicates'] = sum(row[1] for row in buckets if row[1] > 1)
                
                # Unique URLs
                url_query = "SELECT COUNT(DISTINCT canonical_url) FROM articles"
                result = await session.execute(text(url_query))
                stats['unique_urls'] = result.scalar() or 0
                
                # Duplicate rate
                total_articles = await session.scalar(select(func.count(ArticleTable.id)))
                if total_articles > 0:
                    stats['duplicate_rate'] = round((stats['content_hash_duplicates'] / total_articles) * 100, 1)
                else:
                    stats['duplicate_rate'] = 0
                
                return stats
                
        except Exception as e:
            logger.error(f"Failed to get deduplication stats: {e}")
            return {
                'content_hash_duplicates': 0,
                'duplicate_details': [],
                'simhash_coverage': 0,
                'bucket_distribution': [],
                'most_active_bucket': None,
                'near_duplicates': 0,
                'unique_urls': 0,
                'duplicate_rate': 0
            }
    
    async def get_performance_metrics(self) -> List[Dict[str, Any]]:
        """Get database performance metrics."""
        try:
            async with self.get_session() as session:
                metrics = []
                
                # Test queries with timing
                import time
                
                # Articles count query
                start_time = time.time()
                result = await session.scalar(select(func.count(ArticleTable.id)))
                query_time = (time.time() - start_time) * 1000
                metrics.append({
                    'test': 'Articles Count',
                    'query_time_ms': round(query_time, 2),
                    'rows_returned': result or 0
                })
                
                # Sources count query
                start_time = time.time()
                result = await session.scalar(select(func.count(SourceTable.id)))
                query_time = (time.time() - start_time) * 1000
                metrics.append({
                    'test': 'Sources Count',
                    'query_time_ms': round(query_time, 2),
                    'rows_returned': result or 0
                })
                
                # Recent articles query
                start_time = time.time()
                result = await session.execute(
                    select(ArticleTable.id)
                    .order_by(desc(ArticleTable.discovered_at))
                    .limit(10)
                )
                query_time = (time.time() - start_time) * 1000
                metrics.append({
                    'test': 'Recent Articles',
                    'query_time_ms': round(query_time, 2),
                    'rows_returned': len(result.fetchall())
                })
                
                return metrics
                
        except Exception as e:
            logger.error(f"Failed to get performance metrics: {e}")
            return []
    
    async def get_ingestion_analytics(self) -> Dict[str, Any]:
        """Get ingestion analytics and trends."""
        try:
            async with self.get_session() as session:
                analytics = {}
                
                # Total stats
                total_articles = await session.scalar(select(func.count(ArticleTable.id)))
                total_sources = await session.scalar(select(func.count(SourceTable.id)))
                
                # Date range queries
                earliest_query = select(func.min(ArticleTable.discovered_at))
                latest_query = select(func.max(ArticleTable.discovered_at))
                
                earliest_article = await session.scalar(earliest_query)
                latest_article = await session.scalar(latest_query)
                
                analytics['total_stats'] = {
                    'total_articles': total_articles or 0,
                    'total_sources': total_sources or 0,
                    'earliest_article': earliest_article.isoformat() if earliest_article else None,
                    'latest_article': latest_article.isoformat() if latest_article else None
                }
                
                # Daily trends (last 30 days)
                daily_query = """
                SELECT 
                    DATE(discovered_at) as date,
                    COUNT(*) as articles_count,
                    COUNT(DISTINCT source_id) as sources_count
                FROM articles 
                WHERE discovered_at >= NOW() - INTERVAL '30 days'
                GROUP BY DATE(discovered_at)
                ORDER BY date DESC
                LIMIT 30
                """
                result = await session.execute(text(daily_query))
                daily_trends = [
                    {
                        'date': row[0].strftime('%Y-%m-%d'),
                        'articles_count': row[1],
                        'sources_count': row[2]
                    }
                    for row in result.fetchall()
                ]
                analytics['daily_trends'] = daily_trends
                
                # Hourly distribution (today)
                hourly_query = """
                SELECT 
                    EXTRACT(hour FROM discovered_at) as hour,
                    COUNT(*) as articles_count
                FROM articles 
                WHERE DATE(discovered_at) = CURRENT_DATE
                GROUP BY EXTRACT(hour FROM discovered_at)
                ORDER BY hour
                """
                result = await session.execute(text(hourly_query))
                hourly_data = {row[0]: row[1] for row in result.fetchall()}
                
                hourly_distribution = [
                    {'hour': i, 'articles_count': hourly_data.get(i, 0)}
                    for i in range(24)
                ]
                analytics['hourly_distribution'] = hourly_distribution
                
                # Source breakdown (last 7 days)
                source_query = """
                SELECT 
                    s.name as source_name,
                    COUNT(a.id) as articles_count,
                    ROUND(AVG(CAST(a.article_metadata->>'threat_hunting_score' AS FLOAT)), 1) as avg_hunt_score,
                    COUNT(CASE WHEN a.article_metadata->>'training_category' = 'chosen' THEN 1 END) as chosen_count,
                    COUNT(CASE WHEN a.article_metadata->>'training_category' = 'rejected' THEN 1 END) as rejected_count,
                    COUNT(CASE WHEN a.article_metadata->>'training_category' IS NULL OR a.article_metadata->>'training_category' = 'unclassified' THEN 1 END) as unclassified_count
                FROM sources s
                LEFT JOIN articles a ON s.id = a.source_id
                WHERE a.discovered_at >= NOW() - INTERVAL '7 days'
                GROUP BY s.id, s.name
                ORDER BY articles_count DESC
                LIMIT 10
                """
                result = await session.execute(text(source_query))
                source_breakdown = []
                
                for row in result.fetchall():
                    total = row[1] or 0
                    chosen = row[3] or 0
                    rejected = row[4] or 0
                    unclassified = row[5] or 0
                    
                    source_breakdown.append({
                        'source_name': row[0],
                        'articles_count': total,
                        'avg_hunt_score': row[2] or 0,
                        'chosen_count': chosen,
                        'rejected_count': rejected,
                        'unclassified_count': unclassified,
                        'chosen_ratio': f"{round((chosen/total)*100, 1)}%" if total > 0 else "0%",
                        'rejected_ratio': f"{round((rejected/total)*100, 1)}%" if total > 0 else "0%",
                        'unclassified_ratio': f"{round((unclassified/total)*100, 1)}%" if total > 0 else "0%"
                    })
                
                analytics['source_breakdown'] = source_breakdown
                
                return analytics
                
        except Exception as e:
            logger.error(f"Failed to get ingestion analytics: {e}")
            return {
                'total_stats': {'total_articles': 0, 'total_sources': 0},
                'daily_trends': [],
                'hourly_distribution': [],
                'source_breakdown': []
            }

    async def close(self):
        """Close database connections properly."""
        await self.engine.dispose()
        logger.info("Database connections closed")


# Global instance for easy access
async_db_manager = AsyncDatabaseManager()
