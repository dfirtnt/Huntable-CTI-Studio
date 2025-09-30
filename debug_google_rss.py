#!/usr/bin/env python3
"""Debug script to test Google Cloud RSS feed parsing."""

import asyncio
import sys
import feedparser

async def test_with_httpclient():
    """Test with the actual HTTPClient used by the scraper."""
    from src.utils.http import HTTPClient

    print("=" * 80)
    print("TEST 1: Using HTTPClient (what the scraper uses)")
    print("=" * 80)

    async with HTTPClient() as client:
        response = await client.get("https://feeds.feedburner.com/threatintelligence/pvexyqv7v0v")

        print(f"Status: {response.status_code}")
        print(f"Headers: {dict(response.headers)}")
        print(f"Response text length: {len(response.text)}")
        print(f"First 500 chars of response.text:\n{response.text[:500]}\n")

        # Parse with feedparser
        feed = feedparser.parse(response.text)

        print(f"\nFeed entries: {len(feed.entries)}")
        print(f"Feed bozo: {feed.bozo}")
        if feed.bozo:
            print(f"Bozo exception: {feed.bozo_exception}")

        if feed.entries:
            entry = feed.entries[0]
            print(f"\nFirst entry:")
            print(f"  Title: {entry.get('title', 'N/A')}")
            print(f"  Link: {entry.get('link', 'N/A')}")
            print(f"  Has 'description': {hasattr(entry, 'description')}")
            print(f"  Has 'summary': {hasattr(entry, 'summary')}")
            print(f"  Has 'content': {hasattr(entry, 'content')}")

            if hasattr(entry, 'description'):
                desc = entry.description
                print(f"  Description length: {len(desc)}")
                print(f"  Description first 200 chars: {desc[:200]}")
            else:
                print(f"  Description: MISSING!")

            # Check all attributes
            print(f"\n  All entry attributes: {dir(entry)}")

def test_with_direct_fetch():
    """Test with direct fetch using requests/httpx."""
    import httpx

    print("\n" + "=" * 80)
    print("TEST 2: Using httpx directly")
    print("=" * 80)

    response = httpx.get("https://feeds.feedburner.com/threatintelligence/pvexyqv7v0v", timeout=15)

    print(f"Status: {response.status_code}")
    print(f"Response text length: {len(response.text)}")
    print(f"First 500 chars:\n{response.text[:500]}\n")

    feed = feedparser.parse(response.text)

    print(f"Feed entries: {len(feed.entries)}")
    if feed.entries:
        entry = feed.entries[0]
        print(f"First entry has description: {hasattr(entry, 'description')}")
        if hasattr(entry, 'description'):
            print(f"Description length: {len(entry.description)}")

if __name__ == "__main__":
    print("Testing Google Cloud RSS feed parsing...\n")

    # Test with direct fetch first
    test_with_direct_fetch()

    # Test with HTTPClient
    asyncio.run(test_with_httpclient())