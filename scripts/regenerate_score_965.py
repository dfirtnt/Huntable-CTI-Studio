#!/usr/bin/env python3

import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.database.async_manager import AsyncDatabaseManager
from src.core.processor import ContentProcessor
from src.models.article import ArticleCreate

async def regenerate_threat_hunting_score():
    """Regenerate threat hunting score for article 965."""
    db = AsyncDatabaseManager()
    try:
        # Get article 965
        article = await db.get_article(965)
        if not article:
            print("❌ Article 965 not found")
            return
        
        print(f"Article 965: {article.title}")
        print(f"Current metadata: {article.metadata}")
        
        # Create a processor to regenerate the score
        processor = ContentProcessor(enable_content_enhancement=True)
        
        # Create ArticleCreate object for processing
        article_create = ArticleCreate(
            source_id=article.source_id,
            canonical_url=article.canonical_url,
            title=article.title,
            content=article.content,
            published_at=article.published_at,
            metadata=article.metadata or {}
        )
        
        # Regenerate threat hunting score
        enhanced_metadata = await processor._enhance_metadata(article_create)
        
        print(f"\nEnhanced metadata: {enhanced_metadata}")
        
        if 'threat_hunting_score' in enhanced_metadata:
            new_score = enhanced_metadata['threat_hunting_score']
            print(f"✅ New threat hunting score: {new_score}")
            
            # Update the article in database
            if not article.metadata:
                article.metadata = {}
            
            # Update only the threat hunting score
            article.metadata['threat_hunting_score'] = new_score
            
            # Save the updated article
            await db.update_article(article.id, article)
            print(f"✅ Article 965 updated with threat hunting score: {new_score}")
            
        else:
            print("❌ No threat hunting score generated")
            
    except Exception as e:
        print(f"Error regenerating score: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(regenerate_threat_hunting_score())
