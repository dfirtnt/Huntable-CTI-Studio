"""Database manager for threat intelligence aggregator with deduplication support."""

import asyncio
from typing import List, Optional, Dict, Any, Set, Tuple
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text, and_, or_, desc, func
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.dialects.postgresql import insert as pg_insert
import logging

from database.models import Base, SourceTable, ArticleTable, SourceCheckTable, ContentHashTable, URLTrackingTable, SimHashBucketTable
from models.source import Source, SourceCreate, SourceUpdate, SourceFilter, SourceHealth
from models.article import Article, ArticleCreate, ArticleUpdate, ArticleFilter
from src.services.deduplication import DeduplicationService

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Database manager for efficient operations with conflict resolution."""
    
    def __init__(
        self,
        database_url: str = "sqlite:///threat_intel.db",
        echo: bool = False,
        pool_size: int = 10,
        max_overflow: int = 20
    ):
        self.database_url = database_url
        self.echo = echo
        
        # Create engine with appropriate settings
        if database_url.startswith("sqlite"):
            # SQLite specific settings
            self.engine = create_engine(
                database_url,
                echo=echo,
                connect_args={"check_same_thread": False}
            )
        else:
            # PostgreSQL settings
            self.engine = create_engine(
                database_url,
                echo=echo,
                pool_size=pool_size,
                max_overflow=max_overflow,
                pool_pre_ping=True
            )
        
        # Create session factory
        self.SessionLocal = sessionmaker(bind=self.engine)
        
        # Initialize database
        self.create_tables()
    
    def create_tables(self):
        """Create all database tables."""
        try:
            Base.metadata.create_all(bind=self.engine)
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Failed to create database tables: {e}")
            raise
    
    def get_session(self) -> Session:
        """Get database session."""
        return self.SessionLocal()
    
    # Source management methods
    
    def create_source(self, source_data: SourceCreate) -> Source:
        """Create a new source."""
        with self.get_session() as session:
            try:
                # Convert to database model
                db_source = SourceTable(
                    identifier=source_data.identifier,
                    name=source_data.name,
                    url=source_data.url,
                    rss_url=source_data.rss_url,
                    tier=source_data.tier,
                    weight=source_data.weight,
                    check_frequency=source_data.check_frequency,
                    active=source_data.active,
                    config=source_data.config.dict() if source_data.config else {}
                )
                
                session.add(db_source)
                session.commit()
                session.refresh(db_source)
                
                logger.info(f"Created source: {db_source.identifier}")
                return self._db_source_to_model(db_source)
                
            except IntegrityError as e:
                session.rollback()
                logger.error(f"Source with identifier '{source_data.identifier}' already exists")
                raise ValueError(f"Source identifier must be unique") from e
            except Exception as e:
                session.rollback()
                logger.error(f"Failed to create source: {e}")
                raise
    
    def get_source(self, source_id: int) -> Optional[Source]:
        """Get source by ID."""
        with self.get_session() as session:
            db_source = session.query(SourceTable).filter(SourceTable.id == source_id).first()
            return self._db_source_to_model(db_source) if db_source else None
    
    def get_source_by_identifier(self, identifier: str) -> Optional[Source]:
        """Get source by identifier."""
        with self.get_session() as session:
            db_source = session.query(SourceTable).filter(SourceTable.identifier == identifier).first()
            return self._db_source_to_model(db_source) if db_source else None
    
    def list_sources(self, filter_params: Optional[SourceFilter] = None) -> List[Source]:
        """List sources with optional filtering."""
        with self.get_session() as session:
            query = session.query(SourceTable)
            
            if filter_params:
                if filter_params.tier is not None:
                    query = query.filter(SourceTable.tier == filter_params.tier)
                
                if filter_params.active is not None:
                    query = query.filter(SourceTable.active == filter_params.active)
                
                if filter_params.identifier_contains:
                    query = query.filter(SourceTable.identifier.contains(filter_params.identifier_contains))
                
                if filter_params.name_contains:
                    query = query.filter(SourceTable.name.contains(filter_params.name_contains))
                
                if filter_params.consecutive_failures_gte is not None:
                    query = query.filter(SourceTable.consecutive_failures >= filter_params.consecutive_failures_gte)
                
                if filter_params.last_check_before:
                    query = query.filter(SourceTable.last_check < filter_params.last_check_before)
                
                # Apply pagination
                query = query.offset(filter_params.offset).limit(filter_params.limit)
            
            db_sources = query.all()
            return [self._db_source_to_model(db_source) for db_source in db_sources]
    
    def update_source(self, source_id: int, update_data: SourceUpdate) -> Optional[Source]:
        """Update source."""
        with self.get_session() as session:
            try:
                db_source = session.query(SourceTable).filter(SourceTable.id == source_id).first()
                
                if not db_source:
                    return None
                
                # Update fields
                update_dict = update_data.dict(exclude_unset=True)
                for field, value in update_dict.items():
                    if field == 'config' and value:
                        setattr(db_source, field, value.dict())
                    else:
                        setattr(db_source, field, value)
                
                session.commit()
                session.refresh(db_source)
                
                logger.info(f"Updated source: {db_source.identifier}")
                return self._db_source_to_model(db_source)
                
            except Exception as e:
                session.rollback()
                logger.error(f"Failed to update source {source_id}: {e}")
                raise
    
    def delete_source(self, source_id: int) -> bool:
        """Delete source and all associated data."""
        with self.get_session() as session:
            try:
                db_source = session.query(SourceTable).filter(SourceTable.id == source_id).first()
                
                if not db_source:
                    return False
                
                session.delete(db_source)
                session.commit()
                
                logger.info(f"Deleted source: {db_source.identifier}")
                return True
                
            except Exception as e:
                session.rollback()
                logger.error(f"Failed to delete source {source_id}: {e}")
                raise
    
    def update_source_health(self, source_id: int, success: bool, response_time: float = 0.0):
        """Update source health metrics."""
        with self.get_session() as session:
            try:
                db_source = session.query(SourceTable).filter(SourceTable.id == source_id).first()
                
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
                
                session.commit()
                
            except Exception as e:
                session.rollback()
                logger.error(f"Failed to update source health for {source_id}: {e}")
                raise
    
    # Article management methods
    
    def create_articles_bulk(self, articles: List[ArticleCreate]) -> Tuple[List[Article], List[str]]:
        """
        Bulk create articles with conflict resolution.
        
        Returns:
            Tuple of (created_articles, errors)
        """
        if not articles:
            return [], []
        
        created_articles = []
        errors = []
        
        with self.get_session() as session:
            try:
                for article_data in articles:
                    try:
                        # Check for existing article by content hash
                        existing = session.query(ArticleTable).filter(
                            ArticleTable.content_hash == article_data.content_hash
                        ).first()
                        
                        if existing:
                            errors.append(f"Duplicate content hash: {article_data.title[:50]}...")
                            continue
                        
                        # Extract quality score from metadata
                        quality_score = article_data.metadata.get('quality_score')
                        word_count = article_data.metadata.get('word_count')
                        
                        # Create database record
                        db_article = ArticleTable(
                            source_id=article_data.source_id,
                            canonical_url=article_data.canonical_url,
                            title=article_data.title,
                            published_at=article_data.published_at,
                            modified_at=article_data.modified_at,
                            authors=article_data.authors,
                            tags=article_data.tags,
                            summary=article_data.summary,
                            content=article_data.content,
                            content_hash=article_data.content_hash,
                            article_metadata=article_data.metadata,
                            quality_score=quality_score,
                            word_count=word_count
                        )
                        
                        session.add(db_article)
                        session.flush()  # Get ID without committing
                        
                        # Create content hash record
                        content_hash_record = ContentHashTable(
                            content_hash=article_data.content_hash,
                            article_id=db_article.id
                        )
                        session.add(content_hash_record)
                        
                        # Convert to model
                        article = self._db_article_to_model(db_article)
                        created_articles.append(article)
                        
                    except Exception as e:
                        logger.error(f"Failed to create article '{article_data.title[:50]}...': {e}")
                        errors.append(f"Error creating article: {e}")
                        continue
                
                # Commit all successful articles
                session.commit()
                
                # Update source article count
                if created_articles:
                    source_id = articles[0].source_id
                    self._update_source_article_count(session, source_id)
                
                logger.info(f"Created {len(created_articles)} articles, {len(errors)} errors")
                
                return created_articles, errors
                
            except Exception as e:
                session.rollback()
                logger.error(f"Bulk article creation failed: {e}")
                raise
    
    def get_article(self, article_id: int) -> Optional[Article]:
        """Get article by ID."""
        with self.get_session() as session:
            db_article = session.query(ArticleTable).filter(ArticleTable.id == article_id).first()
            return self._db_article_to_model(db_article) if db_article else None
    
    def list_articles(self, filter_params: Optional[ArticleFilter] = None) -> List[Article]:
        """List articles with optional filtering."""
        with self.get_session() as session:
            query = session.query(ArticleTable)
            
            if filter_params:
                if filter_params.source_id is not None:
                    query = query.filter(ArticleTable.source_id == filter_params.source_id)
                
                if filter_params.author:
                    query = query.filter(ArticleTable.authors.contains([filter_params.author]))
                
                if filter_params.tag:
                    query = query.filter(ArticleTable.tags.contains([filter_params.tag]))
                
                if filter_params.published_after:
                    query = query.filter(ArticleTable.published_at >= filter_params.published_after)
                
                if filter_params.published_before:
                    query = query.filter(ArticleTable.published_at <= filter_params.published_before)
                
                if filter_params.content_contains:
                    query = query.filter(ArticleTable.content.contains(filter_params.content_contains))
                
                if filter_params.processing_status:
                    query = query.filter(ArticleTable.processing_status == filter_params.processing_status)
                
                # Apply pagination
                query = query.offset(filter_params.offset).limit(filter_params.limit)
            
            # Order by publication date (newest first)
            query = query.order_by(desc(ArticleTable.published_at))
            
            db_articles = query.all()
            return [self._db_article_to_model(db_article) for db_article in db_articles]
    
    def get_existing_content_hashes(self, limit: int = 10000) -> Set[str]:
        """Get set of existing content hashes for deduplication."""
        with self.get_session() as session:
            hashes = session.query(ContentHashTable.content_hash).limit(limit).all()
            return {hash_tuple[0] for hash_tuple in hashes}
    
    # Source check tracking
    
    def record_source_check(
        self,
        source_id: int,
        success: bool,
        method: str,
        articles_found: int = 0,
        response_time: Optional[float] = None,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Record a source check for tracking and analysis."""
        with self.get_session() as session:
            try:
                check_record = SourceCheckTable(
                    source_id=source_id,
                    success=success,
                    method=method,
                    articles_found=articles_found,
                    response_time=response_time,
                    error_message=error_message,
                    check_metadata=metadata or {}
                )
                
                session.add(check_record)
                session.commit()
                
            except Exception as e:
                session.rollback()
                logger.error(f"Failed to record source check: {e}")
    
    def get_source_health_status(self, source_id: int) -> Optional[SourceHealth]:
        """Get detailed health status for a source."""
        with self.get_session() as session:
            db_source = session.query(SourceTable).filter(SourceTable.id == source_id).first()
            
            if not db_source:
                return None
            
            return SourceHealth(
                source_id=db_source.id,
                identifier=db_source.identifier,
                name=db_source.name,
                active=db_source.active,
                tier=db_source.tier,
                last_check=db_source.last_check,
                last_success=db_source.last_success,
                consecutive_failures=db_source.consecutive_failures,
                success_rate=db_source.success_rate,
                average_response_time=db_source.average_response_time,
                total_articles=db_source.total_articles
            )
    
    # Statistics and reporting
    
    def get_database_stats(self) -> Dict[str, Any]:
        """Get overall database statistics."""
        with self.get_session() as session:
            stats = {}
            
            # Source statistics
            stats['total_sources'] = session.query(SourceTable).count()
            stats['active_sources'] = session.query(SourceTable).filter(SourceTable.active == True).count()
            stats['sources_by_tier'] = {}
            
            for tier in [1, 2, 3]:
                count = session.query(SourceTable).filter(SourceTable.tier == tier).count()
                stats['sources_by_tier'][f'tier_{tier}'] = count
            
            # Article statistics
            stats['total_articles'] = session.query(ArticleTable).count()
            
            # Articles by date range
            now = datetime.utcnow()
            day_ago = now - timedelta(days=1)
            week_ago = now - timedelta(days=7)
            month_ago = now - timedelta(days=30)
            
            stats['articles_last_day'] = session.query(ArticleTable).filter(
                ArticleTable.discovered_at >= day_ago
            ).count()
            
            stats['articles_last_week'] = session.query(ArticleTable).filter(
                ArticleTable.discovered_at >= week_ago
            ).count()
            
            stats['articles_last_month'] = session.query(ArticleTable).filter(
                ArticleTable.discovered_at >= month_ago
            ).count()
            
            # Add missing fields for web interface
            stats['articles_last_24h'] = stats['articles_last_day']
            
            # Calculate database size (approximate for SQLite)
            try:
                if self.database_url.startswith("sqlite"):
                    # For SQLite, get file size
                    import os
                    db_file = self.database_url.replace("sqlite:///", "")
                    if os.path.exists(db_file):
                        stats['database_size_mb'] = round(os.path.getsize(db_file) / (1024 * 1024), 2)
                    else:
                        stats['database_size_mb'] = 0.0
                else:
                    # For PostgreSQL, estimate size
                    stats['database_size_mb'] = 0.0
            except Exception:
                stats['database_size_mb'] = 0.0
            
            # Quality statistics
            avg_quality = session.query(func.avg(ArticleTable.quality_score)).filter(
                ArticleTable.quality_score.isnot(None)
            ).scalar()
            stats['average_quality_score'] = float(avg_quality) if avg_quality else 0.0
            
            return stats
    
    # Utility methods
    
    def _db_source_to_model(self, db_source: SourceTable) -> Source:
        """Convert database source to Pydantic model."""
        from models.source import SourceConfig
        
        return Source(
            id=db_source.id,
            identifier=db_source.identifier,
            name=db_source.name,
            url=db_source.url,
            rss_url=db_source.rss_url,
            tier=db_source.tier,
            weight=db_source.weight,
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
            discovered_at=db_article.discovered_at,
            processing_status=db_article.processing_status
        )
    
    def _update_source_article_count(self, session: Session, source_id: int):
        """Update the total article count for a source."""
        count = session.query(ArticleTable).filter(ArticleTable.source_id == source_id).count()
        session.query(SourceTable).filter(SourceTable.id == source_id).update(
            {'total_articles': count}
        )
    
    def cleanup_old_data(self, days_to_keep: int = 90):
        """Clean up old data to manage database size."""
        cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
        
        with self.get_session() as session:
            try:
                # Clean up old source checks
                old_checks = session.query(SourceCheckTable).filter(
                    SourceCheckTable.check_time < cutoff_date
                ).delete()
                
                # Clean up old URL tracking
                old_urls = session.query(URLTrackingTable).filter(
                    URLTrackingTable.last_checked < cutoff_date
                ).delete()
                
                session.commit()
                
                logger.info(f"Cleaned up {old_checks} old source checks and {old_urls} old URL records")
                
            except Exception as e:
                session.rollback()
                logger.error(f"Failed to cleanup old data: {e}")
                raise
