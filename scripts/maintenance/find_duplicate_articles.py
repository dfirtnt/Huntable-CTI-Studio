#!/usr/bin/env python3

import asyncio
import sys
import os
from collections import defaultdict
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.database.async_manager import AsyncDatabaseManager

async def check_duplicates_and_cleanup():
    """Check for duplicate articles and clean up short content records."""
    db = AsyncDatabaseManager()
    try:
        # Get all articles
        articles = await db.list_articles()
        
        print("Analyzing articles for duplicates and short content...")
        print("=" * 80)
        
        # Group articles by URL and date
        url_date_groups = defaultdict(list)
        short_content_articles = []
        
        for article in articles:
            # Create key: URL + date (day only)
            if article.published_at:
                date_key = article.published_at.strftime('%Y-%m-%d')
            else:
                date_key = 'unknown'
            
            key = f"{article.canonical_url}|{date_key}"
            url_date_groups[key].append(article)
            
            # Check for short content
            content_length = len(article.content) if article.content else 0
            if content_length < 500:
                short_content_articles.append((article, content_length))
        
        print(f"Total articles: {len(articles)}")
        print(f"Articles with short content (<500 chars): {len(short_content_articles)}")
        print(f"Unique URL+date combinations: {len(url_date_groups)}")
        
        # Find duplicates
        duplicates = []
        for key, group in url_date_groups.items():
            if len(group) > 1:
                duplicates.append((key, group))
        
        print(f"URL+date combinations with duplicates: {len(duplicates)}")
        
        # Analyze duplicates
        if duplicates:
            print("\nDuplicate Analysis:")
            print("-" * 40)
            
            for key, group in duplicates[:10]:  # Show first 10
                url, date = key.split('|', 1)
                print(f"\nURL: {url}")
                print(f"Date: {date}")
                print(f"Duplicate count: {len(group)}")
                
                # Sort by content length (longest first)
                sorted_group = sorted(group, key=lambda x: len(x.content or ""), reverse=True)
                
                for i, article in enumerate(sorted_group):
                    content_length = len(article.content) if article.content else 0
                    status = "✅ KEEP" if i == 0 and content_length >= 500 else "❌ DELETE"
                    print(f"  {i+1}. ID: {article.id}, Length: {content_length}, Status: {status}")
        
        # Show short content articles
        if short_content_articles:
            print(f"\nArticles with Short Content (<500 chars):")
            print("-" * 50)
            
            for article, length in short_content_articles[:20]:  # Show first 20
                url, date = article.canonical_url, article.published_at.strftime('%Y-%m-%d') if article.published_at else 'unknown'
                key = f"{url}|{date}"
                
                # Check if we have better versions
                group = url_date_groups[key]
                has_better_version = any(len(a.content or "") >= 500 for a in group if a.id != article.id)
                
                status = "❌ DELETE (has better version)" if has_better_version else "❓ REVIEW"
                print(f"ID: {article.id}, Length: {length}, URL: {url[:60]}..., Status: {status}")
        
        # Summary
        print("\n" + "=" * 80)
        print("SUMMARY:")
        print(f"- Total articles: {len(articles)}")
        print(f"- Short content articles: {len(short_content_articles)}")
        print(f"- Duplicate groups: {len(duplicates)}")
        
        # Count articles that can be safely deleted
        safe_to_delete = 0
        for key, group in duplicates:
            sorted_group = sorted(group, key=lambda x: len(x.content or ""), reverse=True)
            # Keep the longest, delete the rest
            safe_to_delete += len(sorted_group) - 1
        
        # Add short content articles that have better versions
        short_with_better = 0
        for article, length in short_content_articles:
            url, date = article.canonical_url, article.published_at.strftime('%Y-%m-%d') if article.published_at else 'unknown'
            key = f"{url}|{date}"
            group = url_date_groups[key]
            if any(len(a.content or "") >= 500 for a in group if a.id != article.id):
                short_with_better += 1
        
        print(f"- Articles safe to delete: {safe_to_delete + short_with_better}")
        print(f"  - Duplicates: {safe_to_delete}")
        print(f"  - Short content with better versions: {short_with_better}")
        
        return {
            'total_articles': len(articles),
            'short_content': len(short_content_articles),
            'duplicates': len(duplicates),
            'safe_to_delete': safe_to_delete + short_with_better
        }
        
    except Exception as e:
        print(f"Error analyzing articles: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    result = asyncio.run(check_duplicates_and_cleanup())
    if result:
        print(f"\nAnalysis complete. Found {result['safe_to_delete']} articles that can be safely deleted.")
