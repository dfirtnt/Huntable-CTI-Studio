"""Hierarchical content fetcher orchestrating the three-tier collection strategy."""

import asyncio
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
import logging

from models.article import ArticleCreate
from src.models.source import Source
from src.utils.http import HTTPClient
from core.rss_parser import RSSParser
from core.modern_scraper import ModernScraper, LegacyScraper

logger = logging.getLogger(__name__)


class FetchResult:
    """Result of a fetch operation."""
    
    def __init__(
        self,
        source: Source,
        articles: List[ArticleCreate],
        method: str,
        success: bool = True,
        error: Optional[str] = None,
        response_time: float = 0.0
    ):
        self.source = source
        self.articles = articles
        self.method = method
        self.success = success
        self.error = error
        self.response_time = response_time
        self.timestamp = datetime.utcnow()
    
    def __str__(self):
        status = "SUCCESS" if self.success else "FAILED"
        return f"FetchResult[{self.source.name}]: {status} - {len(self.articles)} articles via {self.method}"


class ContentFetcher:
    """
    Hierarchical content fetcher implementing three-tier strategy:
    Tier 1: RSS Feeds (Primary) → Fast, standardized, efficient
    Tier 2: Modern Web Scraping (Fallback) → JSON-LD, structured data extraction  
    Tier 3: Legacy HTML Scraping (Last Resort) → CSS selectors, basic content
    """
    
    def __init__(
        self,
        user_agent: str = "ThreatIntelAggregator/1.0",
        timeout: float = 30.0,
        max_concurrent: int = 5,
        rate_limit_delay: float = 1.0
    ):
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_concurrent = max_concurrent
        self.rate_limit_delay = rate_limit_delay
        
        # Initialize HTTP client and parsers
        self.http_client = HTTPClient(
            user_agent=user_agent,
            timeout=timeout,
            rate_limit_delay=rate_limit_delay
        )
        
        self.rss_parser = RSSParser(self.http_client)
        self.modern_scraper = ModernScraper(self.http_client)
        self.legacy_scraper = LegacyScraper(self.http_client)
        
        # Statistics
        self.stats = {
            'total_fetches': 0,
            'successful_fetches': 0,
            'failed_fetches': 0,
            'articles_collected': 0,
            'rss_successes': 0,
            'modern_scraping_successes': 0,
            'legacy_scraping_successes': 0,
            'avg_response_time': 0.0
        }
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.http_client.__aenter__()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.http_client.__aexit__(exc_type, exc_val, exc_tb)
    
    async def fetch_source(self, source: Source) -> FetchResult:
        """
        Fetch content from a single source using hierarchical strategy.
        
        Args:
            source: Source configuration
            
        Returns:
            FetchResult with articles and metadata
        """
        logger.info(f"Starting fetch for source: {source.name} (tier {source.tier})")
        start_time = datetime.utcnow()
        
        try:
            # Tier 1: Try RSS first if available
            if source.rss_url and source.rss_url.strip():
                try:
                    logger.debug(f"Attempting RSS fetch for {source.name}")
                    articles = await self.rss_parser.parse_feed(source)
                    
                    if articles:
                        response_time = (datetime.utcnow() - start_time).total_seconds()
                        self._update_stats('rss_successes', len(articles), response_time, True)
                        
                        logger.info(f"RSS fetch successful for {source.name}: {len(articles)} articles")
                        return FetchResult(
                            source=source,
                            articles=articles,
                            method="rss",
                            success=True,
                            response_time=response_time
                        )
                    else:
                        logger.warning(f"RSS feed returned no articles for {source.name}")
                        
                except Exception as e:
                    logger.warning(f"RSS fetch failed for {source.name}: {e}")
            
            # Tier 2: Modern scraping if RSS failed and modern config available
            if self._has_modern_config(source):
                try:
                    logger.debug(f"Attempting modern scraping for {source.name}")
                    articles = await self.modern_scraper.scrape_source(source)
                    
                    if articles:
                        response_time = (datetime.utcnow() - start_time).total_seconds()
                        self._update_stats('modern_scraping_successes', len(articles), response_time, True)
                        
                        logger.info(f"Modern scraping successful for {source.name}: {len(articles)} articles")
                        return FetchResult(
                            source=source,
                            articles=articles,
                            method="modern_scraping",
                            success=True,
                            response_time=response_time
                        )
                    else:
                        logger.warning(f"Modern scraping returned no articles for {source.name}")
                        
                except Exception as e:
                    logger.warning(f"Modern scraping failed for {source.name}: {e}")
            
            # Tier 3: Legacy HTML scraping as last resort
            try:
                logger.debug(f"Attempting legacy scraping for {source.name}")
                articles = await self.legacy_scraper.scrape_source(source)
                
                response_time = (datetime.utcnow() - start_time).total_seconds()
                
                if articles:
                    self._update_stats('legacy_scraping_successes', len(articles), response_time, True)
                    
                    logger.info(f"Legacy scraping successful for {source.name}: {len(articles)} articles")
                    return FetchResult(
                        source=source,
                        articles=articles,
                        method="legacy_scraping",
                        success=True,
                        response_time=response_time
                    )
                else:
                    self._update_stats('legacy_scraping_successes', 0, response_time, False)
                    error_msg = "No articles extracted from any method"
                    
                    logger.error(f"All fetch methods failed for {source.name}: {error_msg}")
                    return FetchResult(
                        source=source,
                        articles=[],
                        method="all_failed",
                        success=False,
                        error=error_msg,
                        response_time=response_time
                    )
                    
            except Exception as e:
                response_time = (datetime.utcnow() - start_time).total_seconds()
                self._update_stats('legacy_scraping_successes', 0, response_time, False)
                error_msg = f"Legacy scraping failed: {e}"
                
                logger.error(f"All fetch methods failed for {source.name}: {error_msg}")
                return FetchResult(
                    source=source,
                    articles=[],
                    method="all_failed",
                    success=False,
                    error=error_msg,
                    response_time=response_time
                )
        
        except Exception as e:
            response_time = (datetime.utcnow() - start_time).total_seconds()
            self._update_stats('failed_fetches', 0, response_time, False)
            error_msg = f"Unexpected error during fetch: {e}"
            
            logger.error(f"Fetch failed for {source.name}: {error_msg}")
            return FetchResult(
                source=source,
                articles=[],
                method="error",
                success=False,
                error=error_msg,
                response_time=response_time
            )
    
    async def fetch_multiple_sources(
        self,
        sources: List[Source],
        max_concurrent: Optional[int] = None
    ) -> List[FetchResult]:
        """
        Fetch content from multiple sources concurrently.
        
        Args:
            sources: List of sources to fetch
            max_concurrent: Maximum concurrent fetches (defaults to instance setting)
            
        Returns:
            List of FetchResult objects
        """
        if not sources:
            return []
        
        max_concurrent = max_concurrent or self.max_concurrent
        logger.info(f"Starting concurrent fetch for {len(sources)} sources (max concurrent: {max_concurrent})")
        
        # Create semaphore to limit concurrency
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def fetch_with_semaphore(source: Source) -> FetchResult:
            async with semaphore:
                return await self.fetch_source(source)
        
        # Start all fetch tasks
        tasks = [fetch_with_semaphore(source) for source in sources]
        
        # Wait for all to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        fetch_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Fetch task failed for {sources[i].name}: {result}")
                fetch_results.append(FetchResult(
                    source=sources[i],
                    articles=[],
                    method="task_error",
                    success=False,
                    error=str(result)
                ))
            else:
                fetch_results.append(result)
        
        # Log summary
        successful = sum(1 for r in fetch_results if r.success)
        total_articles = sum(len(r.articles) for r in fetch_results)
        
        logger.info(f"Batch fetch completed: {successful}/{len(sources)} sources successful, {total_articles} total articles")
        
        return fetch_results
    
    async def fetch_due_sources(
        self,
        sources: List[Source],
        force_check: bool = False
    ) -> List[FetchResult]:
        """
        Fetch content from sources that are due for checking.
        
        Args:
            sources: List of all sources
            force_check: If True, check all sources regardless of schedule
            
        Returns:
            List of FetchResult objects for checked sources
        """
        if force_check:
            due_sources = [s for s in sources if s.active]
        else:
            due_sources = [s for s in sources if s.active and s.should_check()]
        
        if not due_sources:
            logger.info("No sources due for checking")
            return []
        
        logger.info(f"Found {len(due_sources)} sources due for checking")
        
        return await self.fetch_multiple_sources(due_sources)
    
    def _has_modern_config(self, source: Source) -> bool:
        """Check if source has modern scraping configuration."""
        config = source.config
        
        # Check for discovery strategies
        discovery = getattr(config, 'discovery', {})
        if discovery and discovery.get('strategies'):
            return True
        
        # Check for extraction configuration beyond basic selectors
        extract = getattr(config, 'extract', {})
        if extract and (extract.get('title_selectors') or 
            extract.get('date_selectors') or 
            extract.get('body_selectors')):
            return True
        
        return False
    
    def _update_stats(self, method: str, article_count: int, response_time: float, success: bool):
        """Update internal statistics."""
        self.stats['total_fetches'] += 1
        
        if success:
            self.stats['successful_fetches'] += 1
            self.stats['articles_collected'] += article_count
            if method in self.stats:
                self.stats[method] += 1
        else:
            self.stats['failed_fetches'] += 1
        
        # Update average response time
        current_avg = self.stats['avg_response_time']
        total_fetches = self.stats['total_fetches']
        self.stats['avg_response_time'] = ((current_avg * (total_fetches - 1)) + response_time) / total_fetches
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get current fetching statistics."""
        return self.stats.copy()
    
    def reset_statistics(self):
        """Reset all statistics."""
        for key in self.stats:
            self.stats[key] = 0


class ScheduledFetcher:
    """Scheduler for automated content fetching."""
    
    def __init__(
        self,
        content_fetcher: ContentFetcher,
        check_interval: int = 300,  # 5 minutes
        max_check_age: int = 86400  # 24 hours
    ):
        self.content_fetcher = content_fetcher
        self.check_interval = check_interval
        self.max_check_age = max_check_age
        self.running = False
        self._task: Optional[asyncio.Task] = None
    
    async def start(self, sources: List[Source], callback=None):
        """
        Start scheduled fetching.
        
        Args:
            sources: List of sources to monitor
            callback: Optional callback function for fetch results
        """
        if self.running:
            logger.warning("Scheduled fetcher already running")
            return
        
        self.running = True
        logger.info(f"Starting scheduled fetcher with {len(sources)} sources")
        
        self._task = asyncio.create_task(self._run_scheduler(sources, callback))
    
    async def stop(self):
        """Stop scheduled fetching."""
        if not self.running:
            return
        
        self.running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("Scheduled fetcher stopped")
    
    async def _run_scheduler(self, sources: List[Source], callback=None):
        """Main scheduler loop."""
        try:
            while self.running:
                logger.debug("Checking for sources due for fetching...")
                
                # Find sources due for checking
                due_sources = []
                current_time = datetime.utcnow()
                
                for source in sources:
                    if not source.active:
                        continue
                    
                    # Check if source should be checked
                    if source.should_check():
                        due_sources.append(source)
                    
                    # Auto-disable sources with too many failures
                    elif source.should_disable():
                        logger.warning(f"Auto-disabling source {source.name} due to excessive failures")
                        source.active = False
                
                # Fetch due sources
                if due_sources:
                    logger.info(f"Fetching {len(due_sources)} due sources")
                    
                    results = await self.content_fetcher.fetch_due_sources(due_sources)
                    
                    # Call callback if provided
                    if callback:
                        try:
                            await callback(results)
                        except Exception as e:
                            logger.error(f"Callback failed: {e}")
                
                # Sleep until next check
                await asyncio.sleep(self.check_interval)
                
        except asyncio.CancelledError:
            logger.info("Scheduler cancelled")
            raise
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
            self.running = False
