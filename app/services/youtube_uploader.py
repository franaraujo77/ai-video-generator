"""YouTube resumable upload service (Story 7.4).

This service uploads videos to YouTube using the resumable upload protocol with:
- Quota pre-checking to prevent exhaustion
- 1MB chunk uploads for reliability
- Network interruption recovery
- Progress logging every 30 seconds
- Comprehensive error handling (permanent vs transient)

Key Features:
- Resumable uploads using Google's mediaFileUpload with resumable=True
- Pre-flight quota checks to prevent quota exhaustion
- OAuth credential refresh from CredentialService (Story 7.2)
- Metadata from MetadataService (Story 7.3)
- Short database transaction pattern (claim → close → upload → reopen → update)

Error Classification:
- YouTubeUploadError: Permanent failures (invalid credentials, metadata, quota exceeded)
- YouTubeUploadRetryError: Transient failures (network errors, 5xx server errors, rate limits)

Usage:
    from app.services.youtube_uploader import upload_video
    from app.services.metadata_service import generate_metadata

    async with AsyncSession() as db:
        task = await db.get(Task, task_id)
        metadata = await generate_metadata(task, db)

    # Upload (closes DB connection during long upload)
    async with AsyncSession() as db:
        video_id = await upload_video(task, metadata, db)

    # Update task
    async with AsyncSession() as db:
        task = await db.get(Task, task_id)
        task.youtube_video_id = video_id
        task.status = TaskStatus.PUBLISHED
        await db.commit()
"""

import asyncio
import os
from datetime import date
from uuid import UUID

import structlog
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Channel, Task, TaskStatus, YouTubeQuotaUsage
from app.services.credential_service import CredentialService
from app.services.metadata_service import MetadataDict
from app.utils.filesystem import get_video_dir

log = structlog.get_logger(__name__)

# Quota costs per operation (YouTube Data API v3)
OPERATION_COSTS = {
    "upload": 1600,  # videos.insert
    "update": 50,  # videos.update
    "delete": 50,  # videos.delete
}

# Upload configuration
MAX_UPLOAD_RETRIES = 3  # Maximum retry attempts for transient failures
RETRY_BACKOFF_BASE = 2  # Exponential backoff base (seconds): 2^0=1s, 2^1=2s, 2^2=4s
PROGRESS_LOG_INTERVAL = 30  # Log upload progress every N seconds


class YouTubeUploadError(Exception):
    """Permanent upload failure (fix required).

    Raised when upload fails due to:
    - Invalid task status (task.status != APPROVED)
    - Video file not found on filesystem
    - Quota exceeded (daily limit reached)
    - Invalid metadata (400 Bad Request)
    - Invalid credentials (401 Unauthorized)
    - Insufficient permissions (403 Forbidden)
    - Channel not found (404 Not Found)

    These errors require manual intervention and should not be retried automatically.
    """

    pass


class YouTubeUploadRetryError(Exception):
    """Transient upload failure (will retry).

    Raised when upload fails due to:
    - Network timeout (ConnectionError, TimeoutError)
    - Server errors (500, 502, 503, 504)
    - Rate limit exceeded (429 Too Many Requests)

    These errors are transient and can be retried with exponential backoff.
    """

    pass


async def check_quota_available( # noqa: D417
    channel_id: str, operation: str, db: AsyncSession, correlation_id: str | None = None
) -> bool:
    """Check if YouTube quota is available for operation.

    Queries the YouTubeQuotaUsage table to verify if the operation can be performed
    without exceeding the daily quota limit. This is a pre-flight check that prevents
    quota exhaustion by checking before uploading.

    Args:
        channel_id: Channel UUID (string format).
        operation: Operation name ("upload", "update", "delete").
        db: Async database session.

    Returns:
        True if quota available, False if operation would exceed daily limit.

    Raises:
        YouTubeUploadError: If quota record not found for today (should exist from Story 7.0).

    Example:
        # Check before upload
        if not await check_quota_available(channel_id, "upload", db):
            raise YouTubeUploadError("Quota exceeded")
    """
    try:
        today = date.today()
        operation_cost = OPERATION_COSTS.get(operation, 0)

        # Convert channel_id string to UUID
        channel_uuid = UUID(channel_id) if isinstance(channel_id, str) else channel_id

        # Query today's quota usage for channel
        result = await db.execute(
            select(YouTubeQuotaUsage).where(
                YouTubeQuotaUsage.channel_id == channel_uuid, YouTubeQuotaUsage.date == today
            )
        )
        quota_usage = result.scalar_one_or_none()

        if not quota_usage:
            # Story 7.0 should create daily records automatically
            # If record missing, this is an unexpected error
            log.error(
                "quota_record_not_found",
                channel_id=str(channel_id),
                date=str(today),
            )
            raise YouTubeUploadError(
                f"Quota record not found for channel {channel_id} on {today}. "
                f"Story 7.0 quota reset should have created this record."
            )

        # Calculate remaining quota
        remaining = quota_usage.daily_limit - quota_usage.units_used
        quota_available = (quota_usage.units_used + operation_cost) <= quota_usage.daily_limit

        log_data = {
            "channel_id": str(channel_id),
            "operation": operation,
            "operation_cost": operation_cost,
            "units_used": quota_usage.units_used,
            "daily_limit": quota_usage.daily_limit,
            "remaining": remaining,
            "quota_available": quota_available,
        }
        if correlation_id:
            log_data["correlation_id"] = correlation_id

        log.info("quota_check", **log_data)

        return quota_available

    except YouTubeUploadError:
        # Re-raise known errors
        raise
    except Exception as e:
        log.error(
            "quota_check_unexpected_error",
            channel_id=str(channel_id),
            error=str(e),
            error_type=type(e).__name__,
        )
        raise YouTubeUploadError(f"Quota check failed: {e!s}") from e


async def update_quota_usage(channel_id: str, operation: str, db: AsyncSession) -> None:
    """Update quota usage after successful operation.

    Increments the YouTubeQuotaUsage.units_used for today's record after a successful
    YouTube API operation. This keeps quota tracking accurate for future pre-flight checks.

    Args:
        channel_id: Channel UUID (string format).
        operation: Operation name ("upload", "update", "delete").
        db: Async database session.

    Note:
        This function does NOT raise exceptions on failure to avoid breaking the upload flow.
        Quota tracking failures are logged as errors but do not interrupt successful uploads.

    Example:
        # After successful upload
        await update_quota_usage(channel_id, "upload", db)
    """
    try:
        today = date.today()
        operation_cost = OPERATION_COSTS.get(operation, 0)

        # Convert channel_id string to UUID
        channel_uuid = UUID(channel_id) if isinstance(channel_id, str) else channel_id

        # Get today's quota record
        result = await db.execute(
            select(YouTubeQuotaUsage).where(
                YouTubeQuotaUsage.channel_id == channel_uuid, YouTubeQuotaUsage.date == today
            )
        )
        quota_usage = result.scalar_one()

        # Increment usage
        quota_usage.units_used += operation_cost
        await db.commit()

        log.info(
            "quota_updated",
            channel_id=str(channel_id),
            operation=operation,
            cost=operation_cost,
            total_used=quota_usage.units_used,
            remaining=quota_usage.daily_limit - quota_usage.units_used,
        )

    except Exception as e:
        log.error("quota_update_failed", channel_id=str(channel_id), error=str(e))
        # Non-fatal error - don't raise (upload succeeded even if quota tracking failed)


async def upload_video(task: Task, metadata: MetadataDict, db: AsyncSession) -> str:
    """Upload video to YouTube using resumable upload protocol.

    This is the main entry point for Story 7.4. It performs the complete upload flow:
    1. Validate task status (must be APPROVED)
    2. Check video file exists on filesystem
    3. Pre-check quota availability
    4. Get OAuth credentials from CredentialService
    5. Build YouTube API client
    6. Create resumable upload with 1MB chunks
    7. Upload in chunks with progress logging
    8. Handle network errors (raise retry error)
    9. Extract video_id from response
    10. Update quota usage in database

    Args:
        task: Task in APPROVED status with video file ready.
        metadata: YouTube metadata from Story 7.3 (MetadataDict).
        db: Async database session for quota tracking.

    Returns:
        YouTube video ID (e.g., "dQw4w9WgXcQ").

    Raises:
        YouTubeUploadError: Permanent failure (invalid metadata, credentials, quota).
        YouTubeUploadRetryError: Transient failure (network error, rate limit).

    Example:
        task = await db.get(Task, task_id)
        metadata = await generate_metadata(task, db)
        video_id = await upload_video(task, metadata, db)

        # Update task with video_id
        task.youtube_video_id = video_id
        task.status = TaskStatus.PUBLISHED
        await db.commit()
    """
    try:
        # Step 1: Validate task status
        if task.status != TaskStatus.APPROVED:
            raise YouTubeUploadError(
                f"Cannot upload video for task in {task.status.value} status. "
                f"Status must be APPROVED."
            )

        # Step 2: Get channel for filesystem path (need channel.channel_id string, not UUID)
        result = await db.execute(select(Channel).where(Channel.id == task.channel_id))
        channel = result.scalar_one()

        # Get video file path using channel string ID and task ID
        video_dir = get_video_dir(channel.channel_id, str(task.id))
        video_path = video_dir / f"{task.id}_final.mp4"

        if not video_path.exists():
            raise YouTubeUploadError(f"Video file not found: {video_path}")

        file_size = video_path.stat().st_size
        file_size_mb = file_size / (1024 * 1024)

        log.info(
            "upload_starting",
            correlation_id=str(task.id),
            channel_id=channel.channel_id,
            video_path=str(video_path),
            file_size_bytes=file_size,
            file_size_mb=round(file_size_mb, 2),
        )

        # Step 3: Check quota availability
        quota_available = await check_quota_available(
            str(task.channel_id), "upload", db, correlation_id=str(task.id)
        )

        if not quota_available:
            raise YouTubeUploadError(
                "YouTube quota exceeded for today. Upload would exceed daily limit."
            )

        # Step 4: Get OAuth credentials
        credential_service = CredentialService()
        refresh_token = await credential_service.get_youtube_token(task.channel_id, db)

        # Build OAuth credentials object
        credentials = Credentials(
            token=None,  # Will be refreshed
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token", # noqa: S106
            client_id=os.environ["GOOGLE_CLIENT_ID"],
            client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        )

        # Refresh access token if needed
        if not credentials.valid:
            await asyncio.to_thread(credentials.refresh, Request())

        # Step 5: Build YouTube API client (sync call, use asyncio.to_thread)
        youtube = await asyncio.to_thread(build, "youtube", "v3", credentials=credentials)

        # Step 6: Build request body from metadata
        request_body = {
            "snippet": {
                "title": metadata["title"],
                "description": metadata["description"],
                "tags": metadata["tags"],
                "categoryId": metadata["category_id"],
            },
            "status": {"privacyStatus": metadata["privacy_status"]},
        }

        # Step 7: Create resumable upload (1MB chunks)
        media = MediaFileUpload(
            str(video_path),
            chunksize=1024 * 1024,  # 1MB chunks
            resumable=True,
        )

        request = youtube.videos().insert(
            part="snippet,status", body=request_body, media_body=media
        )

        # Step 8: Upload with progress tracking and retry logic
        response = None
        last_log_time = asyncio.get_event_loop().time()

        while response is None:
            # Retry loop for each chunk (up to MAX_UPLOAD_RETRIES attempts)
            chunk_uploaded = False

            for attempt in range(MAX_UPLOAD_RETRIES):
                try:
                    # Upload next chunk (sync call, use asyncio.to_thread)
                    status, response = await asyncio.to_thread(request.next_chunk)

                    if status:
                        progress_percent = int(status.progress() * 100)
                        current_time = asyncio.get_event_loop().time()

                        # Log progress every N seconds
                        if current_time - last_log_time >= PROGRESS_LOG_INTERVAL:
                            log.info(
                                "upload_progress",
                                correlation_id=str(task.id),
                                progress_percent=progress_percent,
                                bytes_uploaded=status.resumable_progress,
                                total_bytes=file_size,
                            )
                            last_log_time = current_time

                    # Chunk uploaded successfully
                    chunk_uploaded = True
                    break

                except HttpError as e:
                    # Classify HTTP errors as retriable or permanent
                    if e.resp.status in [500, 502, 503, 504]:
                        # Server error - retriable
                        if attempt < MAX_UPLOAD_RETRIES - 1:
                            # Retry with exponential backoff
                            delay = RETRY_BACKOFF_BASE**attempt
                            log.warning(
                                "upload_chunk_failed_retrying",
                                correlation_id=str(task.id),
                                error_code=e.resp.status,
                                attempt=attempt + 1,
                                max_retries=MAX_UPLOAD_RETRIES,
                                retry_delay=delay,
                            )
                            await asyncio.sleep(delay)
                            continue
                        else:
                            # Max retries reached
                            log.error(
                                "upload_chunk_failed_max_retries",
                                correlation_id=str(task.id),
                                error_code=e.resp.status,
                                max_retries=MAX_UPLOAD_RETRIES,
                            )
                            raise YouTubeUploadRetryError(
                                f"YouTube server error ({e.resp.status}) after {MAX_UPLOAD_RETRIES} retries: {e!s}" # noqa: E501
                            ) from e
                    elif e.resp.status == 429:
                        # Rate limit - retriable
                        if attempt < MAX_UPLOAD_RETRIES - 1:
                            delay = RETRY_BACKOFF_BASE**attempt
                            log.warning(
                                "upload_rate_limited_retrying",
                                correlation_id=str(task.id),
                                attempt=attempt + 1,
                                max_retries=MAX_UPLOAD_RETRIES,
                                retry_delay=delay,
                            )
                            await asyncio.sleep(delay)
                            continue
                        else:
                            log.error(
                                "upload_rate_limited_max_retries",
                                correlation_id=str(task.id),
                                max_retries=MAX_UPLOAD_RETRIES,
                            )
                            raise YouTubeUploadRetryError(
                                f"YouTube rate limit exceeded after {MAX_UPLOAD_RETRIES} retries"
                            ) from e
                    elif e.resp.status == 400:
                        # Bad request - permanent
                        log.error(
                            "upload_failed_invalid_metadata",
                            correlation_id=str(task.id),
                            error=str(e),
                        )
                        raise YouTubeUploadError(f"Invalid metadata: {e!s}") from e
                    elif e.resp.status in [401, 403]:
                        # Auth error - permanent
                        log.error(
                            "upload_failed_auth_error",
                            correlation_id=str(task.id),
                            error_code=e.resp.status,
                            error=str(e),
                        )
                        raise YouTubeUploadError(f"Authentication error: {e!s}") from e
                    else:
                        # Unknown error - permanent
                        log.error(
                            "upload_failed_unknown_http_error",
                            correlation_id=str(task.id),
                            error_code=e.resp.status,
                            error=str(e),
                        )
                        raise YouTubeUploadError(f"Upload failed: {e!s}") from e

                except (ConnectionError, TimeoutError) as e:
                    # Network error - retriable
                    if attempt < MAX_UPLOAD_RETRIES - 1:
                        delay = RETRY_BACKOFF_BASE**attempt
                        log.warning(
                            "upload_network_error_retrying",
                            correlation_id=str(task.id),
                            error=str(e),
                            error_type=type(e).__name__,
                            attempt=attempt + 1,
                            max_retries=MAX_UPLOAD_RETRIES,
                            retry_delay=delay,
                        )
                        await asyncio.sleep(delay)
                        continue
                    else:
                        log.error(
                            "upload_network_error_max_retries",
                            correlation_id=str(task.id),
                            error=str(e),
                            error_type=type(e).__name__,
                            max_retries=MAX_UPLOAD_RETRIES,
                        )
                        raise YouTubeUploadRetryError(
                            f"Network error after {MAX_UPLOAD_RETRIES} retries: {e!s}"
                        ) from e

            # If we didn't successfully upload chunk after all retries, break outer loop
            if not chunk_uploaded:
                break

        # Step 9: Extract video ID from response
        video_id = response["id"]

        log.info(
            "upload_completed",
            correlation_id=str(task.id),
            channel_id=str(task.channel_id),
            video_id=video_id,
            file_size_mb=round(file_size_mb, 2),
        )

        # Step 10: Update quota usage
        await update_quota_usage(str(task.channel_id), "upload", db)

        return video_id

    except (YouTubeUploadError, YouTubeUploadRetryError):
        # Re-raise known errors
        raise

    except Exception as e:
        # Unexpected error - log and raise as permanent
        log.error(
            "upload_unexpected_error",
            correlation_id=str(task.id),
            error=str(e),
            error_type=type(e).__name__,
        )
        raise YouTubeUploadError(f"Unexpected upload error: {e!s}") from e
