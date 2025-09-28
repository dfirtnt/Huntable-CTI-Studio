#!/usr/bin/env python3
"""Test script to debug Assetnote RSS feed parsing."""

import feedparser
import logging
from typing import Dict, Any
from datetime import datetime
import requests

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def test_assetnote_rss():
    """Test parsing the Assetnote RSS feed."""
    feed_url = "https://blog.assetnote.io/feed.xml"

    try:
        logger.info(f"Fetching RSS feed: {feed_url}")

        # Fetch RSS feed using requests
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        }
        response = requests.get(feed_url, headers=headers, timeout=30)
        response.raise_for_status()
        content = response.text

        logger.info(f"RSS feed fetched successfully, content length: {len(content)} chars")

        # Parse with feedparser
        feed_data = feedparser.parse(content)

        logger.info(f"Feed parsed, bozo: {feed_data.bozo}")
        if feed_data.bozo and feed_data.bozo_exception:
            logger.warning(f"Feed parsing warning: {feed_data.bozo_exception}")

        # Check feed info
        feed_info = feed_data.feed
        logger.info(f"Feed title: {getattr(feed_info, 'title', 'N/A')}")
        logger.info(f"Feed description: {getattr(feed_info, 'description', 'N/A')}")
        logger.info(f"Feed version: {getattr(feed_info, 'version', 'N/A')}")
        logger.info(f"Number of entries: {len(feed_data.entries)}")

        # Examine first few entries
        for i, entry in enumerate(feed_data.entries[:3]):
            logger.info(f"\n--- Entry {i+1} ---")
            logger.info(f"Title: {getattr(entry, 'title', 'N/A')}")
            logger.info(f"Link: {getattr(entry, 'link', 'N/A')}")
            logger.info(f"Published: {getattr(entry, 'published', 'N/A')}")
            logger.info(f"Updated: {getattr(entry, 'updated', 'N/A')}")

            # Check content fields
            content = None
            if hasattr(entry, 'content') and entry.content:
                if isinstance(entry.content, list) and entry.content:
                    content = entry.content[0].get('value', '')
                else:
                    content = str(entry.content)
                logger.info(f"Content length: {len(content)} chars")

            if hasattr(entry, 'description') and entry.description:
                description = entry.description
                logger.info(f"Description length: {len(description)} chars")
                if not content:
                    content = description

            if hasattr(entry, 'summary') and entry.summary:
                summary = entry.summary
                logger.info(f"Summary length: {len(summary)} chars")
                if not content:
                    content = summary

            if content:
                # Check if content length meets minimum requirements
                import html
                from bs4 import BeautifulSoup

                # Clean HTML to get text length
                soup = BeautifulSoup(content, 'lxml')
                clean_text = soup.get_text().strip()
                logger.info(f"Clean text length: {len(clean_text)} chars")
                logger.info(f"Clean text preview: {clean_text[:200]}...")

                # Check if it meets the 2000 char minimum from config
                if len(clean_text) >= 2000:
                    logger.info("✅ Content meets minimum length requirement (2000 chars)")
                else:
                    logger.warning(f"❌ Content too short: {len(clean_text)} chars (need >= 2000)")
            else:
                logger.warning("❌ No content found in entry")

        return len(feed_data.entries)

    except Exception as e:
        logger.error(f"Error testing RSS feed: {e}", exc_info=True)
        return 0

if __name__ == "__main__":
    article_count = test_assetnote_rss()
    print(f"\n🎯 Final result: Found {article_count} articles in Assetnote RSS feed")