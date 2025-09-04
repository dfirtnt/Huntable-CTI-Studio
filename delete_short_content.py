#!/usr/bin/env python3

import asyncio
import sys
import os
from collections import defaultdict
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.database.async_manager import AsyncDatabaseManager

async def delete_short_content_articles():
    """Delete all articles with content length less than 500 characters."""
    db = AsyncDatabaseManager()
    try:
        # Get all articles
        articles = await db.list_articles()
        
        print("Finding articles with short content (<500 chars)...")
        print("=" * 80)
        
        # Find short content articles
        short_content_articles = []
        
        for article in articles:
            content_length = len(article.content) if article.content else 0
            if content_length < 500:
                short_content_articles.append((article, content_length))
        
        print(f"Total articles: {len(articles)}")
        print(f"Articles with short content (<500 chars): {len(short_content_articles)}")
        
        if not short_content_articles:
            print("No articles with short content found. Nothing to delete.")
            return
        
        # Show first 10 articles that will be deleted
        print(f"\nFirst 10 articles to be deleted:")
        print("-" * 50)
        
        for i, (article, length) in enumerate(short_content_articles[:10]):
            print(f"{i+1}. ID: {article.id}, Length: {length}, Title: {article.title[:60]}...")
            print(f"   URL: {article.canonical_url}")
        
        if len(short_content_articles) > 10:
            print(f"... and {len(short_content_articles) - 10} more articles")
        
        # Confirm deletion
        print(f"\n" + "=" * 80)
        print(f"WARNING: This will delete {len(short_content_articles)} articles!")
        print("These articles have content shorter than 500 characters and are likely RSS excerpts.")
        print("The improved scraping logic will collect better versions in future runs.")
        
        # For safety, ask for confirmation
        confirm = input(f"\nType 'DELETE {len(short_content_articles)}' to confirm deletion: ")
        
        if confirm != f"DELETE {len(short_content_articles)}":
            print("Deletion cancelled.")
            return
        
        # Delete the articles
        print(f"\nDeleting {len(short_content_articles)} articles...")
        
        deleted_count = 0
        for article, length in short_content_articles:
            try:
                await db.delete_article(article.id)
                deleted_count += 1
                if deleted_count % 50 == 0:  # Progress indicator
                    print(f"Deleted {deleted_count}/{len(short_content_articles)} articles...")
            except Exception as e:
                print(f"Error deleting article {article.id}: {e}")
        
        print(f"\n" + "=" * 80)
        print("DELETION COMPLETE!")
        print(f"Successfully deleted {deleted_count} articles with short content.")
        
        # Verify deletion
        remaining_articles = await db.list_articles()
        remaining_short = [a for a in remaining_articles if len(a.content or "") < 500]
        
        print(f"Remaining articles: {len(remaining_articles)}")
        print(f"Remaining articles with short content: {len(remaining_short)}")
        
        if remaining_short:
            print(f"\nNote: {len(remaining_short)} articles still have short content.")
            print("These may be legitimate short articles or need manual review.")
        
        return {
            'total_deleted': deleted_count,
            'remaining_articles': len(remaining_articles),
            'remaining_short': len(remaining_short)
        }
        
    except Exception as e:
        print(f"Error during deletion: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    result = asyncio.run(delete_short_content_articles())
    if result:
        print(f"\nCleanup complete. Deleted {result['total_deleted']} articles.")
