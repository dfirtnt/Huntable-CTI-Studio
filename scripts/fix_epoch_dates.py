#!/usr/bin/env python3
"""
Script to fix epoch dates (1970-01-21) in existing articles by fetching correct dates from article pages.
"""

import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime
import logging
from typing import Optional

from src.database.async_manager import AsyncDatabaseManager
from src.utils.http import HTTPClient
from src.utils.content import DateExtractor
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def extract_date_from_page(url: str, http_client: HTTPClient) -> Optional[datetime]:
    """Extract publication date from article page metadata."""
    try:
        # Fetch the article page
        response = await http_client.get(url)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'lxml')
        
        # Try different meta tags for publication date
        date_selectors = [
            'meta[name="published-date"]',
            'meta[name="article:published_time"]',
            'meta[property="article:published_time"]',
            'meta[name="date"]',
            'meta[name="pubdate"]',
            'meta[name="publishdate"]',
            'meta[name="publication_date"]',
            'meta[name="og:published_time"]',
            'meta[property="og:published_time"]',
            'time[datetime]',
            'time[pubdate]'
        ]
        
        for selector in date_selectors:
            element = soup.select_one(selector)
            if element:
                date_str = element.get('content') or element.get('datetime')
                if date_str:
                    parsed_date = DateExtractor.parse_date(date_str)
                    if parsed_date and parsed_date.year > 1970:
                        logger.info(f"Extracted date from page metadata: {date_str} -> {parsed_date}")
                        return parsed_date
        
        # Try to extract date from URL patterns
        url_date = DateExtractor.extract_date_from_url(url)
        if url_date and url_date.year > 1970:
            logger.info(f"Extracted date from URL pattern: {url_date}")
            return url_date
        
        return None
        
    except Exception as e:
        logger.warning(f"Failed to extract date from page {url}: {e}")
        return None


async def fix_epoch_dates():
    """Fix epoch dates in existing articles."""
    # Initialize database manager
    db_manager = AsyncDatabaseManager()
    
    try:
        # Get all articles with epoch dates from Recorded Future
        async with db_manager.get_session() as session:
            from sqlalchemy import text
            result = await session.execute(text("""
                SELECT id, title, canonical_url, published_at 
                FROM articles 
                WHERE source_id = 22 AND published_at < '1971-01-01'
                ORDER BY id
            """))
            articles = result.fetchall()
        
        logger.info(f"Found {len(articles)} articles with epoch dates to fix")
        
        fixed_count = 0
        failed_count = 0
        
        # Use HTTPClient as async context manager
        async with HTTPClient() as http_client:
            for article in articles:
                article_id = article.id
                title = article.title
                url = article.canonical_url
                current_date = article.published_at
                
                logger.info(f"Processing article {article_id}: {title[:50]}...")
                
                # Extract correct date from article page
                correct_date = await extract_date_from_page(url, http_client)
                
                if correct_date:
                    # Update the article with correct date
                    try:
                        async with db_manager.get_session() as session:
                            await session.execute(text("""
                                UPDATE articles 
                                SET published_at = :new_date, updated_at = NOW()
                                WHERE id = :article_id
                            """), {
                                'new_date': correct_date,
                                'article_id': article_id
                            })
                            await session.commit()
                        
                        logger.info(f"✅ Updated article {article_id}: {current_date} -> {correct_date}")
                        fixed_count += 1
                        
                    except Exception as e:
                        logger.error(f"❌ Failed to update article {article_id}: {e}")
                        failed_count += 1
                else:
                    logger.warning(f"⚠️ Could not extract date for article {article_id}: {url}")
                    failed_count += 1
                
                # Small delay to be respectful to the server
                await asyncio.sleep(1)
        
        logger.info(f"🎉 Fix completed!")
        logger.info(f"✅ Fixed: {fixed_count} articles")
        logger.info(f"❌ Failed: {failed_count} articles")
        
    except Exception as e:
        logger.error(f"Error in fix_epoch_dates: {e}")


if __name__ == "__main__":
    asyncio.run(fix_epoch_dates())
