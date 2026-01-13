"""Notion API client with mandatory 3 req/sec rate limiting.

This module provides a rate-limited, retry-enabled client for interacting with
the Notion API. It implements:
- Global 3 requests per second rate limit via AsyncLimiter (Notion API requirement)
- Automatic retry with exponential backoff for transient errors (429, 5xx, timeouts)
- Proper error classification (retriable vs non-retriable)
- Clean async/await patterns for all operations

Usage:
    client = NotionClient(auth_token)
    result = await client.update_task_status(page_id, "In Progress")
"""

import asyncio
from typing import Any

import httpx
from aiolimiter import AsyncLimiter


class NotionAPIError(Exception):
    """Raised for non-retriable Notion API errors (401, 403, 400)."""

    def __init__(self, message: str, response: httpx.Response):
        self.message = message
        self.status_code = response.status_code
        self.response_body = response.text
        super().__init__(f"{message} - Status: {response.status_code}")


class NotionRateLimitError(Exception):
    """Raised when Notion API rate limit persists after all retries."""

    def __init__(self, message: str, retry_count: int, last_error: Exception):
        self.message = message
        self.retry_count = retry_count
        self.last_error = last_error
        super().__init__(f"{message} (retries: {retry_count}, last error: {last_error})")


class NotionClient:
    """Notion API client with mandatory 3 req/sec rate limiting.

    Implements:
    - Global 3 requests per second rate limit via AsyncLimiter
    - Automatic retry with exponential backoff for transient errors
    - Proper error classification (retriable vs non-retriable)

    Usage:
        client = NotionClient(auth_token)
        result = await client.update_task_status(page_id, "In Progress")
    """

    def __init__(self, auth_token: str):
        """Initialize Notion API client with rate limiting.

        Args:
            auth_token: Notion Internal Integration token
        """
        self.auth_token = auth_token
        self.client = httpx.AsyncClient(timeout=30.0)
        # CRITICAL: 3 requests per 1 second (Notion API hard limit)
        self.rate_limiter = AsyncLimiter(max_rate=3, time_period=1)
        self.base_url = "https://api.notion.com/v1"
        self.notion_version = "2025-09-03"

    def _get_headers(self) -> dict[str, str]:
        """Get standard Notion API headers.

        Returns:
            Dictionary of HTTP headers for Notion API requests
        """
        return {
            "Authorization": f"Bearer {self.auth_token}",
            "Notion-Version": self.notion_version,
            "Content-Type": "application/json",
        }

    def _is_retriable_error(self, exception: Exception) -> bool:
        """Determine if an error should trigger retry logic.

        Args:
            exception: Exception to classify

        Returns:
            True if error is retriable (429, 5xx, timeouts), False otherwise
        """
        if isinstance(exception, httpx.HTTPStatusError):
            # Retry server errors and rate limits
            return exception.response.status_code in [429, 500, 502, 503, 504]
        # Retry network errors
        return isinstance(exception, (httpx.TimeoutException, httpx.ConnectError))

    async def update_task_status(self, page_id: str, status: str) -> dict[str, Any]:
        """Update task status in Notion database (rate limited, auto-retry).

        Args:
            page_id: Notion page ID (32 chars, no dashes)
            status: New status value (must match database schema)

        Returns:
            Updated page object from Notion API

        Raises:
            NotionRateLimitError: After 3 failed retry attempts
            NotionAPIError: On non-retriable errors (401, 403, 400)
        """
        attempt_count = 0
        last_error: Exception | None = None

        for attempt in range(3):
            attempt_count = attempt + 1
            try:
                async with self.rate_limiter:  # Enforce 3 req/sec limit
                    response = await self.client.patch(
                        f"{self.base_url}/pages/{page_id}",
                        headers=self._get_headers(),
                        json={"properties": {"Status": {"status": {"name": status}}}},
                    )

                    # Check for Retry-After header on 429
                    if response.status_code == 429:
                        await self._handle_retry_after(response)

                    # Classify error type for retry logic
                    if response.status_code in [401, 403, 400]:
                        # Non-retriable: Fail fast
                        raise NotionAPIError(
                            f"Non-retriable error: {response.status_code}", response
                        )

                    response.raise_for_status()  # Raises HTTPStatusError for 4xx/5xx
                    return response.json()  # type: ignore[no-any-return]

            except httpx.HTTPStatusError as e:
                last_error = e
                if not self._is_retriable_error(e):
                    raise
                # Wait with exponential backoff before retry
                if attempt < 2:  # Don't wait after last attempt
                    wait_time = 2**attempt  # 2s, 4s
                    await asyncio.sleep(wait_time)
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_error = e
                if attempt < 2:  # Don't wait after last attempt
                    wait_time = 2**attempt
                    await asyncio.sleep(wait_time)

        # All retries exhausted
        raise NotionRateLimitError(
            "Notion API rate limit exceeded after retries",
            attempt_count,
            last_error or Exception("Unknown error"),
        )

    async def get_database_pages(self, database_id: str) -> list[dict[str, Any]]:
        """Get all pages from Notion database (rate limited, auto-retry).

        Args:
            database_id: Notion database ID (32 chars, no dashes)

        Returns:
            List of page objects from Notion database

        Raises:
            NotionRateLimitError: After 3 failed retry attempts
            NotionAPIError: On non-retriable errors (401, 403, 400)
        """
        attempt_count = 0
        last_error: Exception | None = None

        for attempt in range(3):
            attempt_count = attempt + 1
            try:
                async with self.rate_limiter:  # Enforce 3 req/sec limit
                    response = await self.client.post(
                        f"{self.base_url}/databases/{database_id}/query",
                        headers=self._get_headers(),
                        json={},
                    )

                    # Check for Retry-After header on 429
                    if response.status_code == 429:
                        await self._handle_retry_after(response)

                    # Classify error type for retry logic
                    if response.status_code in [401, 403, 400]:
                        # Non-retriable: Fail fast
                        raise NotionAPIError(
                            f"Non-retriable error: {response.status_code}", response
                        )

                    response.raise_for_status()
                    return response.json()["results"]  # type: ignore[no-any-return]

            except httpx.HTTPStatusError as e:
                last_error = e
                if not self._is_retriable_error(e):
                    raise
                if attempt < 2:
                    wait_time = 2**attempt
                    await asyncio.sleep(wait_time)
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_error = e
                if attempt < 2:
                    wait_time = 2**attempt
                    await asyncio.sleep(wait_time)

        # All retries exhausted
        raise NotionRateLimitError(
            "Notion API rate limit exceeded after retries",
            attempt_count,
            last_error or Exception("Unknown error"),
        )

    async def update_page_properties(
        self, page_id: str, properties: dict[str, Any]
    ) -> dict[str, Any]:
        """Update multiple page properties (rate limited, auto-retry).

        Args:
            page_id: Notion page ID (32 chars, no dashes)
            properties: Dictionary of properties to update

        Returns:
            Updated page object from Notion API

        Raises:
            NotionRateLimitError: After 3 failed retry attempts
            NotionAPIError: On non-retriable errors (401, 403, 400)
        """
        attempt_count = 0
        last_error: Exception | None = None

        for attempt in range(3):
            attempt_count = attempt + 1
            try:
                async with self.rate_limiter:  # Enforce 3 req/sec limit
                    response = await self.client.patch(
                        f"{self.base_url}/pages/{page_id}",
                        headers=self._get_headers(),
                        json={"properties": properties},
                    )

                    # Check for Retry-After header on 429
                    if response.status_code == 429:
                        await self._handle_retry_after(response)

                    # Classify error type for retry logic
                    if response.status_code in [401, 403, 400]:
                        # Non-retriable: Fail fast
                        raise NotionAPIError(
                            f"Non-retriable error: {response.status_code}", response
                        )

                    response.raise_for_status()
                    return response.json()  # type: ignore[no-any-return]

            except httpx.HTTPStatusError as e:
                last_error = e
                if not self._is_retriable_error(e):
                    raise
                if attempt < 2:
                    wait_time = 2**attempt
                    await asyncio.sleep(wait_time)
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_error = e
                if attempt < 2:
                    wait_time = 2**attempt
                    await asyncio.sleep(wait_time)

        # All retries exhausted
        raise NotionRateLimitError(
            "Notion API rate limit exceeded after retries",
            attempt_count,
            last_error or Exception("Unknown error"),
        )

    async def get_page(self, page_id: str) -> dict[str, Any]:
        """Retrieve single page details (rate limited, auto-retry).

        Args:
            page_id: Notion page ID (32 chars, no dashes)

        Returns:
            Page object from Notion API

        Raises:
            NotionRateLimitError: After 3 failed retry attempts
            NotionAPIError: On non-retriable errors (401, 403, 400)
        """
        attempt_count = 0
        last_error: Exception | None = None

        for attempt in range(3):
            attempt_count = attempt + 1
            try:
                async with self.rate_limiter:  # Enforce 3 req/sec limit
                    response = await self.client.get(
                        f"{self.base_url}/pages/{page_id}",
                        headers=self._get_headers(),
                    )

                    # Check for Retry-After header on 429
                    if response.status_code == 429:
                        await self._handle_retry_after(response)

                    # Classify error type for retry logic
                    if response.status_code in [401, 403, 400]:
                        # Non-retriable: Fail fast
                        raise NotionAPIError(
                            f"Non-retriable error: {response.status_code}", response
                        )

                    response.raise_for_status()
                    return response.json()  # type: ignore[no-any-return]

            except httpx.HTTPStatusError as e:
                last_error = e
                if not self._is_retriable_error(e):
                    raise
                if attempt < 2:
                    wait_time = 2**attempt
                    await asyncio.sleep(wait_time)
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_error = e
                if attempt < 2:
                    wait_time = 2**attempt
                    await asyncio.sleep(wait_time)

        # All retries exhausted
        raise NotionRateLimitError(
            "Notion API rate limit exceeded after retries",
            attempt_count,
            last_error or Exception("Unknown error"),
        )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self.client.aclose()

    async def __aenter__(self) -> "NotionClient":
        """Enter async context manager."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit async context manager."""
        await self.close()

    async def _handle_retry_after(self, response: httpx.Response) -> None:
        """Handle Retry-After header for 429 responses.

        Args:
            response: HTTP response that may contain Retry-After header
        """
        if response.status_code == 429 and "Retry-After" in response.headers:
            retry_after = float(response.headers["Retry-After"])
            await asyncio.sleep(retry_after)
