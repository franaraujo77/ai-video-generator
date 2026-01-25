"""YouTube Publishing Integration - Upload + Notion Sync (Story 7.5).

This module integrates Story 7.4 (YouTube Upload) with Story 7.5 (Notion URL Sync).
Provides a complete publishing flow that can be called by the pipeline orchestrator.

Integration Flow:
    1. Upload video to YouTube (Story 7.4: upload_video)
    2. Construct YouTube URL from video_id (Story 7.5: construct_youtube_url)
    3. Sync URL to Notion database (Story 7.5: sync_youtube_url_to_notion)
    4. Update task status to PUBLISHED
    5. Handle fallback storage on Notion failures

Error Handling:
    - Upload errors: Re-raised as YouTubeUploadError/YouTubeUploadRetryError
    - Notion permanent errors: Fallback URL stored, task still updated to PUBLISHED
    - Notion transient errors: Re-raised as NotionSyncRetryError for retry
"""

import structlog
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Task, TaskStatus
from app.services.youtube_uploader import (
    upload_video,
    YouTubeUploadError,
    YouTubeUploadRetryError,
)
from app.services.notion_sync_service import (
    construct_youtube_url,
    sync_youtube_url_to_notion,
    NotionSyncError,
    NotionSyncRetryError,
)
from app.services.metadata_service import generate_metadata, MetadataDict

log = structlog.get_logger(__name__)


async def publish_video_to_youtube(
    task: Task,
    metadata: MetadataDict,
    db: AsyncSession,
    webhook_url: Optional[str] = None,
) -> str:
    """Publish video to YouTube and sync URL to Notion (Stories 7.4 + 7.5).

    This function orchestrates the complete YouTube publishing flow:
    1. Upload video to YouTube using resumable upload (Story 7.4)
    2. Extract video_id from upload response
    3. Construct YouTube URL (Story 7.5)
    4. Sync URL to Notion database with "Published" status (Story 7.5)
    5. Update task.youtube_url and task.status in database

    The function handles the short transaction pattern: it receives a database session
    for quota checking during upload, but the session should be closed during the
    actual upload and Notion sync (which are long-running operations). The caller
    should reopen the session to fetch the final task state.

    Args:
        task: Task in APPROVED status with video file ready
        metadata: YouTube metadata from Story 7.3 (title, description, tags, etc.)
        db: Async database session for quota tracking during upload
        webhook_url: Discord webhook URL for failure alerts (optional)

    Returns:
        YouTube video ID (e.g., "dQw4w9WgXcQ")

    Raises:
        YouTubeUploadError: Permanent upload failure (invalid metadata, credentials, quota)
        YouTubeUploadRetryError: Transient upload failure (network error, rate limit)
        NotionSyncRetryError: Transient Notion failure (rate limit, conflict, service down)

    Note on NotionSyncError:
        Permanent Notion errors (invalid token, permissions, validation) are caught
        and handled via fallback URL storage. The task is still updated to PUBLISHED
        status because the video was successfully uploaded to YouTube. Operators can
        manually recover the URL via Story 6.7 manual retry trigger.

    Example Usage:
        # In pipeline orchestrator or worker
        async with async_session_factory() as db:
            task = await db.get(Task, task_id)
            metadata = await generate_metadata(task, db)

        # Publish (closes DB connection during long operations)
        try:
            video_id = await publish_video_to_youtube(
                task, metadata, db, webhook_url="https://discord.com/..."
            )
        except NotionSyncRetryError:
            # Transient Notion error - retry later
            log.warning("notion_sync_retry_needed", task_id=str(task.id))
            raise

        # Fetch updated task state
        async with async_session_factory() as db:
            task = await db.get(Task, task_id)
            assert task.status == TaskStatus.PUBLISHED
            assert task.youtube_url is not None
    """
    # Step 1: Upload video to YouTube (Story 7.4)
    try:
        video_id = await upload_video(task, metadata, db)
    except (YouTubeUploadError, YouTubeUploadRetryError):
        # Re-raise upload errors for caller to handle
        raise

    # Step 2: Construct YouTube URL (Story 7.5)
    youtube_url = await construct_youtube_url(video_id)

    # Step 3: Sync URL to Notion (Story 7.5)
    # CRITICAL: Handle permanent Notion errors gracefully - video is already uploaded!
    try:
        await sync_youtube_url_to_notion(task, video_id, youtube_url, db, webhook_url)
        log.info(
            "youtube_publish_notion_sync_success",
            correlation_id=str(task.id),
            video_id=video_id,
        )
    except NotionSyncError as e:
        # Permanent Notion error - fallback URL already stored by sync function
        # Continue to update task status because video is successfully uploaded
        log.error(
            "youtube_publish_notion_sync_failed_permanent",
            correlation_id=str(task.id),
            video_id=video_id,
            error=str(e),
        )
        # Don't raise - task should still be marked as PUBLISHED
    except NotionSyncRetryError:
        # Transient Notion error - re-raise for caller to retry
        log.warning(
            "youtube_publish_notion_sync_failed_transient",
            correlation_id=str(task.id),
            video_id=video_id,
        )
        raise

    # Step 4: Update task in database
    # NOTE: This happens AFTER Notion sync to ensure URL is propagated
    # If Notion failed permanently, task is still updated (video is published)
    task.youtube_video_id = video_id
    task.youtube_url = youtube_url
    task.status = TaskStatus.PUBLISHED
    await db.commit()

    log.info(
        "youtube_publish_complete",
        correlation_id=str(task.id),
        video_id=video_id,
        status=TaskStatus.PUBLISHED.value,
    )

    return video_id
