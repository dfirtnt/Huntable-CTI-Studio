"""Hierarchical content fetcher with RSS-first strategy and basic web scraping fallback."""

import asyncio
import contextlib
import logging
from datetime import datetime
from typing import Any

from src.core.modern_scraper import LegacyScraper, ModernScraper
from src.core.playwright_scraper import PlaywrightScraper
from src.core.rss_parser import RSSParser
from src.models.article import ArticleCreate
from src.models.source import Source
from src.utils.http import HTTPClient

logger = logging.getLogger(__name__)


class FetchResult:
    """Result of a fetch operation."""

    def __init__(
        self,
        source: Source,
        articles: list[ArticleCreate],
        method: str,
        success: bool = True,
        error: str | None = None,
        response_time: float = 0.0,
        rss_parsing_stats: dict[str, Any] | None = None,
    ):
        self.source = source
        self.articles = articles
        self.method = method
        self.success = success
        self.error = error
        self.response_time = response_time
        self.rss_parsing_stats = rss_parsing_stats or {}
        self.timestamp = datetime.now()

    def __str__(self):
        status = "SUCCESS" if self.success else "FAILED"
        return f"FetchResult[{self.source.name}]: {status} - {len(self.articles)} articles via {self.method}"


class ContentFetcher:
    """
    Hierarchical content fetcher implementing three-tier strategy:
    Tier 1: RSS Feeds (Primary) → Fast, standardized, efficient
    Tier 2: Basic Web Scraping (Fallback) → CSS selectors, basic JSON-LD parsing
    Tier 3: Simple HTML Scraping (Last Resort) → Basic CSS selectors only
    """

    def __init__(
        self,
        user_agent: str = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        timeout: float = 30.0,
        max_concurrent: int = 5,
        rate_limit_delay: float = 1.0,
    ):
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_concurrent = max_concurrent
        self.rate_limit_delay = rate_limit_delay

        # Initialize HTTP client and parsers
        from src.utils.http import RateLimiter, RequestConfig

        config = RequestConfig(user_agent=user_agent, timeout=timeout, retry_delay=rate_limit_delay)
        rate_limiter = RateLimiter()

        self.http_client = HTTPClient(config=config, rate_limiter=rate_limiter)

        self.rss_parser = RSSParser(self.http_client)
        self.modern_scraper = ModernScraper(self.http_client)
        self.legacy_scraper = LegacyScraper(self.http_client)

        # Statistics
        self.stats = {
            "total_fetches": 0,
            "successful_fetches": 0,
            "failed_fetches": 0,
            "articles_collected": 0,
            "rss_successes": 0,
            "modern_scraping_successes": 0,
            "legacy_scraping_successes": 0,
            "playwright_scraping_successes": 0,
            "avg_response_time": 0.0,
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
        logger.info(f"Starting fetch for source: {source.name}")
        start_time = datetime.now()

        try:
            # Tier 1: Try RSS first if available
            if source.rss_url and source.rss_url.strip():
                try:
                    logger.debug(f"Attempting RSS fetch for {source.name}")
                    articles = await self.rss_parser.parse_feed(source)

                    # Extract RSS parsing stats from first article if available
                    rss_stats = {}
                    if articles and len(articles) > 0:
                        # Try to get stats from article_metadata (correct field name for ArticleCreate)
                        first_article = articles[0]
                        if hasattr(first_article, "article_metadata") and first_article.article_metadata:
                            rss_stats = first_article.article_metadata.get("rss_parsing_stats", {})
                        elif hasattr(first_article, "metadata") and first_article.metadata:
                            rss_stats = first_article.metadata.get("rss_parsing_stats", {})

                    response_time = (datetime.now() - start_time).total_seconds()

                    if articles:
                        self._update_stats("rss_successes", len(articles), response_time, True)
                        logger.info(
                            f"RSS fetch successful for {source.name}: {len(articles)} articles (RSS stats: {rss_stats})"
                        )
                    else:
                        logger.warning(f"RSS feed returned no articles for {source.name}")

                    return FetchResult(
                        source=source,
                        articles=articles,
                        method="rss",
                        success=True,
                        response_time=response_time,
                        rss_parsing_stats=rss_stats,
                    )

                except Exception as e:
                    logger.warning(f"RSS fetch failed for {source.name}: {e}")

            # Tier 2: Playwright scraping for JS-rendered content (if enabled)
            if self._should_use_playwright(source):
                try:
                    logger.debug(f"Attempting Playwright scraping for {source.name} (JS-rendered content)")

                    # Create new Playwright scraper instance for this source
                    playwright_scraper = PlaywrightScraper(headless=True, timeout=30000.0)

                    async with playwright_scraper:
                        articles = await playwright_scraper.scrape_source(source)

                        if articles:
                            response_time = (datetime.now() - start_time).total_seconds()
                            self._update_stats("playwright_scraping_successes", len(articles), response_time, True)

                            logger.info(f"Playwright scraping successful for {source.name}: {len(articles)} articles")
                            return FetchResult(
                                source=source,
                                articles=articles,
                                method="playwright_scraping",
                                success=True,
                                response_time=response_time,
                            )
                        logger.warning(f"Playwright scraping returned no articles for {source.name}")

                except Exception as e:
                    logger.warning(f"Playwright scraping failed for {source.name}: {e}")

            # Tier 3: Basic scraping if RSS failed and scraping config available
            if self._has_modern_config(source):
                try:
                    logger.debug(f"Attempting basic web scraping for {source.name}")
                    articles = await self.modern_scraper.scrape_source(source)

                    if articles:
                        response_time = (datetime.now() - start_time).total_seconds()
                        self._update_stats("modern_scraping_successes", len(articles), response_time, True)

                        logger.info(f"Basic scraping successful for {source.name}: {len(articles)} articles")
                        return FetchResult(
                            source=source,
                            articles=articles,
                            method="basic_scraping",
                            success=True,
                            response_time=response_time,
                        )
                    logger.warning(f"Basic scraping returned no articles for {source.name}")

                except Exception as e:
                    logger.warning(f"Basic scraping failed for {source.name}: {e}")

            # Tier 4: Simple HTML scraping as last resort
            try:
                logger.debug(f"Attempting simple HTML scraping for {source.name}")
                articles = await self.legacy_scraper.scrape_source(source)

                response_time = (datetime.now() - start_time).total_seconds()

                if articles:
                    self._update_stats("legacy_scraping_successes", len(articles), response_time, True)

                    logger.info(f"Legacy scraping successful for {source.name}: {len(articles)} articles")
                    return FetchResult(
                        source=source,
                        articles=articles,
                        method="legacy_scraping",
                        success=True,
                        response_time=response_time,
                    )
                self._update_stats("legacy_scraping_successes", 0, response_time, False)
                error_msg = "No articles extracted from any method"

                logger.error(f"All fetch methods failed for {source.name}: {error_msg}")
                return FetchResult(
                    source=source,
                    articles=[],
                    method="all_failed",
                    success=False,
                    error=error_msg,
                    response_time=response_time,
                )

            except Exception as e:
                response_time = (datetime.now() - start_time).total_seconds()
                self._update_stats("legacy_scraping_successes", 0, response_time, False)
                error_msg = f"Legacy scraping failed: {e}"

                logger.error(f"All fetch methods failed for {source.name}: {error_msg}")
                return FetchResult(
                    source=source,
                    articles=[],
                    method="all_failed",
                    success=False,
                    error=error_msg,
                    response_time=response_time,
                )

        except Exception as e:
            response_time = (datetime.now() - start_time).total_seconds()
            self._update_stats("failed_fetches", 0, response_time, False)
            error_msg = f"Unexpected error during fetch: {e}"

            logger.error(f"Fetch failed for {source.name}: {error_msg}")
            return FetchResult(
                source=source, articles=[], method="error", success=False, error=error_msg, response_time=response_time
            )

    async def fetch_multiple_sources(
        self, sources: list[Source], max_concurrent: int | None = None
    ) -> list[FetchResult]:
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
                fetch_results.append(
                    FetchResult(source=sources[i], articles=[], method="task_error", success=False, error=str(result))
                )
            else:
                fetch_results.append(result)

        # Log summary
        successful = sum(1 for r in fetch_results if r.success)
        total_articles = sum(len(r.articles) for r in fetch_results)

        logger.info(
            f"Batch fetch completed: {successful}/{len(sources)} sources successful, {total_articles} total articles"
        )

        return fetch_results

    async def fetch_due_sources(self, sources: list[Source], force_check: bool = False) -> list[FetchResult]:
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

    def _should_use_playwright(self, source: Source) -> bool:
        """Check if source should use Playwright for JS-rendered content."""
        config = source.config if isinstance(source.config, dict) else {}

        # Handle nested config structure (when loaded from YAML, config may be nested under 'config' key)
        if isinstance(config, dict) and "config" in config and isinstance(config["config"], dict):
            actual_config = config["config"]
        else:
            actual_config = config

        config_keys = list(actual_config.keys()) if isinstance(actual_config, dict) else "N/A"
        logger.debug(f"Checking Playwright for {source.name}: config type={type(actual_config)}, keys={config_keys}")
        use_playwright = actual_config.get("use_playwright", False) if isinstance(actual_config, dict) else False
        logger.debug(f"Playwright check for {source.name}: use_playwright={use_playwright}")

        if use_playwright:
            logger.info(f"Playwright enabled for {source.name}")
            return True

        return False

    def _has_modern_config(self, source: Source) -> bool:
        """Check if source has modern scraping configuration."""
        config = source.config

        config_keys = list(config.keys()) if isinstance(config, dict) else "not a dict"
        logger.debug(f"Checking modern config for {source.name}: config type={type(config)}, config keys={config_keys}")

        # Check for discovery strategies
        discovery = config.get("discovery", {}) if isinstance(config, dict) else getattr(config, "discovery", {})
        logger.debug(
            f"Discovery config: {discovery}, has strategies: {bool(discovery and discovery.get('strategies'))}"
        )
        if discovery and discovery.get("strategies"):
            logger.debug(f"Modern config detected via discovery strategies for {source.name}")
            return True

        # Check for extraction configuration beyond basic selectors
        extract = config.get("extract", {}) if isinstance(config, dict) else getattr(config, "extract", {})
        has_selectors = bool(
            extract
            and (extract.get("title_selectors") or extract.get("date_selectors") or extract.get("body_selectors"))
        )
        logger.debug(f"Extract config: {extract}, has selectors: {has_selectors}")
        if extract and (
            extract.get("title_selectors") or extract.get("date_selectors") or extract.get("body_selectors")
        ):
            logger.debug(f"Modern config detected via extract selectors for {source.name}")
            return True

        logger.debug(f"No modern config found for {source.name}")
        return False

    def _update_stats(self, method: str, article_count: int, response_time: float, success: bool):
        """Update internal statistics."""
        self.stats["total_fetches"] += 1

        if success:
            self.stats["successful_fetches"] += 1
            self.stats["articles_collected"] += article_count
            if method in self.stats:
                self.stats[method] += 1
        else:
            self.stats["failed_fetches"] += 1

        # Update average response time
        current_avg = self.stats["avg_response_time"]
        total_fetches = self.stats["total_fetches"]
        self.stats["avg_response_time"] = ((current_avg * (total_fetches - 1)) + response_time) / total_fetches

    def get_statistics(self) -> dict[str, Any]:
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
        max_check_age: int = 86400,  # 24 hours
    ):
        self.content_fetcher = content_fetcher
        self.check_interval = check_interval
        self.max_check_age = max_check_age
        self.running = False
        self._task: asyncio.Task | None = None

    async def start(self, sources: list[Source], callback=None):
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
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

        logger.info("Scheduled fetcher stopped")

    async def _run_scheduler(self, sources: list[Source], callback=None):
        """Main scheduler loop."""
        try:
            while self.running:
                logger.debug("Checking for sources due for fetching...")

                # Find sources due for checking
                due_sources = []

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
