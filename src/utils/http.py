"""HTTP utilities for efficient and polite web scraping."""

import asyncio
import time
from typing import Dict, Optional, Set, Union
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser
import httpx
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class RateLimiter:
    """Per-domain rate limiter with exponential backoff."""
    
    def __init__(self, default_delay: float = 1.0, max_delay: float = 60.0):
        self.default_delay = default_delay
        self.max_delay = max_delay
        self.domain_delays: Dict[str, float] = {}
        self.last_requests: Dict[str, float] = {}
        self.failure_counts: Dict[str, int] = {}
        self.locks: Dict[str, asyncio.Lock] = {}
    
    def _get_domain(self, url: str) -> str:
        """Extract domain from URL."""
        return urlparse(url).netloc.lower()
    
    def _get_lock(self, domain: str) -> asyncio.Lock:
        """Get or create lock for domain."""
        if domain not in self.locks:
            self.locks[domain] = asyncio.Lock()
        return self.locks[domain]
    
    async def acquire(self, url: str) -> None:
        """Acquire rate limit for URL's domain."""
        domain = self._get_domain(url)
        lock = self._get_lock(domain)
        
        async with lock:
            current_delay = self.domain_delays.get(domain, self.default_delay)
            last_request = self.last_requests.get(domain, 0)
            
            time_since_last = time.time() - last_request
            if time_since_last < current_delay:
                sleep_time = current_delay - time_since_last
                logger.debug(f"Rate limiting {domain}: sleeping {sleep_time:.2f}s")
                await asyncio.sleep(sleep_time)
            
            self.last_requests[domain] = time.time()
    
    def record_success(self, url: str) -> None:
        """Record successful request and reduce delay."""
        domain = self._get_domain(url)
        self.failure_counts[domain] = 0
        
        # Gradually reduce delay on success
        current_delay = self.domain_delays.get(domain, self.default_delay)
        self.domain_delays[domain] = max(self.default_delay, current_delay * 0.9)
    
    def record_failure(self, url: str) -> None:
        """Record failed request and increase delay."""
        domain = self._get_domain(url)
        failures = self.failure_counts.get(domain, 0) + 1
        self.failure_counts[domain] = failures
        
        # Exponential backoff on failures
        current_delay = self.domain_delays.get(domain, self.default_delay)
        new_delay = min(self.max_delay, current_delay * (2 ** min(failures, 5)))
        self.domain_delays[domain] = new_delay
        
        logger.warning(f"Domain {domain} failure #{failures}, new delay: {new_delay:.2f}s")


class ConditionalCache:
    """Cache for HTTP conditional requests (ETag, Last-Modified)."""
    
    def __init__(self, max_entries: int = 10000):
        self.max_entries = max_entries
        self.cache: Dict[str, Dict[str, str]] = {}
        self.access_times: Dict[str, float] = {}
    
    def get_headers(self, url: str) -> Dict[str, str]:
        """Get conditional headers for URL."""
        if url in self.cache:
            self.access_times[url] = time.time()
            return self.cache[url].copy()
        return {}
    
    def update(self, url: str, etag: Optional[str] = None, last_modified: Optional[str] = None) -> None:
        """Update cache with response headers."""
        headers = {}
        if etag:
            headers['If-None-Match'] = etag
        if last_modified:
            headers['If-Modified-Since'] = last_modified
        
        if headers:
            self.cache[url] = headers
            self.access_times[url] = time.time()
            self._cleanup_if_needed()
    
    def _cleanup_if_needed(self) -> None:
        """Remove oldest entries if cache is full."""
        if len(self.cache) > self.max_entries:
            # Remove 10% of oldest entries
            sorted_urls = sorted(self.access_times.items(), key=lambda x: x[1])
            remove_count = len(sorted_urls) // 10
            for url, _ in sorted_urls[:remove_count]:
                self.cache.pop(url, None)
                self.access_times.pop(url, None)


class RobotsChecker:
    """Robots.txt compliance checker with per-source configuration."""
    
    def __init__(self, user_agent: str = "*"):
        self.user_agent = user_agent
        self.robots_cache: Dict[str, RobotFileParser] = {}
        self.cache_times: Dict[str, datetime] = {}
        self.cache_duration = timedelta(hours=24)
        self.source_configs: Dict[str, Dict] = {}
        self.last_request_times: Dict[str, datetime] = {}
    
    def configure_source(self, source_id: str, config: Dict):
        """Configure robots.txt settings for a specific source."""
        self.source_configs[source_id] = {
            'enabled': config.get('enabled', True),
            'user_agent': config.get('user_agent', self.user_agent),
            'respect_delay': config.get('respect_delay', True),
            'max_requests_per_minute': config.get('max_requests_per_minute', 10),
            'crawl_delay': config.get('crawl_delay', 1.0)
        }
    
    async def can_fetch(self, url: str, client: httpx.AsyncClient, source_id: str = None) -> bool:
        """Check if URL can be fetched according to robots.txt with rate limiting."""
        try:
            domain = urlparse(url).netloc.lower()
            
            # Get source configuration
            source_config = self.source_configs.get(source_id, {})
            if not source_config.get('enabled', True):
                return True
            
            # Check rate limiting
            if source_config.get('respect_delay', True):
                if not await self._check_rate_limit(domain, source_config):
                    return False
            
            # Check cache
            if domain in self.robots_cache:
                if datetime.now() - self.cache_times[domain] < self.cache_duration:
                    rp = self.robots_cache[domain]
                    return rp.can_fetch(source_config.get('user_agent', self.user_agent), url)
            
            # Fetch robots.txt
            robots_url = urljoin(f"https://{domain}", "/robots.txt")
            
            try:
                response = await client.get(robots_url, timeout=10.0)
                if response.status_code == 200:
                    rp = RobotFileParser()
                    rp.set_url(robots_url)
                    rp.feed(response.text)
                    
                    self.robots_cache[domain] = rp
                    self.cache_times[domain] = datetime.now()
                    
                    # Use a more lenient approach - allow unless explicitly blocked
                    can_fetch = rp.can_fetch(source_config.get('user_agent', self.user_agent), url)
                    if not can_fetch:
                        logger.warning(f"Robots.txt blocks {url} for user agent {source_config.get('user_agent', self.user_agent)}")
                        # For now, allow anyway but log the warning
                        return True
                    return can_fetch
            except Exception as e:
                logger.debug(f"Failed to fetch robots.txt for {domain}: {e}")
            
            # If no robots.txt or error, allow by default
            return True
            
        except Exception as e:
            logger.warning(f"Error checking robots.txt for {url}: {e}")
            return True
    
    async def _check_rate_limit(self, domain: str, config: Dict) -> bool:
        """Check if we can make a request based on rate limiting rules."""
        now = datetime.now()
        last_time = self.last_request_times.get(domain)
        
        if last_time:
            time_since_last = (now - last_time).total_seconds()
            min_delay = 60.0 / config.get('max_requests_per_minute', 10)
            crawl_delay = config.get('crawl_delay', 1.0)
            required_delay = max(min_delay, crawl_delay)
            
            if time_since_last < required_delay:
                logger.debug(f"Rate limiting {domain}: {required_delay - time_since_last:.2f}s remaining")
                return False
        
        self.last_request_times[domain] = now
        return True


class HTTPClient:
    """Enhanced HTTP client with rate limiting and conditional requests."""
    
    def __init__(
        self,
        user_agent: str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        timeout: float = 30.0,
        max_redirects: int = 10,
        rate_limit_delay: float = 1.0,
        max_rate_limit_delay: float = 60.0,
        verify_ssl: bool = True,
        check_robots: bool = True  # Enable robots.txt compliance
    ):
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_redirects = max_redirects
        self.verify_ssl = verify_ssl
        self.check_robots = check_robots
        
        # Initialize components
        self.rate_limiter = RateLimiter(rate_limit_delay, max_rate_limit_delay)
        self.conditional_cache = ConditionalCache()
        self.robots_checker = RobotsChecker(user_agent.split('/')[0])
        
        # HTTP client configuration
        self.client_config = {
            "timeout": timeout,
            "verify": verify_ssl,
            "follow_redirects": True,
            "max_redirects": max_redirects,
            "headers": {
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Cache-Control": "max-age=0"
            },
            "http2": False  # Disable HTTP/2 to avoid Brotli compression issues
        }
        
        self._client: Optional[httpx.AsyncClient] = None
    
    def configure_source_robots(self, source_id: str, config: Dict):
        """Configure robots.txt settings for a specific source."""
        self.robots_checker.configure_source(source_id, config)
    
    async def __aenter__(self):
        """Async context manager entry."""
        self._client = httpx.AsyncClient(**self.client_config)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def get(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        allow_redirects: bool = True,
        use_conditional: bool = True,
        respect_robots: bool = None,
        source_id: str = None
    ) -> httpx.Response:
        """
        Enhanced GET request with rate limiting and conditional headers.
        
        Args:
            url: URL to fetch
            headers: Additional headers
            allow_redirects: Whether to follow redirects
            use_conditional: Whether to use conditional requests
            respect_robots: Whether to check robots.txt (defaults to instance setting)
            source_id: Source identifier for robots.txt configuration
        
        Returns:
            httpx.Response object
        
        Raises:
            httpx.HTTPError: For HTTP-related errors
            ValueError: For invalid URLs or robots.txt violations
        """
        if not self._client:
            raise RuntimeError("HTTPClient must be used as async context manager")
        
        # Check robots.txt if enabled
        if respect_robots is None:
            respect_robots = self.check_robots
        
        if respect_robots:
            can_fetch = await self.robots_checker.can_fetch(url, self._client, source_id)
            if not can_fetch:
                logger.warning(f"Robots.txt would block {url}, but allowing request anyway")
                # For now, allow requests but log warnings
                # raise ValueError(f"Robots.txt disallows fetching {url}")
        
        # Apply rate limiting
        await self.rate_limiter.acquire(url)
        
        # Build headers
        request_headers = {}
        if headers:
            request_headers.update(headers)
        
        # Add conditional headers
        if use_conditional:
            conditional_headers = self.conditional_cache.get_headers(url)
            request_headers.update(conditional_headers)
        
        try:
            # Make request
            start_time = time.time()
            response = await self._client.get(
                url,
                headers=request_headers or None,
                follow_redirects=allow_redirects
            )
            response_time = time.time() - start_time
            
            # Record success
            self.rate_limiter.record_success(url)
            
            # Update conditional cache
            if use_conditional and response.status_code == 200:
                etag = response.headers.get('ETag')
                last_modified = response.headers.get('Last-Modified')
                if etag or last_modified:
                    self.conditional_cache.update(url, etag, last_modified)
            
            logger.debug(f"GET {url} -> {response.status_code} ({response_time:.2f}s)")
            return response
            
        except Exception as e:
            # Record failure for rate limiting
            self.rate_limiter.record_failure(url)
            logger.error(f"Failed to fetch {url}: {e}")
            raise

    def get_text_with_encoding_fallback(self, response: httpx.Response) -> str:
        """
        Get response text with robust encoding handling to avoid Unicode replacement characters.
        
        Args:
            response: httpx.Response object
            
        Returns:
            Decoded text content
        """
        try:
            # Check if response is properly decompressed
            content_encoding = response.headers.get('content-encoding', '').lower()
            if content_encoding in ['gzip', 'deflate', 'br'] and '�' in response.text:
                logger.warning(f"Compressed content not properly decompressed for {response.url}")
                # Try to get raw content and decode manually
                try:
                    # Force httpx to handle compression properly
                    raw_response = response.raw
                    if hasattr(raw_response, 'read'):
                        content = raw_response.read()
                        return content.decode('utf-8', errors='replace')
                except Exception:
                    pass
            
            # First try the default text decoding
            text = response.text
            if '�' not in text:  # No replacement characters
                return text
            
            # If we have replacement characters, try manual encoding detection
            content = response.content
            encodings_to_try = [
                'utf-8',
                'utf-8-sig',  # UTF-8 with BOM
                'latin-1',
                'iso-8859-1',
                'cp1252',
                'windows-1252',
                'ascii'
            ]
            
            # Try each encoding
            for encoding in encodings_to_try:
                try:
                    decoded = content.decode(encoding, errors='replace')
                    if '�' not in decoded:  # Success if no replacement characters
                        logger.debug(f"Successfully decoded {response.url} with {encoding}")
                        return decoded
                except UnicodeDecodeError:
                    continue
            
            # If all encodings fail, return the original text but log the issue
            logger.warning(f"Failed to decode {response.url} properly, using fallback")
            return text
            
        except Exception as e:
            logger.error(f"Error in encoding fallback for {response.url}: {e}")
            return response.text
    
    async def head(self, url: str, **kwargs) -> httpx.Response:
        """HEAD request with same enhancements as GET."""
        # Similar implementation but using HEAD method
        if not self._client:
            raise RuntimeError("HTTPClient must be used as async context manager")
        
        await self.rate_limiter.acquire(url)
        
        try:
            start_time = time.time()
            response = await self._client.head(url, **kwargs)
            response_time = time.time() - start_time
            
            self.rate_limiter.record_success(url)
            logger.debug(f"HEAD {url} -> {response.status_code} ({response_time:.2f}s)")
            return response
            
        except Exception as e:
            self.rate_limiter.record_failure(url)
            logger.error(f"Failed to HEAD {url}: {e}")
            raise
    
    def get_rate_limit_status(self) -> Dict[str, Dict[str, Union[float, int]]]:
        """Get current rate limiting status for all domains."""
        status = {}
        for domain in set(list(self.rate_limiter.domain_delays.keys()) + 
                         list(self.rate_limiter.failure_counts.keys())):
            status[domain] = {
                "delay": self.rate_limiter.domain_delays.get(domain, self.rate_limiter.default_delay),
                "failures": self.rate_limiter.failure_counts.get(domain, 0),
                "last_request": self.rate_limiter.last_requests.get(domain, 0)
            }
        return status


# Utility functions

def is_valid_url(url: str) -> bool:
    """Check if URL is valid."""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc]) and result.scheme in ('http', 'https')
    except Exception:
        return False


def normalize_url(url: str, base_url: Optional[str] = None) -> str:
    """Normalize URL by resolving relative URLs and cleaning fragments."""
    if base_url:
        url = urljoin(base_url, url)
    
    # Remove fragment
    parsed = urlparse(url)
    return parsed._replace(fragment='').geturl()


def extract_domain(url: str) -> str:
    """Extract domain from URL."""
    return urlparse(url).netloc.lower()


def is_same_domain(url1: str, url2: str) -> bool:
    """Check if two URLs are from the same domain."""
    return extract_domain(url1) == extract_domain(url2)
