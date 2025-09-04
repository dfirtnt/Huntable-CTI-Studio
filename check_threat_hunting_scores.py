#!/usr/bin/env python3

import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.database.async_manager import AsyncDatabaseManager

async def check_threat_hunting_scores():
    """Check if articles have threat hunting scores in their metadata."""
    db = AsyncDatabaseManager()
    try:
        # Get sample articles
        articles = await db.list_articles(limit=10)
        
        print("Checking threat hunting scores in articles:")
        print("=" * 80)
        
        articles_with_score = 0
        articles_without_score = 0
        articles_without_metadata = 0
        
        for article in articles:
            if not article.metadata:
                articles_without_metadata += 1
                print(f"ID: {article.id} | Title: {article.title[:60]}... | Status: NO METADATA")
            elif 'threat_hunting_score' not in article.metadata:
                articles_without_score += 1
                print(f"ID: {article.id} | Title: {article.title[:60]}... | Status: NO THREAT HUNTING SCORE")
            else:
                articles_with_score += 1
                score = article.metadata['threat_hunting_score']
                print(f"ID: {article.id} | Title: {article.title[:60]}... | Score: {score}")
        
        print("=" * 80)
        print(f"Total articles checked: {len(articles)}")
        print(f"Articles with threat hunting score: {articles_with_score}")
        print(f"Articles without threat hunting score: {articles_without_score}")
        print(f"Articles without metadata: {articles_without_metadata}")
        
        # Check if content enhancement is enabled
        print("\nChecking content enhancement configuration:")
        try:
            from src.core.processor import ContentProcessor
            processor = ContentProcessor()
            print(f"Content enhancement enabled: {processor.enable_content_enhancement}")
        except Exception as e:
            print(f"Could not check processor configuration: {e}")
            
    except Exception as e:
        print(f"Error checking articles: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(check_threat_hunting_scores())
