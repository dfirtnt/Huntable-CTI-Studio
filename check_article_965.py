#!/usr/bin/env python3

import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.database.async_manager import AsyncDatabaseManager

async def check_article_965():
    """Check specific article 965 for threat hunting score."""
    db = AsyncDatabaseManager()
    try:
        article = await db.get_article(965)
        if article:
            print(f"Article 965: {article.title}")
            print(f"Content length: {len(article.content) if article.content else 0}")
            print(f"Metadata: {article.metadata}")
            
            if article.metadata and 'threat_hunting_score' in article.metadata:
                score = article.metadata['threat_hunting_score']
                print(f"✅ Threat hunting score: {score}")
            else:
                print("❌ No threat hunting score found in metadata")
        else:
            print("❌ Article 965 not found")
            
    except Exception as e:
        print(f"Error checking article: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(check_article_965())
