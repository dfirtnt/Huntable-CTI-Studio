#!/usr/bin/env python3
"""Test IOC extraction on article 1840 to reproduce the error."""

import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from utils.ioc_extractor import HybridIOCExtractor

async def test_article_1840():
    """Test IOC extraction on article 1840."""
    try:
        # Get the article content from database
        import subprocess
        result = subprocess.run([
            "docker", "exec", "cti_postgres", "psql", "-U", "cti_user", "-d", "cti_scraper", 
            "-c", "SELECT content FROM articles WHERE id = 1840;"
        ], capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"Database query failed: {result.stderr}")
            return False
            
        # Extract content from the output
        lines = result.stdout.strip().split('\n')
        content = None
        for line in lines:
            if line.strip() and not line.startswith('content') and not line.startswith('(') and not line.startswith('-'):
                content = line.strip()
                break
        
        if not content:
            print("No content found")
            return False
            
        print(f"Testing IOC extraction on article 1840...")
        print(f"Content length: {len(content)}")
        print(f"Content preview: {content[:200]}...")
        
        # Test the extractor
        extractor = HybridIOCExtractor(use_llm_validation=False)
        
        print("\n1. Testing extract_raw_iocs...")
        raw_iocs = extractor.extract_raw_iocs(content)
        print(f"Raw IOCs result: {raw_iocs}")
        print(f"Raw IOCs type: {type(raw_iocs)}")
        
        if raw_iocs is None:
            print("❌ extract_raw_iocs returned None!")
            return False
            
        print(f"Raw IOCs keys: {list(raw_iocs.keys()) if raw_iocs else 'None'}")
        
        print("\n2. Testing full extract_iocs...")
        result = await extractor.extract_iocs(content)
        print(f"Extraction result: {result}")
        print(f"Success: {result is not None}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_article_1840())
    print(f"\nTest {'passed' if success else 'failed'}")
