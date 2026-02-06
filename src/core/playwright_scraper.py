"""Playwright-based scraper for JS-rendered content."""

import asyncio
import logging
from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup
from playwright.async_api import Browser, BrowserContext, Page, async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from src.models.article import ArticleCreate
from src.models.source import Source
from src.utils.content import ContentCleaner, DateExtractor, MetadataExtractor, validate_content

logger = logging.getLogger(__name__)


class PlaywrightScraper:
    """Scraper using Playwright for JS-rendered content."""

    def __init__(self, headless: bool = True, timeout: float = 30000.0, wait_until: str = "networkidle"):
        """
        Initialize Playwright scraper.

        Args:
            headless: Run browser in headless mode
            timeout: Page load timeout in milliseconds
            wait_until: When to consider navigation successful ("load", "domcontentloaded", "networkidle")
        """
        self.headless = headless
        self.timeout = timeout
        self.wait_until = wait_until
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._playwright = None

    async def __aenter__(self):
        """Async context manager entry."""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def scrape_source(self, source: Source) -> list[ArticleCreate]:
        """
        Scrape articles from source using Playwright.

        Args:
            source: Source configuration

        Returns:
            List of ArticleCreate objects
        """
        logger.info(f"Starting Playwright scraping for {source.name}")

        if not self._context:
            raise RuntimeError("PlaywrightScraper must be used as async context manager")

        # Get discovery URLs
        urls = await self._discover_urls(source)

        if not urls:
            logger.warning(f"No URLs discovered for {source.name}")
            return []

        # Extract articles
        articles = []
        page = await self._context.new_page()

        try:
            for url in urls[:50]:  # Limit to prevent overwhelming
                try:
                    article = await self._extract_article(page, url, source)
                    if article:
                        articles.append(article)

                    # Rate limiting between articles
                    await asyncio.sleep(1.0)

                except Exception as e:
                    logger.error(f"Failed to extract article from {url}: {e}")
                    continue
        finally:
            await page.close()

        logger.info(f"Extracted {len(articles)} articles from {source.name} using Playwright")
        return articles

    async def _discover_urls(self, source: Source) -> list[str]:
        """Discover article URLs from source."""
        discovered_urls = set()

        # Handle nested config structure
        config = source.config if isinstance(source.config, dict) else {}
        if isinstance(config, dict) and "config" in config and isinstance(config["config"], dict):
            actual_config = config["config"]
        else:
            actual_config = config

        discovery_config = actual_config.get("discovery", {}) if isinstance(actual_config, dict) else {}
        strategies = discovery_config.get("strategies", []) if isinstance(discovery_config, dict) else []

        logger.info(f"Discovery config for {source.name}: strategies={len(strategies)}, config={discovery_config}")

        if not strategies:
            # Fallback: use base URL
            discovered_urls.add(source.url)
        else:
            page = await self._context.new_page()
            try:
                for strategy in strategies:
                    try:
                        if "listing" in strategy:
                            urls = await self._discover_from_listing(page, strategy["listing"], source)
                            discovered_urls.update(urls)
                        elif "sitemap" in strategy:
                            # Sitemap discovery doesn't need Playwright
                            logger.debug("Sitemap discovery not implemented for Playwright, skipping")
                    except Exception as e:
                        logger.error(f"Discovery strategy failed for {source.name}: {e}")
                        continue
            finally:
                await page.close()

        # Filter by scope
        filtered_urls = self._filter_by_scope(list(discovered_urls), source)
        logger.info(f"Discovered {len(filtered_urls)} URLs for {source.name} using Playwright")
        if filtered_urls:
            logger.debug(f"Sample URLs: {filtered_urls[:3]}")
        return filtered_urls

    async def _discover_from_listing(self, page: Page, config: dict[str, Any], source: Source) -> list[str]:
        """Discover URLs from listing pages using Playwright."""
        urls = set()

        listing_urls = config.get("urls", [])
        post_link_selector = config.get("post_link_selector", "")
        next_selector = config.get("next_selector", "")
        max_pages = config.get("max_pages", 3)

        if not listing_urls or not post_link_selector:
            return []

        for listing_url in listing_urls:
            try:
                page_count = 0
                current_url = listing_url

                while current_url and page_count < max_pages:
                    logger.debug(f"Scraping listing page {page_count + 1}: {current_url}")

                    await page.goto(current_url, wait_until=self.wait_until, timeout=self.timeout)

                    # Additional wait for JS to render
                    await asyncio.sleep(2.0)

                    # Normalize selector - remove invalid CSS syntax ([href!="..."]) and use simpler base selector
                    # CSS doesn't support !=, so we'll filter in code
                    base_selector = post_link_selector
                    if "[href!=" in base_selector:
                        # Extract the base part before the invalid syntax
                        base_selector = base_selector.split("[href!=")[0].strip()
                    # Remove :not() clauses that might have issues
                    if ":not([href*=" in base_selector:
                        base_selector = base_selector.split(":not([href*=")[0].strip()

                    logger.debug(f"Using normalized selector: {base_selector} (original: {post_link_selector})")

                    # Wait for content to load using the normalized selector
                    try:
                        await page.wait_for_selector(base_selector, timeout=10000)
                    except PlaywrightTimeoutError:
                        logger.warning(f"Selector '{base_selector}' not found on {current_url}, trying any links")
                        # Try to find any links as fallback
                        all_links = await page.query_selector_all("a[href]")
                        logger.debug(f"Found {len(all_links)} total links on page")
                        if all_links:
                            sample_hrefs = []
                            for link in all_links[:5]:
                                href = await link.get_attribute("href")
                                if href:
                                    sample_hrefs.append(href)
                            logger.debug(f"Sample hrefs: {sample_hrefs}")
                        # Continue anyway - we'll try to extract links

                    # Extract post links using normalized selector, then filter manually
                    try:
                        post_links = await page.query_selector_all(base_selector)
                    except Exception as e:
                        logger.warning(f"Selector '{base_selector}' failed: {e}")
                        # Last resort: get all links
                        post_links = await page.query_selector_all("a[href]")

                    logger.debug(f"Found {len(post_links)} links matching selector")
                    for link in post_links:
                        href = await link.get_attribute("href")
                        if href:
                            # Filter out excluded patterns manually (since CSS doesn't support !=)
                            if "/blog/security.html" in href or "?p=" in href:
                                continue
                            full_url = self._resolve_url(href, current_url)
                            logger.debug(f"Resolved URL: {full_url}")
                            if self._matches_post_regex(full_url, source):
                                urls.add(full_url)
                                logger.debug(f"Added URL: {full_url}")
                            else:
                                logger.debug(f"URL doesn't match post_regex: {full_url}")

                    # Find next page link
                    if next_selector:
                        next_link = await page.query_selector(next_selector)
                        if next_link:
                            next_href = await next_link.get_attribute("href")
                            if next_href:
                                current_url = self._resolve_url(next_href, current_url)
                                page_count += 1
                            else:
                                break
                        else:
                            break
                    else:
                        break

            except PlaywrightTimeoutError:
                logger.warning(f"Timeout loading listing page: {current_url}")
                continue
            except Exception as e:
                logger.error(f"Error discovering from listing {listing_url}: {e}")
                continue

        return list(urls)

    async def _extract_article(self, page: Page, url: str, source: Source) -> ArticleCreate | None:
        """
        Extract article from URL using Playwright.

        Args:
            page: Playwright page instance
            url: Article URL
            source: Source configuration

        Returns:
            ArticleCreate object or None if extraction fails
        """
        try:
            logger.debug(f"Loading article page: {url}")

            # Navigate to page
            await page.goto(url, wait_until=self.wait_until, timeout=self.timeout)

            # Wait for content to be rendered (additional wait for JS-heavy sites)
            await asyncio.sleep(2.0)

            # Get page HTML after JS execution
            html_content = await page.content()

            # Parse HTML
            soup = BeautifulSoup(html_content, "lxml")

            # Extract article data using same logic as ModernScraper
            extract_config = (
                source.config.get("extract", {})
                if isinstance(source.config, dict)
                else getattr(source.config, "extract", {})
            )

            article_data = {}

            # Extract title
            title_selectors = (
                extract_config.get("title_selectors", ["h1"]) if isinstance(extract_config, dict) else ["h1"]
            )
            title = self._extract_with_selector_list(soup, title_selectors)
            if title:
                article_data["title"] = ContentCleaner.normalize_whitespace(title)

            # Extract publication date
            date_selectors = extract_config.get("date_selectors", []) if isinstance(extract_config, dict) else []
            published_at = None
            for selector in date_selectors:
                date_text = self._extract_with_selector_list(soup, [selector])
                if date_text:
                    published_at = DateExtractor.parse_date(date_text)
                    if published_at:
                        break

            if not published_at:
                published_at = DateExtractor.extract_date_from_url(url)

            if published_at:
                article_data["published_at"] = published_at

            # Extract content
            body_selectors = (
                extract_config.get("body_selectors", ["article", "main"])
                if isinstance(extract_config, dict)
                else ["article", "main"]
            )

            content_html = None
            for selector in body_selectors:
                content_elem = soup.select_one(selector)
                if content_elem:
                    text_length = len(ContentCleaner.html_to_text(str(content_elem)).strip())
                    if text_length > 100:
                        content_html = str(content_elem)
                        logger.debug(f"Found content with selector '{selector}' for {url} ({text_length} chars)")
                        break

            # Fallback selectors
            if not content_html:
                for fallback_selector in [
                    "article",
                    "main",
                    '[role="main"]',
                    ".content",
                    ".post-content",
                    ".entry-content",
                    ".splunkBlogsArticle-body-content",
                    ".cmp-text",
                    ".rte-container",
                ]:
                    content_elem = soup.select_one(fallback_selector)
                    if content_elem:
                        text_length = len(ContentCleaner.html_to_text(str(content_elem)).strip())
                        if text_length > 500:
                            content_html = str(content_elem)
                            logger.debug(
                                f"Found content with fallback selector '{fallback_selector}' for {url} "
                                f"({text_length} chars)"
                            )
                            break

            if content_html:
                cleaned_content = ContentCleaner.clean_html(content_html)
                text_length = len(cleaned_content.strip())
                if text_length > 100:
                    article_data["content"] = cleaned_content
                else:
                    logger.warning(f"Content too short after cleaning for {url} ({text_length} chars)")
                    return None
            else:
                logger.warning(f"No content found for {url} with selectors: {body_selectors}")
                return None

            # Validate required fields
            if not article_data.get("title") or not article_data.get("content"):
                logger.warning(f"Missing required fields for {url}")
                return None

            # Validate content
            issues = validate_content(article_data["title"], article_data["content"], url)
            if issues:
                logger.warning(f"Content validation issues for {url}: {issues}")

            # Extract authors
            author_selectors = extract_config.get("author_selectors", []) if isinstance(extract_config, dict) else []
            if author_selectors:
                authors = []
                for selector in author_selectors:
                    author_text = self._extract_with_selector_list(soup, [selector])
                    if author_text:
                        authors.append(author_text.strip())
                if authors:
                    article_data["authors"] = authors[:3]

            if not article_data.get("authors"):
                article_data["authors"] = MetadataExtractor.extract_authors(soup)

            # Extract canonical URL
            canonical_url = MetadataExtractor.extract_canonical_url(soup)
            if canonical_url:
                article_data["canonical_url"] = canonical_url

            # Generate required fields
            content_hash = ContentCleaner.calculate_content_hash(article_data["title"], article_data["content"])
            word_count = len(article_data["content"].split()) if article_data["content"] else 0
            collected_at = datetime.now()

            # Build and return article
            return ArticleCreate(
                source_id=source.id,
                url=url,
                canonical_url=article_data.get("canonical_url", url),
                title=article_data["title"],
                published_at=article_data.get("published_at") or datetime.now(),
                content=article_data["content"],
                content_hash=content_hash,
                word_count=word_count,
                collected_at=collected_at,
            )

        except PlaywrightTimeoutError:
            logger.error(f"Timeout loading article: {url}")
            return None
        except Exception as e:
            logger.error(f"Failed to extract article from {url}: {e}")
            return None

    def _extract_with_selector_list(self, soup: BeautifulSoup, selectors: list[str]) -> str | None:
        """Extract text using list of selectors, trying each until one works."""
        for selector in selectors:
            try:
                if "::attr(" in selector:
                    selector_part, attr_part = selector.split("::attr(")
                    attr_name = attr_part.rstrip(")")

                    elem = soup.select_one(selector_part)
                    if elem:
                        value = elem.get(attr_name)
                        if value:
                            return str(value).strip()
                else:
                    elem = soup.select_one(selector)
                    if elem:
                        text = elem.get_text(strip=True)
                        if text:
                            return text

            except Exception as e:
                logger.debug(f"Selector '{selector}' failed: {e}")
                continue

        return None

    def _filter_by_scope(self, urls: list[str], source: Source) -> list[str]:
        """Filter URLs by source scope (post_url_regex)."""
        config = source.config if isinstance(source.config, dict) else {}
        post_url_regex = config.get("post_url_regex", [])

        if not post_url_regex:
            return urls

        import re

        filtered = []
        for url in urls:
            for pattern in post_url_regex:
                if re.match(pattern, url):
                    filtered.append(url)
                    break

        return filtered

    def _matches_post_regex(self, url: str, source: Source) -> bool:
        """Check if URL matches post_url_regex patterns."""
        config = source.config if isinstance(source.config, dict) else {}
        post_url_regex = config.get("post_url_regex", [])

        if not post_url_regex:
            return True

        import re

        return any(re.match(pattern, url) for pattern in post_url_regex)

    def _resolve_url(self, href: str, base_url: str) -> str:
        """Resolve relative URL to absolute."""
        from urllib.parse import urljoin

        return urljoin(base_url, href)
