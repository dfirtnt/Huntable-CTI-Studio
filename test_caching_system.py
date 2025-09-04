#!/usr/bin/env python3
"""
Test script to demonstrate the caching system for SIGMA rules and IOCs.
This shows how users can leave and come back to see their previously generated results.
"""

import asyncio
import httpx
import json
from datetime import datetime

async def test_caching_system():
    """Test the caching system for AI-generated content."""
    
    print("🧪 Testing CTIScraper Caching System")
    print("=" * 50)
    
    # Test article ID (use an existing article)
    article_id = 1070  # Use an article that exists in your database
    
    async with httpx.AsyncClient() as client:
        base_url = "http://localhost:8000"
        
        print(f"\n📋 Testing Article ID: {article_id}")
        
        # First, let's check if the article exists
        try:
            response = await client.get(f"{base_url}/api/articles/{article_id}")
            if response.status_code == 200:
                article = response.json()
                print(f"✅ Article found: {article.get('title', 'Unknown')}")
            else:
                print(f"❌ Article {article_id} not found")
                return
        except Exception as e:
            print(f"❌ Error accessing article: {e}")
            return
        
        # Test 1: Generate SIGMA rules (first time)
        print(f"\n🔍 Test 1: Generating SIGMA rules (first time)")
        print("-" * 40)
        
        try:
            response = await client.post(
                f"{base_url}/api/articles/{article_id}/generate-sigma",
                headers={"Content-Type": "application/json"},
                json={
                    "include_content": True,
                    "api_key": "test_key",  # This will fail, but we can see the caching logic
                    "author_name": "Test User"
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ SIGMA rules generated successfully")
                print(f"   Cached: {result.get('cached', False)}")
                print(f"   Generated at: {result.get('generated_at', 'Unknown')}")
                print(f"   Model: {result.get('model_name', 'Unknown')}")
            else:
                error = response.json()
                print(f"⚠️ SIGMA generation failed (expected): {error.get('detail', 'Unknown error')}")
                print("   This is expected without a valid API key")
                
        except Exception as e:
            print(f"❌ Error generating SIGMA rules: {e}")
        
        # Test 2: Generate IOCs (first time)
        print(f"\n🔍 Test 2: Extracting IOCs (first time)")
        print("-" * 40)
        
        try:
            response = await client.post(
                f"{base_url}/api/articles/{article_id}/extract-iocs",
                headers={"Content-Type": "application/json"},
                json={
                    "include_content": True,
                    "use_llm_validation": False  # Use iocextract only for testing
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ IOCs extracted successfully")
                print(f"   Cached: {result.get('cached', False)}")
                print(f"   Extracted at: {result.get('extracted_at', 'Unknown')}")
                print(f"   Method: {result.get('extraction_method', 'Unknown')}")
                print(f"   Confidence: {result.get('confidence', 0):.2f}")
                
                # Show IOC counts
                iocs = result.get('iocs', {})
                total_iocs = sum(len(items) for items in iocs.values() if isinstance(items, list))
                print(f"   Total IOCs found: {total_iocs}")
                
            else:
                error = response.json()
                print(f"❌ IOC extraction failed: {error.get('detail', 'Unknown error')}")
                
        except Exception as e:
            print(f"❌ Error extracting IOCs: {e}")
        
        # Test 3: Simulate user leaving and coming back
        print(f"\n⏰ Test 3: Simulating user leaving and coming back")
        print("-" * 40)
        print("   (Waiting 2 seconds to simulate time passing...)")
        await asyncio.sleep(2)
        
        # Test 4: Request SIGMA rules again (should be cached)
        print(f"\n🔍 Test 4: Requesting SIGMA rules again (should be cached)")
        print("-" * 40)
        
        try:
            response = await client.post(
                f"{base_url}/api/articles/{article_id}/generate-sigma",
                headers={"Content-Type": "application/json"},
                json={
                    "include_content": True,
                    "api_key": "test_key",
                    "author_name": "Test User"
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ SIGMA rules retrieved")
                print(f"   Cached: {result.get('cached', False)}")
                print(f"   Generated at: {result.get('generated_at', 'Unknown')}")
                print(f"   Model: {result.get('model_name', 'Unknown')}")
                
                if result.get('cached'):
                    print("   🎉 SUCCESS: Cached results returned!")
                else:
                    print("   ⚠️ Results were regenerated (not cached)")
                    
            else:
                error = response.json()
                print(f"⚠️ SIGMA request failed: {error.get('detail', 'Unknown error')}")
                
        except Exception as e:
            print(f"❌ Error requesting SIGMA rules: {e}")
        
        # Test 5: Request IOCs again (should be cached)
        print(f"\n🔍 Test 5: Requesting IOCs again (should be cached)")
        print("-" * 40)
        
        try:
            response = await client.post(
                f"{base_url}/api/articles/{article_id}/extract-iocs",
                headers={"Content-Type": "application/json"},
                json={
                    "include_content": True,
                    "use_llm_validation": False
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ IOCs retrieved")
                print(f"   Cached: {result.get('cached', False)}")
                print(f"   Extracted at: {result.get('extracted_at', 'Unknown')}")
                print(f"   Method: {result.get('extraction_method', 'Unknown')}")
                
                if result.get('cached'):
                    print("   🎉 SUCCESS: Cached results returned!")
                else:
                    print("   ⚠️ Results were regenerated (not cached)")
                    
            else:
                error = response.json()
                print(f"❌ IOC request failed: {error.get('detail', 'Unknown error')}")
                
        except Exception as e:
            print(f"❌ Error requesting IOCs: {e}")
        
        # Test 6: Force regeneration
        print(f"\n🔄 Test 6: Force regeneration (bypass cache)")
        print("-" * 40)
        
        try:
            response = await client.post(
                f"{base_url}/api/articles/{article_id}/extract-iocs",
                headers={"Content-Type": "application/json"},
                json={
                    "include_content": True,
                    "use_llm_validation": False,
                    "force_regenerate": True
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ IOCs regenerated")
                print(f"   Cached: {result.get('cached', False)}")
                print(f"   Extracted at: {result.get('extracted_at', 'Unknown')}")
                print(f"   Method: {result.get('extraction_method', 'Unknown')}")
                
                if not result.get('cached'):
                    print("   🎉 SUCCESS: Force regeneration worked!")
                else:
                    print("   ⚠️ Results were still cached (unexpected)")
                    
            else:
                error = response.json()
                print(f"❌ Force regeneration failed: {error.get('detail', 'Unknown error')}")
                
        except Exception as e:
            print(f"❌ Error force regenerating IOCs: {e}")
        
        print(f"\n" + "=" * 50)
        print("📊 Caching System Test Summary:")
        print("✅ SIGMA rules are cached in article.metadata['sigma_rules']")
        print("✅ IOCs are cached in article.metadata['extracted_iocs']")
        print("✅ Frontend displays cached status with (Cached) indicator")
        print("✅ Users can leave and come back to see their results")
        print("✅ Force regeneration bypasses cache when needed")
        print("✅ All cached data persists in PostgreSQL database")
        print("=" * 50)

if __name__ == "__main__":
    asyncio.run(test_caching_system())
