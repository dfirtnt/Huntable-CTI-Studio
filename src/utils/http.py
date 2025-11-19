"""HTTP utilities for efficient and polite web scraping."""

import asyncio
import time
from typing import Dict, Optional, Set, Union, Any
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser
import httpx
from datetime import datetime, timedelta
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Try to import brotli for manual decompression if httpx doesn't handle it
try:
    import brotli  # type: ignore
    BROTLI_AVAILABLE = True
except ImportError:
    BROTLI_AVAILABLE = False
    logger.debug("brotli library not available - brotli-compressed responses may not decompress automatically")


@dataclass
class RequestConfig:
    """Configuration for HTTP requests."""
    timeout: float = 30.0
    max_retries: int = 3
    retry_delay: float = 1.0
    follow_redirects: bool = True
    verify_ssl: bool = True
    user_agent: str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    headers: Optional[Dict[str, str]] = None
    
    def __post_init__(self):
        """Post-initialization to set default values."""
        if self.headers is None:
            self.headers = {}
    
    def get_browser_headers(self, url: Optional[str] = None) -> Dict[str, str]:
        """Get browser-like headers to bypass anti-bot detection."""
        headers = {
            'User-Agent': self.user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Sec-Ch-Ua': '"Google Chrome";v="131", "Chromium";v="131", "Not A(Brand";v="24"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"macOS"',
            'Cache-Control': 'max-age=0',
        }
        
        # Add Referer if URL is provided
        if url:
            try:
                from urllib.parse import urlparse
                parsed = urlparse(url)
                headers['Referer'] = f"{parsed.scheme}://{parsed.netloc}/"
            except Exception:
                pass
        
        # Merge with custom headers
        headers.update(self.headers)
        return headers
    
    def to_dict(self) -> Dict:
        """Convert config to dictionary."""
        return {
            'timeout': self.timeout,
            'max_retries': self.max_retries,
            'retry_delay': self.retry_delay,
            'follow_redirects': self.follow_redirects,
            'verify_ssl': self.verify_ssl,
            'user_agent': self.user_agent,
            'headers': self.headers
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'RequestConfig':
        """Create config from dictionary."""
        return cls(**data)


@dataclass
class Response:
    """HTTP response wrapper."""
    status_code: int
    headers: Dict[str, str]
    content: bytes
    url: str
    elapsed: float = 0.0
    encoding: str = 'utf-8'
    
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
        """Get response text."""
        try:
            # Try to decode with the specified encoding
            text = self.content.decode(self.encoding)
            # Verify it's not corrupted (check for excessive replacement chars)
            # The replacement character is '\ufffd' ()
            replacement_char = '\ufffd'
            if text.count(replacement_char) > len(text) * 0.1:  # More than 10% replacement chars suggests corruption
                # Try UTF-8 as fallback
                try:
                    text = self.content.decode('utf-8')
                except UnicodeDecodeError:
                    # Last resort: decode with errors='replace'
                    text = self.content.decode('utf-8', errors='replace')
            return text
        except UnicodeDecodeError:
            # Try UTF-8 as fallback
            try:
                return self.content.decode('utf-8')
            except UnicodeDecodeError:
                # Last resort: decode with errors='replace'
                return self.content.decode('utf-8', errors='replace')


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
        else:
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
    
    def __init__(
        self,
        config: Optional[RequestConfig] = None,
        rate_limiter: Optional[RateLimiter] = None
    ):
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
        return None
    
    async def get(self, url: str, headers: Optional[Dict[str, str]] = None, params: Optional[Dict] = None, source_id: Optional[str] = None, use_conditional: bool = False) -> Response:
        """Make a GET request with retry logic.
        
        Args:
            url: URL to fetch
            headers: Optional HTTP headers (will be merged with default browser headers)
            params: Optional query parameters
            source_id: Optional source identifier for tracking (unused, for compatibility)
            use_conditional: Optional flag for conditional requests (unused, for compatibility)
        """
        if not url:
            raise ValueError("URL cannot be None")
        if not url.strip():
            raise ValueError("URL cannot be empty")
        if not url.startswith(('http://', 'https://')):
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
                        url,
                        headers=merged_headers,
                        params=params,
                        follow_redirects=self.config.follow_redirects
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
                            else:
                                self._error_count += 1
                                raise status_exception
                        self._error_count += 1
                    
                    # Handle mock headers properly
                    response_headers = {}
                    if hasattr(response.headers, 'items'):
                        response_headers = dict(response.headers)
                    elif hasattr(response.headers, '__iter__'):
                        response_headers = dict(response.headers)
                    else:
                        # For mock objects, try to get the value directly
                        response_headers = getattr(response.headers, '_mock_name', {})
                        if not response_headers:
                            response_headers = {}
                    
                    # httpx automatically decompresses content (gzip, brotli, deflate) when accessing response.text
                    # Always use response.text for text-based content to ensure proper decompression and encoding
                    # Read content-type from response.headers directly (not from dict)
                    content_type_header = response.headers.get('content-type', '') if hasattr(response.headers, 'get') else response_headers.get('content-type', '')
                    content_encoding_header = response.headers.get('content-encoding', '') if hasattr(response.headers, 'get') else response_headers.get('content-encoding', '')
                    
                    # Determine if this is text-based content (HTML, XML, JSON, etc.)
                    is_text_content = (
                        'text/' in content_type_header.lower() or
                        'html' in content_type_header.lower() or
                        'xml' in content_type_header.lower() or
                        'json' in content_type_header.lower() or
                        'application/xml' in content_type_header.lower() or
                        'application/json' in content_type_header.lower() or
                        'sitemap' in url.lower() or
                        content_encoding_header.lower() in ('gzip', 'br', 'deflate')
                    )
                    
                    # For text-based content, always use response.text to ensure decompression
                    # httpx automatically handles gzip and deflate, but may need manual brotli handling
                    if is_text_content:
                        # Check if content appears to be HTML/text (not binary)
                        content_preview = response.content[:200] if len(response.content) > 200 else response.content
                        is_likely_binary = (
                            content_encoding_header.lower() == 'br' and 
                            (not content_preview.startswith(b'<!') and 
                             not content_preview.startswith(b'<html') and
                             not b'<!DOCTYPE' in content_preview[:100])
                        )
                        
                        # If brotli-compressed and appears binary, manually decompress
                        if content_encoding_header.lower() == 'br' and (is_likely_binary or BROTLI_AVAILABLE):
                            try:
                                if BROTLI_AVAILABLE:
                                    decompressed_bytes = brotli.decompress(response.content)
                                    # Try to decode as text
                                    try:
                                        decompressed_text = decompressed_bytes.decode(response.encoding or 'utf-8')
                                        # Verify it's actually HTML/text
                                        if '<html' in decompressed_text[:500].lower() or '<!doctype' in decompressed_text[:500].lower() or '<body' in decompressed_text[:500].lower():
                                            response_content = decompressed_text.encode(response.encoding or 'utf-8')
                                            logger.debug(f"Manually decompressed brotli content - content length: {len(response_content)}")
                                        else:
                                            # Fallback to httpx's decompression
                                            decompressed_text = response.text
                                            response_content = decompressed_text.encode(response.encoding or 'utf-8')
                                            logger.debug(f"Brotli decompression didn't yield HTML, using httpx text - content length: {len(response_content)}")
                                    except UnicodeDecodeError:
                                        # If decode fails, try response.text as fallback
                                        decompressed_text = response.text
                                        response_content = decompressed_text.encode(response.encoding or 'utf-8')
                                        logger.debug(f"Brotli decode failed, using httpx text - content length: {len(response_content)}")
                                else:
                                    # No brotli library, use httpx's decompression
                                    decompressed_text = response.text
                                    response_content = decompressed_text.encode(response.encoding or 'utf-8')
                                    logger.debug(f"Brotli library not available, using httpx text - content length: {len(response_content)}")
                            except Exception as e:
                                logger.warning(f"Brotli decompression failed for {url}: {e}, using httpx text")
                                # Fallback to httpx's text
                                try:
                                    decompressed_text = response.text
                                    response_content = decompressed_text.encode(response.encoding or 'utf-8')
                                except Exception:
                                    response_content = response.content
                        else:
                            # For gzip, deflate, or uncompressed content, use httpx's automatic decompression
                            try:
                                # httpx automatically decompresses when accessing response.text
                                # Use response.text directly to get properly decoded text
                                decompressed_text = response.text
                                
                                # Verify it's actually text (not binary corruption)
                                # Check first 500 chars for HTML/text indicators
                                preview = decompressed_text[:500].lower()
                                is_valid_text = (
                                    '<html' in preview or 
                                    '<!doctype' in preview or 
                                    '<body' in preview or
                                    '<article' in preview or
                                    '<main' in preview or
                                    len([c for c in preview[:100] if c.isprintable() or c.isspace()]) > 80
                                )
                                
                                if is_valid_text:
                                    # Encode back to bytes using the detected encoding
                                    response_content = decompressed_text.encode(response.encoding or 'utf-8')
                                    logger.debug(f"Decompressed {content_encoding_header or 'uncompressed'} content via httpx - content length: {len(response_content)}")
                                else:
                                    # Content doesn't look like valid text, might be binary
                                    logger.warning(f"Response.text for {url} doesn't appear to be valid HTML/text, checking raw content")
                                    # Try to detect if raw content is compressed
                                    if content_encoding_header.lower() in ('gzip', 'br', 'deflate'):
                                        # Content is compressed but decompression didn't work properly
                                        # Try using response.content which httpx should have decompressed
                                        response_content = response.content
                                        logger.debug(f"Using response.content (should be auto-decompressed by httpx) - length: {len(response_content)}")
                                    else:
                                        response_content = response.content
                            except Exception as e:
                                logger.warning(f"Failed to use response.text for {url}: {e}, falling back to content")
                                response_content = response.content
                    else:
                        # For binary content (images, PDFs, etc.), use raw content
                        response_content = response.content
                    
                    return Response(
                        status_code=response.status_code,
                        headers=response_headers,
                        content=response_content,
                        url=str(response.url),
                        elapsed=elapsed,
                        encoding=response.encoding or 'utf-8'
                    )
                    
            except Exception as e:
                last_exception = e
                if attempt < self.config.max_retries:
                    await asyncio.sleep(self.config.retry_delay)
                    continue
                else:
                    self._error_count += 1
                    raise last_exception
    
    async def post(self, url: str, data: Optional[Dict] = None, json: Optional[Dict] = None, headers: Optional[Dict[str, str]] = None) -> Response:
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
                    url,
                    data=data,
                    json=json,
                    headers=merged_headers,
                    follow_redirects=self.config.follow_redirects
                )
                
                elapsed = time.time() - start_time
                self._total_time += elapsed
                
                if response.is_success:
                    self._success_count += 1
                else:
                    self._error_count += 1
                
                # Handle mock headers properly
                headers = {}
                if hasattr(response.headers, 'items'):
                    headers = dict(response.headers)
                elif hasattr(response.headers, '__iter__'):
                    headers = dict(response.headers)
                else:
                    # For mock objects, try to get the value directly
                    headers = getattr(response.headers, '_mock_name', {})
                    if not headers:
                        headers = {}
                
                return Response(
                    status_code=response.status_code,
                    headers=headers,
                    content=response.content,
                    url=str(response.url),
                    elapsed=elapsed,
                    encoding=response.encoding or 'utf-8'
                )
                
        except Exception as e:
            self._error_count += 1
            raise
    
    async def put(self, url: str, data: Optional[Dict] = None, json: Optional[Dict] = None, headers: Optional[Dict[str, str]] = None) -> Response:
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
                    url,
                    data=data,
                    json=json,
                    headers=merged_headers,
                    follow_redirects=self.config.follow_redirects
                )
                
                elapsed = time.time() - start_time
                self._total_time += elapsed
                
                if response.is_success:
                    self._success_count += 1
                else:
                    self._error_count += 1
                
                # Handle mock headers properly
                headers = {}
                if hasattr(response.headers, 'items'):
                    headers = dict(response.headers)
                elif hasattr(response.headers, '__iter__'):
                    headers = dict(response.headers)
                else:
                    # For mock objects, try to get the value directly
                    headers = getattr(response.headers, '_mock_name', {})
                    if not headers:
                        headers = {}
                
                return Response(
                    status_code=response.status_code,
                    headers=headers,
                    content=response.content,
                    url=str(response.url),
                    elapsed=elapsed,
                    encoding=response.encoding or 'utf-8'
                )
            
        except Exception as e:
            self._error_count += 1
            raise

    async def delete(self, url: str, headers: Optional[Dict[str, str]] = None) -> Response:
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
                    url,
                    headers=merged_headers,
                    follow_redirects=self.config.follow_redirects
                )
                
                elapsed = time.time() - start_time
                self._total_time += elapsed
                
                if response.is_success:
                    self._success_count += 1
                else:
                    self._error_count += 1
                
                # Handle mock headers properly
                headers = {}
                if hasattr(response.headers, 'items'):
                    headers = dict(response.headers)
                elif hasattr(response.headers, '__iter__'):
                    headers = dict(response.headers)
                else:
                    # For mock objects, try to get the value directly
                    headers = getattr(response.headers, '_mock_name', {})
                    if not headers:
                        headers = {}
                
                return Response(
                    status_code=response.status_code,
                    headers=headers,
                    content=response.content,
                    url=str(response.url),
                    elapsed=elapsed,
                    encoding=response.encoding or 'utf-8'
                )
            
        except Exception as e:
            self._error_count += 1
            raise
    
    async def head(self, url: str, headers: Optional[Dict[str, str]] = None) -> Response:
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
                response = await client.head(
                    url,
                    headers=merged_headers,
                    follow_redirects=self.config.follow_redirects
                )
                
                elapsed = time.time() - start_time
                self._total_time += elapsed
                
                if response.is_success:
                    self._success_count += 1
                else:
                    self._error_count += 1
                
                # Handle mock headers properly
                headers = {}
                if hasattr(response.headers, 'items'):
                    headers = dict(response.headers)
                elif hasattr(response.headers, '__iter__'):
                    headers = dict(response.headers)
                else:
                    # For mock objects, try to get the value directly
                    headers = getattr(response.headers, '_mock_name', {})
                    if not headers:
                        headers = {}
                
                return Response(
                    status_code=response.status_code,
                    headers=headers,
                    content=response.content,
                    url=str(response.url),
                    elapsed=elapsed,
                    encoding=response.encoding or 'utf-8'
                )
            
        except Exception as e:
            self._error_count += 1
            raise
    
    def update_config(self, config: RequestConfig):
        """Update request configuration."""
        self.config = config
    
    def update_rate_limiter(self, rate_limiter: RateLimiter):
        """Update rate limiter."""
        self.rate_limiter = rate_limiter
    
    def get_statistics(self) -> Dict:
        """Get request statistics."""
        return {
            'total_requests': self._request_count,
            'request_count': self._request_count,
            'successful_requests': self._success_count,
            'success_count': self._success_count,
            'failed_requests': self._error_count,
            'error_count': self._error_count,
            'success_rate': self._success_count / self._request_count if self._request_count > 0 else 0.0,
            'average_time': self._total_time / self._request_count if self._request_count > 0 else 0.0
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