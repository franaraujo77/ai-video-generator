"""YouTube Upload Error Handling (Story 7.6).

This module provides comprehensive error handling for YouTube API upload failures,
including error classification, quota management, and retry orchestration.

Error Classification:
    - 403 quotaExceeded → YouTubeQuotaExceededError (pause until midnight PST)
    - 500/503 server errors → YouTubeTransientError (exponential backoff retry)
    - 400/401/404 client errors → YouTubeBadRequestError (permanent failure, no retry)

Retry Strategy:
    - Quota errors: Pause until midnight PST (YouTube quota resets at midnight Pacific Time)
    - Transient errors: Exponential backoff (1min → 5min → 15min → 1hr → terminal)
    - Permanent errors: No retry, alert immediately

Integration:
    - Story 6.2: Uses retry_orchestrator MAX_RETRY_ATTEMPTS = 5 constant
    - Story 6.6: Uses alert_service for Discord webhook alerts
    - Story 7.4: Wraps youtube_uploader.upload_video() with error handling
    - Story 7.5: Integrates with youtube_uploader_integration for complete flow
"""

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import pytz
import structlog
from google.api_core.exceptions import GoogleAPIError
from googleapiclient.errors import HttpError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Task, TaskStatus
from app.services.alert_service import send_discord_alert

log = structlog.get_logger(__name__)

# Story 6.2: Maximum retry attempts before terminal failure
MAX_RETRIES = 5

# Exponential backoff schedule from retry_orchestrator (Story 6.2)
RETRY_DELAYS = [
    timedelta(minutes=1),  # Attempt 1
    timedelta(minutes=5),  # Attempt 2
    timedelta(minutes=15),  # Attempt 3
    timedelta(hours=1),  # Attempt 4
    # Attempt 5 = terminal (no retry)
]

# Maximum error log size to prevent DoS (10KB)
MAX_ERROR_LOG_SIZE = 10240


def _truncate_error_log(error_data: dict[str, Any]) -> str:
    """Truncate error log if it exceeds MAX_ERROR_LOG_SIZE.

    Args:
        error_data: Error data dictionary to serialize

    Returns:
        JSON string, truncated if necessary
    """
    error_log_json = json.dumps(error_data)
    if len(error_log_json) > MAX_ERROR_LOG_SIZE:
        # Truncate to prevent DoS
        truncated_data = {
            "error": "Error log truncated (exceeds 10KB limit)",
            "original_size": len(error_log_json),
            "truncated_at": datetime.now(timezone.utc).isoformat(),
        }
        error_log_json = json.dumps(truncated_data)
    return error_log_json


class YouTubeUploadError(Exception):
    """Base class for YouTube upload errors.

    Attributes:
        error_content: Parsed JSON error response from YouTube API
        status_code: HTTP status code
        error_reason: YouTube API error reason code
        message: Error message text
        raw_response: Full error response for debugging
    """

    def __init__(self, error_content: dict[str, Any], raw_response: str | None = None):
        """Initialize YouTubeUploadError.

        Args:
            error_content: Parsed error response from YouTube API
            raw_response: Full HTTP error response (optional, for debugging)
        """
        self.error_content = error_content
        self.status_code = error_content.get("error", {}).get("code")
        errors_list = error_content.get("error", {}).get("errors", [])
        error_details = errors_list[0] if errors_list else {}
        self.error_reason = error_details.get("reason")
        self.message = error_content.get("error", {}).get("message", "Unknown error")
        self.raw_response = raw_response
        super().__init__(self.message)


class YouTubeQuotaExceededError(YouTubeUploadError):
    """YouTube quota exceeded - retry at midnight PST.

    This error occurs when the channel has exhausted its daily YouTube API quota
    (default: 10,000 units/day, uploads cost 1,600 units = ~6 uploads/day).

    Retry Strategy:
        - Pause uploads until midnight Pacific Time (PST/PDT)
        - Send Discord alert with quota status and reset time
        - Update task status to UPLOAD_ERROR_RETRYING
    """

    pass


class YouTubeBadRequestError(YouTubeUploadError):
    """Bad request - permanent error, no retry.

    This error indicates a client-side issue that won't resolve on retry:
        - 400: Invalid metadata, malformed request
        - 401: Invalid OAuth token, authentication failure
        - 404: Video not found, missing resource

    Retry Strategy:
        - No retry - mark task as UPLOAD_ERROR (terminal)
        - Send Discord alert for manual intervention
        - Log structured error details for debugging
    """

    pass


class YouTubeTransientError(YouTubeUploadError):
    """Transient server error - retry with exponential backoff.

    This error indicates a temporary server-side issue that may resolve on retry:
        - 500: Backend error
        - 502: Bad gateway
        - 503: Service unavailable

    Retry Strategy:
        - Exponential backoff: 1min → 5min → 15min → 1hr
        - Max 5 attempts, then mark as terminal failure
        - Send Discord alert on retry exhaustion
    """

    pass


def calculate_quota_reset_time() -> datetime:
    """Calculate next midnight PST for YouTube quota reset.

    YouTube API quotas reset at midnight Pacific Time (PST/PDT), which is
    UTC-8 during standard time and UTC-7 during daylight saving time.

    This function correctly handles timezone conversion and daylight saving
    time transitions using pytz.

    Returns:
        datetime: Next midnight PST/PDT (timezone-aware)

    Example:
        >>> # Called at 2026-01-25 14:30 PST (UTC-8)
        >>> calculate_quota_reset_time()  # doctest: +SKIP
        datetime(2026, 1, 26, 0, 0, 0, tzinfo=<DstTzInfo 'US/Pacific' PST-1 day, 16:00:00 STD>)

        >>> # Called at 2026-06-15 14:30 PDT (UTC-7, daylight saving)
        >>> calculate_quota_reset_time()  # doctest: +SKIP
        datetime(2026, 06, 16, 0, 0, 0, tzinfo=<DstTzInfo 'US/Pacific' PDT-1 day, 17:00:00 DST>)
    """
    pst = pytz.timezone("US/Pacific")
    now_pst = datetime.now(pst)

    # Get today's midnight PST
    today_midnight = now_pst.replace(hour=0, minute=0, second=0, microsecond=0)

    # If already past midnight, use tomorrow's midnight
    if now_pst >= today_midnight:
        next_midnight = today_midnight + timedelta(days=1)
    else:
        next_midnight = today_midnight

    return next_midnight


def classify_youtube_upload_error(http_error: HttpError) -> YouTubeUploadError:
    """Classify YouTube API error into specific exception type.

    Parses YouTube API error response and maps to appropriate error class:
        - 403 + quotaExceeded → YouTubeQuotaExceededError
        - 500/502/503/429 → YouTubeTransientError
        - 400/401/404 → YouTubeBadRequestError (permanent)

    Args:
        http_error: HttpError from googleapiclient.errors

    Returns:
        YouTubeUploadError subclass instance

    Example:
        >>> # Mock HttpError for quota exceeded
        >>> http_error = HttpError(
        ...     resp=MagicMock(status=403),
        ...     content=json.dumps(
        ...         {
        ...             "error": {
        ...                 "code": 403,
        ...                 "message": "Quota exceeded",
        ...                 "errors": [{"reason": "quotaExceeded", "domain": "youtube.quota"}],
        ...             }
        ...         }
        ...     ).encode("utf-8"),
        ... )
        >>> classify_youtube_upload_error(http_error)  # doctest: +SKIP
        YouTubeQuotaExceededError(...)
    """
    try:
        error_content = json.loads(http_error.content.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
        # Fallback if error content is not valid JSON
        error_content = {
            "error": {
                "code": getattr(http_error.resp, "status", 500),
                "message": str(http_error),
                "errors": [],
            }
        }

    error_code = error_content.get("error", {}).get("code")
    errors_list = error_content.get("error", {}).get("errors", [])
    error_reason = errors_list[0].get("reason") if errors_list else None

    log.info(
        "youtube_error_classified",
        error_code=error_code,
        error_reason=error_reason,
        error_category=None,  # Set after classification
    )

    # Quota exceeded - pause until midnight PST
    if error_code == 403 and error_reason == "quotaExceeded":
        return YouTubeQuotaExceededError(
            error_content, raw_response=http_error.content.decode("utf-8")
        )

    # Transient errors - retry with exponential backoff
    if error_code in [500, 502, 503, 429] or error_reason in [
        "backendError",
        "serviceUnavailable",
        "rateLimitExceeded",
    ]:
        return YouTubeTransientError(error_content, raw_response=http_error.content.decode("utf-8"))

    # Permanent errors (400, 401, 404, etc.) - no retry
    return YouTubeBadRequestError(error_content, raw_response=http_error.content.decode("utf-8"))


async def handle_youtube_upload_error(
    task: Task, error: Exception, db: AsyncSession, webhook_url: str | None = None
) -> None:
    """Handle YouTube upload error with appropriate retry strategy.

    This function implements the complete error handling flow for YouTube uploads:
    1. Classify error (quota/transient/permanent)
    2. Update task status and error_log
    3. Schedule retry or mark as terminal
    4. Send Discord alerts

    Error Handling Logic:
        - YouTubeQuotaExceededError:
            - Schedule retry at midnight PST
            - Update status to UPLOAD_ERROR_RETRYING
            - Send quota exhaustion alert

        - YouTubeBadRequestError:
            - Mark as permanent failure (UPLOAD_ERROR)
            - No retry scheduled
            - Send terminal error alert

        - YouTubeTransientError:
            - Check retry count < MAX_RETRIES
            - If exhausted: Mark as terminal (UPLOAD_ERROR), send alert
            - If not exhausted: Schedule exponential backoff retry, update status

    Args:
        task: Task that failed upload
        error: Exception from upload attempt (HttpError, GoogleAPIError, or other)
        db: Database session for task updates
        webhook_url: Discord webhook URL for alerts (optional, defaults to env var)

    Raises:
        YouTubeUploadError: Re-raises classified error after handling

    Example:
        >>> # In youtube_uploader_integration.py
        >>> try:
        ...     video_id = await upload_video(task, metadata, db)
        ... except HttpError as e:
        ...     await handle_youtube_upload_error(task, e, db, webhook_url)
        ...     # Error handled - task status updated, retry scheduled
    """
    # Classify error
    if isinstance(error, HttpError):
        youtube_error = classify_youtube_upload_error(error)
    elif isinstance(error, GoogleAPIError):
        # Treat unexpected Google API errors as transient
        log.warning(
            "google_api_error_as_transient",
            correlation_id=str(task.id),
            error_type=type(error).__name__,
            error_message=str(error),
        )
        youtube_error = YouTubeTransientError(
            {
                "error": {
                    "code": 500,
                    "message": str(error),
                    "errors": [{"reason": "unexpectedGoogleAPIError"}],
                }
            }
        )
    else:
        # Non-YouTube error - treat as transient for safety
        log.warning(
            "unexpected_exception_as_transient",
            correlation_id=str(task.id),
            error_type=type(error).__name__,
            error_message=str(error),
        )
        youtube_error = YouTubeTransientError(
            {
                "error": {
                    "code": 500,
                    "message": str(error),
                    "errors": [{"reason": "unexpectedException"}],
                }
            }
        )

    log.error(
        "youtube_upload_error_handled",
        correlation_id=str(task.id),
        error_type=type(youtube_error).__name__,
        error_code=youtube_error.status_code,
        error_reason=youtube_error.error_reason,
    )

    # Get webhook URL from env if not provided
    if webhook_url is None:
        webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "")

    # Validate webhook URL (must be non-empty string for alerts to work)
    webhook_url_valid = (
        webhook_url and isinstance(webhook_url, str) and len(webhook_url.strip()) > 0
    )

    # Handle quota exceeded
    if isinstance(youtube_error, YouTubeQuotaExceededError):
        reset_time = calculate_quota_reset_time()
        hours_until_reset = (
            reset_time - datetime.now(pytz.timezone("US/Pacific"))
        ).total_seconds() / 3600

        # Update task
        task.retry_count += 1
        task.next_retry_at = reset_time
        task.status = TaskStatus.UPLOAD_ERROR_RETRYING
        task.error_log = _truncate_error_log(
            {
                "error": youtube_error.message,
                "error_code": youtube_error.status_code,
                "error_reason": youtube_error.error_reason,
                "category": "quota",
                "retry_count": task.retry_count,
                "quota_reset_at": reset_time.isoformat(),
            }
        )
        await db.commit()

        # Send quota alert
        if webhook_url_valid:
            await send_discord_alert(
                alert_type="quota_exhausted",
                severity="WARNING",
                title="⚠️ YouTube Quota Exceeded",
                description=f"Task **{task.id}** hit YouTube quota limit. Uploads paused until quota resets at midnight PST.", # noqa: E501
                fields={
                    "Task ID": str(task.id),
                    "Channel ID": str(task.channel_id),
                    "Quota Reset": reset_time.strftime("%Y-%m-%d %H:%M:%S %Z"),
                    "Hours Until Reset": f"{hours_until_reset:.1f}",
                    "Action": "Uploads paused until midnight PST",
                },
                webhook_url=webhook_url,
                correlation_id=str(task.id),
            )

        log.warning(
            "quota_retry_scheduled",
            correlation_id=str(task.id),
            quota_reset_at=reset_time.isoformat(),
            hours_until_reset=hours_until_reset,
        )

        raise youtube_error

    # Handle permanent errors
    elif isinstance(youtube_error, YouTubeBadRequestError):
        # Mark as permanent failure
        task.status = TaskStatus.UPLOAD_ERROR
        task.error_log = _truncate_error_log(
            {
                "error": youtube_error.message,
                "error_code": youtube_error.status_code,
                "error_reason": youtube_error.error_reason,
                "category": "permanent",
                "failed_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        await db.commit()

        # Send terminal failure alert
        if webhook_url_valid:
            await send_discord_alert(
                alert_type="terminal_failure",
                severity="CRITICAL",
                title="🚨 YouTube Upload Permanent Error",
                description=f"Task **{task.id}** failed with permanent error. Manual intervention required.", # noqa: E501
                fields={
                    "Task ID": str(task.id),
                    "Error Code": str(youtube_error.status_code),
                    "Error Reason": youtube_error.error_reason or "unknown",
                    "Error Message": youtube_error.message,
                    "Action": "Manual intervention required - fix metadata or request",
                },
                webhook_url=webhook_url,
                correlation_id=str(task.id),
            )

        log.error(
            "youtube_upload_permanent_error",
            correlation_id=str(task.id),
            error_code=youtube_error.status_code,
            error_reason=youtube_error.error_reason,
        )

        raise youtube_error

    # Handle transient errors
    elif isinstance(youtube_error, YouTubeTransientError):
        # Check retry exhaustion
        if task.retry_count >= MAX_RETRIES:
            # Mark as terminal failure
            task.status = TaskStatus.UPLOAD_ERROR
            task.error_log = _truncate_error_log(
                {
                    "error": youtube_error.message,
                    "error_code": youtube_error.status_code,
                    "error_reason": youtube_error.error_reason,
                    "category": "transient",
                    "retry_attempts": task.retry_count,
                    "exhausted_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            await db.commit()

            # Send retry exhaustion alert
            if webhook_url_valid:
                await send_discord_alert(
                    alert_type="terminal_failure",
                    severity="CRITICAL",
                    title="🚨 YouTube Upload Retry Exhausted",
                    description=f"Task **{task.id}** failed after **{MAX_RETRIES}** retries. Manual intervention required.", # noqa: E501
                    fields={
                        "Task ID": str(task.id),
                        "Error Code": str(youtube_error.status_code),
                        "Retry Attempts": str(task.retry_count),
                        "Last Error": youtube_error.message,
                        "Action": "Manual intervention required - check YouTube API status",
                    },
                    webhook_url=webhook_url,
                    correlation_id=str(task.id),
                )

            log.error(
                "youtube_upload_retry_exhausted",
                correlation_id=str(task.id),
                retry_count=task.retry_count,
            )

            raise ValueError(f"Retry exhausted for task {task.id}")

        # Schedule exponential backoff retry
        retry_delay = RETRY_DELAYS[task.retry_count]
        next_retry_at = datetime.now(timezone.utc) + retry_delay

        task.retry_count += 1
        task.next_retry_at = next_retry_at
        task.status = TaskStatus.UPLOAD_ERROR_RETRYING
        task.error_log = _truncate_error_log(
            {
                "error": youtube_error.message,
                "error_code": youtube_error.status_code,
                "error_reason": youtube_error.error_reason,
                "category": "transient",
                "retry_count": task.retry_count,
                "next_retry_at": next_retry_at.isoformat(),
            }
        )
        await db.commit()

        log.warning(
            "youtube_upload_retry_scheduled",
            correlation_id=str(task.id),
            retry_count=task.retry_count,
            next_retry_at=next_retry_at.isoformat(),
            delay_minutes=retry_delay.total_seconds() / 60,
        )

        raise youtube_error
