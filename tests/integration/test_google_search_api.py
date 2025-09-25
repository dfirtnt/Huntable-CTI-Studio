#!/usr/bin/env python3
"""Test script for Google Custom Search API integration."""

import asyncio
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.core.google_search import GoogleSearchAPI, GoogleSearchFetcher
from src.models.source import Source, SourceConfig
from src.utils.http import HTTPClient


async def test_google_search_api():
    """Test Google Search API directly."""
    print("🔍 Testing Google Custom Search API...")
    
    api_key = os.getenv('GOOGLE_SEARCH_API_KEY')
    search_engine_id = os.getenv('GOOGLE_SEARCH_ENGINE_ID')
    
    if not api_key or not search_engine_id:
        print("❌ Missing environment variables:")
        print("   GOOGLE_SEARCH_API_KEY")
        print("   GOOGLE_SEARCH_ENGINE_ID")
        print("\nSee GOOGLE_SEARCH_SETUP.md for setup instructions")
        return False
    
    try:
        api = GoogleSearchAPI(api_key, search_engine_id)
        
        # Test search
        results = await api.search(
            query="threat intelligence malware analysis",
            num_results=5,
            date_restrict="m1"  # Past month
        )
        
        print(f"✅ API Test Successful: Found {len(results)} results")
        
        for i, result in enumerate(results[:3], 1):
            print(f"   {i}. {result.title}")
            print(f"      {result.link}")
            print(f"      {result.snippet[:100]}...")
            print()
        
        await api.close()
        return True
        
    except Exception as e:
        print(f"❌ API Test Failed: {e}")
        return False


async def test_google_search_fetcher():
    """Test Google Search Fetcher integration."""
    print("\n🔍 Testing Google Search Fetcher...")
    
    api_key = os.getenv('GOOGLE_SEARCH_API_KEY')
    search_engine_id = os.getenv('GOOGLE_SEARCH_ENGINE_ID')
    
    if not api_key or not search_engine_id:
        print("❌ Missing environment variables")
        return False
    
    try:
        # Create test source
        source_config = SourceConfig(
            source_type="google_search",
            search_config={
                "api_key": api_key,
                "search_engine_id": search_engine_id,
                "queries": ["threat intelligence malware"],
                "max_results": 5,
                "date_range": "past_month"
            }
        )
        
        source = Source(
            id=999,
            identifier="test_google_search",
            name="Test Google Search",
            url="https://www.google.com/search",
            rss_url=None,
            check_frequency=3600,
            active=True,
            config=source_config
        )
        
        # Test fetcher
        http_client = HTTPClient()
        fetcher = GoogleSearchFetcher(http_client)
        
        async with http_client:
            articles = await fetcher.fetch_source(source)
        
        print(f"✅ Fetcher Test Successful: Found {len(articles)} articles")
        
        for i, article in enumerate(articles[:3], 1):
            print(f"   {i}. {article.title}")
            print(f"      {article.canonical_url}")
            print(f"      Published: {article.published_at}")
            print()
        
        await fetcher.close()
        return True
        
    except Exception as e:
        print(f"❌ Fetcher Test Failed: {e}")
        return False


async def main():
    """Run all tests."""
    print("🚀 Google Custom Search API Integration Test")
    print("=" * 50)
    
    # Test 1: Direct API
    api_success = await test_google_search_api()
    
    # Test 2: Fetcher Integration
    fetcher_success = await test_google_search_fetcher()
    
    print("\n" + "=" * 50)
    if api_success and fetcher_success:
        print("🎉 All tests passed! Google Search integration is ready.")
        print("\nNext steps:")
        print("1. Add your API credentials to environment variables")
        print("2. Restart the CTI Scraper application")
        print("3. The Google Search source will be available in the sources list")
    else:
        print("❌ Some tests failed. Check the error messages above.")
        print("\nTroubleshooting:")
        print("1. Verify API key and search engine ID")
        print("2. Ensure Custom Search API is enabled")
        print("3. Check your Google Cloud Console quotas")


if __name__ == "__main__":
    asyncio.run(main())
