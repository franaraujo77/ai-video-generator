"""Tests for YouTube upload error handling (Story 7.6).

This test suite validates comprehensive error handling for YouTube API upload failures:
- Error classification (quota/transient/permanent)
- Retry scheduling (exponential backoff vs quota reset)
- Discord alert integration
- Task status updates and error logging

Coverage:
    - Error Classification: 6 tests
    - Quota Error Handling: 3 tests
    - Transient Error Handling: 4 tests
    - Permanent Error Handling: 2 tests
    - Integration with youtube_uploader_integration: 2 tests
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytz
from googleapiclient.errors import HttpError
from google.api_core.exceptions import GoogleAPIError

from app.models import Task, TaskStatus
from app.services.youtube_error_handler import (
    YouTubeQuotaExceededError,
    YouTubeBadRequestError,
    YouTubeTransientError,
    classify_youtube_upload_error,
    calculate_quota_reset_time,
    handle_youtube_upload_error,
    MAX_RETRIES,
)


# ==================== Error Classification Tests ====================


def test_classify_quota_exceeded_error():
    """Test classification of YouTube quota exceeded error (403 quotaExceeded)."""
    # Mock HttpError for quota exceeded (403)
    error_content = {
        "error": {
            "code": 403,
            "message": "The request cannot be completed because you have exceeded your quota.",
            "errors": [
                {"reason": "quotaExceeded", "domain": "youtube.quota", "message": "Quota exceeded"}
            ],
        }
    }

    http_error = MagicMock(spec=HttpError)
    http_error.resp = MagicMock(status=403)
    http_error.content = json.dumps(error_content).encode("utf-8")

    # Classify error
    result = classify_youtube_upload_error(http_error)

    # Assert
    assert isinstance(result, YouTubeQuotaExceededError)
    assert result.status_code == 403
    assert result.error_reason == "quotaExceeded"
    assert "quota" in result.message.lower()


def test_classify_transient_500_error():
    """Test classification of YouTube server error (500) as transient."""
    error_content = {
        "error": {
            "code": 500,
            "message": "Backend error",
            "errors": [{"reason": "backendError", "message": "Backend error"}],
        }
    }

    http_error = MagicMock(spec=HttpError)
    http_error.resp = MagicMock(status=500)
    http_error.content = json.dumps(error_content).encode("utf-8")

    result = classify_youtube_upload_error(http_error)

    assert isinstance(result, YouTubeTransientError)
    assert result.status_code == 500
    assert result.error_reason == "backendError"


def test_classify_transient_503_error():
    """Test classification of YouTube service unavailable (503) as transient."""
    error_content = {
        "error": {
            "code": 503,
            "message": "Service unavailable",
            "errors": [{"reason": "serviceUnavailable"}],
        }
    }

    http_error = MagicMock(spec=HttpError)
    http_error.resp = MagicMock(status=503)
    http_error.content = json.dumps(error_content).encode("utf-8")

    result = classify_youtube_upload_error(http_error)

    assert isinstance(result, YouTubeTransientError)
    assert result.status_code == 503


def test_classify_permanent_400_error():
    """Test classification of bad request (400) as permanent."""
    error_content = {
        "error": {
            "code": 400,
            "message": "Invalid request",
            "errors": [{"reason": "invalidRequest"}],
        }
    }

    http_error = MagicMock(spec=HttpError)
    http_error.resp = MagicMock(status=400)
    http_error.content = json.dumps(error_content).encode("utf-8")

    result = classify_youtube_upload_error(http_error)

    assert isinstance(result, YouTubeBadRequestError)
    assert result.status_code == 400


def test_classify_permanent_401_error():
    """Test classification of auth error (401) as permanent."""
    error_content = {
        "error": {
            "code": 401,
            "message": "Invalid credentials",
            "errors": [{"reason": "authError"}],
        }
    }

    http_error = MagicMock(spec=HttpError)
    http_error.resp = MagicMock(status=401)
    http_error.content = json.dumps(error_content).encode("utf-8")

    result = classify_youtube_upload_error(http_error)

    assert isinstance(result, YouTubeBadRequestError)
    assert result.status_code == 401


def test_classify_malformed_json_error():
    """Test classification of malformed error response (fallback to transient)."""
    http_error = MagicMock(spec=HttpError)
    http_error.resp = MagicMock(status=500)
    http_error.content = b"Not valid JSON"

    result = classify_youtube_upload_error(http_error)

    # Should fallback to transient error with status 500
    assert isinstance(result, YouTubeTransientError)
    assert result.status_code == 500


# ==================== Quota Reset Calculation Tests ====================


def test_calculate_quota_reset_time_before_midnight():
    """Test quota reset calculation when called before midnight PST."""
    with patch("app.services.youtube_error_handler.datetime") as mock_datetime:
        # Mock current time: 2026-01-25 14:30 PST (before midnight)
        pst = pytz.timezone("US/Pacific")
        now_pst = pst.localize(datetime(2026, 1, 25, 14, 30, 0))
        mock_datetime.now.return_value = now_pst

        # Calculate reset time
        reset_time = calculate_quota_reset_time()

        # Should return tomorrow's midnight PST (2026-01-26 00:00:00 PST)
        expected = pst.localize(datetime(2026, 1, 26, 0, 0, 0))
        assert reset_time == expected


def test_calculate_quota_reset_time_after_midnight():
    """Test quota reset calculation when called after midnight PST."""
    with patch("app.services.youtube_error_handler.datetime") as mock_datetime:
        # Mock current time: 2026-01-26 00:30 PST (after midnight)
        pst = pytz.timezone("US/Pacific")
        now_pst = pst.localize(datetime(2026, 1, 26, 0, 30, 0))
        mock_datetime.now.return_value = now_pst

        reset_time = calculate_quota_reset_time()

        # Should return tomorrow's midnight PST (2026-01-27 00:00:00 PST)
        expected = pst.localize(datetime(2026, 1, 27, 0, 0, 0))
        assert reset_time == expected


def test_calculate_quota_reset_time_handles_dst():
    """Test quota reset calculation handles daylight saving time correctly."""
    with patch("app.services.youtube_error_handler.datetime") as mock_datetime:
        # Mock current time during daylight saving time (June 2026, PDT = UTC-7)
        pst = pytz.timezone("US/Pacific")
        now_pdt = pst.localize(datetime(2026, 6, 15, 14, 30, 0))
        mock_datetime.now.return_value = now_pdt

        reset_time = calculate_quota_reset_time()

        # Should return tomorrow's midnight PDT (2026-06-16 00:00:00 PDT)
        expected = pst.localize(datetime(2026, 6, 16, 0, 0, 0))
        assert reset_time == expected


# ==================== Quota Error Handling Tests ====================


@pytest.mark.asyncio
async def test_handle_quota_exceeded_error(async_test_session):
    """Test handling of quota exceeded error (pause until midnight PST)."""
    # Create task
    task = Task(
        id=uuid4(),
        channel_id=uuid4(),
        notion_page_id="test_page_123",
        title="Test Video Upload",
        topic="Pokemon Nature Documentary",
        story_direction="Dramatic nature documentary following wild Pokemon",
        status=TaskStatus.UPLOADING,
        retry_count=0,
    )
    async_test_session.add(task)
    await async_test_session.commit()

    # Mock HttpError for quota exceeded
    error_content = {
        "error": {
            "code": 403,
            "message": "Quota exceeded",
            "errors": [{"reason": "quotaExceeded"}],
        }
    }
    http_error = MagicMock(spec=HttpError)
    http_error.resp = MagicMock(status=403)
    http_error.content = json.dumps(error_content).encode("utf-8")

    # Mock Discord webhook
    with patch("app.services.youtube_error_handler.send_discord_alert") as mock_alert:
        mock_alert.return_value = True

        # Handle error
        with pytest.raises(YouTubeQuotaExceededError):
            await handle_youtube_upload_error(
                task, http_error, async_test_session, webhook_url="https://discord.com/webhook"
            )

    # Refresh task
    await async_test_session.refresh(task)

    # Assert task updated
    assert task.status == TaskStatus.UPLOAD_ERROR_RETRYING
    assert task.retry_count == 1
    assert task.next_retry_at is not None
    error_log = json.loads(task.error_log)
    assert error_log["category"] == "quota"
    assert "quota_reset_at" in error_log

    # Assert Discord alert sent with correct content
    mock_alert.assert_called_once()
    call_args = mock_alert.call_args
    assert call_args.kwargs["alert_type"] == "quota_exhausted"
    assert call_args.kwargs["severity"] == "WARNING"
    assert "Task ID" in call_args.kwargs["fields"]
    assert "Channel ID" in call_args.kwargs["fields"]
    assert "Quota Reset" in call_args.kwargs["fields"]
    assert "Hours Until Reset" in call_args.kwargs["fields"]
    assert "Action" in call_args.kwargs["fields"]


@pytest.mark.asyncio
async def test_handle_quota_error_no_webhook_configured(async_test_session):
    """Test quota error handling when Discord webhook not configured."""
    task = Task(
        id=uuid4(),
        channel_id=uuid4(),
        notion_page_id="test_page_123",
        title="Test Video Upload",
        topic="Pokemon Nature Documentary",
        story_direction="Dramatic nature documentary following wild Pokemon",
        status=TaskStatus.UPLOADING,
        retry_count=0,
    )
    async_test_session.add(task)
    await async_test_session.commit()

    # Mock HttpError for quota exceeded
    error_content = {
        "error": {
            "code": 403,
            "message": "Quota exceeded",
            "errors": [{"reason": "quotaExceeded"}],
        }
    }
    http_error = MagicMock(spec=HttpError)
    http_error.resp = MagicMock(status=403)
    http_error.content = json.dumps(error_content).encode("utf-8")

    # Handle error WITHOUT webhook URL
    with patch("app.services.youtube_error_handler.send_discord_alert") as mock_alert:
        with pytest.raises(YouTubeQuotaExceededError):
            await handle_youtube_upload_error(
                task, http_error, async_test_session, webhook_url=None
            )

        # Assert alert NOT called when webhook is None
        mock_alert.assert_not_called()

    # Refresh and verify task still updated
    await async_test_session.refresh(task)
    assert task.status == TaskStatus.UPLOAD_ERROR_RETRYING


# ==================== Transient Error Handling Tests ====================


@pytest.mark.asyncio
async def test_handle_transient_error_first_retry(async_test_session):
    """Test handling of transient error on first failure (schedule 1min retry)."""
    task = Task(
        id=uuid4(),
        channel_id=uuid4(),
        notion_page_id="test_page_123",
        title="Test Video Upload",
        topic="Pokemon Nature Documentary",
        story_direction="Dramatic nature documentary following wild Pokemon",
        status=TaskStatus.UPLOADING,
        retry_count=0,
    )
    async_test_session.add(task)
    await async_test_session.commit()

    # Mock 500 error
    error_content = {
        "error": {
            "code": 500,
            "message": "Backend error",
            "errors": [{"reason": "backendError"}],
        }
    }
    http_error = MagicMock(spec=HttpError)
    http_error.resp = MagicMock(status=500)
    http_error.content = json.dumps(error_content).encode("utf-8")

    # Handle error
    with pytest.raises(YouTubeTransientError):
        await handle_youtube_upload_error(task, http_error, async_test_session)

    # Refresh task
    await async_test_session.refresh(task)

    # Assert task updated
    assert task.status == TaskStatus.UPLOAD_ERROR_RETRYING
    assert task.retry_count == 1
    error_log = json.loads(task.error_log)
    assert error_log["category"] == "transient"
    error_log = json.loads(task.error_log)
    assert error_log["retry_count"] == 1

    # Verify retry scheduled for ~1 minute from now
    now = datetime.now(timezone.utc)
    expected_retry = now + timedelta(minutes=1)
    # Convert naive datetime from SQLite to timezone-aware for comparison
    task_retry_time = (
        task.next_retry_at.replace(tzinfo=timezone.utc)
        if task.next_retry_at.tzinfo is None
        else task.next_retry_at
    )
    assert abs((task_retry_time - expected_retry).total_seconds()) < 5  # Within 5 seconds


@pytest.mark.asyncio
async def test_handle_transient_error_retry_exhausted(async_test_session):
    """Test handling of transient error when retry limit reached (terminal)."""
    task = Task(
        id=uuid4(),
        channel_id=uuid4(),
        notion_page_id="test_page_123",
        title="Test Video Upload - Retry Exhausted",
        topic="Pokemon Nature Documentary",
        story_direction="Dramatic nature documentary following wild Pokemon",
        status=TaskStatus.UPLOADING,
        retry_count=MAX_RETRIES,  # Already at max retries
    )
    async_test_session.add(task)
    await async_test_session.commit()

    # Mock 500 error
    error_content = {
        "error": {
            "code": 500,
            "message": "Backend error",
            "errors": [{"reason": "backendError"}],
        }
    }
    http_error = MagicMock(spec=HttpError)
    http_error.resp = MagicMock(status=500)
    http_error.content = json.dumps(error_content).encode("utf-8")

    # Handle error
    with patch("app.services.youtube_error_handler.send_discord_alert") as mock_alert:
        with pytest.raises(ValueError, match="Retry exhausted"):
            await handle_youtube_upload_error(
                task, http_error, async_test_session, webhook_url="https://discord.com/webhook"
            )

        # Verify terminal failure alert sent with correct content
        mock_alert.assert_called_once()
        call_args = mock_alert.call_args
        assert call_args.kwargs["alert_type"] == "terminal_failure"
        assert call_args.kwargs["severity"] == "CRITICAL"
        assert "Task ID" in call_args.kwargs["fields"]
        assert "Error Code" in call_args.kwargs["fields"]
        assert "Retry Attempts" in call_args.kwargs["fields"]
        assert "Last Error" in call_args.kwargs["fields"]
        assert "Action" in call_args.kwargs["fields"]

    # Refresh task
    await async_test_session.refresh(task)

    # Assert task marked as terminal
    assert task.status == TaskStatus.UPLOAD_ERROR
    error_log = json.loads(task.error_log)
    assert error_log["category"] == "transient"
    assert "exhausted_at" in task.error_log


@pytest.mark.asyncio
async def test_handle_transient_error_exponential_backoff(async_test_session):
    """Test transient error retry uses exponential backoff schedule."""
    # Test each retry level
    expected_delays = [
        timedelta(minutes=1),  # Retry 1
        timedelta(minutes=5),  # Retry 2
        timedelta(minutes=15),  # Retry 3
        timedelta(hours=1),  # Retry 4
    ]

    for retry_count, expected_delay in enumerate(expected_delays):
        task = Task(
            id=uuid4(),
            channel_id=uuid4(),
            notion_page_id=f"test_page_{retry_count}",
            title=f"Test Video Upload {retry_count}",
            topic="Pokemon Nature Documentary",
            story_direction="Dramatic nature documentary following wild Pokemon",
            status=TaskStatus.UPLOADING,
            retry_count=retry_count,
        )
        async_test_session.add(task)
        await async_test_session.commit()

        # Mock 500 error
        error_content = {
            "error": {
                "code": 500,
                "message": "Backend error",
                "errors": [{"reason": "backendError"}],
            }
        }
        http_error = MagicMock(spec=HttpError)
        http_error.resp = MagicMock(status=500)
        http_error.content = json.dumps(error_content).encode("utf-8")

        # Handle error
        with pytest.raises(YouTubeTransientError):
            await handle_youtube_upload_error(task, http_error, async_test_session)

        # Refresh task
        await async_test_session.refresh(task)

        # Verify retry scheduled with correct delay
        now = datetime.now(timezone.utc)
        expected_retry = now + expected_delay
        # Convert naive datetime from SQLite to timezone-aware for comparison
    task_retry_time = (
        task.next_retry_at.replace(tzinfo=timezone.utc)
        if task.next_retry_at.tzinfo is None
        else task.next_retry_at
    )
    assert abs((task_retry_time - expected_retry).total_seconds()) < 5  # Within 5 seconds


@pytest.mark.asyncio
async def test_handle_google_api_error_as_transient(async_test_session):
    """Test that GoogleAPIError is treated as transient."""
    task = Task(
        id=uuid4(),
        channel_id=uuid4(),
        notion_page_id="test_page_123",
        title="Test Video Upload",
        topic="Pokemon Nature Documentary",
        story_direction="Dramatic nature documentary following wild Pokemon",
        status=TaskStatus.UPLOADING,
        retry_count=0,
    )
    async_test_session.add(task)
    await async_test_session.commit()

    # Mock GoogleAPIError
    google_error = GoogleAPIError("Unexpected Google API error")

    # Handle error
    with pytest.raises(YouTubeTransientError):
        await handle_youtube_upload_error(task, google_error, async_test_session)

    # Refresh task
    await async_test_session.refresh(task)

    # Assert treated as transient
    assert task.status == TaskStatus.UPLOAD_ERROR_RETRYING
    error_log = json.loads(task.error_log)
    assert error_log["category"] == "transient"


# ==================== Permanent Error Handling Tests ====================


@pytest.mark.asyncio
async def test_handle_permanent_error_400(async_test_session):
    """Test handling of permanent error (400 bad request)."""
    task = Task(
        id=uuid4(),
        channel_id=uuid4(),
        notion_page_id="test_page_123",
        title="Test Video Upload",
        topic="Pokemon Nature Documentary",
        story_direction="Dramatic nature documentary following wild Pokemon",
        status=TaskStatus.UPLOADING,
        retry_count=0,
    )
    async_test_session.add(task)
    await async_test_session.commit()

    # Mock 400 error
    error_content = {
        "error": {
            "code": 400,
            "message": "Invalid metadata",
            "errors": [{"reason": "invalidRequest"}],
        }
    }
    http_error = MagicMock(spec=HttpError)
    http_error.resp = MagicMock(status=400)
    http_error.content = json.dumps(error_content).encode("utf-8")

    # Handle error
    with patch("app.services.youtube_error_handler.send_discord_alert") as mock_alert:
        with pytest.raises(YouTubeBadRequestError):
            await handle_youtube_upload_error(
                task, http_error, async_test_session, webhook_url="https://discord.com/webhook"
            )

        # Verify terminal failure alert sent with correct content
        mock_alert.assert_called_once()
        call_args = mock_alert.call_args
        assert call_args.kwargs["alert_type"] == "terminal_failure"
        assert call_args.kwargs["severity"] == "CRITICAL"
        assert "Task ID" in call_args.kwargs["fields"]
        assert "Error Code" in call_args.kwargs["fields"]
        assert "Error Reason" in call_args.kwargs["fields"]
        assert "Error Message" in call_args.kwargs["fields"]
        assert "Action" in call_args.kwargs["fields"]

    # Refresh task
    await async_test_session.refresh(task)

    # Assert task marked as terminal (no retry)
    assert task.status == TaskStatus.UPLOAD_ERROR
    error_log = json.loads(task.error_log)
    assert error_log["category"] == "permanent"
    assert task.next_retry_at is None  # No retry scheduled


@pytest.mark.asyncio
async def test_handle_permanent_error_401(async_test_session):
    """Test handling of permanent error (401 unauthorized)."""
    task = Task(
        id=uuid4(),
        channel_id=uuid4(),
        notion_page_id="test_page_123",
        title="Test Video Upload",
        topic="Pokemon Nature Documentary",
        story_direction="Dramatic nature documentary following wild Pokemon",
        status=TaskStatus.UPLOADING,
        retry_count=0,
    )
    async_test_session.add(task)
    await async_test_session.commit()

    # Mock 401 error
    error_content = {
        "error": {
            "code": 401,
            "message": "Invalid credentials",
            "errors": [{"reason": "authError"}],
        }
    }
    http_error = MagicMock(spec=HttpError)
    http_error.resp = MagicMock(status=401)
    http_error.content = json.dumps(error_content).encode("utf-8")

    # Handle error
    with pytest.raises(YouTubeBadRequestError):
        await handle_youtube_upload_error(task, http_error, async_test_session)

    # Refresh task
    await async_test_session.refresh(task)

    # Assert terminal failure
    assert task.status == TaskStatus.UPLOAD_ERROR
    error_log = json.loads(task.error_log)
    assert error_log["category"] == "permanent"
