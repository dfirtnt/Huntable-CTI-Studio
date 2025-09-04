#!/usr/bin/env python3
"""
Update existing short articles with full content using modern scraping.
"""

import asyncio
import sys
import os
sys.path.insert(0, 'src')

from database.manager import DatabaseManager
from core.rss_parser import RSSParser
from utils.http import HTTPClient
from utils.content import ContentCleaner
from models.source import Source
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def update_short_articles():
    """Update articles with short content using modern scraping."""
    print("🔄 Updating Short Articles with Full Content")
    print("=" * 50)
    
    # Create database manager
    db = DatabaseManager(database_url="postgresql://cti_user:cti_password_2024@postgres:5432/cti_scraper")
    
    # Create HTTP client
    http_client = HTTPClient()
    async with http_client:
        # Create RSS parser
        rss_parser = RSSParser(http_client)
        
        # Find articles with short content
        with db.engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT a.id, a.title, a.canonical_url, a.content, s.name as source_name, s.identifier as source_identifier
                    FROM articles a 
                    JOIN sources s ON a.source_id = s.id 
                    WHERE LENGTH(a.content) < 1000 
                    AND a.canonical_url LIKE 'http%'
                    ORDER BY LENGTH(a.content) ASC
                    LIMIT 10
                """)
            )
            short_articles = result.fetchall()
            
            if not short_articles:
                print("✅ No short articles found!")
                return
            
            print(f"Found {len(short_articles)} short articles to update:")
            
            updated_count = 0
            for article in short_articles:
                article_id, title, url, current_content, source_name, source_identifier = article
                current_length = len(current_content)
                
                print(f"\n📝 Article ID {article_id}: {title}")
                print(f"   Current length: {current_length} chars")
                print(f"   URL: {url}")
                print(f"   Source: {source_name}")
                
                # Create source object for the parser
                source = Source(
                    id=1,  # We don't need the actual ID for this
                    identifier=source_identifier,
                    name=source_name,
                    url="",  # Not needed for this operation
                    rss_url="",  # Not needed for this operation
                    check_frequency=3600,
                    active=True,
                    config={}
                )
                
                try:
                    # Try modern scraping
                    new_content = await rss_parser._extract_with_modern_scraping(url, source)
                    
                    if new_content:
                        new_length = len(ContentCleaner.html_to_text(new_content).strip())
                        improvement = new_length - current_length
                        
                        if improvement > 1000:  # Only update if we get significant improvement
                            # Update the article
                            conn.execute(
                                text("UPDATE articles SET content = :content WHERE id = :id"),
                                {"content": new_content, "id": article_id}
                            )
                            conn.commit()
                            
                            print(f"   ✅ Updated! New length: {new_length} chars (+{improvement})")
                            updated_count += 1
                        else:
                            print(f"   ⚠️  Not enough improvement: {new_length} chars (+{improvement})")
                    else:
                        print(f"   ❌ Modern scraping failed")
                        
                except Exception as e:
                    print(f"   ❌ Error: {e}")
                    continue
            
            print(f"\n📊 Summary: Updated {updated_count} out of {len(short_articles)} articles")

if __name__ == "__main__":
    asyncio.run(update_short_articles())
