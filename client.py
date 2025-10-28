"""
httpx Best Practices for Production Environments

This module provides production-ready HTTP clients with:
- Connection pooling via client reuse
- Exponential backoff with jitter for retries
- Retry logic for transient errors (5xx, 429, network errors)
- Retry-After header support for rate limiting
- Configurable timeouts and retry limits
- Comprehensive error handling and logging
- Both sync (SyncProductionHTTPClient) and async (AsyncProductionHTTPClient) variants
"""

import asyncio
import logging
import random
import time
from typing import Optional

import httpx
import pendulum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

RETRIABLE_STATUS_CODES = {
    104: "Connection Reset",
    408: "Request Timeout",
    429: "Too Many Requests (rate limited)",
    500: "Internal Server Error",
    502: "Bad Gateway",
    503: "Service Unavailable",
    504: "Gateway Timeout",
}


def _parse_retry_after(retry_after_header: Optional[str]) -> Optional[float]:
    """Parse the Retry-After header value."""
    if not retry_after_header:
        return None

    try:
        seconds = int(retry_after_header.strip())
        return float(seconds)
    except ValueError:
        try:
            retry_date = pendulum.parse(retry_after_header.strip())
            now = pendulum.now()
            seconds = (retry_date - now).total_seconds()
            # If date is in the past or invalid, fall back to None
            if seconds <= 0:
                return None
            return seconds
        except Exception:
            logger.warning(f"Could not parse Retry-After header: {retry_after_header}")
            return None


def _calculate_backoff(attempt: int) -> float:
    """Calculate exponential backoff delay with jitter."""
    return random.uniform(0.8, 1.0) * (2**attempt)


def _calculate_backoff_for_response(status_code: int, headers, attempt: int) -> float:
    """Calculate backoff delay for a response with retry logic."""
    if status_code == 429:
        retry_after = _parse_retry_after(headers.get("Retry-After"))
        if retry_after is not None:
            return retry_after

    return _calculate_backoff(attempt)


class SyncProductionHTTPClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        request_timeout: float = 10.0,
        max_retries: int = 4,  # 4 retries = 5 attempts
        default_headers: Optional[dict] = None,
    ):
        self.base_url = base_url
        self.request_timeout = request_timeout
        self.max_retries = max_retries

        # Configure timeout: 5s to connect, request_timeout for read/write
        httpx_timeout = httpx.Timeout(
            request_timeout, connect=min(request_timeout / 2, 5.0)
        )

        self.client = httpx.Client(
            base_url=base_url,
            timeout=httpx_timeout,
            headers=default_headers,
            limits=httpx.Limits(
                max_keepalive_connections=20,
                max_connections=50,
                keepalive_expiry=30.0,
            ),
            http2=True,
        )

    def close(self):
        """Clean up the client and close all connections."""
        self.client.close()

    def __enter__(self):
        """Sync context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Sync context manager exit."""
        self.close()

    def request_with_retry(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Make an HTTP request with automatic retry for transient errors."""
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.request(method, url, **kwargs)

                if response.status_code in RETRIABLE_STATUS_CODES:
                    if attempt < self.max_retries:
                        error_desc = RETRIABLE_STATUS_CODES[response.status_code]
                        backoff = _calculate_backoff_for_response(
                            response.status_code, response.headers, attempt
                        )
                        logger.warning(
                            f"{error_desc} on {method} {url}, retrying in {backoff:.2f}s (attempt {attempt + 1}/{self.max_retries})"
                        )
                        time.sleep(backoff)
                        continue
                    else:
                        response.raise_for_status()

                elif 400 <= response.status_code < 500:
                    response.raise_for_status()

                return response

            except httpx.TimeoutException as e:
                last_exception = e
                if attempt < self.max_retries:
                    backoff = _calculate_backoff(attempt)
                    logger.warning(
                        f"Timeout on {method} {url}, retrying in {backoff:.2f}s (attempt {attempt + 1}/{self.max_retries})"
                    )
                    time.sleep(backoff)
                else:
                    raise

            except httpx.NetworkError as e:
                last_exception = e
                if attempt < self.max_retries:
                    backoff = _calculate_backoff(attempt)
                    logger.warning(
                        f"Network error on {method} {url}, retrying in {backoff:.2f}s (attempt {attempt + 1}/{self.max_retries})"
                    )
                    time.sleep(backoff)
                else:
                    raise

        if last_exception:
            raise last_exception
        raise RuntimeError("Unexpected error in request_with_retry")

    def get(self, url: str, **kwargs) -> httpx.Response:
        """GET request with retry logic."""
        return self.request_with_retry("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> httpx.Response:
        """POST request with retry logic."""
        return self.request_with_retry("POST", url, **kwargs)

    def put(self, url: str, **kwargs) -> httpx.Response:
        """PUT request with retry logic."""
        return self.request_with_retry("PUT", url, **kwargs)

    def delete(self, url: str, **kwargs) -> httpx.Response:
        """DELETE request with retry logic."""
        return self.request_with_retry("DELETE", url, **kwargs)


class AsyncProductionHTTPClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        request_timeout: float = 10.0,
        max_retries: int = 4,  # 4 retries = 5 attempts
        default_headers: Optional[dict] = None,
    ):
        self.base_url = base_url
        self.request_timeout = request_timeout
        self.max_retries = max_retries

        # Configure timeout: 5s to connect, request_timeout for read/write
        httpx_timeout = httpx.Timeout(
            request_timeout, connect=min(request_timeout / 2, 5.0)
        )

        self.client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx_timeout,
            headers=default_headers,
            limits=httpx.Limits(
                max_keepalive_connections=20,  # Keep connections alive
                max_connections=50,  # Max total connections
                keepalive_expiry=30.0,  # Keep connections for 30s
            ),
            http2=True,  # Enable HTTP/2 for better connection reuse
        )

    async def close(self):
        """Clean up the client and close all connections."""
        await self.client.aclose()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def request_with_retry(
        self, method: str, url: str, **kwargs
    ) -> httpx.Response:
        """
        Make an HTTP request with automatic retry for transient errors.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: URL to request
            **kwargs: Additional httpx request arguments

        Returns:
            httpx.Response

        Raises:
            httpx.HTTPStatusError: For non-retriable client errors (4xx except 429)
            httpx.RequestError: For network errors that exceed retry limit
        """
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                response = await self.client.request(method, url, **kwargs)

                if response.status_code in RETRIABLE_STATUS_CODES:
                    if attempt < self.max_retries:
                        error_desc = RETRIABLE_STATUS_CODES[response.status_code]
                        backoff = _calculate_backoff_for_response(
                            response.status_code, response.headers, attempt
                        )
                        logger.warning(
                            f"{error_desc} on {method} {url}, retrying in {backoff:.2f}s (attempt {attempt + 1}/{self.max_retries})"
                        )
                        await asyncio.sleep(backoff)
                        continue
                    else:
                        response.raise_for_status()

                elif 400 <= response.status_code < 500:
                    response.raise_for_status()

                return response

            except httpx.TimeoutException as e:
                last_exception = e
                if attempt < self.max_retries:
                    backoff = _calculate_backoff(attempt)
                    logger.warning(
                        f"Timeout on {method} {url}, retrying in {backoff:.2f}s (attempt {attempt + 1}/{self.max_retries})"
                    )
                    await asyncio.sleep(backoff)
                else:
                    raise

            except httpx.NetworkError as e:
                last_exception = e
                if attempt < self.max_retries:
                    backoff = _calculate_backoff(attempt)
                    logger.warning(
                        f"Network error on {method} {url}, retrying in {backoff:.2f}s (attempt {attempt + 1}/{self.max_retries})"
                    )
                    await asyncio.sleep(backoff)
                else:
                    raise

        if last_exception:
            raise last_exception
        raise RuntimeError("Unexpected error in request_with_retry")

    async def get(self, url: str, **kwargs) -> httpx.Response:
        """GET request with retry logic."""
        return await self.request_with_retry("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> httpx.Response:
        """POST request with retry logic."""
        return await self.request_with_retry("POST", url, **kwargs)

    async def put(self, url: str, **kwargs) -> httpx.Response:
        """PUT request with retry logic."""
        return await self.request_with_retry("PUT", url, **kwargs)

    async def delete(self, url: str, **kwargs) -> httpx.Response:
        """DELETE request with retry logic."""
        return await self.request_with_retry("DELETE", url, **kwargs)
