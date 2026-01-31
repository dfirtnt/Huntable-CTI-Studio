#!/usr/bin/env python3
"""Fix all corrupted articles by re-scraping with fixed HTTPClient."""

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
    """Re-scrape and fix a corrupted article."""
    db = DatabaseManager()

    # Get the article
    article = db.get_article(article_id)
    if not article:
        print(f"❌ Article {article_id} not found")
        return False

    print(f"\n📄 Article {article_id}: {article.title}")
    print(f"🔗 URL: {article.canonical_url}")
    print(f"📊 Current content length: {len(article.content)} chars")

    # Check current corruption level
    replacement_chars = article.content.count("�")
    # Match non-printable characters (excluding printable ASCII and whitespace)
    non_printable = len(re.sub(r"[\x20-\x7E\s]", "", article.content))
    print(f"   Current corruption: {replacement_chars} replacement chars, {non_printable} non-printable")

    # Re-scrape the article using fixed HTTPClient
    config = RequestConfig()
    http_client = HTTPClient(config=config)

    try:
        response = await http_client.get(article.canonical_url)
        if response.status_code != 200:
            print(f"❌ Failed to fetch URL: HTTP {response.status_code}")
            return False

        html_content = response.text

        # Check if new content is corrupted
        new_replacement_chars = html_content.count("�")
        new_non_printable = len(re.sub(r"[\x20-\x7E\s]", "", html_content[:10000]))

        if new_replacement_chars > 100 or new_non_printable > 500:
            print(
                f"⚠️ New content still appears corrupted: {new_replacement_chars} replacement chars, {new_non_printable} non-printable"
            )
            # Still try to process it, but log the issue

        soup = BeautifulSoup(html_content, "html.parser")

        # Remove unwanted elements (but keep structure for content extraction)
        for script in soup(["script", "style", "meta", "noscript", "iframe", "nav", "header", "footer"]):
            script.decompose()

        # Try multiple extraction strategies for JS-rendered pages
        content_text = None
        content_length = 0

        # Strategy 1: Try semantic HTML5 elements and common content selectors
        selectors = [
            "article",
            "main",
            ".article-content",
            ".post-content",
            ".entry-content",
            '[role="main"]',
            ".content",
            ".post-body",
            ".article-body",
            "#content",
            ".main-content",
        ]

        for selector in selectors:
            content_elem = soup.select_one(selector)
            if content_elem:
                text = content_elem.get_text(separator=" ", strip=True)
                if len(text) > content_length:
                    content_text = text
                    content_length = len(text)
                    print(f"✅ Found content with selector '{selector}': {len(text)} chars")

        # Strategy 2: If no good selector found, try body but filter out likely JS-rendered empty pages
        if not content_text or content_length < 500:
            body = soup.find("body")
            if body:
                body_text = body.get_text(separator=" ", strip=True)
                # Check if body has meaningful content (not just JS placeholder)
                # JS-rendered pages often have very short body text after script removal
                if len(body_text) > 500:
                    if not content_text or len(body_text) > content_length:
                        content_text = body_text
                        content_length = len(body_text)
                        print(f"✅ Using body text: {len(body_text)} chars")

        # Strategy 3: Last resort - full document text
        if not content_text or content_length < 500:
            full_text = soup.get_text(separator=" ", strip=True)
            if len(full_text) > content_length:
                content_text = full_text
                content_length = len(full_text)
                print(f"✅ Using full document text: {len(full_text)} chars")

        # If still no meaningful content, this is likely a JS-rendered page
        if not content_text or content_length < 500:
            print(f"⚠️ Page appears to be JavaScript-rendered (only {content_length} chars after extraction)")
            print("   Skipping update to preserve existing content")
            return False

        # Conservative sanitization
        sanitized_content = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", content_text)
        sanitized_content = re.sub(r"\s+", " ", sanitized_content).strip()

        print(f"✅ Scraped content length: {len(sanitized_content)} chars")

        # Check final corruption level
        final_replacement = sanitized_content.count("�")
        final_non_printable = len(re.sub(r"[\x20-\x7E\s]", "", sanitized_content))
        print(f"   Final corruption: {final_replacement} replacement chars, {final_non_printable} non-printable")

        if len(sanitized_content) < 500:
            print(f"⚠️ Scraped content too short ({len(sanitized_content)} chars)")
            if len(sanitized_content) <= len(article.content):
                print("⚠️ New content not longer than existing, skipping update")
                return False

        # Only update if corruption is significantly reduced
        if replacement_chars > 0 and final_replacement >= replacement_chars * 0.8:
            print(f"⚠️ Corruption not significantly reduced ({replacement_chars} -> {final_replacement}), skipping")
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


async def fix_articles(article_ids: list[int], batch_size: int = 10):
    """Fix multiple articles with batching."""
    results = []
    total = len(article_ids)

    for i in range(0, total, batch_size):
        batch = article_ids[i : i + batch_size]
        print(f"\n{'=' * 60}")
        print(
            f"Processing batch {i // batch_size + 1}/{(total + batch_size - 1) // batch_size} ({len(batch)} articles)"
        )
        print(f"{'=' * 60}")

        for article_id in batch:
            success = await fix_article(article_id)
            results.append((article_id, success))
            # Small delay between requests
            await asyncio.sleep(0.5)

        # Longer delay between batches
        if i + batch_size < total:
            await asyncio.sleep(2)

    # Summary
    print(f"\n{'=' * 60}")
    print("Final Summary:")
    print(f"{'=' * 60}")
    successful = [aid for aid, success in results if success]
    failed = [aid for aid, success in results if not success]

    print(f"✅ Successfully fixed: {len(successful)}/{total} articles")
    if successful:
        print(f"   IDs: {successful[:20]}{'...' if len(successful) > 20 else ''}")

    if failed:
        print(f"❌ Failed to fix: {len(failed)}/{total} articles")
        print(f"   IDs: {failed[:20]}{'...' if len(failed) > 20 else ''}")

    return len(successful), len(failed)


async def main():
    """Main function."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python fix_corrupted_articles.py <option>")
        print("\nOptions:")
        print("  --all          # Fix all corrupted articles (with replacement chars)")
        print("  --recent       # Fix corrupted articles from last 2 days")
        print("  <id1> <id2>... # Fix specific article IDs")
        sys.exit(1)

    db = DatabaseManager()

    if sys.argv[1] == "--all":
        # Find all articles with corruption
        with db.get_session() as session:
            corrupted = (
                session.query(ArticleTable.id)
                .filter(ArticleTable.archived == False, ArticleTable.content.like("%�%"))
                .all()
            )
            article_ids = [aid for (aid,) in corrupted]
            print(f"🔧 Found {len(article_ids)} corrupted articles")
    elif sys.argv[1] == "--recent":
        # Find corrupted articles from last 2 days
        from datetime import timedelta

        cutoff_date = datetime.now() - timedelta(days=2)
        with db.get_session() as session:
            corrupted = (
                session.query(ArticleTable.id)
                .filter(
                    ArticleTable.archived == False,
                    ArticleTable.discovered_at >= cutoff_date,
                    ArticleTable.content.like("%�%"),
                )
                .all()
            )
            article_ids = [aid for (aid,) in corrupted]
            print(f"🔧 Found {len(article_ids)} corrupted articles from last 2 days")
    else:
        article_ids = [int(arg) for arg in sys.argv[1:]]

    if not article_ids:
        print("No articles to fix")
        sys.exit(0)

    successful, failed = await fix_articles(article_ids)
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
