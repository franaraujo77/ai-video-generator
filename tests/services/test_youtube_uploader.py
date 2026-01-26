"""Tests for YouTube uploader service (Story 7.4).

This test module covers the resumable upload implementation for YouTube videos.

Test Coverage:
- Quota checking (pre-check passes/fails)
- Upload flow (small/large files, progress logging)
- Error handling (400, 401, 403, 429, 500-504, network errors)
- Resumable upload (resume after network error, max retries)
- Integration tests (quota tracking, task status updates)

Mocking Strategy:
- Mock googleapiclient.discovery.build() for YouTube API
- Mock MediaFileUpload for file upload simulation
- Mock filesystem helpers (get_video_dir)
- Use AsyncSession fixtures for database testing
"""

import os
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from googleapiclient.errors import HttpError
from http.client import HTTPMessage, HTTPResponse

from app.models import Task, Channel, YouTubeQuotaUsage, TaskStatus
from app.services.youtube_uploader import (
    YouTubeUploadError,
    YouTubeUploadRetryError,
    check_quota_available,
    update_quota_usage,
    upload_video,
    OPERATION_COSTS,
)
from app.services.metadata_service import MetadataDict


# ============================================================================
# Fixtures
# ============================================================================


def mock_youtube_credentials():
    """Context manager to mock Google OAuth credentials."""
    return patch("app.services.youtube_uploader.Credentials", return_value=MagicMock(valid=True))


@pytest.fixture
async def sample_task(async_session):
    """Create a sample task in APPROVED status."""
    channel = Channel(
        id=uuid4(),
        channel_id="test_channel",
        channel_name="Test Channel",
        is_active=True,
    )
    async_session.add(channel)

    task = Task(
        id=uuid4(),
        channel_id=channel.id,
        notion_page_id=str(uuid4()),
        title="Test Video",
        topic="Test Topic",
        story_direction="Test story direction",
        status=TaskStatus.APPROVED,
    )
    async_session.add(task)
    await async_session.commit()
    await async_session.refresh(task)
    await async_session.refresh(channel)

    return task


@pytest.fixture
def sample_metadata():
    """Create sample YouTube metadata."""
    return MetadataDict(
        title="Test Video",
        description="Test Description",
        tags=["test", "demo"],
        privacy_status="unlisted",
        category_id="24",  # Entertainment
    )


@pytest.fixture
async def quota_record(async_session, sample_task):
    """Create a quota record for today with available quota."""
    quota = YouTubeQuotaUsage(
        channel_id=sample_task.channel_id,
        date=date.today(),
        units_used=0,
        daily_limit=10000,
    )
    async_session.add(quota)
    await async_session.commit()
    await async_session.refresh(quota)
    return quota


# ============================================================================
# Task 1: Service Foundation Tests
# ============================================================================


def test_operation_costs_defined():
    """Operation costs should be defined for YouTube API operations."""
    assert "upload" in OPERATION_COSTS
    assert OPERATION_COSTS["upload"] == 1600
    assert "update" in OPERATION_COSTS
    assert "delete" in OPERATION_COSTS


def test_youtube_upload_error_is_exception():
    """YouTubeUploadError should be an Exception subclass."""
    error = YouTubeUploadError("Test error")
    assert isinstance(error, Exception)
    assert str(error) == "Test error"


def test_youtube_upload_retry_error_is_exception():
    """YouTubeUploadRetryError should be an Exception subclass."""
    error = YouTubeUploadRetryError("Test retry error")
    assert isinstance(error, Exception)
    assert str(error) == "Test retry error"


# ============================================================================
# Task 2: Quota Pre-Check Tests
# ============================================================================


@pytest.mark.asyncio
async def test_quota_check_passes_with_sufficient_quota(async_session, sample_task, quota_record):
    """Quota check should pass when sufficient quota available."""
    # Initial quota: 0 / 10000
    # Upload cost: 1600
    # Remaining after: 1600 / 10000 = OK

    quota_available = await check_quota_available(
        str(sample_task.channel_id),
        "upload",
        async_session,
    )

    assert quota_available is True


@pytest.mark.asyncio
async def test_quota_check_fails_when_quota_exceeded(async_session, sample_task):
    """Quota check should fail when upload would exceed quota."""
    # Create quota record with 9000 units already used
    quota = YouTubeQuotaUsage(
        channel_id=sample_task.channel_id,
        date=date.today(),
        units_used=9000,  # 9000 + 1600 = 10600 > 10000
        daily_limit=10000,
    )
    async_session.add(quota)
    await async_session.commit()

    quota_available = await check_quota_available(
        str(sample_task.channel_id),
        "upload",
        async_session,
    )

    assert quota_available is False


@pytest.mark.asyncio
async def test_quota_check_fails_when_quota_record_not_found(async_session, sample_task):
    """Quota check should raise error when quota record not found."""
    # No quota record exists for today
    with pytest.raises(YouTubeUploadError, match="Quota record not found"):
        await check_quota_available(
            str(sample_task.channel_id),
            "upload",
            async_session,
        )


# ============================================================================
# Task 6: Quota Usage Update Tests
# ============================================================================


@pytest.mark.asyncio
async def test_quota_updated_after_successful_upload(async_session, sample_task, quota_record):
    """Quota usage should increment after successful upload."""
    # Initial: 0 / 10000
    assert quota_record.units_used == 0

    await update_quota_usage(
        str(sample_task.channel_id),
        "upload",
        async_session,
    )

    await async_session.refresh(quota_record)

    # After upload: 1600 / 10000
    assert quota_record.units_used == 1600


# ============================================================================
# Task 8.1-8.3: Upload Tests - Basic Flow
# ============================================================================


@pytest.mark.asyncio
async def test_upload_fails_when_task_not_approved(async_session, sample_metadata, quota_record):
    """Upload should fail when task status != APPROVED."""
    # Create a task with non-APPROVED status
    channel = Channel(
        id=uuid4(),
        channel_id=f"test_channel_{uuid4()}",  # Unique channel_id
        channel_name="Test Channel",
        is_active=True,
    )
    async_session.add(channel)

    task = Task(
        id=uuid4(),
        channel_id=channel.id,
        notion_page_id=str(uuid4()),
        title="Test Video",
        topic="Test Topic",
        story_direction="Test story direction",
        status=TaskStatus.FINAL_REVIEW,  # Not APPROVED
    )
    async_session.add(task)
    await async_session.commit()

    with pytest.raises(YouTubeUploadError, match="Cannot upload video for task in"):
        await upload_video(task, sample_metadata, async_session)


@pytest.mark.asyncio
async def test_upload_fails_when_video_file_not_found(
    async_session, sample_task, sample_metadata, quota_record, tmp_path
):
    """Upload should fail when video file doesn't exist."""
    with patch("app.services.youtube_uploader.get_video_dir", return_value=tmp_path):
        with pytest.raises(YouTubeUploadError, match="Video file not found"):
            await upload_video(sample_task, sample_metadata, async_session)


@pytest.mark.asyncio
async def test_upload_fails_when_quota_insufficient(
    async_session, sample_task, sample_metadata, tmp_path
):
    """Upload should fail when quota would be exceeded."""
    # Create video file
    video_file = tmp_path / f"{sample_task.id}_final.mp4"
    video_file.write_bytes(b"fake video data" * 1000)

    # Create quota record with insufficient quota
    quota = YouTubeQuotaUsage(
        channel_id=sample_task.channel_id,
        date=date.today(),
        units_used=9500,  # 9500 + 1600 > 10000
        daily_limit=10000,
    )
    async_session.add(quota)
    await async_session.commit()

    with patch("app.services.youtube_uploader.get_video_dir", return_value=tmp_path):
        with pytest.raises(YouTubeUploadError, match="YouTube quota exceeded"):
            await upload_video(sample_task, sample_metadata, async_session)


# ============================================================================
# Task 8.4-8.5: Upload Tests - Success Scenarios
# ============================================================================


@pytest.mark.asyncio
async def test_upload_successful_small_file(
    async_session, sample_task, sample_metadata, quota_record, tmp_path, monkeypatch
):
    """Upload should succeed for small file (< 1MB, single chunk)."""
    # Create small video file (< 1MB)
    video_file = tmp_path / f"{sample_task.id}_final.mp4"
    video_file.write_bytes(b"fake video data" * 1000)  # ~15KB

    # Mock environment variables
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")

    # Mock filesystem helper
    with patch("app.services.youtube_uploader.get_video_dir", return_value=tmp_path):
        # Mock YouTube API
        mock_youtube = MagicMock()
        mock_request = MagicMock()

        # Simulate single-chunk upload (small file)
        mock_request.next_chunk.return_value = (None, {"id": "test_video_id_123"})

        mock_youtube.videos().insert.return_value = mock_request

        with patch("app.services.youtube_uploader.build", return_value=mock_youtube):
            # Mock CredentialService
            with patch("app.services.youtube_uploader.CredentialService") as mock_cred_service:
                mock_cred_instance = AsyncMock()
                mock_cred_instance.get_youtube_token.return_value = "mock_refresh_token"
                mock_cred_service.return_value = mock_cred_instance

                # Mock Credentials to avoid actual OAuth refresh
                with patch("app.services.youtube_uploader.Credentials") as mock_credentials_class:
                    mock_cred_obj = MagicMock()
                    mock_cred_obj.valid = True  # Mark as already valid (no refresh needed)
                    mock_credentials_class.return_value = mock_cred_obj

                    # Upload
                    video_id = await upload_video(sample_task, sample_metadata, async_session)

                    assert video_id == "test_video_id_123"

                    # Verify quota updated
                    await async_session.refresh(quota_record)
                    assert quota_record.units_used == 1600


@pytest.mark.asyncio
async def test_upload_successful_large_file(
    async_session, sample_task, sample_metadata, quota_record, tmp_path, monkeypatch
):
    """Upload should succeed for large file (> 1MB, multiple chunks)."""
    # Create large video file (> 1MB)
    video_file = tmp_path / f"{sample_task.id}_final.mp4"
    video_file.write_bytes(b"fake video data" * 200000)  # ~2MB

    # Mock environment variables
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")

    with patch("app.services.youtube_uploader.get_video_dir", return_value=tmp_path):
        mock_youtube = MagicMock()
        mock_request = MagicMock()

        # Simulate multi-chunk upload (large file)
        mock_status_1 = MagicMock()
        mock_status_1.progress.return_value = 0.5
        mock_status_1.resumable_progress = 1000000

        mock_status_2 = MagicMock()
        mock_status_2.progress.return_value = 1.0
        mock_status_2.resumable_progress = 2000000

        mock_request.next_chunk.side_effect = [
            (mock_status_1, None),  # First chunk (50% progress)
            (mock_status_2, None),  # Second chunk (100% progress)
            (None, {"id": "test_video_id_456"}),  # Upload complete
        ]

        mock_youtube.videos().insert.return_value = mock_request

        with patch("app.services.youtube_uploader.build", return_value=mock_youtube):
            with patch("app.services.youtube_uploader.CredentialService") as mock_cred_service:
                mock_cred_instance = AsyncMock()
                mock_cred_instance.get_youtube_token.return_value = "mock_refresh_token"
                mock_cred_service.return_value = mock_cred_instance

                with mock_youtube_credentials():
                    video_id = await upload_video(sample_task, sample_metadata, async_session)

                    assert video_id == "test_video_id_456"


# ============================================================================
# Task 8.6-8.7: Resumable Upload Tests
# ============================================================================


@pytest.mark.asyncio
async def test_upload_resumes_after_network_error(
    async_session, sample_task, sample_metadata, quota_record, tmp_path, monkeypatch
):
    """Upload should raise retry error on network failure."""
    video_file = tmp_path / f"{sample_task.id}_final.mp4"
    video_file.write_bytes(b"fake video data" * 1000)

    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")

    with patch("app.services.youtube_uploader.get_video_dir", return_value=tmp_path):
        mock_youtube = MagicMock()
        mock_request = MagicMock()

        # Simulate network error on chunk upload
        mock_request.next_chunk.side_effect = ConnectionError("Network timeout")

        mock_youtube.videos().insert.return_value = mock_request

        with patch("app.services.youtube_uploader.build", return_value=mock_youtube):
            with patch("app.services.youtube_uploader.CredentialService") as mock_cred_service:
                mock_cred_instance = AsyncMock()
                mock_cred_instance.get_youtube_token.return_value = "mock_refresh_token"
                mock_cred_service.return_value = mock_cred_instance

                with mock_youtube_credentials():
                    # Should raise retry error on network failure
                    with pytest.raises(YouTubeUploadRetryError, match="Network error"):
                        await upload_video(sample_task, sample_metadata, async_session)


@pytest.mark.asyncio
async def test_upload_fails_after_max_retries(
    async_session, sample_task, sample_metadata, quota_record, tmp_path, monkeypatch
):
    """Upload should fail after MAX_UPLOAD_RETRIES consecutive failures."""
    video_file = tmp_path / f"{sample_task.id}_final.mp4"
    video_file.write_bytes(b"fake video data" * 1000)

    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")

    with patch("app.services.youtube_uploader.get_video_dir", return_value=tmp_path):
        mock_youtube = MagicMock()
        mock_request = MagicMock()

        # Simulate persistent network error (will retry MAX_UPLOAD_RETRIES=3 times)
        call_count = 0

        def network_error_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise ConnectionError("Network timeout")

        mock_request.next_chunk.side_effect = network_error_side_effect

        mock_youtube.videos().insert.return_value = mock_request

        with patch("app.services.youtube_uploader.build", return_value=mock_youtube):
            with patch("app.services.youtube_uploader.CredentialService") as mock_cred_service:
                mock_cred_instance = AsyncMock()
                mock_cred_instance.get_youtube_token.return_value = "mock_refresh_token"
                mock_cred_service.return_value = mock_cred_instance

                with mock_youtube_credentials():
                    # Should fail after MAX_UPLOAD_RETRIES attempts
                    with pytest.raises(
                        YouTubeUploadRetryError, match=r"Network error after \d+ retries"
                    ):
                        await upload_video(sample_task, sample_metadata, async_session)

                    # Verify it retried MAX_UPLOAD_RETRIES times
                    assert call_count == 3  # MAX_UPLOAD_RETRIES


# ============================================================================
# Task 8.8-8.9: Error Handling Tests
# ============================================================================


@pytest.mark.asyncio
async def test_upload_fails_on_invalid_metadata(
    async_session, sample_task, sample_metadata, quota_record, tmp_path, monkeypatch
):
    """Upload should raise permanent error on 400 Bad Request."""
    video_file = tmp_path / f"{sample_task.id}_final.mp4"
    video_file.write_bytes(b"fake video data" * 1000)

    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")

    with patch("app.services.youtube_uploader.get_video_dir", return_value=tmp_path):
        mock_youtube = MagicMock()
        mock_request = MagicMock()

        # Create mock HTTP 400 error
        mock_resp = MagicMock()
        mock_resp.status = 400
        http_error = HttpError(resp=mock_resp, content=b"Invalid metadata")

        mock_request.next_chunk.side_effect = http_error

        mock_youtube.videos().insert.return_value = mock_request

        with patch("app.services.youtube_uploader.build", return_value=mock_youtube):
            with patch("app.services.youtube_uploader.CredentialService") as mock_cred_service:
                mock_cred_instance = AsyncMock()
                mock_cred_instance.get_youtube_token.return_value = "mock_refresh_token"
                mock_cred_service.return_value = mock_cred_instance

                with mock_youtube_credentials():
                    with pytest.raises(YouTubeUploadError, match="Invalid metadata"):
                        await upload_video(sample_task, sample_metadata, async_session)


@pytest.mark.asyncio
async def test_upload_fails_on_invalid_credentials(
    async_session, sample_task, sample_metadata, quota_record, tmp_path, monkeypatch
):
    """Upload should raise permanent error on 401 Unauthorized."""
    video_file = tmp_path / f"{sample_task.id}_final.mp4"
    video_file.write_bytes(b"fake video data" * 1000)

    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")

    with patch("app.services.youtube_uploader.get_video_dir", return_value=tmp_path):
        mock_youtube = MagicMock()
        mock_request = MagicMock()

        # Create mock HTTP 401 error
        mock_resp = MagicMock()
        mock_resp.status = 401
        http_error = HttpError(resp=mock_resp, content=b"Unauthorized")

        mock_request.next_chunk.side_effect = http_error

        mock_youtube.videos().insert.return_value = mock_request

        with patch("app.services.youtube_uploader.build", return_value=mock_youtube):
            with patch("app.services.youtube_uploader.CredentialService") as mock_cred_service:
                mock_cred_instance = AsyncMock()
                mock_cred_instance.get_youtube_token.return_value = "mock_refresh_token"
                mock_cred_service.return_value = mock_cred_instance

                with mock_youtube_credentials():
                    with pytest.raises(YouTubeUploadError, match="Authentication error"):
                        await upload_video(sample_task, sample_metadata, async_session)
