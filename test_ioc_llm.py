#!/usr/bin/env python3
"""Test IOC extraction with LLM validation to verify the fix."""

import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from utils.ioc_extractor import HybridIOCExtractor

async def test_with_llm_validation():
    """Test IOC extraction with LLM validation."""
    try:
        print("Testing IOC extraction with LLM validation...")
        
        # Test content with some IOCs
        content = """
        Recent analysis reveals new indicators:
        - C2 Server: 192.168.1.100
        - Malicious Domain: malicious[.]com
        - Phishing URL: hxxp://evil[.]com/phish
        - Malware Hash: a1b2c3d4e5f6789012345678901234567890abcd
        - Email: attacker@evil[.]com
        """
        
        # Test with fake API key (should fallback gracefully)
        extractor = HybridIOCExtractor(use_llm_validation=True)
        
        print("1. Testing with fake API key (should fallback)...")
        result = await extractor.extract_iocs(content, api_key='fake_key', ai_model='ollama')
        print(f"   Result: {result.extraction_method}")
        print(f"   IOCs: {result.iocs}")
        print(f"   Success: {result is not None}")
        
        # Test with no API key (should use iocextract only)
        print("\n2. Testing with no API key (should use iocextract only)...")
        result2 = await extractor.extract_iocs(content, api_key=None, ai_model='ollama')
        print(f"   Result: {result2.extraction_method}")
        print(f"   IOCs: {result2.iocs}")
        print(f"   Success: {result2 is not None}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_with_llm_validation())
    print(f"\nTest {'passed' if success else 'failed'}")
