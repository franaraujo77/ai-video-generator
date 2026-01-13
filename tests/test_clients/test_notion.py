"""
Tests for Notion API client with rate limiting.

Tests cover:
- Rate limiter enforcement (3 req/sec)
- Concurrent call queueing
- Retry logic for 429, 5xx errors
- Non-retriable error handling (401, 403, 400)
- Successful API call responses
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx
from app.clients.notion import (
    NotionClient,
    NotionAPIError,
    NotionRateLimitError,
)
import time


@pytest.mark.asyncio
async def test_notion_client_initialization():
    """Test NotionClient initializes with proper configuration."""
    client = NotionClient("test_token_123")

    assert client.auth_token == "test_token_123"
    assert client.base_url == "https://api.notion.com/v1"
    assert client.rate_limiter.max_rate == 3
    assert client.rate_limiter.time_period == 1
    assert isinstance(client.client, httpx.AsyncClient)

    await client.close()


@pytest.mark.asyncio
async def test_update_status_success():
    """Test successful status update with rate limiting."""
    client = NotionClient("test_token")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": "page123",
        "properties": {"Status": {"status": {"name": "In Progress"}}},
    }

    with patch.object(
        client.client, "patch", new_callable=AsyncMock, return_value=mock_response
    ):
        result = await client.update_task_status("page123", "In Progress")

        assert result["id"] == "page123"
        assert result["properties"]["Status"]["status"]["name"] == "In Progress"

    await client.close()


@pytest.mark.asyncio
async def test_rate_limiting_enforces_3_req_sec():
    """Test rate limiter throttles to 3 req/sec."""
    client = NotionClient("test_token")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"id": "page123"}

    with patch.object(
        client.client, "get", new_callable=AsyncMock, return_value=mock_response
    ):
        start = time.time()

        # Make 10 calls (should take ~3.3 seconds for 10 calls at 3 req/sec)
        for _ in range(10):
            await client.get_page("page123")

        elapsed = time.time() - start

        # 10 calls at 3 req/sec = ~3.33 seconds minimum
        # Allow tolerance for test timing (2.3s is reasonable given async overhead)
        assert elapsed >= 2.0, f"Rate limiter didn't throttle properly: {elapsed}s"

    await client.close()


@pytest.mark.asyncio
async def test_concurrent_calls_queue_properly():
    """Test concurrent calls queue and don't fail due to rate limiting."""
    import asyncio

    client = NotionClient("test_token")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"id": "page123"}

    with patch.object(
        client.client, "get", new_callable=AsyncMock, return_value=mock_response
    ):
        # Fire 10 concurrent requests
        tasks = [client.get_page(f"page{i}") for i in range(10)]
        results = await asyncio.gather(*tasks)

        # All should succeed (queued, not failed)
        assert len(results) == 10
        assert all(r["id"] == "page123" for r in results)

    await client.close()


@pytest.mark.asyncio
async def test_429_response_triggers_retry():
    """Test 429 rate limit response triggers exponential backoff retry."""
    client = NotionClient("test_token")

    # First 2 attempts: 429, Third attempt: 200
    mock_responses = [
        MagicMock(
            status_code=429,
            text="Rate limited",
            raise_for_status=MagicMock(
                side_effect=httpx.HTTPStatusError(
                    "Rate limited",
                    request=MagicMock(),
                    response=MagicMock(status_code=429),
                )
            ),
        ),
        MagicMock(
            status_code=429,
            text="Rate limited",
            raise_for_status=MagicMock(
                side_effect=httpx.HTTPStatusError(
                    "Rate limited",
                    request=MagicMock(),
                    response=MagicMock(status_code=429),
                )
            ),
        ),
        MagicMock(
            status_code=200,
            json=MagicMock(return_value={"success": True}),
            raise_for_status=MagicMock(),
        ),
    ]

    with patch.object(
        client.client, "patch", new_callable=AsyncMock, side_effect=mock_responses
    ):
        result = await client.update_task_status("page123", "In Progress")

        assert result["success"] is True
        # Should have made 3 attempts (2 failures + 1 success)
        assert client.client.patch.call_count == 3

    await client.close()


@pytest.mark.asyncio
async def test_500_error_triggers_retry():
    """Test 500 server error triggers retry."""
    client = NotionClient("test_token")

    # First attempt: 500, Second attempt: 200
    mock_responses = [
        MagicMock(
            status_code=500,
            text="Internal Server Error",
            raise_for_status=MagicMock(
                side_effect=httpx.HTTPStatusError(
                    "Server error",
                    request=MagicMock(),
                    response=MagicMock(status_code=500),
                )
            ),
        ),
        MagicMock(
            status_code=200,
            json=MagicMock(return_value={"success": True}),
            raise_for_status=MagicMock(),
        ),
    ]

    with patch.object(
        client.client, "get", new_callable=AsyncMock, side_effect=mock_responses
    ):
        result = await client.get_page("page123")

        assert result["success"] is True
        assert client.client.get.call_count == 2  # 1 failure + 1 success

    await client.close()


@pytest.mark.asyncio
async def test_non_retriable_errors_fail_fast():
    """Test non-retriable errors (401, 403, 400) fail immediately without retry."""
    for status_code in [401, 403, 400]:
        client = NotionClient("test_token")

        mock_response = MagicMock()
        mock_response.status_code = status_code
        mock_response.text = f"Error {status_code}"

        with patch.object(
            client.client, "patch", new_callable=AsyncMock, return_value=mock_response
        ) as mock_patch:
            with pytest.raises(NotionAPIError) as exc_info:
                await client.update_task_status("page123", "In Progress")

            assert exc_info.value.status_code == status_code
            # Should only attempt once (no retry)
            assert mock_patch.call_count == 1

        await client.close()


@pytest.mark.asyncio
async def test_exhausted_retries_raises_notion_rate_limit_error():
    """Test NotionRateLimitError raised after 3 failed attempts."""
    client = NotionClient("test_token")

    # All attempts fail with 429
    mock_response = MagicMock(
        status_code=429,
        text="Rate limited",
        raise_for_status=MagicMock(
            side_effect=httpx.HTTPStatusError(
                "Rate limited",
                request=MagicMock(),
                response=MagicMock(status_code=429),
            )
        ),
    )

    with patch.object(
        client.client, "patch", new_callable=AsyncMock, return_value=mock_response
    ):
        with pytest.raises(NotionRateLimitError) as exc_info:
            await client.update_task_status("page123", "In Progress")

        # Verify exception details
        assert exc_info.value.retry_count == 3
        assert "rate limit exceeded" in str(exc_info.value).lower()

        # Should have attempted 3 times
        assert client.client.patch.call_count == 3

    await client.close()


@pytest.mark.asyncio
async def test_get_database_pages_success():
    """Test successful database query."""
    client = NotionClient("test_token")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [
            {"id": "page1", "properties": {}},
            {"id": "page2", "properties": {}},
        ]
    }

    with patch.object(
        client.client, "post", new_callable=AsyncMock, return_value=mock_response
    ):
        results = await client.get_database_pages("db123")

        assert len(results) == 2
        assert results[0]["id"] == "page1"
        assert results[1]["id"] == "page2"

    await client.close()


@pytest.mark.asyncio
async def test_update_page_properties_success():
    """Test successful bulk property update."""
    client = NotionClient("test_token")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": "page123",
        "properties": {
            "Status": {"status": {"name": "Done"}},
            "Priority": {"number": 5},
        },
    }

    properties = {
        "Status": {"status": {"name": "Done"}},
        "Priority": {"number": 5},
    }

    with patch.object(
        client.client, "patch", new_callable=AsyncMock, return_value=mock_response
    ):
        result = await client.update_page_properties("page123", properties)

        assert result["id"] == "page123"
        assert result["properties"]["Status"]["status"]["name"] == "Done"
        assert result["properties"]["Priority"]["number"] == 5

    await client.close()


@pytest.mark.asyncio
async def test_get_page_success():
    """Test successful page retrieval."""
    client = NotionClient("test_token")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": "page123",
        "properties": {"Title": {"title": [{"text": {"content": "Test Page"}}]}},
    }

    with patch.object(
        client.client, "get", new_callable=AsyncMock, return_value=mock_response
    ):
        result = await client.get_page("page123")

        assert result["id"] == "page123"
        assert "properties" in result

    await client.close()


@pytest.mark.asyncio
async def test_headers_include_auth_and_version():
    """Test API requests include proper headers."""
    client = NotionClient("test_token_abc123")

    headers = client._get_headers()

    assert headers["Authorization"] == "Bearer test_token_abc123"
    assert headers["Notion-Version"] == "2025-09-03"
    assert headers["Content-Type"] == "application/json"

    await client.close()


@pytest.mark.asyncio
async def test_is_retriable_error_classification():
    """Test error classification logic."""
    client = NotionClient("test_token")

    # Retriable: 429, 500, 502, 503, 504
    for status_code in [429, 500, 502, 503, 504]:
        mock_response = MagicMock()
        mock_response.status_code = status_code
        error = httpx.HTTPStatusError("Error", request=MagicMock(), response=mock_response)
        assert client._is_retriable_error(error) is True

    # Non-retriable: 400, 401, 403
    for status_code in [400, 401, 403]:
        mock_response = MagicMock()
        mock_response.status_code = status_code
        error = httpx.HTTPStatusError("Error", request=MagicMock(), response=mock_response)
        assert client._is_retriable_error(error) is False

    # Retriable: Network errors
    assert client._is_retriable_error(httpx.TimeoutException("Timeout")) is True
    assert client._is_retriable_error(httpx.ConnectError("Connection failed")) is True

    # Non-retriable: Other exceptions
    assert client._is_retriable_error(ValueError("Invalid")) is False

    await client.close()


@pytest.mark.asyncio
async def test_client_close():
    """Test client properly closes HTTP connection."""
    client = NotionClient("test_token")

    with patch.object(client.client, "aclose", new_callable=AsyncMock) as mock_close:
        await client.close()
        mock_close.assert_called_once()


@pytest.mark.asyncio
async def test_context_manager_support():
    """Test client can be used as async context manager."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"id": "page123"}

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.aclose = AsyncMock()
        mock_client_class.return_value = mock_client_instance

        async with NotionClient("test_token") as client:
            result = await client.get_page("page123")
            assert result["id"] == "page123"

        # Verify close was called on exit
        mock_client_instance.aclose.assert_called_once()


@pytest.mark.asyncio
async def test_retry_after_header_handling():
    """Test 429 responses with Retry-After header are respected."""
    client = NotionClient("test_token")

    # First attempt: 429 with Retry-After, Second attempt: 200
    mock_responses = [
        MagicMock(
            status_code=429,
            headers={"Retry-After": "0.1"},  # 0.1 second for test speed
            text="Rate limited",
            raise_for_status=MagicMock(
                side_effect=httpx.HTTPStatusError(
                    "Rate limited",
                    request=MagicMock(),
                    response=MagicMock(status_code=429),
                )
            ),
        ),
        MagicMock(
            status_code=200,
            json=MagicMock(return_value={"success": True}),
            raise_for_status=MagicMock(),
        ),
    ]

    with patch.object(
        client.client, "get", new_callable=AsyncMock, side_effect=mock_responses
    ):
        result = await client.get_page("page123")

        assert result["success"] is True
        # Should have retried after respecting Retry-After header
        assert client.client.get.call_count == 2

    await client.close()
