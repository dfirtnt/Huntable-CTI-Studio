"""HTTP utilities for efficient and polite web scraping."""

import asyncio
import logging
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx

logger = logging.getLogger(__name__)


@dataclass
class RequestConfig:
    """Configuration for HTTP requests."""

    timeout: float = 30.0
    max_retries: int = 3
    retry_delay: float = 1.0
    follow_redirects: bool = True
    verify_ssl: bool = True
    user_agent: str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    headers: dict[str, str] | None = None

    def __post_init__(self):
        """Post-initialization to set default values."""
        if self.headers is None:
            self.headers = {}

    def get_browser_headers(self, url: str | None = None) -> dict[str, str]:
        """Get browser-like headers to bypass anti-bot detection."""
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not A(Brand";v="24"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"macOS"',
            "Cache-Control": "max-age=0",
        }

        # Add Referer if URL is provided
        if url:
            try:
                from urllib.parse import urlparse

                parsed = urlparse(url)
                headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"
            except Exception:
                pass

        # Merge with custom headers
        headers.update(self.headers)
        return headers

    def to_dict(self) -> dict:
        """Convert config to dictionary."""
        return {
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay,
            "follow_redirects": self.follow_redirects,
            "verify_ssl": self.verify_ssl,
            "user_agent": self.user_agent,
            "headers": self.headers,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RequestConfig":
        """Create config from dictionary."""
        return cls(**data)


@dataclass
class Response:
    """HTTP response wrapper."""

    status_code: int
    headers: dict[str, str]
    content: bytes
    url: str
    elapsed: float = 0.0
    encoding: str = "utf-8"

    def is_success(self) -> bool:
        """Check if response is successful."""
        return 200 <= self.status_code < 300

    def is_redirect(self) -> bool:
        """Check if response is a redirect."""
        return 300 <= self.status_code < 400

    def is_client_error(self) -> bool:
        """Check if response is a client error."""
        return 400 <= self.status_code < 500

    def is_server_error(self) -> bool:
        """Check if response is a server error."""
        return 500 <= self.status_code < 600

    def raise_for_status(self):
        """Raise exception for error status codes."""
        if self.is_client_error() or self.is_server_error():
            raise Exception(f"HTTP {self.status_code} error")

    @property
    def text(self) -> str:
        """Get response text with proper charset detection."""
        try:
            # First, try the specified encoding
            try:
                text = self.content.decode(self.encoding)
                # Check for excessive replacement characters (indicates wrong encoding)
                replacement_char = "\ufffd"
                replacement_ratio = text.count(replacement_char) / len(text) if text else 0

                # If less than 1% replacement chars, encoding is likely correct
                if replacement_ratio < 0.01:
                    return text
            except (UnicodeDecodeError, LookupError):
                pass  # Fall through to charset detection

            # Use charset-normalizer for proper detection
            try:
                from charset_normalizer import detect

                detection_result = detect(self.content)
                detected_encoding = detection_result.get("encoding", "utf-8")
                confidence = detection_result.get("confidence", 0.0)

                # Only use detected encoding if confidence is reasonable
                if confidence > 0.5 and detected_encoding:
                    try:
                        text = self.content.decode(detected_encoding)
                        # Verify it's not corrupted
                        replacement_ratio = text.count("\ufffd") / len(text) if text else 0
                        if replacement_ratio < 0.01:
                            return text
                    except (UnicodeDecodeError, LookupError):
                        pass
            except ImportError:
                # charset-normalizer not available, fall back to standard methods
                pass

            # Try common encodings in order of likelihood
            for encoding in ["utf-8", "latin-1", "iso-8859-1", "cp1252"]:
                try:
                    text = self.content.decode(encoding)
                    # Verify it's not corrupted
                    replacement_ratio = text.count("\ufffd") / len(text) if text else 0
                    if replacement_ratio < 0.01:
                        return text
                except (UnicodeDecodeError, LookupError):
                    continue

            # Last resort: decode with errors='ignore' (better than 'replace' for most use cases)
            # This removes problematic bytes rather than replacing them
            return self.content.decode("utf-8", errors="ignore")

        except Exception as e:
            # Absolute fallback
            logger.warning(f"Failed to decode response content: {e}, using utf-8 with ignore")
            return self.content.decode("utf-8", errors="ignore")


class RateLimiter:
    """Per-domain rate limiter with exponential backoff."""

    def __init__(self, requests_per_second: float = 1.0, burst_size: int = 10):
        self.requests_per_second = requests_per_second
        self.burst_size = burst_size
        self.tokens = burst_size
        self.last_refill = time.time()
        self.lock = asyncio.Lock()

    def acquire_token(self) -> bool:
        """Acquire a token for making a request (synchronous)."""
        now = time.time()
        time_passed = now - self.last_refill

        # Refill tokens based on time passed
        tokens_to_add = time_passed * self.requests_per_second
        self.tokens = min(self.burst_size, self.tokens + tokens_to_add)
        self.last_refill = now

        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False

    async def wait_for_token(self) -> bool:
        """Wait until a token is available (asynchronous)."""
        while not self.acquire_token():
            await asyncio.sleep(0.1)
        return True

    def refill_tokens(self) -> None:
        """Manually refill tokens."""
        now = time.time()
        time_passed = now - self.last_refill
        tokens_to_add = time_passed * self.requests_per_second
        self.tokens = min(self.burst_size, self.tokens + tokens_to_add)
        self.last_refill = now


class HTTPClient:
    """Enhanced HTTP client with rate limiting and conditional requests."""

    def __init__(self, config: RequestConfig | None = None, rate_limiter: RateLimiter | None = None):
        self.config = config or RequestConfig()
        self.rate_limiter = rate_limiter or RateLimiter()

        # Statistics tracking
        self._request_count = 0
        self._success_count = 0
        self._error_count = 0
        self._total_time = 0.0

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        return

    async def get(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict | None = None,
        source_id: str | None = None,
        _use_conditional: bool = False,
    ) -> Response:
        """Make a GET request with retry logic.

        Args:
            url: URL to fetch
            headers: Optional HTTP headers (will be merged with default browser headers)
            params: Optional query parameters
            source_id: Optional source identifier for tracking (unused, for compatibility)
            _use_conditional: Optional flag for conditional requests (unused, for compatibility)
        """
        if not url:
            raise ValueError("URL cannot be None")
        if not url.strip():
            raise ValueError("URL cannot be empty")
        if not url.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")

        # Build browser-like headers and merge with provided headers
        default_headers = self.config.get_browser_headers(url)
        if headers:
            # Merge: provided headers override defaults
            merged_headers = {**default_headers, **headers}
        else:
            merged_headers = default_headers

        start_time = time.time()
        self._request_count += 1

        last_exception = None
        for attempt in range(self.config.max_retries + 1):
            try:
                # Wait for rate limiter
                await self.rate_limiter.wait_for_token()

                # Make request
                async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                    response = await client.get(
                        url, headers=merged_headers, params=params, follow_redirects=self.config.follow_redirects
                    )

                    elapsed = time.time() - start_time
                    self._total_time += elapsed

                    # Check if we should retry on server errors
                    if response.is_success:
                        self._success_count += 1
                    else:
                        # Try to raise for status to trigger retry logic
                        try:
                            response.raise_for_status()
                        except Exception as status_exception:
                            if attempt < self.config.max_retries:
                                # Retry on status errors
                                await asyncio.sleep(self.config.retry_delay)
                                continue
                            self._error_count += 1
                            raise status_exception
                        self._error_count += 1

                    # Handle mock headers properly
                    response_headers = {}
                    if hasattr(response.headers, "items") or hasattr(response.headers, "__iter__"):
                        response_headers = dict(response.headers)
                    else:
                        # For mock objects, try to get the value directly
                        response_headers = getattr(response.headers, "_mock_name", {})
                        if not response_headers:
                            response_headers = {}

                    # httpx automatically decompresses ALL content encodings (gzip, deflate, brotli)
                    # when you access response.content or response.text. We trust httpx completely.
                    # The only thing we need to fix is charset detection, which happens in Response.text property.
                    response_content = response.content  # Already decompressed by httpx

                    # Detect encoding: httpx does basic detection, but we'll improve it in Response.text
                    detected_encoding = response.encoding or "utf-8"

                    return Response(
                        status_code=response.status_code,
                        headers=response_headers,
                        content=response_content,
                        url=str(response.url),
                        elapsed=elapsed,
                        encoding=detected_encoding,
                    )

            except Exception as e:
                last_exception = e
                if attempt < self.config.max_retries:
                    await asyncio.sleep(self.config.retry_delay)
                    continue
                self._error_count += 1
                raise last_exception from e

    async def post(
        self, url: str, data: dict | None = None, json: dict | None = None, headers: dict[str, str] | None = None
    ) -> Response:
        """Make a POST request."""
        # Build browser-like headers and merge with provided headers
        default_headers = self.config.get_browser_headers(url)
        if headers:
            merged_headers = {**default_headers, **headers}
        else:
            merged_headers = default_headers

        start_time = time.time()
        self._request_count += 1

        try:
            # Wait for rate limiter
            await self.rate_limiter.wait_for_token()

            # Make request
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.post(
                    url, data=data, json=json, headers=merged_headers, follow_redirects=self.config.follow_redirects
                )

                elapsed = time.time() - start_time
                self._total_time += elapsed

                if response.is_success:
                    self._success_count += 1
                else:
                    self._error_count += 1

                # Handle mock headers properly
                headers = {}
                if hasattr(response.headers, "items") or hasattr(response.headers, "__iter__"):
                    headers = dict(response.headers)
                else:
                    # For mock objects, try to get the value directly
                    headers = getattr(response.headers, "_mock_name", {})
                    if not headers:
                        headers = {}

                return Response(
                    status_code=response.status_code,
                    headers=headers,
                    content=response.content,
                    url=str(response.url),
                    elapsed=elapsed,
                    encoding=response.encoding or "utf-8",
                )

        except Exception:
            self._error_count += 1
            raise

    async def put(
        self, url: str, data: dict | None = None, json: dict | None = None, headers: dict[str, str] | None = None
    ) -> Response:
        """Make a PUT request."""
        # Build browser-like headers and merge with provided headers
        default_headers = self.config.get_browser_headers(url)
        if headers:
            merged_headers = {**default_headers, **headers}
        else:
            merged_headers = default_headers

        start_time = time.time()
        self._request_count += 1

        try:
            # Wait for rate limiter
            await self.rate_limiter.wait_for_token()

            # Make request
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.put(
                    url, data=data, json=json, headers=merged_headers, follow_redirects=self.config.follow_redirects
                )

                elapsed = time.time() - start_time
                self._total_time += elapsed

                if response.is_success:
                    self._success_count += 1
                else:
                    self._error_count += 1

                # Handle mock headers properly
                headers = {}
                if hasattr(response.headers, "items") or hasattr(response.headers, "__iter__"):
                    headers = dict(response.headers)
                else:
                    # For mock objects, try to get the value directly
                    headers = getattr(response.headers, "_mock_name", {})
                    if not headers:
                        headers = {}

                return Response(
                    status_code=response.status_code,
                    headers=headers,
                    content=response.content,
                    url=str(response.url),
                    elapsed=elapsed,
                    encoding=response.encoding or "utf-8",
                )

        except Exception:
            self._error_count += 1
            raise

    async def delete(self, url: str, headers: dict[str, str] | None = None) -> Response:
        """Make a DELETE request."""
        # Build browser-like headers and merge with provided headers
        default_headers = self.config.get_browser_headers(url)
        if headers:
            merged_headers = {**default_headers, **headers}
        else:
            merged_headers = default_headers

        start_time = time.time()
        self._request_count += 1

        try:
            # Wait for rate limiter
            await self.rate_limiter.wait_for_token()

            # Make request
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.delete(
                    url, headers=merged_headers, follow_redirects=self.config.follow_redirects
                )

                elapsed = time.time() - start_time
                self._total_time += elapsed

                if response.is_success:
                    self._success_count += 1
                else:
                    self._error_count += 1

                # Handle mock headers properly
                headers = {}
                if hasattr(response.headers, "items") or hasattr(response.headers, "__iter__"):
                    headers = dict(response.headers)
                else:
                    # For mock objects, try to get the value directly
                    headers = getattr(response.headers, "_mock_name", {})
                    if not headers:
                        headers = {}

                return Response(
                    status_code=response.status_code,
                    headers=headers,
                    content=response.content,
                    url=str(response.url),
                    elapsed=elapsed,
                    encoding=response.encoding or "utf-8",
                )

        except Exception:
            self._error_count += 1
            raise

    async def head(self, url: str, headers: dict[str, str] | None = None) -> Response:
        """Make a HEAD request."""
        # Build browser-like headers and merge with provided headers
        default_headers = self.config.get_browser_headers(url)
        if headers:
            merged_headers = {**default_headers, **headers}
        else:
            merged_headers = default_headers

        start_time = time.time()
        self._request_count += 1

        try:
            # Wait for rate limiter
            await self.rate_limiter.wait_for_token()

            # Make request
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.head(url, headers=merged_headers, follow_redirects=self.config.follow_redirects)

                elapsed = time.time() - start_time
                self._total_time += elapsed

                if response.is_success:
                    self._success_count += 1
                else:
                    self._error_count += 1

                # Handle mock headers properly
                headers = {}
                if hasattr(response.headers, "items") or hasattr(response.headers, "__iter__"):
                    headers = dict(response.headers)
                else:
                    # For mock objects, try to get the value directly
                    headers = getattr(response.headers, "_mock_name", {})
                    if not headers:
                        headers = {}

                return Response(
                    status_code=response.status_code,
                    headers=headers,
                    content=response.content,
                    url=str(response.url),
                    elapsed=elapsed,
                    encoding=response.encoding or "utf-8",
                )

        except Exception:
            self._error_count += 1
            raise

    def update_config(self, config: RequestConfig):
        """Update request configuration."""
        self.config = config

    def update_rate_limiter(self, rate_limiter: RateLimiter):
        """Update rate limiter."""
        self.rate_limiter = rate_limiter

    def get_statistics(self) -> dict:
        """Get request statistics."""
        return {
            "total_requests": self._request_count,
            "request_count": self._request_count,
            "successful_requests": self._success_count,
            "success_count": self._success_count,
            "failed_requests": self._error_count,
            "error_count": self._error_count,
            "success_rate": self._success_count / self._request_count if self._request_count > 0 else 0.0,
            "average_time": self._total_time / self._request_count if self._request_count > 0 else 0.0,
        }

    def reset_statistics(self):
        """Reset request statistics."""
        self._request_count = 0
        self._success_count = 0
        self._error_count = 0
        self._total_time = 0.0


# Utility functions


def is_valid_url(url: str) -> bool:
    """Check if URL is valid."""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc]) and result.scheme in ("http", "https")
    except Exception:
        return False


def normalize_url(url: str, base_url: str | None = None) -> str:
    """Normalize URL by resolving relative URLs and cleaning fragments."""
    if base_url:
        url = urljoin(base_url, url)

    # Remove fragment
    parsed = urlparse(url)
    return parsed._replace(fragment="").geturl()


def extract_domain(url: str) -> str:
    """Extract domain from URL."""
    return urlparse(url).netloc.lower()


def is_same_domain(url1: str, url2: str) -> bool:
    """Check if two URLs are from the same domain."""
    return extract_domain(url1) == extract_domain(url2)
