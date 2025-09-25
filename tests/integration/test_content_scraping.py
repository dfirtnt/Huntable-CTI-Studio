#!/usr/bin/env python3

import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.core.rss_parser import RSSParser
from src.utils.http import HTTPClient
from src.models.source import Source
from src.utils.content import ContentCleaner

async def test_hacker_news_scraping():
    """Test modern scraping on The Hacker News articles."""
    
    # Sample The Hacker News URLs to test
    test_urls = [
        "https://thehackernews.com/2025/08/blind-eagles-five-clusters-target.html",
        "https://thehackernews.com/2025/08/anthropic-disrupts-ai-powered.html",
        "https://thehackernews.com/2025/08/malicious-nx-packages-in-s1ngularity.html"
    ]
    
    # Create a mock source config for The Hacker News
    source_config = {
        'allow': ["thehackernews.com"],
        'post_url_regex': ["^https://thehackernews\\.com/.*"],
        'extract': {
            'prefer_jsonld': True,
            'title_selectors': ["h1", "meta[property='og:title']::attr(content)"],
            'date_selectors': ["meta[property='article:published_time']::attr(content)"],
            'body_selectors': ["article", "main", ".content", ".post-content"]
        }
    }
    
    source = Source(
        identifier="test_hacker_news",
        name="The Hacker News",
        url="https://thehackernews.com/",
        rss_url="https://feeds.feedburner.com/TheHackersNews",
        config=source_config
    )
    
    async with HTTPClient() as http_client:
        parser = RSSParser(http_client)
        
        print("Testing modern scraping on The Hacker News articles...")
        print("=" * 80)
        
        for i, url in enumerate(test_urls, 1):
            print(f"\n{i}. Testing URL: {url}")
            print("-" * 60)
            
            try:
                # Test modern scraping
                modern_content = await parser._extract_with_modern_scraping(url, source)
                
                if modern_content:
                    clean_text = ContentCleaner.html_to_text(modern_content).strip()
                    word_count = len(clean_text.split())
                    char_count = len(clean_text)
                    
                    print(f"✅ Modern scraping SUCCESSFUL")
                    print(f"   Content length: {char_count} characters")
                    print(f"   Word count: {word_count} words")
                    print(f"   First 200 chars: {clean_text[:200]}...")
                    
                    if char_count >= 1000:
                        print(f"   🎯 EXCELLENT: Substantial content ({char_count} chars)")
                    elif char_count >= 500:
                        print(f"   🟡 GOOD: Adequate content ({char_count} chars)")
                    else:
                        print(f"   🔴 POOR: Insufficient content ({char_count} chars)")
                        
                else:
                    print(f"❌ Modern scraping FAILED")
                    print(f"   No content extracted")
                    
            except Exception as e:
                print(f"❌ Error during scraping: {e}")
            
            print()
        
        print("=" * 80)
        print("Test complete!")

if __name__ == "__main__":
    asyncio.run(test_hacker_news_scraping())
