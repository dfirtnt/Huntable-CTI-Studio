#!/usr/bin/env python3
"""
Test RSS fallback to modern scraping functionality.
"""

import asyncio
import sys
import os
sys.path.insert(0, 'src')

from core.rss_parser import RSSParser
from utils.http import HTTPClient
from models.source import Source
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_rss_fallback():
    """Test the RSS fallback functionality."""
    print("🧪 Testing RSS Fallback to Modern Scraping")
    print("=" * 50)
    
    # Create HTTP client
    http_client = HTTPClient()
    async with http_client:
        # Create RSS parser
        rss_parser = RSSParser(http_client)
        
        # Test with a Huntress article URL
        test_url = "https://www.huntress.com/blog/ransomware-canaries-a-2022-update"
        
        # Create a mock source
        source = Source(
            id=1,
            identifier="huntress_cybersecurity",
            name="Huntress Cybersecurity Blog",
            url="https://www.huntress.com/blog",
            rss_url="https://www.huntress.com/blog/rss.xml",
            check_frequency=3600,
            active=True,
            config={}
        )
        
        print(f"Testing URL: {test_url}")
        
        try:
            # Test modern scraping directly
            content = await rss_parser._extract_with_modern_scraping(test_url, source)
            
            if content:
                text_length = len(content.strip())
                print(f"✅ Modern scraping successful!")
                print(f"Content length: {text_length} characters")
                print(f"Preview: {content[:200]}...")
            else:
                print("❌ Modern scraping failed")
                
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_rss_fallback())
