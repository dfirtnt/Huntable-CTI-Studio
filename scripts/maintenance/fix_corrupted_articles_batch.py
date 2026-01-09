#!/usr/bin/env python3
"""Fix all corrupted articles by re-scraping with fixed HTTPClient."""

import asyncio
import hashlib
import re
from datetime import datetime
from typing import List

from bs4 import BeautifulSoup

from src.database.manager import DatabaseManager
from src.database.models import ArticleTable
from src.utils.simhash import compute_article_simhash
from src.utils.http import HTTPClient, RequestConfig


async def fix_article(article_id: int) -> bool:
    """Re-scrape and fix a corrupted article."""
    db = DatabaseManager()
    
    # Get the article
    article = db.get_article(article_id)
    if not article:
        print(f"❌ Article {article_id} not found")
        return False
    
    print(f"\n📄 Article {article_id}: {article.title[:60]}...")
    print(f"🔗 URL: {article.canonical_url}")
    
    # Count current corruption
    replacement_chars = article.content.count('\ufffd')
    non_printable = len(re.sub(r'[[:print:][:space:]]', '', article.content))
    print(f"📊 Current: {len(article.content)} chars, {replacement_chars} replacement chars, {non_printable} non-printable")
    
    # Re-scrape the article using project's HTTPClient (now fixed)
    config = RequestConfig()
    http_client = HTTPClient(config=config)
    
    try:
        response = await http_client.get(article.canonical_url)
        if response.status_code != 200:
            print(f"❌ Failed to fetch URL: HTTP {response.status_code}")
            return False
        
        html_content = response.text
        
        # Check if content is still corrupted
        replacement_chars_new = html_content.count('\ufffd')
        if replacement_chars_new > len(html_content) * 0.1:
            print(f"⚠️ Scraped content still has {replacement_chars_new} replacement chars ({replacement_chars_new/len(html_content)*100:.1f}%)")
            # Still proceed, might be better than current
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove unwanted elements
        for script in soup(['script', 'style', 'meta', 'noscript', 'iframe', 'nav', 'header', 'footer']):
            script.decompose()
        
        # Try to find article content in common containers
        content_elem = None
        for selector in ['article', 'main', '.article-content', '.post-content', '.entry-content', '[role="main"]', '.content']:
            content_elem = soup.select_one(selector)
            if content_elem:
                print(f"✅ Found content with selector: {selector}")
                break
        
        if content_elem:
            content_text = content_elem.get_text(separator=' ', strip=True)
        else:
            # Fallback to body text
            body = soup.find('body')
            if body:
                content_text = body.get_text(separator=' ', strip=True)
            else:
                content_text = soup.get_text(separator=' ', strip=True)
        
        # Conservative sanitization
        sanitized_content = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', content_text)
        sanitized_content = re.sub(r'\s+', ' ', sanitized_content).strip()
        
        # Check for corruption in sanitized content
        replacement_chars_final = sanitized_content.count('\ufffd')
        non_printable_final = len(re.sub(r'[[:print:][:space:]]', '', sanitized_content))
        
        print(f"✅ Scraped: {len(sanitized_content)} chars, {replacement_chars_final} replacement chars, {non_printable_final} non-printable")
        
        if len(sanitized_content) < 500:
            print(f"⚠️ Scraped content too short ({len(sanitized_content)} chars)")
            if len(sanitized_content) <= len(article.content):
                print(f"⚠️ New content not longer than existing, skipping update")
                return False
        
        # Only update if new content is significantly better (less corruption)
        if replacement_chars_final > replacement_chars * 0.9 and replacement_chars > 100:
            print(f"⚠️ New content has similar corruption ({replacement_chars_final} vs {replacement_chars}), skipping")
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
            
            # Check if content_hash already exists
            existing = session.query(ArticleTable).filter(
                ArticleTable.content_hash == content_hash,
                ArticleTable.id != article_id
            ).first()
            
            if existing:
                print(f"⚠️ Content hash already exists for article {existing.id}, using modified hash")
                content_hash = hashlib.sha256(
                    f"{article.title}\n{sanitized_content}\n{article_id}".encode('utf-8')
                ).hexdigest()
            
            # Update fields
            db_article.content = sanitized_content
            db_article.content_hash = content_hash
            db_article.simhash = simhash
            db_article.simhash_bucket = simhash_bucket
            db_article.word_count = len(sanitized_content.split())
            db_article.updated_at = datetime.now()
            
            # Update summary if it's too short
            if len(article.summary or '') < 100:
                db_article.summary = sanitized_content[:500]
            
            session.commit()
            print(f"✅ Article {article_id} updated successfully")
            return True
            
    except Exception as e:
        print(f"❌ Error fixing article {article_id}: {e}")
        import traceback
        traceback.print_exc()
        return False


async def fix_articles_batch(article_ids: List[int], batch_size: int = 10):
    """Fix multiple articles in batches."""
    total = len(article_ids)
    results = []
    
    for i in range(0, total, batch_size):
        batch = article_ids[i:i+batch_size]
        print(f"\n{'='*60}")
        print(f"Processing batch {i//batch_size + 1}/{(total-1)//batch_size + 1} ({len(batch)} articles)")
        print(f"{'='*60}")
        
        for article_id in batch:
            success = await fix_article(article_id)
            results.append((article_id, success))
            # Small delay between requests
            await asyncio.sleep(1)
        
        # Brief pause between batches
        if i + batch_size < total:
            await asyncio.sleep(2)
    
    # Summary
    print(f"\n{'='*60}")
    print("Final Summary:")
    print(f"{'='*60}")
    successful = [aid for aid, success in results if success]
    failed = [aid for aid, success in results if not success]
    
    print(f"✅ Successfully fixed: {len(successful)}/{total} articles")
    if successful:
        print(f"   Sample IDs: {successful[:10]}{'...' if len(successful) > 10 else ''}")
    
    if failed:
        print(f"❌ Failed to fix: {len(failed)}/{total} articles")
        print(f"   Sample IDs: {failed[:10]}{'...' if len(failed) > 10 else ''}")
    
    return len(successful), len(failed)


async def main():
    """Main function."""
    import sys
    from src.database.models import ArticleTable
    
    if len(sys.argv) > 1 and sys.argv[1] == '--all':
        # Get all corrupted articles from database
        db = DatabaseManager()
        with db.get_session() as session:
            corrupted = session.query(ArticleTable.id).filter(
                ArticleTable.archived == False,
                ArticleTable.content.like('%%')
            ).all()
            article_ids = [aid for (aid,) in corrupted]
        
        print(f"🔧 Found {len(article_ids)} corrupted articles to fix")
    elif len(sys.argv) > 1:
        article_ids = [int(arg) for arg in sys.argv[1:]]
    else:
        print("Usage: python fix_corrupted_articles_batch.py --all")
        print("   or: python fix_corrupted_articles_batch.py <id1> <id2> ...")
        sys.exit(1)
    
    successful, failed = await fix_articles_batch(article_ids)
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())

