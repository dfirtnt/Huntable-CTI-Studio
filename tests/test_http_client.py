"""Tests for HTTP client functionality."""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
from typing import List, Dict, Any, Optional

from src.utils.http import HTTPClient, RateLimiter, RequestConfig, Response


class TestRateLimiter:
    """Test RateLimiter functionality."""

    @pytest.fixture
    def rate_limiter(self):
        """Create RateLimiter instance for testing."""
        return RateLimiter(requests_per_second=2, burst_size=10)

    def test_init(self, rate_limiter):
        """Test RateLimiter initialization."""
        assert rate_limiter.requests_per_second == 2
        assert rate_limiter.burst_size == 10
        assert rate_limiter.tokens == 10  # Initial burst size

    def test_init_default_values(self):
        """Test RateLimiter initialization with default values."""
        limiter = RateLimiter()
        
        assert limiter.requests_per_second == 1
        assert limiter.burst_size == 10
        assert limiter.tokens == 10

    def test_acquire_token_success(self, rate_limiter):
        """Test successful token acquisition."""
        result = rate_limiter.acquire_token()
        
        assert result is True
        assert rate_limiter.tokens == 9  # One token consumed

    def test_acquire_token_failure(self, rate_limiter):
        """Test token acquisition failure when no tokens available."""
        # Consume all tokens
        for _ in range(10):
            rate_limiter.acquire_token()
        
        # Try to acquire one more token
        result = rate_limiter.acquire_token()
        
        assert result is False
        # Tokens may be slightly above 0 due to time-based refill
        assert rate_limiter.tokens < 1

    def test_refill_tokens(self, rate_limiter):
        """Test token refill mechanism."""
        # Consume all tokens
        for _ in range(10):
            rate_limiter.acquire_token()
        
        # Tokens may be slightly above 0 due to time-based refill
        assert rate_limiter.tokens < 1
        
        # Refill tokens (simulate time passing)
        rate_limiter.refill_tokens()
        
        # Should have refilled based on time elapsed
        assert rate_limiter.tokens > 0

    @pytest.mark.asyncio
    async def test_wait_for_token(self, rate_limiter):
        """Test waiting for token availability."""
        # Consume all tokens
        for _ in range(10):
            rate_limiter.acquire_token()
        
        # Wait for token (should refill and acquire)
        result = await rate_limiter.wait_for_token()
        
        assert result is True
        assert rate_limiter.tokens >= 0

    def test_rate_limiter_performance(self, rate_limiter):
        """Test rate limiter performance."""
        import time
        
        start_time = time.time()
        
        # Acquire multiple tokens
        for _ in range(10):
            rate_limiter.acquire_token()
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # Should process quickly
        assert processing_time < 0.1  # Less than 100ms
        assert processing_time > 0.0


class TestRequestConfig:
    """Test RequestConfig functionality."""

    def test_init_default_config(self):
        """Test RequestConfig initialization with default values."""
        config = RequestConfig()
        
        assert config.timeout == 30
        assert config.max_retries == 3
        assert config.retry_delay == 1.0
        assert config.follow_redirects is True
        assert config.verify_ssl is True
        assert config.user_agent is not None
        assert config.headers == {}

    def test_init_custom_config(self):
        """Test RequestConfig initialization with custom values."""
        config = RequestConfig(
            timeout=60,
            max_retries=5,
            retry_delay=2.0,
            follow_redirects=False,
            verify_ssl=False,
            user_agent="Custom Agent",
            headers={"Authorization": "Bearer token"}
        )
        
        assert config.timeout == 60
        assert config.max_retries == 5
        assert config.retry_delay == 2.0
        assert config.follow_redirects is False
        assert config.verify_ssl is False
        assert config.user_agent == "Custom Agent"
        assert config.headers == {"Authorization": "Bearer token"}

    def test_to_dict(self):
        """Test converting config to dictionary."""
        config = RequestConfig(
            timeout=45,
            max_retries=4,
            user_agent="Test Agent"
        )
        
        config_dict = config.to_dict()
        
        assert isinstance(config_dict, dict)
        assert config_dict['timeout'] == 45
        assert config_dict['max_retries'] == 4
        assert config_dict['user_agent'] == "Test Agent"

    def test_from_dict(self):
        """Test creating config from dictionary."""
        config_dict = {
            'timeout': 45,
            'max_retries': 4,
            'retry_delay': 1.5,
            'follow_redirects': False,
            'user_agent': 'Test Agent'
        }
        
        config = RequestConfig.from_dict(config_dict)
        
        assert config.timeout == 45
        assert config.max_retries == 4
        assert config.retry_delay == 1.5
        assert config.follow_redirects is False
        assert config.user_agent == 'Test Agent'


class TestResponse:
    """Test Response functionality."""

    def test_init(self):
        """Test Response initialization."""
        response = Response(
            status_code=200,
            content="Test content",
            headers={"Content-Type": "text/html"},
            url="https://example.com",
            encoding="utf-8"
        )
        
        assert response.status_code == 200
        assert response.content == "Test content"
        assert response.headers == {"Content-Type": "text/html"}
        assert response.url == "https://example.com"
        assert response.encoding == "utf-8"

    def test_is_success(self):
        """Test success status check."""
        # Success response
        response = Response(status_code=200, content="", headers={}, url="", encoding="")
        assert response.is_success() is True
        
        # Error response
        response = Response(status_code=404, content="", headers={}, url="", encoding="")
        assert response.is_success() is False

    def test_is_redirect(self):
        """Test redirect status check."""
        # Redirect response
        response = Response(status_code=301, content="", headers={}, url="", encoding="")
        assert response.is_redirect() is True
        
        # Non-redirect response
        response = Response(status_code=200, content="", headers={}, url="", encoding="")
        assert response.is_redirect() is False

    def test_is_client_error(self):
        """Test client error status check."""
        # Client error response
        response = Response(status_code=400, content="", headers={}, url="", encoding="")
        assert response.is_client_error() is True
        
        # Non-client error response
        response = Response(status_code=200, content="", headers={}, url="", encoding="")
        assert response.is_client_error() is False

    def test_is_server_error(self):
        """Test server error status check."""
        # Server error response
        response = Response(status_code=500, content="", headers={}, url="", encoding="")
        assert response.is_server_error() is True
        
        # Non-server error response
        response = Response(status_code=200, content="", headers={}, url="", encoding="")
        assert response.is_server_error() is False

    def test_raise_for_status_success(self):
        """Test raise_for_status with success response."""
        response = Response(status_code=200, content="", headers={}, url="", encoding="")
        
        # Should not raise exception
        response.raise_for_status()

    def test_raise_for_status_error(self):
        """Test raise_for_status with error response."""
        response = Response(status_code=404, content="", headers={}, url="", encoding="")
        
        # Should raise exception
        with pytest.raises(Exception):
            response.raise_for_status()


class TestHTTPClient:
    """Test HTTPClient functionality."""

    @pytest.fixture
    def http_client(self):
        """Create HTTPClient instance for testing."""
        return HTTPClient()

    @pytest.fixture
    def mock_response(self):
        """Create mock HTTP response for testing."""
        response = Mock()
        response.status_code = 200
        response.text = "Test content"
        response.content = b"Test content"
        response.headers = {"Content-Type": "text/html"}
        response.url = "https://example.com"
        response.encoding = "utf-8"
        response.raise_for_status = Mock()
        return response

    def test_init(self, http_client):
        """Test HTTPClient initialization."""
        assert http_client is not None
        assert hasattr(http_client, 'get')
        assert hasattr(http_client, 'post')
        assert hasattr(http_client, 'put')
        assert hasattr(http_client, 'delete')
        assert hasattr(http_client, 'head')

    def test_init_with_config(self):
        """Test HTTPClient initialization with config."""
        config = RequestConfig(timeout=60, max_retries=5)
        client = HTTPClient(config=config)
        
        assert client.config == config
        assert client.config.timeout == 60
        assert client.config.max_retries == 5

    def test_init_with_rate_limiter(self):
        """Test HTTPClient initialization with rate limiter."""
        rate_limiter = RateLimiter(requests_per_second=2)
        client = HTTPClient(rate_limiter=rate_limiter)
        
        assert client.rate_limiter == rate_limiter

    @pytest.mark.asyncio
    async def test_get_success(self, http_client, mock_response):
        """Test successful GET request."""
        with patch('httpx.AsyncClient.get', return_value=mock_response):
            response = await http_client.get("https://example.com")
            
            assert response.status_code == 200
            assert response.content == b"Test content"
            assert response.url == "https://example.com"

    @pytest.mark.asyncio
    async def test_get_with_headers(self, http_client, mock_response):
        """Test GET request with custom headers."""
        headers = {"Authorization": "Bearer token"}
        
        with patch('httpx.AsyncClient.get', return_value=mock_response) as mock_get:
            await http_client.get("https://example.com", headers=headers)
            
            mock_get.assert_called_once()
            call_args = mock_get.call_args
            assert call_args[1]['headers'] == headers

    @pytest.mark.asyncio
    async def test_get_with_params(self, http_client, mock_response):
        """Test GET request with query parameters."""
        params = {"q": "test", "page": 1}
        
        with patch('httpx.AsyncClient.get', return_value=mock_response) as mock_get:
            await http_client.get("https://example.com", params=params)
            
            mock_get.assert_called_once()
            call_args = mock_get.call_args
            assert call_args[1]['params'] == params

    @pytest.mark.asyncio
    async def test_post_success(self, http_client, mock_response):
        """Test successful POST request."""
        data = {"key": "value"}
        
        with patch('httpx.AsyncClient.post', return_value=mock_response) as mock_post:
            response = await http_client.post("https://example.com", data=data)
            
            assert response.status_code == 200
            mock_post.assert_called_once()

    @pytest.mark.asyncio
    async def test_post_with_json(self, http_client, mock_response):
        """Test POST request with JSON data."""
        json_data = {"key": "value"}
        
        with patch('httpx.AsyncClient.post', return_value=mock_response) as mock_post:
            await http_client.post("https://example.com", json=json_data)
            
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert call_args[1]['json'] == json_data

    @pytest.mark.asyncio
    async def test_put_success(self, http_client, mock_response):
        """Test successful PUT request."""
        data = {"key": "value"}
        
        with patch('httpx.AsyncClient.put', return_value=mock_response) as mock_put:
            response = await http_client.put("https://example.com", data=data)
            
            assert response.status_code == 200
            mock_put.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_success(self, http_client, mock_response):
        """Test successful DELETE request."""
        with patch('httpx.AsyncClient.delete', return_value=mock_response) as mock_delete:
            response = await http_client.delete("https://example.com")
            
            assert response.status_code == 200
            mock_delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_head_success(self, http_client, mock_response):
        """Test successful HEAD request."""
        with patch('httpx.AsyncClient.head', return_value=mock_response) as mock_head:
            response = await http_client.head("https://example.com")
            
            assert response.status_code == 200
            mock_head.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_with_retry(self, http_client):
        """Test request with retry mechanism."""
        # Mock response that fails first, then succeeds
        error_response = Mock()
        error_response.status_code = 500
        error_response.content = b"Server error"
        error_response.headers = {"Content-Type": "text/html"}
        error_response.url = "https://example.com"
        error_response.encoding = "utf-8"
        error_response.raise_for_status.side_effect = Exception("Server error")
        
        success_response = Mock()
        success_response.status_code = 200
        success_response.text = "Success"
        success_response.content = b"Success"
        success_response.headers = {"Content-Type": "text/html"}
        success_response.url = "https://example.com"
        success_response.encoding = "utf-8"
        success_response.raise_for_status = Mock()
        
        with patch('httpx.AsyncClient.get', side_effect=[error_response, success_response]):
            response = await http_client.get("https://example.com")
            
            assert response.status_code == 200
            assert response.content == "Success"

    @pytest.mark.asyncio
    async def test_request_with_rate_limiting(self):
        """Test request with rate limiting."""
        rate_limiter = RateLimiter(requests_per_second=1, burst_size=1)
        client = HTTPClient(rate_limiter=rate_limiter)
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "Success"
        mock_response.headers = {}
        mock_response.url = "https://example.com"
        mock_response.encoding = "utf-8"
        mock_response.raise_for_status = Mock()
        
        with patch('httpx.AsyncClient.get', return_value=mock_response):
            # First request should succeed
            response1 = await client.get("https://example.com")
            assert response1.status_code == 200
            
            # Second request should also succeed (rate limiter allows)
            response2 = await client.get("https://example.com")
            assert response2.status_code == 200

    @pytest.mark.asyncio
    async def test_request_timeout(self, http_client):
        """Test request timeout handling."""
        with patch('httpx.AsyncClient.get', side_effect=asyncio.TimeoutError):
            with pytest.raises(asyncio.TimeoutError):
                await http_client.get("https://example.com")

    @pytest.mark.asyncio
    async def test_request_connection_error(self, http_client):
        """Test request connection error handling."""
        with patch('httpx.AsyncClient.get', side_effect=ConnectionError):
            with pytest.raises(ConnectionError):
                await http_client.get("https://example.com")

    def test_update_config(self, http_client):
        """Test updating client configuration."""
        new_config = RequestConfig(timeout=60, max_retries=5)
        
        http_client.update_config(new_config)
        
        assert http_client.config == new_config
        assert http_client.config.timeout == 60
        assert http_client.config.max_retries == 5

    def test_update_rate_limiter(self, http_client):
        """Test updating rate limiter."""
        new_rate_limiter = RateLimiter(requests_per_second=5, burst_size=10)
        
        http_client.update_rate_limiter(new_rate_limiter)
        
        assert http_client.rate_limiter == new_rate_limiter
        assert http_client.rate_limiter.requests_per_second == 5
        assert http_client.rate_limiter.burst_size == 10

    def test_get_statistics(self, http_client):
        """Test getting client statistics."""
        # Make some requests to generate statistics
        http_client._request_count = 10
        http_client._success_count = 8
        http_client._error_count = 2
        
        stats = http_client.get_statistics()
        
        assert 'total_requests' in stats
        assert 'successful_requests' in stats
        assert 'failed_requests' in stats
        assert 'success_rate' in stats
        assert stats['total_requests'] == 10
        assert stats['successful_requests'] == 8
        assert stats['failed_requests'] == 2
        assert stats['success_rate'] == 0.8

    def test_reset_statistics(self, http_client):
        """Test resetting client statistics."""
        # Set some statistics
        http_client._request_count = 10
        http_client._success_count = 8
        http_client._error_count = 2
        
        # Reset statistics
        http_client.reset_statistics()
        
        assert http_client._request_count == 0
        assert http_client._success_count == 0
        assert http_client._error_count == 0

    @pytest.mark.asyncio
    async def test_http_client_performance(self, http_client, mock_response):
        """Test HTTP client performance."""
        import time
        
        with patch('httpx.AsyncClient.get', return_value=mock_response):
            start_time = time.time()
            
            # Make multiple requests
            tasks = []
            for _ in range(10):
                task = http_client.get("https://example.com")
                tasks.append(task)
            
            responses = await asyncio.gather(*tasks)
            
            end_time = time.time()
            processing_time = end_time - start_time
            
            # Should process 10 requests in reasonable time
            assert processing_time < 2.0  # Less than 2 seconds
            assert processing_time > 0.0
            assert len(responses) == 10
            assert all(r.status_code == 200 for r in responses)

    @pytest.mark.asyncio
    async def test_http_client_edge_cases(self, http_client):
        """Test HTTP client edge cases."""
        # Test with None URL
        with pytest.raises(ValueError):
            await http_client.get(None)
        
        # Test with empty URL
        with pytest.raises(ValueError):
            await http_client.get("")
        
        # Test with invalid URL
        with pytest.raises(ValueError):
            await http_client.get("not-a-url")
