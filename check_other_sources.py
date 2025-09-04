#!/usr/bin/env python3

import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.database.async_manager import AsyncDatabaseManager

async def check_other_sources():
    """Check articles from sources other than The Hacker News."""
    db = AsyncDatabaseManager()
    try:
        articles = await db.list_articles(limit=20)
        other_sources = [a for a in articles if a.source_id != 26]
        
        print(f"Articles from other sources: {len(other_sources)}")
        print("=" * 80)
        
        for article in other_sources[:5]:
            content_length = len(article.content) if article.content else 0
            print(f"ID: {article.id} | Source: {article.source_id} | Title: {article.title[:50]}... | Content: {content_length} chars")
            
    except Exception as e:
        print(f"Error checking articles: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(check_other_sources())
