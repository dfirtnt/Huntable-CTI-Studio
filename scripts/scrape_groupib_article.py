#!/usr/bin/env python3
"""Manually scrape Group-IB article."""

import asyncio
import re
import traceback
from datetime import datetime

import httpx
from bs4 import BeautifulSoup


async def scrape_article():
    url = "https://www.group-ib.com/blog/muddywater-espionage/"

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            print(f"Fetching: {url}")
            response = await client.get(url, headers=headers)
            print(f"Status: {response.status_code}")
            response.raise_for_status()
            html = response.text
            print(f"HTML length: {len(html)}")
    except Exception as e:
        print(f"Error fetching: {e}")
        traceback.print_exc()
        return

    try:
        soup = BeautifulSoup(html, "html.parser")

        # Remove unwanted tags
        for tag in soup(["script", "style", "meta", "noscript", "iframe", "nav", "header", "footer"]):
            tag.decompose()

        # Extract title
        title = None
        if soup.find("h1"):
            title = soup.find("h1").get_text().strip()
        elif soup.find("title"):
            title = soup.find("title").get_text().strip()
        else:
            title = "Untitled Article"

        print(f"Title: {title[:100]}")

        # Extract content
        content_selectors = ["article", "main", ".content", ".post-content", ".blog-content"]
        content = None
        for selector in content_selectors:
            elem = soup.select_one(selector)
            if elem:
                content = elem.get_text(separator=" ", strip=True)
                print(f"Found content with selector: {selector}")
                break

        if not content:
            content = soup.get_text(separator=" ", strip=True)

        # Clean content
        content = re.sub(r"\s+", " ", content).strip()

        print(f"Content length: {len(content)} chars")

        if len(content) < 1000:
            print(f"⚠️ Content too short: {len(content)} chars")
            return

        # Save to database
        import hashlib

        from src.database.manager import DatabaseManager
        from src.database.models import ArticleTable, SourceTable
        from src.utils.simhash import compute_article_simhash

        db = DatabaseManager()
        with db.get_session() as session:
            # Get Group-IB source
            source = session.query(SourceTable).filter(SourceTable.identifier == "group_ib_threat_intel").first()

            if not source:
                print("❌ Source not found")
                return

            print(f"Source ID: {source.id}")

            # Check if article exists
            existing = session.query(ArticleTable).filter(ArticleTable.canonical_url == url).first()

            if existing:
                print(f"✅ Article already exists: ID {existing.id}")
                return

            # Create article
            content_hash = hashlib.sha256(f"{title}\n{content}".encode()).hexdigest()
            simhash, simhash_bucket = compute_article_simhash(content, title)

            article = ArticleTable(
                title=title,
                canonical_url=url,
                content=content,
                content_hash=content_hash,
                simhash=simhash,
                simhash_bucket=simhash_bucket,
                source_id=source.id,
                published_at=datetime.now(),
                created_at=datetime.now(),
            )

            session.add(article)
            session.commit()
            session.refresh(article)

            print(f"✅ Article saved: ID {article.id}, Title: {title[:60]}...")

    except Exception as e:
        print(f"❌ Error: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(scrape_article())
