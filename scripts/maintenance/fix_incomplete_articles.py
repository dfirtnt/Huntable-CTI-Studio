#!/usr/bin/env python3
"""Fix incomplete articles by re-scraping and updating content."""

import asyncio
import hashlib
import re
from datetime import datetime

from bs4 import BeautifulSoup

from src.database.manager import DatabaseManager
from src.database.models import ArticleTable
from src.utils.http import HTTPClient, RequestConfig
from src.utils.simhash import compute_article_simhash


async def fix_article(article_id: int) -> bool:
    """Re-scrape and fix an incomplete article."""
    db = DatabaseManager()

    # Get the article
    article = db.get_article(article_id)
    if not article:
        print(f"❌ Article {article_id} not found")
        return False

    print(f"\n📄 Article {article_id}: {article.title}")
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

        soup = BeautifulSoup(html_content, "html.parser")

        # Remove unwanted elements
        for script in soup(["script", "style", "meta", "noscript", "iframe", "nav", "header", "footer"]):
            script.decompose()

        # Try to find article content in common containers
        content_elem = None
        for selector in ["article", "main", ".article-content", ".post-content", ".entry-content", '[role="main"]']:
            content_elem = soup.select_one(selector)
            if content_elem:
                print(f"✅ Found content with selector: {selector}")
                break

        if content_elem:
            content_text = content_elem.get_text(separator=" ", strip=True)
        else:
            # Fallback to body text
            body = soup.find("body")
            if body:
                content_text = body.get_text(separator=" ", strip=True)
            else:
                content_text = soup.get_text(separator=" ", strip=True)

        # Conservative sanitization
        sanitized_content = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", content_text)
        sanitized_content = re.sub(r"\s+", " ", sanitized_content).strip()

        print(f"✅ Scraped content length: {len(sanitized_content)} chars")

        if len(sanitized_content) < 500:
            print(f"⚠️ Scraped content still too short ({len(sanitized_content)} chars), may need manual review")
            # Still update if it's longer than current
            if len(sanitized_content) <= len(article.content):
                print("⚠️ New content not longer than existing, skipping update")
                return False

        # Compute new hash and simhash
        content_hash = hashlib.sha256(f"{article.title}\n{sanitized_content}".encode()).hexdigest()
        simhash, simhash_bucket = compute_article_simhash(sanitized_content, article.title)

        # Update the article
        with db.get_session() as session:
            db_article = session.query(ArticleTable).filter(ArticleTable.id == article_id).first()
            if not db_article:
                print(f"❌ Article {article_id} not found in database")
                return False

            # Check if content_hash already exists (would cause unique constraint violation)
            existing = (
                session.query(ArticleTable)
                .filter(ArticleTable.content_hash == content_hash, ArticleTable.id != article_id)
                .first()
            )

            if existing:
                print(f"⚠️ Content hash already exists for article {existing.id}, using modified hash")
                # Use a modified hash to avoid conflict
                content_hash = hashlib.sha256(
                    f"{article.title}\n{sanitized_content}\n{article_id}".encode()
                ).hexdigest()

            # Update fields
            db_article.content = sanitized_content
            db_article.content_hash = content_hash
            db_article.simhash = simhash
            db_article.simhash_bucket = simhash_bucket
            db_article.word_count = len(sanitized_content.split())
            db_article.updated_at = datetime.now()

            # Update summary if it's too short
            if len(article.summary or "") < 100:
                db_article.summary = sanitized_content[:500]

            session.commit()
            print(f"✅ Article {article_id} updated successfully")
            return True

    except Exception as e:
        print(f"❌ Error fixing article {article_id}: {e}")
        import traceback

        traceback.print_exc()
        return False


async def fix_articles(article_ids: list[int]):
    """Fix multiple articles."""
    results = []
    for article_id in article_ids:
        success = await fix_article(article_id)
        results.append((article_id, success))
        # Small delay between requests
        await asyncio.sleep(1)

    # Summary
    print(f"\n{'=' * 60}")
    print("Summary:")
    print(f"{'=' * 60}")
    successful = [aid for aid, success in results if success]
    failed = [aid for aid, success in results if not success]

    if successful:
        print(f"✅ Successfully fixed: {len(successful)} articles")
        print(f"   IDs: {', '.join(map(str, successful))}")

    if failed:
        print(f"❌ Failed to fix: {len(failed)} articles")
        print(f"   IDs: {', '.join(map(str, failed))}")

    return len(successful), len(failed)


async def main():
    """Main function."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python fix_incomplete_articles.py <article_id1> [article_id2] ...")
        print("\nOr use predefined options:")
        print("  python fix_incomplete_articles.py --auto          # Fix known incomplete articles")
        print("  python fix_incomplete_articles.py --recent        # Fix corrupted articles from last 2 days")
        sys.exit(1)

    if sys.argv[1] == "--auto":
        # Predefined list of incomplete articles
        article_ids = [2353, 2166, 1308]
        print(f"🔧 Auto-fixing {len(article_ids)} incomplete articles...")
    elif sys.argv[1] == "--recent":
        # Find corrupted articles from last 2 days
        from sqlalchemy import func

        from src.database.manager import DatabaseManager
        from src.database.models import ArticleTable

        db = DatabaseManager()
        with db.get_session() as session:
            # Find articles with corruption indicators from last 2 days
            corrupted = (
                session.query(ArticleTable.id)
                .filter(
                    ArticleTable.archived == False,
                    ArticleTable.discovered_at >= func.now() - func.make_interval(days=2),
                    func.length(ArticleTable.content) > 0,
                )
                .all()
            )

            # Filter by corruption patterns
            article_ids = []
            for (article_id,) in corrupted:
                article = db.get_article(article_id)
                if not article:
                    continue

                content_len = len(article.content)
                non_printable = len(re.sub(r"[[:print:][:space:]]", "", article.content))
                special_ratio = len(re.sub(r"[a-zA-Z0-9\s]", "", article.content)) / max(content_len, 1)

                # Check for corruption indicators
                if non_printable > 200 or (content_len > 1000 and special_ratio > 0.3):
                    article_ids.append(article_id)

            print(f"🔧 Found {len(article_ids)} corrupted articles from last 2 days")
            print(f"   IDs: {article_ids}")
    else:
        article_ids = [int(arg) for arg in sys.argv[1:]]

    successful, failed = await fix_articles(article_ids)
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
