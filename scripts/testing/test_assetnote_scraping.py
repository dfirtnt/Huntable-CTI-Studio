#!/usr/bin/env python3
"""Test web scraping fallback for Assetnote articles."""

import requests
from bs4 import BeautifulSoup
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_assetnote_article_scraping():
    """Test scraping content from an Assetnote article."""
    # Test with the latest article from the feed
    test_url = "https://blog.assetnote.io/2024/01/19/ivanti-pulse-connect-secure-auth-bypass-rce/"

    try:
        logger.info(f"Testing web scraping for: {test_url}")

        # Fetch the article page
        headers = {
            'User-Agent': 'CTIScraper/2.0 (Web Scraper)',
        }
        response = requests.get(test_url, headers=headers, timeout=30)
        response.raise_for_status()

        logger.info(f"Page fetched successfully, content length: {len(response.text)} chars")

        # Parse HTML
        soup = BeautifulSoup(response.text, 'html.parser')

        # Test different content selectors
        content_selectors = [
            ".post-content",
            ".entry-content",
            "article .content",
            ".blog-post-content",
            "main article",
            ".research-content",
            "article",
            "main",
            ".content"
        ]

        for selector in content_selectors:
            content_elem = soup.select_one(selector)
            if content_elem:
                extracted_content = str(content_elem)
                clean_text = content_elem.get_text().strip()

                logger.info(f"Selector '{selector}' found content: {len(clean_text)} chars")
                logger.info(f"Content preview: {clean_text[:200]}...")

                if len(clean_text) >= 1000:  # Our new minimum
                    logger.info(f"✅ SUCCESS: Found substantial content with selector '{selector}'")
                    logger.info(f"Content length: {len(clean_text)} chars")
                    return True
                else:
                    logger.warning(f"Content too short: {len(clean_text)} chars")
            else:
                logger.warning(f"Selector '{selector}' found no content")

        # If no selector worked, try to find any article content
        logger.info("Trying to find article content without specific selectors...")

        # Look for common article indicators
        article_tags = soup.find_all(['article', 'main', 'div'],
                                   class_=lambda x: x and any(word in x.lower() for word in ['post', 'content', 'article', 'entry']))

        for tag in article_tags:
            text = tag.get_text().strip()
            if len(text) >= 1000:
                logger.info(f"✅ Found content in {tag.name} with class '{tag.get('class')}': {len(text)} chars")
                return True

        logger.error("❌ No substantial content found with any method")
        return False

    except Exception as e:
        logger.error(f"Error testing article scraping: {e}")
        return False

if __name__ == "__main__":
    success = test_assetnote_article_scraping()
    if success:
        print("\n🎯 SUCCESS: Assetnote article content can be scraped!")
    else:
        print("\n❌ FAILED: Could not extract substantial content from Assetnote article")