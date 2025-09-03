#!/usr/bin/env python3
"""
Script to check and print working URLs for all sources in the CTI Scraper.
"""

import yaml
import requests
import time
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys

def load_sources():
    """Load sources from the YAML configuration file."""
    try:
        with open('config/sources.yaml', 'r') as file:
            config = yaml.safe_load(file)
        return config.get('sources', [])
    except Exception as e:
        print(f"Error loading sources: {e}")
        return []

def check_url_health(url, timeout=10):
    """Check if a URL is accessible."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, timeout=timeout, headers=headers, allow_redirects=True)
        return response.status_code == 200
    except Exception as e:
        return False

def check_rss_url_health(url, timeout=10):
    """Check if an RSS URL is accessible and returns valid RSS content."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, timeout=timeout, headers=headers, allow_redirects=True)
        if response.status_code == 200:
            content = response.text.lower()
            # Check if it contains RSS/XML indicators
            return any(indicator in content for indicator in ['<rss', '<feed', 'xml', 'rss'])
        return False
    except Exception as e:
        return False

def check_source_health(source):
    """Check both main URL and RSS URL for a source."""
    source_id = source.get('id', 'unknown')
    name = source.get('name', 'Unknown')
    main_url = source.get('url', '')
    rss_url = source.get('rss_url', '')
    tier = source.get('tier', 'unknown')
    active = source.get('active', True)
    
    if not active:
        return {
            'id': source_id,
            'name': name,
            'tier': tier,
            'main_url': main_url,
            'rss_url': rss_url,
            'main_url_working': False,
            'rss_url_working': False,
            'status': 'INACTIVE'
        }
    
    main_working = check_url_health(main_url) if main_url else False
    rss_working = check_rss_url_health(rss_url) if rss_url else False
    
    status = 'WORKING' if (main_working or rss_working) else 'FAILED'
    
    return {
        'id': source_id,
        'name': name,
        'tier': tier,
        'main_url': main_url,
        'rss_url': rss_url,
        'main_url_working': main_working,
        'rss_url_working': rss_working,
        'status': status
    }

def print_working_urls():
    """Print all working URLs organized by tier."""
    print("🔍 Checking CTI Scraper Source URLs...")
    print("=" * 80)
    
    sources = load_sources()
    if not sources:
        print("❌ No sources found in configuration file.")
        return
    
    print(f"📊 Found {len(sources)} sources to check...")
    print()
    
    # Check all sources concurrently
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_source = {executor.submit(check_source_health, source): source for source in sources}
        results = []
        
        for future in as_completed(future_to_source):
            result = future.result()
            results.append(result)
            # Print progress
            status_icon = "✅" if result['status'] == 'WORKING' else "❌" if result['status'] == 'FAILED' else "⏸️"
            print(f"{status_icon} {result['name']} (Tier {result['tier']}) - {result['status']}")
    
    # Organize results by tier
    tier_1_sources = [r for r in results if r['tier'] == 1]
    tier_2_sources = [r for r in results if r['tier'] == 2]
    other_sources = [r for r in results if r['tier'] not in [1, 2]]
    
    # Print detailed results
    print("\n" + "=" * 80)
    print("📋 DETAILED RESULTS BY TIER")
    print("=" * 80)
    
    # Tier 1 Sources
    print("\n🎯 TIER 1: PREMIUM THREAT INTELLIGENCE SOURCES")
    print("-" * 60)
    working_tier1 = 0
    for source in tier_1_sources:
        status_icon = "✅" if source['status'] == 'WORKING' else "❌" if source['status'] == 'FAILED' else "⏸️"
        print(f"{status_icon} {source['name']}")
        if source['main_url_working']:
            print(f"   🌐 Main URL: {source['main_url']}")
        if source['rss_url_working']:
            print(f"   📡 RSS URL: {source['rss_url']}")
        if source['status'] == 'WORKING':
            working_tier1 += 1
        print()
    
    # Tier 2 Sources
    print("\n📰 TIER 2: NEWS AND ANALYSIS SOURCES")
    print("-" * 60)
    working_tier2 = 0
    for source in tier_2_sources:
        status_icon = "✅" if source['status'] == 'WORKING' else "❌" if source['status'] == 'FAILED' else "⏸️"
        print(f"{status_icon} {source['name']}")
        if source['main_url_working']:
            print(f"   🌐 Main URL: {source['main_url']}")
        if source['rss_url_working']:
            print(f"   📡 RSS URL: {source['rss_url']}")
        if source['status'] == 'WORKING':
            working_tier2 += 1
        print()
    
    # Other Sources
    if other_sources:
        print("\n🔧 OTHER SOURCES")
        print("-" * 60)
        working_other = 0
        for source in other_sources:
            status_icon = "✅" if source['status'] == 'WORKING' else "❌" if source['status'] == 'FAILED' else "⏸️"
            print(f"{status_icon} {source['name']} (Tier {source['tier']})")
            if source['main_url_working']:
                print(f"   🌐 Main URL: {source['main_url']}")
            if source['rss_url_working']:
                print(f"   📡 RSS URL: {source['rss_url']}")
            if source['status'] == 'WORKING':
                working_other += 1
            print()
    
    # Summary
    print("=" * 80)
    print("📊 SUMMARY")
    print("=" * 80)
    total_sources = len(results)
    total_working = len([r for r in results if r['status'] == 'WORKING'])
    total_inactive = len([r for r in results if r['status'] == 'INACTIVE'])
    total_failed = len([r for r in results if r['status'] == 'FAILED'])
    
    print(f"📈 Total Sources: {total_sources}")
    print(f"✅ Working Sources: {total_working}")
    print(f"⏸️  Inactive Sources: {total_inactive}")
    print(f"❌ Failed Sources: {total_failed}")
    print(f"📊 Success Rate: {(total_working/total_sources)*100:.1f}%")
    
    print(f"\n🎯 Tier 1 Working: {working_tier1}/{len(tier_1_sources)} ({(working_tier1/len(tier_1_sources))*100:.1f}%)")
    print(f"📰 Tier 2 Working: {working_tier2}/{len(tier_2_sources)} ({(working_tier2/len(tier_2_sources))*100:.1f}%)")
    
    # Print all working URLs in a simple list
    print("\n" + "=" * 80)
    print("🔗 ALL WORKING URLS")
    print("=" * 80)
    
    working_sources = [r for r in results if r['status'] == 'WORKING']
    for source in working_sources:
        print(f"\n📌 {source['name']} (Tier {source['tier']})")
        if source['main_url_working']:
            print(f"   🌐 {source['main_url']}")
        if source['rss_url_working']:
            print(f"   📡 {source['rss_url']}")

if __name__ == "__main__":
    try:
        print_working_urls()
    except KeyboardInterrupt:
        print("\n\n⏹️  Check interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
