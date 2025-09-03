#!/usr/bin/env python3
"""
Test the improved content extraction on CrowdStrike articles.
"""

import asyncio
import sys
import os
import json
from datetime import datetime

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from database.async_manager import AsyncDatabaseManager
from core.rss_parser import RSSParser

async def test_improved_extraction():
    """Test improved content extraction on CrowdStrike."""
    
    print("🧪 Testing Improved Content Extraction")
    print("=" * 50)
    
    # Initialize database manager
    db = AsyncDatabaseManager()
    
    try:
        # Get CrowdStrike source
        sources = await db.list_sources()
        crowdstrike_source = None
        for source in sources:
            if 'crowdstrike' in source.name.lower():
                crowdstrike_source = source
                break
        
        if not crowdstrike_source:
            print("❌ CrowdStrike source not found")
            return
        
        print(f"🔍 Testing: {crowdstrike_source.name}")
        print(f"📡 RSS URL: {crowdstrike_source.rss_url}")
        
        # Initialize RSS parser with improved extraction
        from utils.http import HTTPClient
        
        async with HTTPClient() as http_client:
            rss_parser = RSSParser(http_client)
            
            print("  🔄 Testing content extraction...")
            
            # Parse with improved extraction
            articles = await rss_parser.parse_feed(crowdstrike_source)
            
            if articles:
                print(f"  ✅ Collected {len(articles)} articles")
                
                # Show details of extracted content
                for i, article in enumerate(articles[:3], 1):
                    content_len = len(article.content) if article.content else 0
                    summary_len = len(article.summary) if article.summary else 0
                    print(f"    📄 Article {i}: {article.title[:60]}...")
                    print(f"       Content: {content_len} chars, Summary: {summary_len} chars")
                    
                    if content_len > 500:
                        print(f"       🎉 SUCCESS: Extracted substantial content!")
                        # Show a preview
                        preview = article.content[:200].replace('\n', ' ')
                        print(f"       Preview: {preview}...")
                    elif content_len > 0:
                        print(f"       ⚠️  Limited content extracted")
                    else:
                        print(f"       ❌ No content extracted")
                
            else:
                print("  ❌ No articles found")
        
    except Exception as e:
        print(f"❌ Test error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await db.close()

if __name__ == "__main__":
    asyncio.run(test_improved_extraction())
