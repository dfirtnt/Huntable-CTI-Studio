#!/usr/bin/env python3
"""Test script for the deduplication system."""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import logging
from datetime import datetime

from src.database.async_manager import AsyncDatabaseManager
from src.models.article import ArticleCreate
from src.services.deduplication import DeduplicationService

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_deduplication():
    """Test the deduplication system."""
    
    # Initialize database manager
    db_manager = AsyncDatabaseManager()
    
    # Test article data
    test_articles = [
        ArticleCreate(
            source_id=1,
            canonical_url="https://example.com/article1",
            title="Test Article 1",
            content="This is a test article about cybersecurity threats and malware detection.",
            published_at=datetime.utcnow(),
            authors=["Test Author"],
            tags=["security", "malware"],
            summary="A test article",
            metadata={}
        ),
        ArticleCreate(
            source_id=1,
            canonical_url="https://example.com/article2",
            title="Test Article 2",
            content="This is a test article about cybersecurity threats and malware detection.",  # Same content
            published_at=datetime.utcnow(),
            authors=["Test Author"],
            tags=["security", "malware"],
            summary="A test article",
            metadata={}
        ),
        ArticleCreate(
            source_id=1,
            canonical_url="https://example.com/article3",
            title="Test Article 3",
            content="This is a similar article about cybersecurity threats and malware detection with some differences.",
            published_at=datetime.utcnow(),
            authors=["Test Author"],
            tags=["security", "malware"],
            summary="A test article",
            metadata={}
        )
    ]
    
    logger.info("Testing deduplication system...")
    
    # Create articles and test deduplication
    created_articles = []
    for i, article in enumerate(test_articles):
        logger.info(f"Creating article {i+1}: {article.title}")
        
        created_article = await db_manager.create_article(article)
        
        if created_article:
            created_articles.append(created_article)
            logger.info(f"Article {i+1} created with ID: {created_article.id}")
        else:
            logger.info(f"Article {i+1} was a duplicate or failed to create")
    
    logger.info(f"Created {len(created_articles)} articles out of {len(test_articles)} attempts")
    
    # Test SimHash functionality
    logger.info("Testing SimHash functionality...")
    
    # Get deduplication stats
    async with db_manager.get_session() as session:
        dedup_service = DeduplicationService(session)
        stats = dedup_service.get_deduplication_stats()
        logger.info(f"Deduplication stats: {stats}")
    
    logger.info("Deduplication test completed!")


if __name__ == "__main__":
    asyncio.run(test_deduplication())
