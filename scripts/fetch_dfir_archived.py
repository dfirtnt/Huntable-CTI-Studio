#!/usr/bin/env python3
"""
Fetch and archive historical articles from TheDFIRReport.
For articles older than 3 months that don't already exist, add them as "Archived".
"""

import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Set

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.http import HTTPClient
from src.database.async_manager import AsyncDatabaseManager
from src.models.source import Source
from src.database.models import ArticleTable
from src.services.deduplication import AsyncDeduplicationService
from src.utils.simhash import compute_article_simhash
from bs4 import BeautifulSoup
import hashlib
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 3 months threshold
THREE_MONTHS_AGO = datetime.now() - timedelta(days=90)

class DFIRArchiveFetcher:
    def __init__(self):
        self.http_client = HTTPClient()
        self.db = AsyncDatabaseManager()
        self.existing_urls: Set[str] = set()
        
    async def __aenter__(self):
        await self.http_client.__aenter__()
        await self._load_existing_urls()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.http_client.__aexit__(exc_type, exc_val, exc_tb)
    
    async def _load_existing_urls(self):
        """Load all existing TheDFIRReport article URLs from database."""
        logger.info("Loading existing article URLs from database...")
        try:
            sources = await self.db.list_sources()
            dfir_source = None
            for s in sources:
                if s.identifier == "dfir_report":
                    dfir_source = s
                    break
            
            if not dfir_source:
                logger.error("DFIR Report source not found in database")
                return
            
            # Get all articles from this source (including archived)
            async with self.db.get_session() as session:
                from sqlalchemy import select
                result = await session.execute(
                    select(ArticleTable.canonical_url).where(
                        ArticleTable.source_id == dfir_source.id
                    )
                )
                urls = result.scalars().all()
                self.existing_urls = set(urls)
                logger.info(f"Loaded {len(self.existing_urls)} existing article URLs")
        except Exception as e:
            logger.error(f"Failed to load existing URLs: {e}")
    
    async def scrape_from_sitemap(self):
        """Scrape article URLs from sitemap."""
        logger.info("Fetching article URLs from sitemap...")
        
        # Get the DFIR Report source
        sources = await self.db.list_sources()
        source = None
        for s in sources:
            if s.identifier == "dfir_report":
                source = s
                break
        
        if not source:
            logger.error("DFIR Report source not found in database")
            return 0, 0, 0, 0
        
        articles_collected = 0
        articles_skipped_existing = 0
        articles_skipped_recent = 0
        articles_failed = 0
        
        try:
            # First, get the sitemap index
            sitemap_index_url = "https://thedfirreport.com/sitemap.xml"
            response = await self.http_client.get(sitemap_index_url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'xml')
            
            # Find all sitemap URLs
            sitemap_urls = []
            for sitemap in soup.find_all('sitemap'):
                loc = sitemap.find('loc')
                if loc:
                    sitemap_url = loc.get_text().strip()
                    # Only process post sitemaps, skip image sitemaps
                    if 'sitemap-' in sitemap_url and 'image' not in sitemap_url:
                        sitemap_urls.append(sitemap_url)
            
            logger.info(f"Found {len(sitemap_urls)} sitemap(s) to process")
            
            # Process each sitemap
            all_article_urls = set()
            for sitemap_url in sitemap_urls:
                try:
                    logger.info(f"Processing sitemap: {sitemap_url}")
                    response = await self.http_client.get(sitemap_url)
                    response.raise_for_status()
                    
                    soup = BeautifulSoup(response.text, 'xml')
                    
                    # Extract all URLs
                    for url_elem in soup.find_all('url'):
                        loc = url_elem.find('loc')
                        if loc:
                            url = loc.get_text().strip()
                            # Filter for article URLs (contain date pattern YYYY/MM/DD)
                            import re
                            if re.search(r'/\d{4}/\d{2}/\d{2}/', url):
                                all_article_urls.add(url)
                    
                    await asyncio.sleep(1)  # Rate limiting
                    
                except Exception as e:
                    logger.error(f"Failed to process sitemap {sitemap_url}: {e}")
                    continue
            
            logger.info(f"Found {len(all_article_urls)} article URLs in sitemap(s)")
            
            # Process each article URL
            for article_url in all_article_urls:
                # Skip if already exists
                if article_url in self.existing_urls:
                    articles_skipped_existing += 1
                    continue
                
                try:
                    result = await self.scrape_and_save_article(article_url, source)
                    if result == "created":
                        articles_collected += 1
                    elif result == "skipped_recent":
                        articles_skipped_recent += 1
                    elif result == "skipped_existing":
                        articles_skipped_existing += 1
                    else:
                        articles_failed += 1
                    
                    # Rate limiting
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.error(f"Failed to scrape article {article_url}: {e}")
                    articles_failed += 1
                    continue
            
            return articles_collected, articles_skipped_existing, articles_skipped_recent, articles_failed
            
        except Exception as e:
            logger.error(f"Failed to parse sitemap: {e}")
            return 0, 0, 0, 0
    
    async def scrape_from_rss(self):
        """Scrape article URLs from RSS feed."""
        import feedparser
        
        logger.info("Fetching article URLs from RSS feed...")
        rss_url = "https://thedfirreport.com/feed/"
        
        try:
            feed = feedparser.parse(rss_url)
            logger.info(f"Found {len(feed.entries)} entries in RSS feed")
            
            # Get the DFIR Report source
            sources = await self.db.list_sources()
            source = None
            for s in sources:
                if s.identifier == "dfir_report":
                    source = s
                    break
            
            if not source:
                logger.error("DFIR Report source not found in database")
                return 0, 0, 0, 0
            
            articles_collected = 0
            articles_skipped_existing = 0
            articles_skipped_recent = 0
            articles_failed = 0
            
            for entry in feed.entries:
                article_url = entry.get('link', '')
                if not article_url:
                    continue
                
                # Skip if already exists
                if article_url in self.existing_urls:
                    articles_skipped_existing += 1
                    continue
                
                try:
                    result = await self.scrape_and_save_article(article_url, source)
                    if result == "created":
                        articles_collected += 1
                    elif result == "skipped_recent":
                        articles_skipped_recent += 1
                    elif result == "skipped_existing":
                        articles_skipped_existing += 1
                    else:
                        articles_failed += 1
                    
                    # Rate limiting
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.error(f"Failed to scrape article {article_url}: {e}")
                    articles_failed += 1
                    continue
            
            return articles_collected, articles_skipped_existing, articles_skipped_recent, articles_failed
            
        except Exception as e:
            logger.error(f"Failed to parse RSS feed: {e}")
            return 0, 0, 0, 0
    
    async def scrape_archive_pages(self, max_pages: int = 200):
        """Scrape archive pages from The DFIR Report."""
        logger.info(f"Starting archive scraping for up to {max_pages} pages")
        
        # First try sitemap (most comprehensive)
        logger.info("Trying sitemap first (most comprehensive)...")
        sitemap_results = await self.scrape_from_sitemap()
        if sitemap_results:
            articles_collected, articles_skipped_existing, articles_skipped_recent, articles_failed = sitemap_results
            logger.info(f"Sitemap results: {articles_collected} created, {articles_skipped_existing} skipped (existing), {articles_skipped_recent} skipped (recent), {articles_failed} failed")
        
        # Then try RSS feed (for any recent articles not in sitemap)
        logger.info("Trying RSS feed for recent articles...")
        rss_results = await self.scrape_from_rss()
        if rss_results:
            rss_collected, rss_skipped_existing, rss_skipped_recent, rss_failed = rss_results
            logger.info(f"RSS feed results: {rss_collected} created, {rss_skipped_existing} skipped (existing), {rss_skipped_recent} skipped (recent), {rss_failed} failed")
            # Accumulate results
            if sitemap_results:
                articles_collected += rss_collected
                articles_skipped_existing += rss_skipped_existing
                articles_skipped_recent += rss_skipped_recent
                articles_failed += rss_failed
            else:
                articles_collected, articles_skipped_existing, articles_skipped_recent, articles_failed = rss_results
        
        # Get the DFIR Report source
        sources = await self.db.list_sources()
        source = None
        for s in sources:
            if s.identifier == "dfir_report":
                source = s
                break
        
        if not source:
            logger.error("DFIR Report source not found in database")
            return
        
        articles_collected = 0
        articles_skipped_existing = 0
        articles_skipped_recent = 0
        articles_failed = 0
        
        # Try scraping main page and look for article links
        logger.info("Scraping main page for article links...")
        try:
            response = await self.http_client.get("https://thedfirreport.com/")
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'lxml')
            
            # Find all links that look like article URLs
            all_links = soup.find_all('a', href=True)
            article_urls = set()
            for link in all_links:
                href = link.get('href', '')
                if href and ('thedfirreport.com' in href or href.startswith('/')) and '/page/' not in href and href.count('/') >= 3 and not href.endswith('.pdf') and not href.endswith('.jpg') and not href.endswith('.png'):
                    if href.startswith('/'):
                        href = f"https://thedfirreport.com{href}"
                    article_urls.add(href)
            
            logger.info(f"Found {len(article_urls)} potential article URLs from main page")
            
            for article_url in article_urls:
                if article_url in self.existing_urls:
                    articles_skipped_existing += 1
                    continue
                
                try:
                    result = await self.scrape_and_save_article(article_url, source)
                    if result == "created":
                        articles_collected += 1
                    elif result == "skipped_recent":
                        articles_skipped_recent += 1
                    elif result == "skipped_existing":
                        articles_skipped_existing += 1
                    else:
                        articles_failed += 1
                    
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.error(f"Failed to scrape article {article_url}: {e}")
                    articles_failed += 1
                    continue
                    
        except Exception as e:
            logger.error(f"Failed to scrape main page: {e}")
        
        # Try archive pages as fallback
        for page_num in range(1, max_pages + 1):
            archive_url = f"https://thedfirreport.com/page/{page_num}/"
            logger.info(f"Scraping archive page {page_num}/{max_pages}: {archive_url}")
            
            try:
                response = await self.http_client.get(archive_url)
                if response.status_code == 404:
                    logger.info(f"Page {page_num} returned 404, stopping archive scraping")
                    break
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'lxml')
                
                # Find article links
                all_links = soup.find_all('a', href=True)
                article_urls = set()
                for link in all_links:
                    href = link.get('href', '')
                    if href and ('thedfirreport.com' in href or href.startswith('/')) and '/page/' not in href and href.count('/') >= 3 and not href.endswith('.pdf'):
                        if href.startswith('/'):
                            href = f"https://thedfirreport.com{href}"
                        article_urls.add(href)
                
                if not article_urls:
                    logger.warning(f"No article links found on page {page_num}")
                    continue
                
                logger.info(f"Found {len(article_urls)} article links on page {page_num}")
                
                for article_url in article_urls:
                    if article_url in self.existing_urls:
                        articles_skipped_existing += 1
                        continue
                    
                    try:
                        result = await self.scrape_and_save_article(article_url, source)
                        if result == "created":
                            articles_collected += 1
                        elif result == "skipped_recent":
                            articles_skipped_recent += 1
                        elif result == "skipped_existing":
                            articles_skipped_existing += 1
                        else:
                            articles_failed += 1
                        
                        await asyncio.sleep(1)
                    except Exception as e:
                        logger.error(f"Failed to scrape article {article_url}: {e}")
                        articles_failed += 1
                        continue
                
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"Failed to scrape archive page {page_num}: {e}")
                continue
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Archive scraping complete!")
        logger.info(f"  Created (archived): {articles_collected}")
        logger.info(f"  Skipped (already exist): {articles_skipped_existing}")
        logger.info(f"  Skipped (recent, <3 months): {articles_skipped_recent}")
        logger.info(f"  Failed: {articles_failed}")
        logger.info(f"{'='*60}")
        
        return articles_collected
    
    async def scrape_and_save_article(self, url: str, source: Source) -> str:
        """
        Scrape a single article and save it if it's older than 3 months.
        Returns: 'created', 'skipped_recent', 'skipped_existing', or 'failed'
        """
        try:
            # Fetch the article
            response = await self.http_client.get(url)
            response.raise_for_status()
            
            # Parse the article
            soup = BeautifulSoup(response.text, 'lxml')
            
            # Extract title - try multiple methods
            title = None
            
            # Method 1: Try h1.entry-title (TheDFIRReport standard)
            title_elem = soup.select_one('h1.entry-title')
            if title_elem:
                title = title_elem.get_text().strip()
            
            # Method 2: Try other h1 selectors
            if not title:
                title_elem = soup.select_one('h1.post-title, article h1, .post-title, h1')
                if title_elem:
                    title = title_elem.get_text().strip()
            
            # Method 3: Try meta tags
            if not title:
                title_meta = soup.select_one('meta[property="og:title"], meta[name="title"]')
                if title_meta and title_meta.get('content'):
                    title = title_meta.get('content').strip()
            
            # Method 4: Try page title and clean it
            if not title:
                title_elem = soup.select_one('title')
                if title_elem:
                    title = title_elem.get_text().strip()
                    # Remove site name if present (various separators)
                    for sep in [' – ', ' - ', ' | ', ' — ']:
                        if sep in title:
                            title = title.split(sep)[0].strip()
                            break
                    # Also remove HTML entities like &#8211;
                    import html
                    title = html.unescape(title)
            
            # Method 5: Try to extract from URL slug as last resort
            if not title or title == "Unknown Title" or "access to this site has been limited" in title.lower():
                import re
                # Extract slug from URL: /2025/07/14/kongtuke-filefix-leads-to-new-interlock-rat-variant/
                url_match = re.search(r'/(\d{4}/\d{2}/\d{2})/([^/]+)/?$', url)
                if url_match:
                    slug = url_match.group(2)
                    # Convert slug to title: kongtuke-filefix-leads-to-new-interlock-rat-variant
                    title = slug.replace('-', ' ').title()
                    logger.info(f"Extracted title from URL slug: {title}")
            
            if not title or "access to this site has been limited" in title.lower():
                title = "Unknown Title"
                logger.warning(f"Could not extract title from {url}")
            
            # Extract content
            content_elem = soup.select_one('.entry-content, article, main, .content, .post-content')
            if not content_elem:
                content_elem = soup.select_one('body')
            content = content_elem.get_text().strip() if content_elem else ""
            
            if len(content) < 1000:  # Skip short articles
                logger.warning(f"Article too short ({len(content)} chars): {url}")
                return "failed"
            
            # Extract date - try multiple methods
            published_at = None
            
            # Method 1: Try meta tags first
            date_meta = soup.select_one('meta[property="article:published_time"], meta[name="date"], meta[name="publishdate"]')
            if date_meta and date_meta.get('content'):
                try:
                    date_str = date_meta.get('content')
                    if 'T' in date_str:
                        published_at = datetime.fromisoformat(date_str.replace('Z', '+00:00').split('+')[0])
                    else:
                        published_at = datetime.strptime(date_str, '%Y-%m-%d')
                except Exception as e:
                    logger.debug(f"Failed to parse meta date: {e}")
            
            # Method 2: Try time elements
            if not published_at:
                date_elem = soup.select_one('time.entry-date, time[datetime], .post-date, time')
                if date_elem:
                    if date_elem.get('datetime'):
                        try:
                            date_str = date_elem.get('datetime')
                            if 'T' in date_str:
                                published_at = datetime.fromisoformat(date_str.replace('Z', '+00:00').split('+')[0])
                            else:
                                published_at = datetime.strptime(date_str, '%Y-%m-%d')
                        except Exception as e:
                            logger.debug(f"Failed to parse datetime attribute: {e}")
                    elif date_elem.get_text():
                        # Try to parse date from text
                        date_text = date_elem.get_text().strip()
                        for fmt in ['%B %d, %Y', '%Y-%m-%d', '%m/%d/%Y', '%d %B %Y']:
                            try:
                                published_at = datetime.strptime(date_text, fmt)
                                break
                            except:
                                continue
            
            # Method 3: Try to extract from URL (TheDFIRReport URLs often contain dates: /2025/11/17/...)
            if not published_at:
                import re
                url_match = re.search(r'/(\d{4})/(\d{2})/(\d{2})/', url)
                if url_match:
                    try:
                        year, month, day = url_match.groups()
                        published_at = datetime(int(year), int(month), int(day))
                    except:
                        pass
            
            # Default to current date if still not found (but log warning)
            if not published_at:
                logger.warning(f"Could not extract date from {url}, using current date")
                published_at = datetime.now()
            
            # Check if article is older than 3 months
            if published_at > THREE_MONTHS_AGO:
                logger.info(f"Skipping recent article: {title[:60]}... (published: {published_at.date()})")
                return "skipped_recent"
            
            # Double-check if it exists (race condition protection)
            async with self.db.get_session() as session:
                from sqlalchemy import select
                result = await session.execute(
                    select(ArticleTable).where(ArticleTable.canonical_url == url)
                )
                existing = result.scalar_one_or_none()
                if existing:
                    logger.info(f"Article already exists: {url}")
                    self.existing_urls.add(url)
                    return "skipped_existing"
            
            # Extract authors
            author_elem = soup.select_one('.author-name, .entry-author, .post-author, meta[name="author"]')
            authors = []
            if author_elem:
                if author_elem.get('content'):  # meta tag
                    authors = [author_elem.get('content').strip()]
                else:
                    authors = [author_elem.get_text().strip()]
            if not authors:
                authors = ["The DFIR Report"]
            
            # Create content hash
            content_hash = hashlib.sha256(content.encode()).hexdigest()
            
            # Compute simhash
            simhash, bucket = compute_article_simhash(content, title)
            
            # Create article directly in database with archived=True
            async with self.db.get_session() as session:
                # Check for duplicates one more time
                dedup_service = AsyncDeduplicationService(session)
                
                # Create ArticleCreate for deduplication check
                from src.models.article import ArticleCreate
                article_create = ArticleCreate(
                    source_id=source.id,
                    canonical_url=url,
                    title=title,
                    published_at=published_at.replace(tzinfo=None) if published_at.tzinfo else published_at,
                    authors=authors,
                    tags=[],
                    summary=content[:500] if len(content) > 500 else content,
                    content=content,
                    content_hash=content_hash,
                    article_metadata={
                        "archived_on_import": True,
                        "import_date": datetime.now().isoformat(),
                    },
                    word_count=len(content.split()),
                    processing_status="pending"
                )
                
                # Check for duplicates
                is_duplicate, existing_article = await dedup_service.check_exact_duplicates(article_create)
                if is_duplicate:
                    logger.info(f"Duplicate found: {url}")
                    self.existing_urls.add(url)
                    return "skipped_existing"
                
                # Create article with archived=True
                db_article = ArticleTable(
                    title=title,
                    content=content,
                    canonical_url=url,
                    source_id=source.id,
                    published_at=published_at.replace(tzinfo=None) if published_at.tzinfo else published_at,
                    authors=authors,
                    tags=[],
                    summary=content[:500] if len(content) > 500 else content,
                    content_hash=content_hash,
                    simhash=simhash,
                    simhash_bucket=bucket,
                    article_metadata={
                        "archived_on_import": True,
                        "import_date": datetime.now().isoformat(),
                    },
                    word_count=len(content.split()),
                    processing_status="pending",
                    archived=True,  # Mark as archived
                    discovered_at=datetime.now(),
                    created_at=datetime.now(),
                    updated_at=datetime.now()
                )
                
                session.add(db_article)
                await session.commit()
                await session.refresh(db_article)
                
                logger.info(f"✅ Created archived article: {title[:60]}... (published: {published_at.date()})")
                self.existing_urls.add(url)
                return "created"
            
        except Exception as e:
            logger.error(f"Failed to scrape article {url}: {e}")
            return "failed"

async def main():
    """Main function to run the archive fetcher."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Fetch and archive historical articles from TheDFIRReport')
    parser.add_argument('--max-pages', type=int, default=200, help='Maximum number of archive pages to scrape (default: 200)')
    args = parser.parse_args()
    
    fetcher = DFIRArchiveFetcher()
    
    async with fetcher:
        articles_collected = await fetcher.scrape_archive_pages(max_pages=args.max_pages)
        print(f"\n✅ Archive fetching complete!")
        print(f"📊 Created {articles_collected} archived articles from TheDFIRReport")

if __name__ == "__main__":
    asyncio.run(main())

