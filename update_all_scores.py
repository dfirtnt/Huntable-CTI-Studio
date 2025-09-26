#!/usr/bin/env python3
"""
Script to regenerate threat hunting scores for all articles after keyword changes.
Run this whenever you add/remove keywords from the scoring system.
"""

import asyncio
import sys
import os

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.database.async_manager import AsyncDatabaseManager
from src.utils.content import ThreatHuntingScorer
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def regenerate_all_scores():
    """Regenerate threat hunting scores for all articles."""
    
    # Initialize database manager
    db_manager = AsyncDatabaseManager()
    
    try:
        logger.info("Starting threat hunting score regeneration...")
        
        # Get all articles
        articles = await db_manager.get_all_articles()
        total_articles = len(articles)
        
        logger.info(f"Found {total_articles} articles to process")
        
        updated_count = 0
        error_count = 0
        
        for i, article in enumerate(articles, 1):
            try:
                # Calculate new threat hunting score
                score_result = ThreatHuntingScorer.score_content(
                    content=article.content,
                    title=article.title
                )
                
                # Update article metadata
                if article.metadata is None:
                    article.metadata = {}
                
                article.metadata.update({
                    'threat_hunting_score': score_result['threat_hunting_score'],
                    'perfect_keyword_matches': score_result['perfect_keyword_matches'],
                    'good_keyword_matches': score_result['good_keyword_matches'],
                    'lolbas_matches': score_result['lolbas_matches']
                })
                
                # Save updated article
                from src.models.article import ArticleUpdate
                update_data = ArticleUpdate(metadata=article.metadata)
                await db_manager.update_article(article.id, update_data)
                
                updated_count += 1
                
                if i % 50 == 0:
                    logger.info(f"Processed {i}/{total_articles} articles...")
                    
            except Exception as e:
                logger.error(f"Error processing article {article.id}: {e}")
                error_count += 1
        
        logger.info(f"✅ Regeneration complete!")
        logger.info(f"   Successfully updated: {updated_count} articles")
        logger.info(f"   Errors: {error_count} articles")
        logger.info(f"   Total processed: {total_articles} articles")
        
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        return False
    finally:
        await db_manager.close()
    
    return True

if __name__ == "__main__":
    print("🔄 Regenerating threat hunting scores for all articles...")
    print("   This will apply the latest keyword rules to all articles.")
    print()
    
    success = asyncio.run(regenerate_all_scores())
    
    if success:
        print("\n✅ All done! Threat hunting scores have been updated.")
    else:
        print("\n❌ Regeneration failed. Check the logs above.")
        sys.exit(1)
