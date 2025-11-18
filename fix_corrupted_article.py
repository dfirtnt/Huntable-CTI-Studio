#!/usr/bin/env python3
"""Fix corrupted article by re-scraping and updating content."""

import asyncio
import hashlib
import re
from datetime import datetime

from bs4 import BeautifulSoup

from src.database.manager import DatabaseManager
from src.database.models import ArticleTable
from src.models.article import Article
from src.utils.simhash import compute_article_simhash
from src.utils.http import HTTPClient, RequestConfig


async def fix_article(article_id: int):
    """Re-scrape and fix a corrupted article."""
    db = DatabaseManager()
    
    # Get the article
    article = db.get_article(article_id)
    if not article:
        print(f"❌ Article {article_id} not found")
        return False
    
    print(f"📄 Article: {article.title}")
    print(f"🔗 URL: {article.canonical_url}")
    print(f"📊 Current content length: {len(article.content)} chars")
    
    # Re-scrape the article using project's HTTPClient
    config = RequestConfig()
    http_client = HTTPClient(config=config)
    
    try:
        response = await http_client.get(article.canonical_url)
        if response.status_code != 200:
            print(f"❌ Failed to fetch URL: HTTP {response.status_code}")
            return False
        
        html_content = response.text
        
        soup = BeautifulSoup(html_content, 'html.parser')
        for script in soup(['script', 'style', 'meta', 'noscript', 'iframe']):
            script.decompose()
        content_text = soup.get_text(separator=' ', strip=True)
        
        # Conservative sanitization
        sanitized_content = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', content_text)
        sanitized_content = re.sub(r'\s+', ' ', sanitized_content).strip()
        
        print(f"✅ Scraped content length: {len(sanitized_content)} chars")
        
        if len(sanitized_content) < 100:
            print(f"⚠️ Scraped content too short, aborting")
            return False
        
        # Compute new hash and simhash
        content_hash = hashlib.sha256(f"{article.title}\n{sanitized_content}".encode('utf-8')).hexdigest()
        simhash, simhash_bucket = compute_article_simhash(sanitized_content, article.title)
        
        # Update the article
        with db.get_session() as session:
            db_article = session.query(ArticleTable).filter(ArticleTable.id == article_id).first()
            if not db_article:
                print(f"❌ Article {article_id} not found in database")
                return False
            
            # Check if content_hash already exists (would cause unique constraint violation)
            existing = session.query(ArticleTable).filter(
                ArticleTable.content_hash == content_hash,
                ArticleTable.id != article_id
            ).first()
            
            if existing:
                print(f"⚠️ Content hash already exists for article {existing.id}, updating hash to avoid conflict")
                # Use a modified hash to avoid conflict
                content_hash = hashlib.sha256(
                    f"{article.title}\n{sanitized_content}\n{article_id}".encode('utf-8')
                ).hexdigest()
            
            # Update fields
            db_article.content = sanitized_content
            db_article.content_hash = content_hash
            db_article.simhash = simhash
            db_article.simhash_bucket = simhash_bucket
            db_article.word_count = len(sanitized_content.split())
            db_article.updated_at = datetime.utcnow()
            
            # Update summary if it's corrupted too
            if len(article.summary or '') < 50:
                db_article.summary = sanitized_content[:500]
            
            session.commit()
            print(f"✅ Article {article_id} updated successfully")
            return True
        
    except Exception as e:
        print(f"❌ Error fixing article: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Main function."""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python fix_corrupted_article.py <article_id>")
        sys.exit(1)
    
    article_id = int(sys.argv[1])
    success = await fix_article(article_id)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())

