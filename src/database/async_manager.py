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
from sqlalchemy import select, update, delete, func, and_, or_, desc
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import selectinload

from src.database.models import Base, SourceTable, ArticleTable, SourceCheckTable
from src.models.source import Source, SourceCreate, SourceUpdate, SourceFilter
from src.models.article import Article, ArticleCreate, ArticleUpdate
from src.services.deduplication import DeduplicationService

logger = logging.getLogger(__name__)


class AsyncDatabaseManager:
    """Modern async database manager with connection pooling and proper transaction handling."""
    
    def __init__(
        self,
        database_url: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:password@localhost:5432/cti_scraper"),
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
                dedup_service = DeduplicationService(session)
                
                # Create article with deduplication checks
                created, new_article, similar_articles = dedup_service.create_article_with_deduplication(article)
                
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
    
    async def close(self):
        """Close database connections properly."""
        await self.engine.dispose()
        logger.info("Database connections closed")


# Global instance for easy access
async_db_manager = AsyncDatabaseManager()
