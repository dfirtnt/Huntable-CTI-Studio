"""SQLAlchemy database models."""

from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float, Text, ForeignKey, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

Base = declarative_base()


class SourceTable(Base):
    """Database table for sources."""
    
    __tablename__ = 'sources'
    
    id = Column(Integer, primary_key=True, index=True)
    identifier = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(500), nullable=False)
    url = Column(Text, nullable=False)
    rss_url = Column(Text, nullable=True)
    check_frequency = Column(Integer, nullable=False, default=3600)
    active = Column(Boolean, nullable=False, default=True)
    config = Column(JSON, nullable=False, default=dict)
    
    # Tracking fields
    last_check = Column(DateTime, nullable=True)
    last_success = Column(DateTime, nullable=True)
    consecutive_failures = Column(Integer, nullable=False, default=0)
    total_articles = Column(Integer, nullable=False, default=0)
    
    # Health metrics
    success_rate = Column(Float, nullable=False, default=0.0)
    average_response_time = Column(Float, nullable=False, default=0.0)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    
    # Relationships
    articles = relationship("ArticleTable", back_populates="source", cascade="all, delete-orphan")
    checks = relationship("SourceCheckTable", back_populates="source", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Source(id={self.id}, identifier='{self.identifier}', name='{self.name}')>"


class ArticleTable(Base):
    """Database table for articles."""
    
    __tablename__ = 'articles'
    
    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey('sources.id'), nullable=False, index=True)
    canonical_url = Column(Text, nullable=False, index=True)
    title = Column(Text, nullable=False)
    published_at = Column(DateTime, nullable=False, index=True)
    modified_at = Column(DateTime, nullable=True)
    authors = Column(JSON, nullable=False, default=list)  # List of strings
    tags = Column(JSON, nullable=False, default=list)    # List of strings
    summary = Column(Text, nullable=True)
    content = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False, unique=True, index=True)
    article_metadata = Column(JSON, nullable=False, default=dict)
    
    # Processing fields
    discovered_at = Column(DateTime, nullable=False, default=func.now())
    processing_status = Column(String(50), nullable=False, default='pending', index=True)
    
    # Quality metrics
    quality_score = Column(Float, nullable=True)
    word_count = Column(Integer, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    
    # Relationships
    source = relationship("SourceTable", back_populates="articles")
    
    def __repr__(self):
        return f"<Article(id={self.id}, title='{self.title[:50]}...', source_id={self.source_id})>"


class SourceCheckTable(Base):
    """Database table for tracking source check history."""
    
    __tablename__ = 'source_checks'
    
    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey('sources.id'), nullable=False, index=True)
    check_time = Column(DateTime, nullable=False, default=func.now(), index=True)
    success = Column(Boolean, nullable=False)
    method = Column(String(50), nullable=False)  # 'rss', 'modern_scraping', 'legacy_scraping'
    articles_found = Column(Integer, nullable=False, default=0)
    response_time = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)
    check_metadata = Column(JSON, nullable=False, default=dict)
    
    # Relationships
    source = relationship("SourceTable", back_populates="checks")
    
    def __repr__(self):
        status = "SUCCESS" if self.success else "FAILED"
        return f"<SourceCheck(source_id={self.source_id}, {status}, {self.articles_found} articles)>"


class ContentHashTable(Base):
    """Database table for content hash tracking (for efficient deduplication)."""
    
    __tablename__ = 'content_hashes'
    
    id = Column(Integer, primary_key=True, index=True)
    content_hash = Column(String(64), nullable=False, unique=True, index=True)
    article_id = Column(Integer, ForeignKey('articles.id'), nullable=False)
    first_seen = Column(DateTime, nullable=False, default=func.now())
    
    def __repr__(self):
        return f"<ContentHash(hash='{self.content_hash[:8]}...', article_id={self.article_id})>"


class URLTrackingTable(Base):
    """Database table for tracking processed URLs (for conditional requests)."""
    
    __tablename__ = 'url_tracking'
    
    id = Column(Integer, primary_key=True, index=True)
    url = Column(Text, nullable=False, unique=True, index=True)
    last_checked = Column(DateTime, nullable=False, default=func.now())
    etag = Column(String(255), nullable=True)
    last_modified = Column(String(255), nullable=True)
    status_code = Column(Integer, nullable=True)
    content_length = Column(Integer, nullable=True)
    
    def __repr__(self):
        return f"<URLTracking(url='{self.url[:50]}...', last_checked={self.last_checked})>"
