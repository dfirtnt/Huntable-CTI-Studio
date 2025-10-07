#!/usr/bin/env python3

import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.database.async_manager import AsyncDatabaseManager

async def check_recent_articles():
    """Check most recent articles."""
    db = AsyncDatabaseManager()
    try:
        articles = await db.list_articles(limit=5)
        
        print("Most Recent Articles:")
        print("=" * 80)
        
        for article in articles:
            content_length = len(article.content) if article.content else 0
            print(f"ID: {article.id} | Source: {article.source_id} | Title: {article.title[:50]}... | Content: {content_length} chars | Date: {article.discovered_at}")
            
    except Exception as e:
        print(f"Error checking articles: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(check_recent_articles())
