#!/usr/bin/env python3
"""
Manual DFIR Report Archive Scraper
Scrapes historical articles from The DFIR Report archive pages.
"""

import asyncio
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import hashlib
import logging
from datetime import datetime

from bs4 import BeautifulSoup

from src.database.async_manager import AsyncDatabaseManager
from src.models.article import ArticleCreate
from src.models.source import Source
from src.utils.http import HTTPClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DFIRArchiveScraper:
    def __init__(self):
        self.http_client = HTTPClient()
        self.db = AsyncDatabaseManager()

    async def __aenter__(self):
        await self.http_client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.http_client.__aexit__(exc_type, exc_val, exc_tb)

    async def scrape_archive_pages(self, max_pages: int = 20):
        """Scrape archive pages from The DFIR Report."""
        logger.info(f"Starting archive scraping for up to {max_pages} pages")

        # Get the DFIR Report source
        sources = await self.db.list_sources()
        source = None
        for s in sources:
            if s.identifier == "dfir_report":
                source = s
                break

        if not source:
            logger.error("DFIR Report source not found in database")
            return None

        articles_collected = 0

        for page_num in range(1, max_pages + 1):
            archive_url = f"https://thedfirreport.com/page/{page_num}/"
            logger.info(f"Scraping archive page {page_num}: {archive_url}")

            try:
                # Fetch the archive page
                response = await self.http_client.get(archive_url)
                response.raise_for_status()

                # Parse the page
                soup = BeautifulSoup(response.text, "lxml")

                # Find article links
                article_links = soup.select("h2.entry-title a, h1.entry-title a, .post-title a")

                if not article_links:
                    logger.warning(f"No article links found on page {page_num}")
                    break

                logger.info(f"Found {len(article_links)} article links on page {page_num}")

                # Process each article
                for link in article_links:
                    article_url = link.get("href")
                    if not article_url:
                        continue

                    # Make sure it's a full URL
                    if article_url.startswith("/"):
                        article_url = f"https://thedfirreport.com{article_url}"

                    try:
                        article = await self.scrape_article(article_url, source)
                        if article:
                            articles_collected += 1
                            logger.info(f"Collected article: {article.title[:100]}...")

                        # Rate limiting
                        await asyncio.sleep(1)

                    except Exception as e:
                        logger.error(f"Failed to scrape article {article_url}: {e}")
                        continue

                # Rate limiting between pages
                await asyncio.sleep(2)

            except Exception as e:
                logger.error(f"Failed to scrape archive page {page_num}: {e}")
                continue

        logger.info(f"Archive scraping complete. Collected {articles_collected} articles.")
        return articles_collected

    async def scrape_article(self, url: str, source: Source) -> ArticleCreate:
        """Scrape a single article from The DFIR Report."""
        try:
            # Fetch the article
            response = await self.http_client.get(url)
            response.raise_for_status()

            # Parse the article
            soup = BeautifulSoup(response.text, "lxml")

            # Extract title
            title_elem = soup.select_one("h1.entry-title, h1, .post-title")
            if not title_elem:
                title_elem = soup.select_one("title")
            title = title_elem.get_text().strip() if title_elem else "Unknown Title"

            # Extract content
            content_elem = soup.select_one(".entry-content, article, main, .content, .post-content")
            if not content_elem:
                content_elem = soup.select_one("body")
            content = content_elem.get_text().strip() if content_elem else ""

            if len(content) < 1000:  # Skip short articles
                logger.warning(f"Article too short ({len(content)} chars): {url}")
                return None

            # Extract date
            date_elem = soup.select_one("time.entry-date, time[datetime], .post-date")
            published_at = datetime.now()

            if date_elem:
                if date_elem.get("datetime"):
                    try:
                        published_at = datetime.fromisoformat(date_elem.get("datetime").replace("Z", "+00:00"))
                    except:
                        pass
                elif date_elem.get_text():
                    # Try to parse date from text
                    try:
                        published_at = datetime.strptime(date_elem.get_text().strip(), "%B %d, %Y")
                    except:
                        pass

            # Extract authors
            author_elem = soup.select_one(".author-name, .entry-author, .post-author")
            authors = [author_elem.get_text().strip()] if author_elem else ["The DFIR Report"]

            # Create content hash
            content_hash = hashlib.sha256(content.encode()).hexdigest()

            # Create article
            article = ArticleCreate(
                source_id=source.id,
                canonical_url=url,
                title=title,
                published_at=published_at,
                authors=authors,
                tags=[],
                summary="",
                content=content,
                content_hash=content_hash,
                article_metadata={},
                word_count=len(content.split()),
                processing_status="pending",
            )

            # Save to database directly
            saved_article = await self.db.create_article(article)

            return saved_article

        except Exception as e:
            logger.error(f"Failed to scrape article {url}: {e}")
            return None


async def main():
    """Main function to run the archive scraper."""
    scraper = DFIRArchiveScraper()

    async with scraper:
        articles_collected = await scraper.scrape_archive_pages(max_pages=20)
        print("\n✅ Archive scraping complete!")
        print(f"📊 Collected {articles_collected} articles from The DFIR Report archives")


if __name__ == "__main__":
    asyncio.run(main())
