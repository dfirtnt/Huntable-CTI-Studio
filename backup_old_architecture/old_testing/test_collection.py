#!/usr/bin/env python3
"""Comprehensive test script to test article collection."""

import sys
import asyncio
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from core.source_manager import SourceConfigLoader
from core.fetcher import ContentFetcher
from core.processor import ContentProcessor
from utils.http import HTTPClient

async def test_article_collection():
    """Test end-to-end article collection."""
    print("🚀 Testing Article Collection Pipeline")
    print("=" * 50)
    
    # Load configuration
    print("\n1. Loading sources...")
    loader = SourceConfigLoader()
    sources = loader.load_from_file("config/sources.yaml")
    
    # Convert to Source objects (without database)
    test_sources = []
    for config in sources[:3]:  # Test first 3 sources
        source = config.to_source()
        source.id = len(test_sources) + 1  # Mock ID
        test_sources.append(source)
        print(f"   - {source.identifier}: {source.name}")
    
    print(f"\n2. Testing content fetching...")
    
    # Initialize content fetcher and processor
    async with ContentFetcher() as fetcher:
        processor = ContentProcessor()
        
        total_articles = 0
        
        for source in test_sources:
            print(f"\n   Testing source: {source.identifier}")
            
            try:
                # Fetch articles
                result = await fetcher.fetch_source(source)
                
                if result.success:
                    print(f"   ✅ Method: {result.method}")
                    print(f"   ✅ Articles found: {len(result.articles)}")
                    print(f"   ✅ Response time: {result.response_time:.2f}s")
                    
                    if result.articles:
                        # Process articles
                        dedup_result = await processor.process_articles(result.articles)
                        
                        print(f"   ✅ Unique articles: {len(dedup_result.unique_articles)}")
                        print(f"   ✅ Duplicates: {len(dedup_result.duplicates)}")
                        
                        # Show sample article
                        if dedup_result.unique_articles:
                            sample = dedup_result.unique_articles[0]
                            print(f"   📰 Sample: {sample.title[:60]}...")
                            print(f"      URL: {sample.canonical_url}")
                            print(f"      Published: {sample.published_at}")
                            print(f"      Content length: {len(sample.content)} chars")
                            
                            quality_score = sample.metadata.get('quality_score', 0)
                            print(f"      Quality score: {quality_score:.2f}")
                        
                        total_articles += len(dedup_result.unique_articles)
                else:
                    print(f"   ❌ Failed: {result.error}")
                    
            except Exception as e:
                print(f"   ❌ Exception: {e}")
            
                # Rate limiting
                await asyncio.sleep(2)
            
        print(f"\n🎉 Collection test complete!")
        print(f"📊 Total unique articles collected: {total_articles}")
        
        # Test processor statistics
        stats = processor.get_statistics()
        print(f"📈 Processing stats: {stats}")

if __name__ == "__main__":
    asyncio.run(test_article_collection())
