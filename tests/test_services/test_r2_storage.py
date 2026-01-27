"""Tests for R2 storage client (Story 8.4).

Tests verify:
- Successful R2 uploads with public URL generation
- Error classification (permanent vs transient)
- Retry logic with exponential backoff
- S3-compatible API integration via aioboto3
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from app.services.r2_storage import (
    R2StorageClient,
    R2StorageError,
    R2StorageRetryError,
)


@pytest.fixture
def r2_client():
    """Create R2 storage client for testing."""
    return R2StorageClient(
        bucket_name="test-bucket",
        access_key_id="test-access-key",
        secret_access_key="test-secret-key",
        region="auto",
    )


@pytest.fixture
def mock_file(tmp_path):
    """Create temporary test file."""
    file_path = tmp_path / "test_asset.png"
    file_path.write_bytes(b"fake image data")
    return file_path


@pytest.mark.asyncio
async def test_r2_upload_success(r2_client, mock_file):
    """Test successful R2 upload returns public URL."""
    with patch("aioboto3.Session") as mock_session, \
         patch("httpx.AsyncClient") as mock_httpx:
        # Setup mock S3 client
        mock_s3_client = AsyncMock()
        mock_s3_client.upload_fileobj = AsyncMock()

        mock_session.return_value.client.return_value.__aenter__.return_value = mock_s3_client

        # Setup mock HTTP client for URL validation
        mock_http_client = AsyncMock()
        mock_http_response = MagicMock()
        mock_http_response.status_code = 200
        mock_http_client.head = AsyncMock(return_value=mock_http_response)
        mock_httpx.return_value.__aenter__.return_value = mock_http_client

        # Execute upload
        url = await r2_client.upload_asset(
            local_file_path=mock_file,
            r2_key="test/path/asset.png",
            content_type="image/png",
        )

        # Verify URL format
        assert url == "https://test-bucket.r2.dev/test/path/asset.png"

        # Verify S3 client was called with correct parameters
        mock_s3_client.upload_fileobj.assert_called_once()

        # Verify URL validation was called
        mock_http_client.head.assert_called_once()


@pytest.mark.asyncio
async def test_r2_permanent_error_access_denied(r2_client, mock_file):
    """Test permanent error (AccessDenied) raises R2StorageError without retry."""
    with patch("aioboto3.Session") as mock_session:
        # Setup mock to raise AccessDenied
        mock_s3_client = AsyncMock()
        mock_s3_client.upload_fileobj.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}},
            "PutObject",
        )

        mock_session.return_value.client.return_value.__aenter__.return_value = mock_s3_client

        # Verify raises R2StorageError (permanent)
        with pytest.raises(R2StorageError, match="R2 permanent error: AccessDenied"):
            await r2_client.upload_asset(
                local_file_path=mock_file,
                r2_key="test/asset.png",
                content_type="image/png",
            )

        # Verify only called once (no retry)
        assert mock_s3_client.upload_fileobj.call_count == 1


@pytest.mark.asyncio
async def test_r2_permanent_error_no_such_bucket(r2_client, mock_file):
    """Test permanent error (NoSuchBucket) raises R2StorageError without retry."""
    with patch("aioboto3.Session") as mock_session:
        # Setup mock to raise NoSuchBucket
        mock_s3_client = AsyncMock()
        mock_s3_client.upload_fileobj.side_effect = ClientError(
            {"Error": {"Code": "NoSuchBucket", "Message": "The specified bucket does not exist"}},
            "PutObject",
        )

        mock_session.return_value.client.return_value.__aenter__.return_value = mock_s3_client

        # Verify raises R2StorageError (permanent)
        with pytest.raises(R2StorageError, match="R2 permanent error: NoSuchBucket"):
            await r2_client.upload_asset(
                local_file_path=mock_file,
                r2_key="test/asset.png",
                content_type="image/png",
            )

        # Verify only called once (no retry)
        assert mock_s3_client.upload_fileobj.call_count == 1


@pytest.mark.asyncio
async def test_r2_transient_error_retry_success(r2_client, mock_file):
    """Test transient error (SlowDown) retries and succeeds."""
    with patch("aioboto3.Session") as mock_session, \
         patch("httpx.AsyncClient") as mock_httpx:
        # Setup mock to fail twice, then succeed
        mock_s3_client = AsyncMock()
        mock_s3_client.upload_fileobj.side_effect = [
            ClientError(
                {"Error": {"Code": "SlowDown", "Message": "Please reduce your request rate"}},
                "PutObject",
            ),
            ClientError(
                {"Error": {"Code": "SlowDown", "Message": "Please reduce your request rate"}},
                "PutObject",
            ),
            None,  # Success on third attempt
        ]

        mock_session.return_value.client.return_value.__aenter__.return_value = mock_s3_client

        # Setup mock HTTP client for URL validation
        mock_http_client = AsyncMock()
        mock_http_response = MagicMock()
        mock_http_response.status_code = 200
        mock_http_client.head = AsyncMock(return_value=mock_http_response)
        mock_httpx.return_value.__aenter__.return_value = mock_http_client

        # Execute upload (should succeed after retries)
        url = await r2_client.upload_asset(
            local_file_path=mock_file,
            r2_key="test/asset.png",
            content_type="image/png",
        )

        # Verify URL returned after retries
        assert url == "https://test-bucket.r2.dev/test/asset.png"

        # Verify retried 3 times
        assert mock_s3_client.upload_fileobj.call_count == 3


@pytest.mark.asyncio
async def test_r2_transient_error_max_retries_exceeded(r2_client, mock_file):
    """Test transient error exceeds max retries and raises exception."""
    with patch("aioboto3.Session") as mock_session:
        # Setup mock to always fail with transient error
        mock_s3_client = AsyncMock()
        mock_s3_client.upload_fileobj.side_effect = ClientError(
            {"Error": {"Code": "SlowDown", "Message": "Please reduce your request rate"}},
            "PutObject",
        )

        mock_session.return_value.client.return_value.__aenter__.return_value = mock_s3_client

        # Verify raises R2StorageRetryError after max retries
        with pytest.raises(R2StorageRetryError, match="R2 transient error: SlowDown"):
            await r2_client.upload_asset(
                local_file_path=mock_file,
                r2_key="test/asset.png",
                content_type="image/png",
            )

        # Verify retried 3 times (max attempts)
        assert mock_s3_client.upload_fileobj.call_count == 3


@pytest.mark.asyncio
async def test_r2_transient_error_service_unavailable(r2_client, mock_file):
    """Test ServiceUnavailable is classified as transient and retries."""
    with patch("aioboto3.Session") as mock_session, \
         patch("httpx.AsyncClient") as mock_httpx:
        # Setup mock to fail once, then succeed
        mock_s3_client = AsyncMock()
        mock_s3_client.upload_fileobj.side_effect = [
            ClientError(
                {"Error": {"Code": "ServiceUnavailable", "Message": "Service temporarily unavailable"}},
                "PutObject",
            ),
            None,  # Success on second attempt
        ]

        mock_session.return_value.client.return_value.__aenter__.return_value = mock_s3_client

        # Setup mock HTTP client for URL validation
        mock_http_client = AsyncMock()
        mock_http_response = MagicMock()
        mock_http_response.status_code = 200
        mock_http_client.head = AsyncMock(return_value=mock_http_response)
        mock_httpx.return_value.__aenter__.return_value = mock_http_client

        # Execute upload (should succeed after retry)
        url = await r2_client.upload_asset(
            local_file_path=mock_file,
            r2_key="test/asset.png",
            content_type="image/png",
        )

        # Verify URL returned after retry
        assert url == "https://test-bucket.r2.dev/test/asset.png"

        # Verify retried once
        assert mock_s3_client.upload_fileobj.call_count == 2


@pytest.mark.asyncio
async def test_r2_unknown_error_classified_as_transient(r2_client, mock_file):
    """Test unknown error is classified as transient (safe default) and retries."""
    with patch("aioboto3.Session") as mock_session, \
         patch("httpx.AsyncClient") as mock_httpx:
        # Setup mock to raise unknown error once, then succeed
        mock_s3_client = AsyncMock()
        mock_s3_client.upload_fileobj.side_effect = [
            ClientError(
                {"Error": {"Code": "UnknownErrorCode", "Message": "Unknown error"}},
                "PutObject",
            ),
            None,  # Success on second attempt
        ]

        mock_session.return_value.client.return_value.__aenter__.return_value = mock_s3_client

        # Setup mock HTTP client for URL validation
        mock_http_client = AsyncMock()
        mock_http_response = MagicMock()
        mock_http_response.status_code = 200
        mock_http_client.head = AsyncMock(return_value=mock_http_response)
        mock_httpx.return_value.__aenter__.return_value = mock_http_client

        # Execute upload (should succeed after retry)
        url = await r2_client.upload_asset(
            local_file_path=mock_file,
            r2_key="test/asset.png",
            content_type="image/png",
        )

        # Verify URL returned after retry
        assert url == "https://test-bucket.r2.dev/test/asset.png"

        # Verify retried once
        assert mock_s3_client.upload_fileobj.call_count == 2


@pytest.mark.asyncio
async def test_r2_delete_success(r2_client):
    """Test successful R2 asset deletion."""
    with patch("aioboto3.Session") as mock_session:
        # Setup mock S3 client
        mock_s3_client = AsyncMock()
        mock_s3_client.delete_object = AsyncMock()

        mock_session.return_value.client.return_value.__aenter__.return_value = mock_s3_client

        # Execute delete
        result = await r2_client.delete_asset(r2_key="test/path/asset.png")

        # Verify success
        assert result is True

        # Verify S3 client was called
        mock_s3_client.delete_object.assert_called_once_with(
            Bucket="test-bucket",
            Key="test/path/asset.png",
        )


@pytest.mark.asyncio
async def test_r2_delete_failure(r2_client):
    """Test R2 asset deletion failure returns False."""
    with patch("aioboto3.Session") as mock_session:
        # Setup mock to raise exception
        mock_s3_client = AsyncMock()
        mock_s3_client.delete_object.side_effect = Exception("Network error")

        mock_session.return_value.client.return_value.__aenter__.return_value = mock_s3_client

        # Execute delete
        result = await r2_client.delete_asset(r2_key="test/path/asset.png")

        # Verify failure
        assert result is False


@pytest.mark.asyncio
async def test_r2_endpoint_url_format(r2_client):
    """Test R2 endpoint URL is correctly formatted for Cloudflare."""
    assert r2_client.endpoint_url == "https://test-bucket.r2.cloudflarestorage.com"


@pytest.mark.asyncio
async def test_r2_public_url_format(r2_client, mock_file):
    """Test public R2 URL format matches expected pattern."""
    with patch("aioboto3.Session") as mock_session, \
         patch("httpx.AsyncClient") as mock_httpx:
        mock_s3_client = AsyncMock()
        mock_s3_client.upload_fileobj = AsyncMock()
        mock_session.return_value.client.return_value.__aenter__.return_value = mock_s3_client

        # Setup mock HTTP client for URL validation
        mock_http_client = AsyncMock()
        mock_http_response = MagicMock()
        mock_http_response.status_code = 200
        mock_http_client.head = AsyncMock(return_value=mock_http_response)
        mock_httpx.return_value.__aenter__.return_value = mock_http_client

        url = await r2_client.upload_asset(
            local_file_path=mock_file,
            r2_key="poke1/task123/assets/char.png",
            content_type="image/png",
        )

        # Verify public URL format
        assert url == "https://test-bucket.r2.dev/poke1/task123/assets/char.png"
        assert url.startswith("https://")
        assert ".r2.dev/" in url
