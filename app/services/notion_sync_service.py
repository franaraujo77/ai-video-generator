"""Notion sync service for YouTube URL updates (Story 7.5).

This service handles synchronization of YouTube URLs to Notion database after
successful video upload. Implements rate limiting, error classification, and
fallback storage for manual recovery when Notion API is unavailable.

Integration:
    - Story 7.4: Receives video_id from youtube_uploader.upload_video()
    - Story 2.2: Uses NotionClient with rate limiting (3 req/sec)
    - Story 5.6: Follows Notion property update patterns
    - Story 6.6: Uses send_discord_alert() for failure notifications
    - Story 1.3: Uses CredentialService for decrypting Notion token

Key Features:
    - URL Construction: Validates video_id format (11 chars, Base64)
    - Rate Limiting: AsyncLimiter enforces Notion API limit (3 req/sec)
    - Error Classification: Permanent (4xx auth/validation) vs Transient (429/409/503)
    - Fallback Storage: Writes to fallback_youtube_urls table on permanent errors
    - Retry-After Header: Respects 429 rate limit header for backoff timing
    - Security: Never logs Notion tokens or full YouTube URLs (logs video_id only)

Error Handling:
    - NotionSyncError: Permanent failures (invalid token, permissions, validation)
    - NotionSyncRetryError: Transient failures (rate limit, conflict, service down)
    - Fallback URL + Discord alert sent on permanent errors
"""

import re

import structlog
from aiolimiter import AsyncLimiter
from notion_client import AsyncClient
from notion_client.errors import APIResponseError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FallbackYouTubeURL, Task
from app.services.alert_service import send_discord_alert
from app.services.credential_service import CredentialService

log = structlog.get_logger(__name__)

# Notion rate limiter: 3 requests per second per integration (Story 2.2 pattern)
# CRITICAL: Must be module-level singleton to work across all function calls
rate_limiter = AsyncLimiter(max_rate=3, time_period=1)

# Video ID validation pattern (11 characters, Base64: A-Z, a-z, 0-9, hyphen, underscore)
VIDEO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{11}$")


class NotionSyncError(Exception):
    """Permanent Notion sync failure (fix required, don't retry).

    Examples:
        - 400 validation_error: Invalid property schema
        - 401 unauthorized: Invalid Notion API token
        - 403 restricted_resource: Missing integration permissions
        - 404 object_not_found: Page not found or not shared with integration
        - Task missing notion_page_id
        - Invalid video_id format
    """

    pass


class NotionSyncRetryError(Exception):
    """Transient Notion sync failure (will retry with exponential backoff).

    Examples:
        - 429 rate_limited: Exceeded 3 req/sec limit (respect Retry-After header)
        - 409 conflict: Concurrent modification (retry after short delay)
        - 503 service_unavailable: Notion temporarily down (retry after delay)
    """

    pass


async def construct_youtube_url(video_id: str) -> str:
    """Construct YouTube URL from video ID.

    Args:
        video_id: YouTube video ID (11 characters, Base64 format)

    Returns:
        Full YouTube URL (e.g., "https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    Raises:
        NotionSyncError: If video_id format is invalid

    Example:
        >>> url = await construct_youtube_url("dQw4w9WgXcQ")
        >>> print(url)
        https://www.youtube.com/watch?v=dQw4w9WgXcQ
    """
    # Validate video ID format (11 chars, Base64)
    if not video_id or not VIDEO_ID_PATTERN.match(video_id):
        log.error(
            "youtube_url_validation_failed",
            video_id=video_id,
            expected_format="11 chars, Base64 (A-Za-z0-9_-)",
        )
        raise NotionSyncError(f"Invalid video ID format: {video_id}")

    # Construct standard YouTube URL (ALWAYS use this format, NOT youtu.be or embed)
    youtube_url = f"https://www.youtube.com/watch?v={video_id}"

    log.info(
        "youtube_url_constructed",
        video_id=video_id,
        url_format="https://www.youtube.com/watch?v={video_id}",
    )

    return youtube_url


async def sync_youtube_url_to_notion(
    task: Task,
    video_id: str,
    youtube_url: str,
    db: AsyncSession,
    webhook_url: str | None = None,
) -> None:
    """Update Notion page with YouTube URL and Published status.

    This function syncs the YouTube URL to Notion after successful video upload.
    If Notion API fails, the URL is stored in fallback table for manual recovery.

    Args:
        task: Task with notion_page_id and channel_id
        video_id: YouTube video ID (e.g., "dQw4w9WgXcQ")
        youtube_url: Full YouTube URL (e.g., "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        db: Database session for fallback logging
        webhook_url: Discord webhook URL for alerts (optional)

    Raises:
        NotionSyncError: Permanent failure (invalid credentials, missing permissions)
        NotionSyncRetryError: Transient failure (rate limit, conflict, service unavailable)

    Error Handling:
        - Permanent errors (4xx auth/validation): Store fallback URL, send alert,
          raise NotionSyncError
        - Transient errors (429/409/503): Log warning, raise NotionSyncRetryError for retry
        - Unknown errors: Store fallback URL, send alert, raise NotionSyncError

    Example:
        >>> try:
        ...     await sync_youtube_url_to_notion(task, "dQw4w9WgXcQ", "https://...", db)
        ... except NotionSyncRetryError:
        ...     # Retry with exponential backoff
        ...     await asyncio.sleep(backoff_delay)
        ...     await sync_youtube_url_to_notion(...)
        ... except NotionSyncError:
        ...     # Fallback URL already stored, manual recovery required
        ...     log.error("notion_sync_permanent_failure", task_id=task.id)
    """
    try:
        # Validate task has Notion page ID (check for None or empty string)
        if not task.notion_page_id or task.notion_page_id.strip() == "":
            log.error(
                "notion_sync_missing_page_id",
                correlation_id=str(task.id),
                task_id=str(task.id),
            )
            raise NotionSyncError(f"Task {task.id} has no notion_page_id. Cannot sync YouTube URL.")

        # Get Notion API token (decrypted from database)
        credential_service = CredentialService()
        notion_token = await credential_service.get_notion_token(task.channel_id, db)

        if not notion_token:
            log.error(
                "notion_token_not_found",
                correlation_id=str(task.id),
                channel_id=str(task.channel_id),
            )
            # Store fallback URL before raising
            await store_fallback_url(task, video_id, youtube_url, db, webhook_url)
            raise NotionSyncError(f"No Notion token found for channel {task.channel_id}")

        # Build Notion client
        notion = AsyncClient(auth=notion_token)

        # Build property update payload
        # CRITICAL: Must match Notion database schema property names
        # "youtube_url" is a URL property type
        # "Status" is a status property type with value "Published"
        properties = {
            "youtube_url": {"url": youtube_url},
            "Status": {"status": {"name": "Published"}},
        }

        log.info(
            "notion_update_starting",
            correlation_id=str(task.id),
            notion_page_id=task.notion_page_id,
            video_id=video_id,
        )

        # Update Notion page with rate limiting (3 req/sec)
        # CRITICAL: AsyncLimiter context manager enforces rate limit
        async with rate_limiter:
            await notion.pages.update(
                page_id=task.notion_page_id,
                properties=properties,
            )

        log.info(
            "notion_update_completed",
            correlation_id=str(task.id),
            notion_page_id=task.notion_page_id,
            video_id=video_id,
        )

    except APIResponseError as error:
        # Classify Notion API errors into permanent vs transient
        # Permanent: 400/401/403/404 → don't retry, store fallback, alert
        # Transient: 429/409/503 → retry with backoff
        if error.code in [
            "validation_error",
            "unauthorized",
            "restricted_resource",
            "object_not_found",
        ]:
            # Permanent errors - don't retry
            log.error(
                "notion_sync_permanent_error",
                correlation_id=str(task.id),
                error_code=error.code,
                error_message=str(error),
            )

            # Store fallback URL for manual recovery
            await store_fallback_url(task, video_id, youtube_url, db, webhook_url)

            raise NotionSyncError(
                f"Permanent Notion error ({error.code}): {error.args[0]}"
            ) from error

        elif error.code in ["rate_limited", "conflict", "service_unavailable"]:
            # Transient errors - retry with exponential backoff
            log.warning(
                "notion_sync_transient_error",
                correlation_id=str(task.id),
                error_code=error.code,
                error_message=str(error),
            )

            # Respect Retry-After header for rate limiting (429)
            if error.code == "rate_limited":
                # Extract Retry-After header (integer seconds)
                retry_after = int(error.headers.get("Retry-After", 5))
                log.info(
                    "rate_limit_triggered",
                    correlation_id=str(task.id),
                    retry_after_seconds=retry_after,
                )

            raise NotionSyncRetryError(
                f"Transient Notion error ({error.code}): {error.args[0]}"
            ) from error

        else:
            # Unknown error - treat as permanent
            log.error(
                "notion_sync_unknown_error",
                correlation_id=str(task.id),
                error_code=error.code,
                error_message=str(error),
            )

            # Store fallback URL for manual recovery
            await store_fallback_url(task, video_id, youtube_url, db, webhook_url)

            raise NotionSyncError(
                f"Unknown Notion error ({error.code}): {error.args[0]}"
            ) from error

    except Exception as e:
        # Unexpected error (network issue, invalid response, etc.)
        log.error(
            "notion_sync_unexpected_error",
            correlation_id=str(task.id),
            error=str(e),
            error_type=type(e).__name__,
        )

        # Store fallback URL for manual recovery
        await store_fallback_url(task, video_id, youtube_url, db, webhook_url)

        raise NotionSyncError(f"Unexpected sync error: {e!s}") from e


async def store_fallback_url(
    task: Task,
    video_id: str,
    youtube_url: str,
    db: AsyncSession,
    webhook_url: str | None = None,
) -> None:
    """Store YouTube URL in fallback table for manual recovery.

    This function is called when Notion sync fails permanently. The fallback URL
    record can be manually recovered via Story 6.7 manual retry trigger.

    Args:
        task: Task that failed Notion sync
        video_id: YouTube video ID
        youtube_url: Full YouTube URL
        db: Database session
        webhook_url: Discord webhook URL for alerts (optional)

    Side Effects:
        - Creates FallbackYouTubeURL record in database
        - Sends Discord alert to operators with recovery instructions
        - Logs fallback_url_stored event for audit trail

    Example:
        >>> await store_fallback_url(task, "dQw4w9WgXcQ", "https://...", db)
        # Creates fallback record and sends Discord alert:
        # "🚨 YouTube URL Sync Failed - Manual Recovery Required"
    """
    try:
        # Create fallback record
        fallback = FallbackYouTubeURL(
            task_id=task.id,
            channel_id=task.channel_id,
            video_id=video_id,
            youtube_url=youtube_url,
        )

        db.add(fallback)
        await db.commit()

        log.warning(
            "fallback_url_stored",
            correlation_id=str(task.id),
            video_id=video_id,
            fallback_id=str(fallback.id),
        )

        # Send Discord alert for manual intervention
        # CRITICAL: Only send if webhook_url is provided
        if webhook_url:
            await send_discord_alert(
                alert_type="terminal_failure",
                severity="CRITICAL",
                title="🚨 YouTube URL Sync Failed",
                description=f"Notion sync failed for task {task.id}. URL stored in fallback table for manual recovery.",  # noqa: E501
                fields={
                    "Task ID": str(task.id),
                    "Video ID": video_id,
                    "Fallback ID": str(fallback.id),
                    "Recovery Instructions": f"Use Story 6.7 manual retry trigger with task_id={task.id}",  # noqa: E501
                },
                webhook_url=webhook_url,
                correlation_id=task.id,
            )

    except Exception as e:
        # Fallback storage failed - CRITICAL
        # This is worst-case scenario: upload succeeded, Notion failed, AND fallback failed
        # The YouTube URL is only in memory at this point
        log.error(
            "fallback_storage_failed",
            correlation_id=str(task.id),
            video_id=video_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        # Don't raise - best effort fallback
        # The youtube_url will still be set in task.youtube_url field
