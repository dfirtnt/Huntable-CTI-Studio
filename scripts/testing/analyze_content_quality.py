#!/usr/bin/env python3

import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.database.async_manager import AsyncDatabaseManager

async def check_content_lengths():
    """Check content lengths of recent articles."""
    db = AsyncDatabaseManager()
    try:
        articles = await db.list_articles(limit=10)
        
        print("Content Length Analysis:")
        print("=" * 80)
        
        short_articles = 0
        total_articles = len(articles)
        
        for article in articles:
            content_length = len(article.content) if article.content else 0
            if content_length < 500:
                short_articles += 1
                print(f"ID: {article.id} | Source: {article.source_id} | Title: {article.title[:60]}... | Content: {content_length} chars")
        
        print("=" * 80)
        print(f"Total articles checked: {total_articles}")
        print(f"Articles with <500 chars: {short_articles}")
        print(f"Percentage short articles: {(short_articles/total_articles)*100:.1f}%")
        
        # Check sources
        sources = await db.list_sources()
        print(f"\nTotal sources: {len(sources)}")
        for source in sources:
            print(f"Source {source.id}: {source.name} ({source.identifier})")
            
    except Exception as e:
        print(f"Error checking articles: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(check_content_lengths())
