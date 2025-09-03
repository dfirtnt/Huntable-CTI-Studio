#!/usr/bin/env python3
"""Simple test script to validate configuration and URLs."""

import sys
import asyncio
import yaml
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from core.source_manager import SourceConfigLoader
from utils.http import HTTPClient

async def test_config_and_urls():
    """Test configuration loading and URL accessibility."""
    print("🔧 Testing Threat Intelligence Aggregator Configuration")
    print("=" * 60)
    
    # Test 1: Load configuration
    print("\n1. Loading source configuration...")
    try:
        loader = SourceConfigLoader()
        sources = loader.load_from_file("config/sources.yaml")
        print(f"✅ Successfully loaded {len(sources)} sources")
        
        # Display source summary
        for source in sources:
            print(f"   - {source.identifier}: {source.name} (tier {source.tier})")
    except Exception as e:
        print(f"❌ Configuration loading failed: {e}")
        return
    
    # Test 2: Test HTTP client
    print("\n2. Testing HTTP client...")
    async with HTTPClient() as client:
        # Test a few basic URLs
        test_urls = [
            "https://www.crowdstrike.com/blog/",
            "https://www.crowdstrike.com/blog/feed/",
            "https://msrc.microsoft.com/blog/",
        ]
        
        for url in test_urls:
            try:
                print(f"   Testing: {url}")
                response = await client.get(url)
                print(f"   ✅ {url} -> {response.status_code} ({len(response.content)} bytes)")
            except Exception as e:
                print(f"   ❌ {url} -> Error: {e}")
    
    # Test 3: Validate RSS feeds
    print("\n3. Testing RSS feeds...")
    from core.rss_parser import FeedValidator
    
    async with HTTPClient() as client:
        validator = FeedValidator()
        
        rss_sources = [s for s in sources if s.rss_url]
        print(f"   Found {len(rss_sources)} sources with RSS feeds")
        
        for source in rss_sources[:5]:  # Test first 5 RSS feeds
            try:
                print(f"   Testing RSS: {source.identifier}")
                result = await validator.validate_feed(source.rss_url, client)
                
                if result['valid']:
                    print(f"   ✅ {source.identifier} -> {result['entry_count']} entries")
                else:
                    print(f"   ❌ {source.identifier} -> Errors: {result['errors']}")
                    
            except Exception as e:
                print(f"   ❌ {source.identifier} -> Exception: {e}")
            
            # Rate limiting
            await asyncio.sleep(1)
    
    print("\n🎉 Configuration and URL testing complete!")

if __name__ == "__main__":
    asyncio.run(test_config_and_urls())
