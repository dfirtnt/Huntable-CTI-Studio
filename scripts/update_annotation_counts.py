#!/usr/bin/env python3
"""
Update annotation counts for all articles that have annotations.
This script fixes the annotation count display on the articles page.
"""

import asyncio
import sys
import os
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.async_manager import AsyncDatabaseManager
from src.models.article import ArticleUpdate
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def update_annotation_counts():
    """Update annotation counts for all articles."""
    db = AsyncDatabaseManager()
    
    try:
        # Get all articles
        articles = await db.list_articles()
        logger.info(f"Found {len(articles)} articles to check")
        
        updated_count = 0
        
        for article in articles:
            try:
                # Get annotations for this article
                annotations = await db.get_article_annotations(article.id)
                annotation_count = len(annotations)
                
                # Get current metadata
                current_metadata = article.article_metadata.copy() if article.article_metadata else {}
                current_count = current_metadata.get('annotation_count', 0)
                
                # Only update if the count is different
                if current_count != annotation_count:
                    current_metadata['annotation_count'] = annotation_count
                    
                    # Update the article
                    update_data = ArticleUpdate(article_metadata=current_metadata)
                    await db.update_article(article.id, update_data)
                    
                    logger.info(f"Updated article {article.id}: {current_count} → {annotation_count} annotations")
                    updated_count += 1
                else:
                    logger.debug(f"Article {article.id}: count already correct ({annotation_count})")
                    
            except Exception as e:
                logger.error(f"Failed to update article {article.id}: {e}")
                continue
        
        logger.info(f"✅ Updated annotation counts for {updated_count} articles")
        
    except Exception as e:
        logger.error(f"Failed to update annotation counts: {e}")
        raise
    finally:
        await db.close()

async def main():
    """Main function."""
    logger.info("Starting annotation count update...")
    await update_annotation_counts()
    logger.info("Annotation count update complete!")

if __name__ == "__main__":
    asyncio.run(main())
