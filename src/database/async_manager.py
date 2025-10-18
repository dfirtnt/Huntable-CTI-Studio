"""
Modern Async Database Manager for CTI Scraper

Uses PostgreSQL with SQLAlchemy async for production-grade performance.
"""

import os
import asyncio
import logging
from typing import List, Optional, Dict, Any, AsyncGenerator, Set
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    create_async_engine, 
    AsyncSession, 
    async_sessionmaker,
    AsyncEngine
)
from sqlalchemy import select, update, delete, func, and_, or_, desc, text, Float, Numeric, String
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import selectinload

from src.database.models import Base, SourceTable, ArticleTable, SourceCheckTable, ArticleAnnotationTable
from src.models.source import Source, SourceCreate, SourceUpdate, SourceFilter
from src.models.article import Article, ArticleCreate, ArticleUpdate, ArticleListFilter
from src.models.annotation import ArticleAnnotation, ArticleAnnotationCreate, ArticleAnnotationUpdate, ArticleAnnotationFilter, AnnotationStats
from src.services.deduplication import AsyncDeduplicationService

logger = logging.getLogger(__name__)


class AsyncDatabaseManager:
    """Modern async database manager with connection pooling and proper transaction handling."""
    
    def __init__(
        self,
        database_url: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://cti_user:cti_password@postgres:5432/cti_scraper"),
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
            expire_on_commit=True,
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
            logger.error(f"Database session error: {e}", exc_info=True)
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
                    select(func.count(ArticleTable.id)).where(ArticleTable.archived == False).where(ArticleTable.archived == False)
                )
                total_articles = articles_result.scalar()
                
                # Articles in last 24h, week, and month
                now = datetime.now()
                yesterday = now - timedelta(days=1)
                week_ago = now - timedelta(days=7)
                month_ago = now - timedelta(days=30)
                
                recent_articles_result = await session.execute(
                    select(func.count(ArticleTable.id)).where(ArticleTable.archived == False).where(
                        ArticleTable.discovered_at >= yesterday
                    )
                )
                articles_last_24h = recent_articles_result.scalar()
                
                week_articles_result = await session.execute(
                    select(func.count(ArticleTable.id)).where(ArticleTable.archived == False).where(
                        ArticleTable.discovered_at >= week_ago
                    )
                )
                articles_last_week = week_articles_result.scalar()
                
                month_articles_result = await session.execute(
                    select(func.count(ArticleTable.id)).where(ArticleTable.archived == False).where(
                        ArticleTable.discovered_at >= month_ago
                    )
                )
                articles_last_month = month_articles_result.scalar()
                
                # Database size (approximate)
                # Calculate size based on content length
                content_size_result = await session.execute(
                    select(func.sum(func.length(ArticleTable.content))).where(ArticleTable.archived == False)
                )
                total_content_bytes = content_size_result.scalar() or 0
                
                # Add estimated size for metadata, titles, etc. (roughly 20% overhead)
                estimated_total_bytes = int(total_content_bytes * 1.2)
                db_size_mb = round(estimated_total_bytes / (1024 * 1024), 2)
                
                # Score range analytics
                score_ranges = {}
                for min_score, max_score, label in [
                    (0, 20, "low"),
                    (20, 40, "low_medium"), 
                    (40, 60, "medium"),
                    (60, 80, "high"),
                    (80, 100, "very_high")
                ]:
                    score_count_result = await session.execute(
                        text(f"""
                            SELECT COUNT(*) FROM articles WHERE archived = FALSE 
                            AND CAST(article_metadata ->> 'threat_hunting_score' AS FLOAT) 
                            BETWEEN {min_score} AND {max_score}
                        """)
                    )
                    score_ranges[label] = score_count_result.scalar() or 0
                
                # Annotation analytics
                annotation_stats = {}
                
                # Total annotations
                total_annotations_result = await session.execute(
                    text("SELECT COUNT(*) FROM article_annotations")
                )
                annotation_stats["total_annotations"] = total_annotations_result.scalar() or 0
                
                # Huntable vs not_huntable annotations
                huntable_result = await session.execute(
                    text("SELECT COUNT(*) FROM article_annotations WHERE annotation_type = 'huntable'")
                )
                annotation_stats["huntable_annotations"] = huntable_result.scalar() or 0
                
                not_huntable_result = await session.execute(
                    text("SELECT COUNT(*) FROM article_annotations WHERE annotation_type = 'not_huntable'")
                )
                annotation_stats["not_huntable_annotations"] = not_huntable_result.scalar() or 0
                
                # Articles with annotations
                articles_with_annotations_result = await session.execute(
                    text("SELECT COUNT(DISTINCT article_id) FROM article_annotations")
                )
                annotation_stats["articles_with_annotations"] = articles_with_annotations_result.scalar() or 0
                
                return {
                    "total_sources": total_sources,
                    "active_sources": active_sources,
                    "total_articles": total_articles,
                    "articles_last_24h": articles_last_24h,
                    "articles_last_week": articles_last_week,
                    "articles_last_month": articles_last_month,
                    "db_size_mb": db_size_mb,
                    "score_ranges": score_ranges,
                    "annotation_stats": annotation_stats
                }
                
        except Exception as e:
            logger.error(f"Error getting database stats: {e}")
            raise

    async def count_annotated_chunks(self) -> int:
        """Count total annotated chunks available for training."""
        async with self.get_session() as session:
            try:
                result = await session.execute(
                    text("SELECT COUNT(*) FROM article_annotations")
                )
                return result.scalar() or 0
            except Exception as e:
                logger.error(f"Error counting annotated chunks: {e}")
                return 0
    
    async def list_sources(self, filter_params: Optional[SourceFilter] = None) -> List[Source]:
        """List all sources with optional filtering."""
        try:
            async with self.get_session() as session:
                query = select(SourceTable)
                
                if filter_params:
                    if filter_params.active is not None:
                        query = query.where(SourceTable.active == filter_params.active)
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

    async def list_source_identifiers(self) -> Set[str]:
        """Return set of all source identifiers."""
        try:
            async with self.get_session() as session:
                result = await session.execute(select(SourceTable.identifier))
                identifiers = result.scalars().all()
                return {identifier for identifier in identifiers}
        except Exception as e:
            logger.error(f"Failed to list source identifiers: {e}")
            return set()

    async def set_robots_user_agent_for_all(self, user_agent: str) -> int:
        """Ensure every source with robots config uses the provided user agent."""
        updated = 0
        try:
            sources = await self.list_sources()
            for source in sources:
                config = dict(source.config or {})
                robots = dict(config.get('robots') or {})
                if not robots:
                    continue
                if robots.get('user_agent') == user_agent:
                    continue
                robots['user_agent'] = user_agent
                config['robots'] = robots
                try:
                    await self.update_source(source.id, SourceUpdate(config=config))
                    updated += 1
                except Exception as inner_exc:  # noqa: BLE001
                    logger.error(f"Failed to update user agent for source {source.identifier}: {inner_exc}")
            return updated
        except Exception as e:
            logger.error(f"Failed to update robots user agents: {e}")
            return updated
    
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
                    check_frequency=source_data.config.check_frequency if source_data.config else 3600,
                    lookback_days=source_data.config.lookback_days if source_data.config else 180,
                    active=source_data.active,
                    config=source_data.config.model_dump(exclude_none=True) if source_data.config else {},
                    consecutive_failures=0,
                    total_articles=0,
                    average_response_time=0.0,
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
    
    async def update_source_min_content_length(self, source_id: int, min_content_length: int) -> Optional[Dict[str, Any]]:
        """Update source minimum content length in config."""
        try:
            async with self.get_session() as session:
                # Get the source
                result = await session.execute(
                    select(SourceTable).where(SourceTable.id == source_id)
                )
                db_source = result.scalar_one_or_none()
                
                if not db_source:
                    return None
                
                # Update config with min_content_length
                config = db_source.config or {}
                config['min_content_length'] = min_content_length
                db_source.config = config
                
                # Update timestamp
                db_source.updated_at = datetime.now()
                
                session.add(db_source)
                await session.commit()
                await session.refresh(db_source)
                
                logger.info(f"Successfully updated min_content_length for source {db_source.identifier}: {min_content_length}")
                
                return {
                    "success": True,
                    "message": f"Minimum content length updated to {min_content_length} characters",
                    "source_name": db_source.name,
                    "min_content_length": min_content_length
                }
                
        except Exception as e:
            logger.error(f"Failed to update min_content_length for source {source_id}: {e}")
            raise
    
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
                update_dict = update_data.model_dump(exclude_unset=True, exclude_none=True)
                for field, value in update_dict.items():
                    if field == 'config' and value:
                        if hasattr(value, 'model_dump'):
                            setattr(db_source, field, value.model_dump(exclude_none=True))
                        else:
                            setattr(db_source, field, value)
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

    async def delete_source(self, source_id: int) -> bool:
        """Delete source by ID."""
        try:
            async with self.get_session() as session:
                db_source = await session.get(SourceTable, source_id)
                if not db_source:
                    return False
                await session.delete(db_source)
                await session.commit()
                logger.info(f"Deleted source: {db_source.identifier}")
                return True
        except Exception as e:
            logger.error(f"Failed to delete source {source_id}: {e}")
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
                    select(func.count(ArticleTable.id)).where(ArticleTable.archived == False).where(ArticleTable.archived == False).where(ArticleTable.source_id == source_id)
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
    
    async def list_articles(self, article_filter: Optional['ArticleListFilter'] = None, limit: Optional[int] = None) -> List[Article]:
        """List articles with optional filtering and sorting."""
        try:
            async with self.get_session() as session:
                # Simple query without annotation counts to test for duplication
                query = select(ArticleTable).where(ArticleTable.archived == False)
                
                # Apply filters if provided
                if article_filter:
                    if article_filter.source_id is not None:
                        query = query.where(ArticleTable.source_id == article_filter.source_id)
                    
                    if article_filter.published_after is not None:
                        query = query.where(ArticleTable.published_at >= article_filter.published_after)
                    
                    if article_filter.published_before is not None:
                        query = query.where(ArticleTable.published_at <= article_filter.published_before)
                    
                    if article_filter.processing_status is not None:
                        query = query.where(ArticleTable.processing_status == article_filter.processing_status)
                    
                    if article_filter.content_contains is not None:
                        query = query.where(ArticleTable.content.contains(article_filter.content_contains))
                    
                    # Apply sorting
                    if article_filter.sort_by == 'threat_hunting_score':
                        # Special handling for threat_hunting_score which is stored in metadata
                        # Handle null values by using COALESCE to provide a default value
                        threat_score_expr = func.cast(
                            func.coalesce(
                                func.cast(ArticleTable.article_metadata['threat_hunting_score'], String), 
                                '0'
                            ), 
                            Numeric
                        )
                        if article_filter.sort_order == 'desc':
                            query = query.order_by(desc(threat_score_expr))
                        else:
                            query = query.order_by(threat_score_expr)
                    elif article_filter.sort_by == 'annotation_count':
                        # Sort by annotation count (simplified - no annotation count available)
                        # Default to discovered_at sorting
                        if article_filter.sort_order == 'desc':
                            query = query.order_by(desc(ArticleTable.discovered_at))
                        else:
                            query = query.order_by(ArticleTable.discovered_at)
                    else:
                        sort_field = getattr(ArticleTable, article_filter.sort_by, ArticleTable.discovered_at)
                        if article_filter.sort_order == 'desc':
                            query = query.order_by(desc(sort_field))
                        else:
                            query = query.order_by(sort_field)
                    
                    # Apply pagination
                    if article_filter.offset is not None and article_filter.offset > 0:
                        query = query.offset(article_filter.offset)
                    
                    if article_filter.limit is not None and article_filter.limit > 0:
                        query = query.limit(article_filter.limit)
                else:
                    # Default sorting by discovered_at desc
                    query = query.order_by(desc(ArticleTable.discovered_at))
                    
                    if limit:
                        query = query.limit(limit)
                
                logger.info("Executing query...")
                try:
                    result = await session.execute(query)
                    rows = result.all()
                    logger.info(f"Query executed, returned {len(rows)} rows")
                except Exception as query_e:
                    logger.error(f"Query execution error: {query_e}", exc_info=True)
                    raise
                
                # Debug: Check for duplicates
                try:
                    dfir_rows = []
                    for i, row in enumerate(rows):
                        db_article = row[0] if hasattr(row, '__getitem__') else row
                        if hasattr(db_article, 'source_id'):
                            if db_article.source_id == 25:
                                dfir_rows.append(db_article)
                                logger.info(f"Found DFIR article {len(dfir_rows)}: ID={db_article.id}, Title={db_article.title[:30]}...")
                    
                    logger.info(f"Query returned {len(rows)} total rows, {len(dfir_rows)} DFIR rows")
                except Exception as debug_e:
                    logger.error(f"Debug error: {debug_e}")
                
                # Convert to Article models
                articles = []
                for row in rows:
                    try:
                        # Row is a SQLAlchemy Row object, access the ArticleTable object
                        db_article = row[0] if hasattr(row, '__getitem__') else row
                        
                        # Debug: Check what type of object we have
                        logger.info(f"Row type: {type(row)}, Article type: {type(db_article)}, has id: {hasattr(db_article, 'id')}")
                    except Exception as row_e:
                        logger.error(f"Error processing row: {row_e}")
                        continue
                    
                    # Use the proper conversion method
                    article = self._db_article_to_model(db_article)
                    
                    # Get actual annotation count for this article
                    try:
                        annotation_count_query = select(func.count(ArticleAnnotationTable.id)).where(
                            ArticleAnnotationTable.article_id == article.id
                        )
                        annotation_count_result = await session.execute(annotation_count_query)
                        annotation_count = annotation_count_result.scalar() or 0
                    except Exception as e:
                        logger.error(f"Failed to get annotation count for article {article.id}: {e}")
                        annotation_count = 0
                    
                    # Add annotation count to metadata
                    if article.article_metadata is None:
                        article.article_metadata = {}
                    article.article_metadata['annotation_count'] = annotation_count
                    
                    articles.append(article)
                
                return articles
                
        except Exception as e:
            logger.error(f"Failed to list articles: {e}")
            return []
    
    async def get_articles_count(self, source_id: Optional[int] = None, processing_status: Optional[str] = None) -> int:
        """Get total count of articles with optional filtering."""
        try:
            async with self.get_session() as session:
                query = select(func.count(ArticleTable.id)).where(ArticleTable.archived == False).where(ArticleTable.archived == False)
                
                # Apply same filters as list_articles
                if source_id is not None:
                    query = query.where(ArticleTable.source_id == source_id)
                
                if processing_status is not None:
                    query = query.where(ArticleTable.processing_status == processing_status)
                
                result = await session.execute(query)
                return result.scalar()
                
        except Exception as e:
            logger.error(f"Failed to get articles count: {e}")
            return 0
    
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
                query = select(ArticleTable).where(ArticleTable.archived == False).where(ArticleTable.source_id == source_id).order_by(desc(ArticleTable.discovered_at))
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
                    # Update existing article metadata with threat hunting scoring
                    if article.article_metadata and 'threat_hunting_score' in article.article_metadata:
                        new_article.article_metadata = article.article_metadata
                        await session.commit()
                        logger.info(f"Updated existing article metadata with threat hunting scoring")
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
                    if field == 'article_metadata' and value:
                        # Replace metadata entirely (caller is responsible for merging)
                        setattr(db_article, 'article_metadata', value)
                    else:
                        setattr(db_article, field, value)
                
                # Update timestamp
                db_article.updated_at = datetime.utcnow()
                
                await session.commit()
                await session.refresh(db_article)
                
                logger.info(f"Updated article: {db_article.title}")
                
                # Convert to model while still in session context (important with expire_on_commit=True)
                result = self._db_article_to_model(db_article)
                
                return result
                
        except Exception as e:
            logger.error(f"Failed to update article {article_id}: {e}")
            return None
    
    async def delete_article(self, article_id: int) -> bool:
        """Delete an article and all related records."""
        try:
            async with self.get_session() as session:
                # Get the article title for logging (handle duplicates by taking first)
                result = await session.execute(
                    select(ArticleTable).where(ArticleTable.id == article_id)
                )
                db_articles = result.scalars().all()
                
                if not db_articles:
                    return False
                
                # Use first article for logging (they should all have same title)
                article_title = db_articles[0].title
                
                # Delete related records first to avoid foreign key constraints
                # Delete from article_annotations table
                await session.execute(
                    text("DELETE FROM article_annotations WHERE article_id = :article_id"),
                    {"article_id": article_id}
                )
                
                # Delete from content_hashes table
                await session.execute(
                    text("DELETE FROM content_hashes WHERE article_id = :article_id"),
                    {"article_id": article_id}
                )
                
                # Delete from simhash_buckets table
                await session.execute(
                    text("DELETE FROM simhash_buckets WHERE article_id = :article_id"),
                    {"article_id": article_id}
                )
                
                # Delete ALL articles with this ID (handles duplicates)
                await session.execute(
                    text("DELETE FROM articles WHERE id = :article_id"),
                    {"article_id": article_id}
                )
                
                # Commit all changes
                await session.commit()
                
                logger.info(f"Deleted article: {article_title}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to delete article {article_id}: {e}")
            return False
    
    async def get_existing_content_hashes(self, limit: int = 10000) -> set:
        """Get existing content hashes for deduplication."""
        try:
            async with self.get_session() as session:
                result = await session.execute(
                    select(ArticleTable.content_hash).where(ArticleTable.archived == False).limit(limit)
                )
                hashes = result.scalars().all()
                return set(hashes)
                
        except Exception as e:
            logger.error(f"Failed to get existing content hashes: {e}")
            return set()
    
    async def get_total_article_count(self) -> int:
        """Get the actual total count of articles in the database."""
        try:
            async with self.get_session() as session:
                result = await session.execute(text("SELECT COUNT(*) FROM articles WHERE archived = FALSE"))
                count = result.scalar()
                return count or 0
        except Exception as e:
            logger.error(f"Failed to get total article count: {e}")
            return 0
    
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

    async def get_source_hunt_scores(self) -> List[Dict[str, Any]]:
        """Get hunt score statistics for all sources."""
        try:
            async with self.get_session() as session:
                # Raw SQL query for hunt score statistics
                query = """
                SELECT
                    s.id,
                    s.name,
                    s.identifier,
                    s.active,
                    COUNT(a.id) as total_articles,
                    COUNT(CASE WHEN (a.article_metadata->>'threat_hunting_score')::float > 0 THEN 1 END) as scored_articles,
                    CASE
                        WHEN COUNT(CASE WHEN (a.article_metadata->>'threat_hunting_score')::float > 0 THEN 1 END) > 0 THEN
                            ROUND(AVG((a.article_metadata->>'threat_hunting_score')::float)::numeric, 2)
                        ELSE 0
                    END as avg_hunt_score,
                    MAX((a.article_metadata->>'threat_hunting_score')::float) as max_hunt_score
                FROM sources s
                LEFT JOIN articles a ON s.id = a.source_id
                GROUP BY s.id, s.name, s.identifier, s.active
                ORDER BY avg_hunt_score DESC NULLS LAST
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
                        "scored_articles": row.scored_articles,
                        "avg_hunt_score": float(row.avg_hunt_score) if row.avg_hunt_score else 0.0,
                        "max_hunt_score": float(row.max_hunt_score) if row.max_hunt_score else 0.0
                    }
                    for row in rows
                ]

        except Exception as e:
            logger.error(f"Failed to get source hunt scores: {e}")
            return []

    def _db_source_to_model(self, db_source: SourceTable) -> Source:
        """Convert database source to Pydantic model."""
        return Source(
            id=db_source.id,
            identifier=db_source.identifier,
            name=db_source.name,
            url=db_source.url,
            rss_url=db_source.rss_url,
            check_frequency=db_source.check_frequency,
            lookback_days=db_source.lookback_days,
            active=db_source.active,
            config=db_source.config if db_source.config else {},
            last_check=db_source.last_check,
            last_success=db_source.last_success,
            consecutive_failures=db_source.consecutive_failures,
            total_articles=db_source.total_articles,
            average_response_time=db_source.average_response_time,
            created_at=db_source.created_at,
            updated_at=db_source.updated_at
        )
    
    def _db_article_to_model(self, db_article: ArticleTable) -> Article:
        """Convert database article to Pydantic model."""
        return Article(
            id=db_article.id,
            source_id=db_article.source_id,
            url=db_article.canonical_url,
            canonical_url=db_article.canonical_url,
            title=db_article.title,
            published_at=db_article.published_at,
            modified_at=db_article.modified_at,
            authors=db_article.authors,
            tags=db_article.tags,
            summary=db_article.summary,
            content=db_article.content,
            content_hash=db_article.content_hash,
            article_metadata=db_article.article_metadata,
            simhash=db_article.simhash,
            simhash_bucket=db_article.simhash_bucket,
            discovered_at=db_article.discovered_at,
            word_count=db_article.word_count,
            content_length=len(db_article.content) if db_article.content else None,
            collected_at=db_article.discovered_at,
            created_at=db_article.created_at,
            updated_at=db_article.updated_at,
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
                url_query = "SELECT COUNT(DISTINCT canonical_url) FROM articles WHERE archived = FALSE"
                result = await session.execute(text(url_query))
                stats['unique_urls'] = result.scalar() or 0
                
                # Duplicate rate
                total_articles = await session.scalar(select(func.count(ArticleTable.id)).where(ArticleTable.archived == False).where(ArticleTable.archived == False))
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
                result = await session.scalar(select(func.count(ArticleTable.id)).where(ArticleTable.archived == False).where(ArticleTable.archived == False))
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
                total_articles = await session.scalar(select(func.count(ArticleTable.id)).where(ArticleTable.archived == False).where(ArticleTable.archived == False))
                total_sources = await session.scalar(select(func.count(SourceTable.id)))
                
                logger.info(f"Ingestion analytics: {total_articles} articles, {total_sources} sources")
                
                # Date range queries
                earliest_query = select(func.min(ArticleTable.discovered_at)).where(ArticleTable.archived == False)
                latest_query = select(func.max(ArticleTable.discovered_at)).where(ArticleTable.archived == False)
                
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
                
                # Hourly distribution (today) - using local timezone
                hourly_query = """
                SELECT 
                    EXTRACT(hour FROM discovered_at AT TIME ZONE 'UTC' AT TIME ZONE 'America/New_York') as hour,
                    COUNT(*) as articles_count
                FROM articles 
                WHERE DATE(discovered_at AT TIME ZONE 'UTC' AT TIME ZONE 'America/New_York') = (CURRENT_DATE AT TIME ZONE 'America/New_York')::date
                GROUP BY EXTRACT(hour FROM discovered_at AT TIME ZONE 'UTC' AT TIME ZONE 'America/New_York')
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
                    ROUND(AVG(CAST(a.article_metadata->>'threat_hunting_score' AS NUMERIC)), 1) as avg_hunt_score,
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
                
                # Hunt score ranges (last 30 days)
                hunt_score_query = """
                SELECT 
                    DATE(discovered_at) as date,
                    COUNT(CASE WHEN CAST(article_metadata->>'threat_hunting_score' AS NUMERIC) >= 80 THEN 1 END) as excellent_count,
                    COUNT(CASE WHEN CAST(article_metadata->>'threat_hunting_score' AS NUMERIC) BETWEEN 60 AND 79 THEN 1 END) as good_count,
                    COUNT(CASE WHEN CAST(article_metadata->>'threat_hunting_score' AS NUMERIC) BETWEEN 40 AND 59 THEN 1 END) as moderate_count,
                    COUNT(CASE WHEN CAST(article_metadata->>'threat_hunting_score' AS NUMERIC) BETWEEN 20 AND 39 THEN 1 END) as low_count,
                    COUNT(CASE WHEN CAST(article_metadata->>'threat_hunting_score' AS NUMERIC) < 20 OR article_metadata->>'threat_hunting_score' IS NULL THEN 1 END) as minimal_count
                FROM articles 
                WHERE discovered_at >= NOW() - INTERVAL '30 days'
                GROUP BY DATE(discovered_at)
                ORDER BY date DESC
                LIMIT 30
                """
                result = await session.execute(text(hunt_score_query))
                hunt_score_ranges = [
                    {
                        'date': row[0].strftime('%Y-%m-%d'),
                        'excellent': row[1] or 0,
                        'good': row[2] or 0,
                        'moderate': row[3] or 0,
                        'low': row[4] or 0,
                        'minimal': row[5] or 0
                    }
                    for row in result.fetchall()
                ]
                analytics['hunt_score_ranges'] = hunt_score_ranges
                
                return analytics
                
        except Exception as e:
            logger.error(f"Failed to get ingestion analytics: {e}", exc_info=True)
            return {
                'total_stats': {'total_articles': 0, 'total_sources': 0},
                'daily_trends': [],
                'hourly_distribution': [],
                'source_breakdown': []
            }

    # Annotation management methods
    
    async def create_annotation(self, annotation_data: ArticleAnnotationCreate) -> Optional[ArticleAnnotation]:
        """Create a new annotation."""
        try:
            async with self.get_session() as session:
                db_annotation = ArticleAnnotationTable(
                    article_id=annotation_data.article_id,
                    user_id=None,  # Set to None for now
                    annotation_type=annotation_data.annotation_type,
                    selected_text=annotation_data.selected_text,
                    start_position=annotation_data.start_position,
                    end_position=annotation_data.end_position,
                    context_before=annotation_data.context_before,
                    context_after=annotation_data.context_after,
                    confidence_score=annotation_data.confidence_score,
                    used_for_training=annotation_data.used_for_training,
                    created_at=datetime.now(),
                    updated_at=datetime.now()
                )
                
                session.add(db_annotation)
                await session.commit()
                await session.refresh(db_annotation)
                
                logger.info(f"Created annotation: {annotation_data.annotation_type} for article {annotation_data.article_id}")
                return self._db_annotation_to_model(db_annotation)
                
        except Exception as e:
            logger.error(f"Failed to create annotation: {e}")
            return None
    
    async def get_annotation(self, annotation_id: int) -> Optional[ArticleAnnotation]:
        """Get a specific annotation by ID."""
        try:
            async with self.get_session() as session:
                result = await session.execute(
                    select(ArticleAnnotationTable).where(ArticleAnnotationTable.id == annotation_id)
                )
                db_annotation = result.scalar_one_or_none()
                
                if db_annotation:
                    return self._db_annotation_to_model(db_annotation)
                return None
                
        except Exception as e:
            logger.error(f"Failed to get annotation {annotation_id}: {e}")
            return None
    
    async def get_article_annotations(self, article_id: int) -> List[ArticleAnnotation]:
        """Get all annotations for a specific article."""
        try:
            async with self.get_session() as session:
                result = await session.execute(
                    select(ArticleAnnotationTable)
                    .where(ArticleAnnotationTable.article_id == article_id)
                    .order_by(ArticleAnnotationTable.created_at.desc())
                )
                db_annotations = result.scalars().all()
                
                return [self._db_annotation_to_model(annotation) for annotation in db_annotations]
                
        except Exception as e:
            logger.error(f"Failed to get annotations for article {article_id}: {e}")
            return []
    
    async def update_annotation(self, annotation_id: int, update_data: ArticleAnnotationUpdate) -> Optional[ArticleAnnotation]:
        """Update an existing annotation."""
        try:
            async with self.get_session() as session:
                result = await session.execute(
                    select(ArticleAnnotationTable).where(ArticleAnnotationTable.id == annotation_id)
                )
                db_annotation = result.scalar_one_or_none()
                
                if not db_annotation:
                    return None
                
                # Update fields
                if update_data.annotation_type is not None:
                    db_annotation.annotation_type = update_data.annotation_type
                if update_data.confidence_score is not None:
                    db_annotation.confidence_score = update_data.confidence_score
                
                db_annotation.updated_at = datetime.now()
                
                await session.commit()
                await session.refresh(db_annotation)
                
                logger.info(f"Updated annotation {annotation_id}")
                return self._db_annotation_to_model(db_annotation)
                
        except Exception as e:
            logger.error(f"Failed to update annotation {annotation_id}: {e}")
            return None
    
    async def delete_annotation(self, annotation_id: int) -> bool:
        """Delete an annotation."""
        try:
            async with self.get_session() as session:
                result = await session.execute(
                    delete(ArticleAnnotationTable).where(ArticleAnnotationTable.id == annotation_id)
                )
                
                if result.rowcount > 0:
                    await session.commit()
                    logger.info(f"Deleted annotation {annotation_id}")
                    return True
                return False
                
        except Exception as e:
            logger.error(f"Failed to delete annotation {annotation_id}: {e}")
            return False
    
    async def get_annotation_stats(self) -> AnnotationStats:
        """Get annotation statistics."""
        try:
            async with self.get_session() as session:
                # Get total counts
                total_result = await session.execute(
                    select(func.count(ArticleAnnotationTable.id))
                )
                total_annotations = total_result.scalar() or 0
                
                # Get huntable count
                huntable_result = await session.execute(
                    select(func.count(ArticleAnnotationTable.id))
                    .where(ArticleAnnotationTable.annotation_type == 'huntable')
                )
                huntable_count = huntable_result.scalar() or 0
                
                # Get not_huntable count
                not_huntable_result = await session.execute(
                    select(func.count(ArticleAnnotationTable.id))
                    .where(ArticleAnnotationTable.annotation_type == 'not_huntable')
                )
                not_huntable_count = not_huntable_result.scalar() or 0
                
                # Get average confidence
                avg_confidence_result = await session.execute(
                    select(func.avg(ArticleAnnotationTable.confidence_score))
                )
                average_confidence = avg_confidence_result.scalar() or 0.0
                
                # Get most annotated article
                most_annotated_result = await session.execute(
                    select(ArticleAnnotationTable.article_id, func.count(ArticleAnnotationTable.id).label('count'))
                    .group_by(ArticleAnnotationTable.article_id)
                    .order_by(desc('count'))
                    .limit(1)
                )
                most_annotated_row = most_annotated_result.first()
                most_annotated_article = most_annotated_row[0] if most_annotated_row else None
                
                # Calculate percentages
                huntable_percentage = (huntable_count / total_annotations * 100) if total_annotations > 0 else 0
                not_huntable_percentage = (not_huntable_count / total_annotations * 100) if total_annotations > 0 else 0
                
                return AnnotationStats(
                    total_annotations=total_annotations,
                    huntable_count=huntable_count,
                    not_huntable_count=not_huntable_count,
                    huntable_percentage=round(huntable_percentage, 1),
                    not_huntable_percentage=round(not_huntable_percentage, 1),
                    average_confidence=round(average_confidence, 2),
                    most_annotated_article=most_annotated_article
                )
                
        except Exception as e:
            logger.error(f"Failed to get annotation stats: {e}")
            return AnnotationStats(
                total_annotations=0,
                huntable_count=0,
                not_huntable_count=0,
                huntable_percentage=0.0,
                not_huntable_percentage=0.0,
                average_confidence=0.0,
                most_annotated_article=None
            )
    
    
    def _db_annotation_to_model(self, db_annotation: ArticleAnnotationTable) -> ArticleAnnotation:
        """Convert database annotation to Pydantic model."""
        return ArticleAnnotation(
            id=db_annotation.id,
            article_id=db_annotation.article_id,
            user_id=db_annotation.user_id,
            annotation_type=db_annotation.annotation_type,
            selected_text=db_annotation.selected_text,
            start_position=db_annotation.start_position,
            end_position=db_annotation.end_position,
            context_before=db_annotation.context_before,
            context_after=db_annotation.context_after,
            confidence_score=db_annotation.confidence_score,
            used_for_training=db_annotation.used_for_training,
            created_at=db_annotation.created_at,
            updated_at=db_annotation.updated_at
        )
    
    async def get_annotation_with_article_info(self, annotation_id: int) -> Optional[ArticleAnnotationTable]:
        """Get annotation with article and source information for embedding generation."""
        try:
            async with self.get_session() as session:
                result = await session.execute(
                    select(ArticleAnnotationTable)
                    .options(selectinload(ArticleAnnotationTable.article).selectinload(ArticleTable.source))
                    .where(ArticleAnnotationTable.id == annotation_id)
                )
                return result.scalar_one_or_none()
                
        except Exception as e:
            logger.error(f"Failed to get annotation with article info {annotation_id}: {e}")
            return None
    
    async def get_annotations_with_article_info(self, annotation_ids: List[int]) -> List[ArticleAnnotationTable]:
        """Get multiple annotations with article and source information."""
        try:
            async with self.get_session() as session:
                result = await session.execute(
                    select(ArticleAnnotationTable)
                    .options(selectinload(ArticleAnnotationTable.article).selectinload(ArticleTable.source))
                    .where(ArticleAnnotationTable.id.in_(annotation_ids))
                )
                return result.scalars().all()
                
        except Exception as e:
            logger.error(f"Failed to get annotations with article info: {e}")
            return []
    
    async def get_annotations_without_embeddings(self) -> List[ArticleAnnotationTable]:
        """Get all annotations that don't have embeddings yet."""
        try:
            async with self.get_session() as session:
                result = await session.execute(
                    select(ArticleAnnotationTable)
                    .where(ArticleAnnotationTable.embedding.is_(None))
                    .order_by(ArticleAnnotationTable.created_at)
                )
                return result.scalars().all()
                
        except Exception as e:
            logger.error(f"Failed to get annotations without embeddings: {e}")
            return []
    
    async def update_annotation_embedding(self, annotation_id: int, embedding: List[float], 
                                       model_name: str = "all-mpnet-base-v2") -> bool:
        """Update annotation with its embedding vector."""
        try:
            async with self.get_session() as session:
                await session.execute(
                    update(ArticleAnnotationTable)
                    .where(ArticleAnnotationTable.id == annotation_id)
                    .values(
                        embedding=embedding,
                        embedding_model=model_name,
                        embedded_at=func.now()
                    )
                )
                await session.commit()
                logger.debug(f"Updated embedding for annotation {annotation_id}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to update annotation embedding {annotation_id}: {e}")
            return False
    
    async def search_similar_annotations(self, query_embedding: List[float], limit: int = 10, 
                                      threshold: float = 0.7, annotation_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Search for similar annotations using cosine similarity."""
        try:
            async with self.get_session() as session:
                # Build query with optional filters
                query = select(
                    ArticleAnnotationTable.id,
                    ArticleAnnotationTable.selected_text,
                    ArticleAnnotationTable.annotation_type,
                    ArticleAnnotationTable.confidence_score,
                    ArticleAnnotationTable.article_id,
                    ArticleTable.title.label('article_title'),
                    SourceTable.name.label('source_name'),
                    text("1 - (embedding <=> :query_vector) AS similarity")
                ).select_from(
                    ArticleAnnotationTable.__table__
                    .join(ArticleTable.__table__, ArticleAnnotationTable.article_id == ArticleTable.id)
                    .join(SourceTable.__table__, ArticleTable.source_id == SourceTable.id)
                ).where(
                    ArticleAnnotationTable.embedding.is_not(None)
                ).order_by(
                    text("embedding <=> :query_vector")
                ).limit(limit)
                
                # Add annotation type filter if specified
                if annotation_type:
                    query = query.where(ArticleAnnotationTable.annotation_type == annotation_type)
                
                # Execute query with vector similarity
                # Convert embedding list to string format for pgvector
                embedding_str = '[' + ','.join(map(str, query_embedding)) + ']'
                result = await session.execute(
                    query.params(query_vector=embedding_str)
                )
                
                # Filter by similarity threshold and format results
                similar_annotations = []
                for row in result:
                    similarity = float(row.similarity)
                    if similarity >= threshold:
                        similar_annotations.append({
                            'id': row.id,
                            'selected_text': row.selected_text,
                            'annotation_type': row.annotation_type,
                            'confidence_score': row.confidence_score,
                            'article_id': row.article_id,
                            'article_title': row.article_title,
                            'source_name': row.source_name,
                            'similarity': similarity
                        })
                
                logger.debug(f"Found {len(similar_annotations)} similar annotations above threshold {threshold}")
                return similar_annotations
                
        except Exception as e:
            logger.error(f"Failed to search similar annotations: {e}")
            return []
    
    async def get_embedding_stats(self) -> Dict[str, Any]:
        """Get statistics about embeddings in the database."""
        try:
            async with self.get_session() as session:
                # Count total annotations
                total_result = await session.execute(
                    select(func.count(ArticleAnnotationTable.id))
                )
                total_annotations = total_result.scalar() or 0
                
                # Count annotations with embeddings
                embedded_result = await session.execute(
                    select(func.count(ArticleAnnotationTable.id))
                    .where(ArticleAnnotationTable.embedding.is_not(None))
                )
                embedded_count = embedded_result.scalar() or 0
                
                # Count by annotation type
                huntable_embedded_result = await session.execute(
                    select(func.count(ArticleAnnotationTable.id))
                    .where(
                        and_(
                            ArticleAnnotationTable.embedding.is_not(None),
                            ArticleAnnotationTable.annotation_type == 'huntable'
                        )
                    )
                )
                huntable_embedded = huntable_embedded_result.scalar() or 0
                
                not_huntable_embedded_result = await session.execute(
                    select(func.count(ArticleAnnotationTable.id))
                    .where(
                        and_(
                            ArticleAnnotationTable.embedding.is_not(None),
                            ArticleAnnotationTable.annotation_type == 'not_huntable'
                        )
                    )
                )
                not_huntable_embedded = not_huntable_embedded_result.scalar() or 0
                
                # Calculate percentages
                embedding_coverage = (embedded_count / total_annotations * 100) if total_annotations > 0 else 0
                
                return {
                    'total_annotations': total_annotations,
                    'embedded_count': embedded_count,
                    'embedding_coverage_percent': round(embedding_coverage, 1),
                    'huntable_embedded': huntable_embedded,
                    'not_huntable_embedded': not_huntable_embedded,
                    'pending_embeddings': total_annotations - embedded_count
                }
                
        except Exception as e:
            logger.error(f"Failed to get embedding stats: {e}")
            return {
                'total_annotations': 0,
                'embedded_count': 0,
                'embedding_coverage_percent': 0.0,
                'huntable_embedded': 0,
                'not_huntable_embedded': 0,
                'pending_embeddings': 0
            }

    # Article embedding methods
    async def get_article_with_source_info(self, article_id: int) -> Optional[ArticleTable]:
        """Get article with source information for embedding generation."""
        try:
            async with self.get_session() as session:
                result = await session.execute(
                    select(ArticleTable)
                    .options(selectinload(ArticleTable.source))
                    .where(ArticleTable.id == article_id)
                )
                return result.scalar_one_or_none()
                
        except Exception as e:
            logger.error(f"Failed to get article with source info {article_id}: {e}")
            return None
    
    async def get_articles_with_source_info(self, article_ids: List[int]) -> List[ArticleTable]:
        """Get multiple articles with source information."""
        try:
            async with self.get_session() as session:
                result = await session.execute(
                    select(ArticleTable)
                    .options(selectinload(ArticleTable.source))
                    .where(ArticleTable.id.in_(article_ids))
                )
                return result.scalars().all()
                
        except Exception as e:
            logger.error(f"Failed to get articles with source info: {e}")
            return []
    
    async def get_articles_without_embeddings(self) -> List[ArticleTable]:
        """Get all articles that don't have embeddings yet."""
        try:
            async with self.get_session() as session:
                result = await session.execute(
                    select(ArticleTable)
                    .where(ArticleTable.embedding.is_(None))
                    .order_by(ArticleTable.created_at)
                )
                return result.scalars().all()
                
        except Exception as e:
            logger.error(f"Failed to get articles without embeddings: {e}")
            return []
    
    async def update_article_embedding(self, article_id: int, embedding: List[float], 
                                     model_name: str = "all-mpnet-base-v2") -> bool:
        """Update article with its embedding vector."""
        try:
            async with self.get_session() as session:
                await session.execute(
                    update(ArticleTable)
                    .where(ArticleTable.id == article_id)
                    .values(
                        embedding=embedding,
                        embedding_model=model_name,
                        embedded_at=func.now()
                    )
                )
                await session.commit()
                logger.debug(f"Updated embedding for article {article_id}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to update article embedding {article_id}: {e}")
            return False
    
    async def search_similar_articles(self, query_embedding: List[float], limit: int = 10, 
                                    threshold: float = 0.7, source_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Search for similar articles using cosine similarity."""
        try:
            async with self.get_session() as session:
                # Build query with optional filters
                query = select(
                    ArticleTable.id,
                    ArticleTable.title,
                    ArticleTable.summary,
                    ArticleTable.content,
                    ArticleTable.published_at,
                    ArticleTable.source_id,
                    SourceTable.name.label('source_name'),
                    text("1 - (embedding <=> :query_vector) AS similarity")
                ).select_from(
                    ArticleTable.__table__
                    .join(SourceTable.__table__, ArticleTable.source_id == SourceTable.id)
                ).where(
                    ArticleTable.embedding.is_not(None)
                ).order_by(
                    text("embedding <=> :query_vector")
                ).limit(limit)
                
                # Add source filter if specified
                if source_id:
                    query = query.where(ArticleTable.source_id == source_id)
                
                # Execute query with vector similarity
                # Convert embedding list to string format for pgvector
                embedding_str = '[' + ','.join(map(str, query_embedding)) + ']'
                result = await session.execute(
                    query.params(query_vector=embedding_str)
                )
                
                # Filter by similarity threshold and format results
                similar_articles = []
                for row in result:
                    similarity = float(row[7])  # similarity is the 8th column (index 7)
                    if similarity >= threshold:
                        similar_articles.append({
                            'id': row.id,
                            'title': row.title,
                            'summary': row.summary,
                            'content': row.content[:500] + '...' if len(row.content) > 500 else row.content,
                            'published_at': row.published_at.isoformat() if row.published_at else None,
                            'source_id': row.source_id,
                            'source_name': row.source_name,
                            'similarity': similarity
                        })
                
                logger.debug(f"Found {len(similar_articles)} similar articles above threshold {threshold}")
                return similar_articles
                
        except Exception as e:
            logger.error(f"Failed to search similar articles: {e}")
            return []
    
    async def get_article_embedding_stats(self) -> Dict[str, Any]:
        """Get statistics about article embeddings in the database."""
        try:
            async with self.get_session() as session:
                # Count total articles
                total_result = await session.execute(
                    select(func.count(ArticleTable.id)).where(ArticleTable.archived == False).where(ArticleTable.archived == False)
                )
                total_articles = total_result.scalar() or 0
                
                # Count articles with embeddings
                embedded_result = await session.execute(
                    select(func.count(ArticleTable.id)).where(ArticleTable.archived == False).where(ArticleTable.archived == False)
                    .where(ArticleTable.embedding.is_not(None))
                )
                embedded_count = embedded_result.scalar() or 0
                
                # Count by source
                source_stats_result = await session.execute(
                    select(
                        SourceTable.name,
                        func.count(ArticleTable.id).label('total'),
                        func.count(ArticleTable.embedding).label('embedded')
                    ).select_from(
                        ArticleTable.__table__
                        .join(SourceTable.__table__, ArticleTable.source_id == SourceTable.id)
                    ).group_by(SourceTable.id, SourceTable.name)
                )
                
                source_stats = []
                for row in source_stats_result:
                    source_stats.append({
                        'source_name': row.name,
                        'total_articles': row.total,
                        'embedded_articles': row.embedded,
                        'coverage_percent': round((row.embedded / row.total * 100) if row.total > 0 else 0, 1)
                    })
                
                # Calculate percentages
                embedding_coverage = (embedded_count / total_articles * 100) if total_articles > 0 else 0
                
                return {
                    'total_articles': total_articles,
                    'embedded_count': embedded_count,
                    'embedding_coverage_percent': round(embedding_coverage, 1),
                    'pending_embeddings': total_articles - embedded_count,
                    'source_stats': source_stats
                }
                
        except Exception as e:
            logger.error(f"Failed to get article embedding stats: {e}")
            return {
                'total_articles': 0,
                'embedded_count': 0,
                'embedding_coverage_percent': 0.0,
                'pending_embeddings': 0,
                'source_stats': []
            }

    async def close(self):
        """Close database connections properly."""
        await self.engine.dispose()
        logger.info("Database connections closed")

    async def create_chunk_feedback(self, feedback_data: dict):
        """Create chunk classification feedback entry."""
        from src.database.models import ChunkClassificationFeedbackTable
        
        try:
            async with self.get_session() as session:
                feedback = ChunkClassificationFeedbackTable(
                    article_id=feedback_data['article_id'],
                    chunk_id=feedback_data['chunk_id'],
                    chunk_text=feedback_data['chunk_text'],
                    model_classification=feedback_data['model_classification'],
                    model_confidence=feedback_data['model_confidence'],
                    model_reason=feedback_data.get('model_reason', ''),
                    is_correct=feedback_data['is_correct'],
                    user_classification=feedback_data.get('user_classification', ''),
                    comment=feedback_data.get('comment', ''),
                    used_for_training=feedback_data.get('used_for_training', False)
                )
                session.add(feedback)
                await session.commit()
                await session.refresh(feedback)
                return feedback
        except Exception as e:
            logger.error(f"Failed to create chunk feedback: {e}")
            raise

    async def get_unused_chunk_feedback(self):
        """Get all unused chunk feedback for training."""
        from src.database.models import ChunkClassificationFeedbackTable
        
        try:
            async with self.get_session() as session:
                result = await session.execute(
                    select(ChunkClassificationFeedbackTable).where(
                        ChunkClassificationFeedbackTable.used_for_training == False
                    )
                )
                feedback_records = result.scalars().all()
                return feedback_records
        except Exception as e:
            logger.error(f"Failed to get unused chunk feedback: {e}")
            raise

    async def mark_chunk_feedback_as_used(self) -> int:
        """Mark all unused chunk feedback as used. Returns count."""
        from src.database.models import ChunkClassificationFeedbackTable
        
        try:
            async with self.get_session() as session:
                result = await session.execute(
                    update(ChunkClassificationFeedbackTable)
                    .where(ChunkClassificationFeedbackTable.used_for_training == False)
                    .values(used_for_training=True)
                )
                await session.commit()
                return result.rowcount
        except Exception as e:
            logger.error(f"Failed to mark chunk feedback as used: {e}")
            raise


# Global instance for easy access
async_db_manager = AsyncDatabaseManager()
