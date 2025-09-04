#!/usr/bin/env python3
"""Test script for hybrid IOC extraction."""

import asyncio
import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from src.utils.ioc_extractor import HybridIOCExtractor

async def test_hybrid_extraction():
    """Test the hybrid IOC extraction functionality."""
    
    # Sample threat intelligence content with IOCs
    test_content = """
    Threat Analysis Report: APT29 Campaign
    
    The threat actor used the following indicators:
    - C2 Server: 192.168.1.100
    - Malware Hash: a1b2c3d4e5f6789012345678901234567890abcd
    - Domain: malicious[.]com
    - Email: attacker@evil[.]com
    - Registry Key: HKEY_LOCAL_MACHINE\\Software\\Malware
    - File Path: C:\\Windows\\System32\\malware.exe
    - Process: cmd.exe /c powershell -enc
    - Mutex: Global\\MalwareMutex
    - Named Pipe: \\\\.\\pipe\\malware_pipe
    - Event ID: 4624
    """
    
    print("🔍 Testing Hybrid IOC Extraction")
    print("=" * 50)
    
    # Test iocextract only
    print("\n1. Testing iocextract only (no LLM validation):")
    extractor = HybridIOCExtractor(use_llm_validation=False)
    result = await extractor.extract_iocs(test_content)
    
    print(f"   Method: {result.extraction_method}")
    print(f"   Confidence: {result.confidence:.2f}")
    print(f"   Processing Time: {result.processing_time:.2f}s")
    print(f"   Raw Count: {result.raw_count}")
    print(f"   Validated Count: {result.validated_count}")
    
    print("\n   Extracted IOCs:")
    for ioc_type, values in result.iocs.items():
        if values:
            print(f"   - {ioc_type}: {values}")
    
    # Test hybrid approach (without API key)
    print("\n2. Testing hybrid approach (no API key - falls back to iocextract):")
    extractor_hybrid = HybridIOCExtractor(use_llm_validation=True)
    result_hybrid = await extractor_hybrid.extract_iocs(test_content)
    
    print(f"   Method: {result_hybrid.extraction_method}")
    print(f"   Confidence: {result_hybrid.confidence:.2f}")
    print(f"   Processing Time: {result_hybrid.processing_time:.2f}s")
    print(f"   Raw Count: {result_hybrid.raw_count}")
    print(f"   Validated Count: {result_hybrid.validated_count}")
    
    print("\n✅ Hybrid IOC extraction test completed!")
    print("\nKey Benefits:")
    print("- Fast extraction with iocextract")
    print("- Defang support (e.g., malicious[.]com)")
    print("- Graceful fallback when LLM unavailable")
    print("- Rich metadata and confidence scoring")

if __name__ == "__main__":
    asyncio.run(test_hybrid_extraction())
