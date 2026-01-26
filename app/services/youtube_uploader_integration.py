"""YouTube Publishing Integration - Upload + Notion Sync (Stories 7.5 + 7.6).

This module integrates Story 7.4 (YouTube Upload), Story 7.5 (Notion URL Sync),
and Story 7.6 (Upload Error Handling). Provides a complete publishing flow that
can be called by the pipeline orchestrator.

Integration Flow:
    1. Upload video to YouTube (Story 7.4: upload_video)
    2. Construct YouTube URL from video_id (Story 7.5: construct_youtube_url)
    3. Sync URL to Notion database (Story 7.5: sync_youtube_url_to_notion)
    4. Update task status to PUBLISHED
    5. Handle fallback storage on Notion failures

Error Handling (Story 7.6):
    - YouTube upload errors: Classified and handled by youtube_error_handler
        - Quota errors: Pause until midnight PST, send quota alert
        - Transient errors: Exponential backoff retry (1min → 5min → 15min → 1hr)
        - Permanent errors: Mark as terminal, send alert, no retry
    - Notion permanent errors: Fallback URL stored, task still updated to PUBLISHED
    - Notion transient errors: Re-raised as NotionSyncRetryError for retry
"""

import structlog
from google.api_core.exceptions import GoogleAPIError
from googleapiclient.errors import HttpError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Task, TaskStatus, utcnow
from app.services.alert_service import send_discord_alert
from app.services.compliance.ai_disclosure_manager import AIDisclosureManager
from app.services.compliance.exceptions import ComplianceViolationError
from app.services.compliance.pre_upload_compliance_validator import (
    PreUploadComplianceValidator,
)
from app.services.metadata_service import MetadataDict
from app.services.notion_sync_service import (
    NotionSyncError,
    NotionSyncRetryError,
    construct_youtube_url,
    sync_youtube_url_to_notion,
)
from app.services.youtube_error_handler import (
    handle_youtube_upload_error,
)
from app.services.youtube_uploader import (
    upload_video,
)

log = structlog.get_logger(__name__)


async def publish_video_to_youtube(
    task: Task,
    metadata: MetadataDict,
    db: AsyncSession,
    webhook_url: str | None = None,
) -> str:
    """Publish video to YouTube and sync URL to Notion (Stories 7.4 + 7.5 + 7.7).

    This function orchestrates the complete YouTube publishing flow:
    0. Validate YouTube Partner Program compliance (Story 7.7)
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
        ComplianceViolationError: Compliance checks failed (uniqueness, duplicate,
            frequency, evidence)
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
    # Step 0: Validate YouTube Partner Program compliance (Story 7.7)
    # CRITICAL: Compliance checks MUST pass before upload to prevent policy violations
    compliance_validator = PreUploadComplianceValidator()

    try:
        # Build video metadata dict for compliance checks
        video_metadata = {
            "title": metadata.get("title"),
            "description": metadata.get("description"),
            "tags": metadata.get("tags", []),
            "thumbnail_path": task.metadata.get("thumbnail_path") if task.metadata else None,
            "composite_path": task.metadata.get("composite_path") if task.metadata else None,
            "story_script": task.story_direction,
        }

        compliance_result = await compliance_validator.validate_before_upload(
            task, video_metadata, db
        )

        # Fix Issue #8: Don't set compliance_validated_at yet
        # Will be set after successful upload + AI disclosure (see Step 4)

        log.info(
            "compliance_validation_passed",
            correlation_id=str(task.id),
            uniqueness_scores=compliance_result["uniqueness_scores"],
            scheduled_upload_time=compliance_result["scheduled_upload_time"].isoformat(),
        )

    except ComplianceViolationError as e:
        # Compliance checks failed - update task status and re-raise
        task.status = TaskStatus.COMPLIANCE_VIOLATION
        task.error_log = (
            f"{task.error_log or ''}\n\n[{utcnow().isoformat()}] COMPLIANCE VIOLATION: {e!s}\n"
            f"Violation Type: {e.violation_type}\n"
            f"Validation Results: {e.validation_results}"
        )
        await db.commit()

        log.error(
            "compliance_violation",
            correlation_id=str(task.id),
            violation_type=e.violation_type,
            validation_results=e.validation_results,
        )

        # Fix Issue #5: Send Discord alert for compliance violations
        if webhook_url:
            await send_discord_alert(
                webhook_url=webhook_url,
                title="🚨 YouTube Compliance Violation",
                description=f"Task {task.id} failed compliance checks and cannot be uploaded",
                fields={
                    "Task ID": str(task.id),
                    "Channel ID": str(task.channel_id),
                    "Violation Type": e.violation_type,
                    "Details": str(e)[:500],  # Truncate long error messages
                    "Action": "Manual review required - fix issues and requeue task",
                },
                color="error",
            )

        raise

    # Step 1: Upload video to YouTube (Story 7.4 + Story 7.6 error handling)
    try:
        video_id = await upload_video(task, metadata, db)
    except (HttpError, GoogleAPIError, Exception) as e:
        # Story 7.6: Handle all YouTube upload errors with comprehensive error handling
        await handle_youtube_upload_error(task, e, db, webhook_url)
        # handle_youtube_upload_error updates task status and re-raises classified error
        raise

    # Step 1.5: Set AI disclosure via YouTube Data API (Story 7.7 - Fix Issue #3)
    # CRITICAL: Must be called after upload, before video goes public
    ai_disclosure_manager = AIDisclosureManager()

    try:
        # Get YouTube service from credentials
        from app.services.youtube_service import get_youtube_service

        youtube_service = await get_youtube_service(task.channel_id, db)

        # Set hasAlteredContent=true via YouTube Data API
        ai_disclosure_manager.set_ai_disclosure(video_id, youtube_service)

        # Validate disclosure was successfully set
        ai_disclosure_manager.validate_disclosure_set(video_id, youtube_service)

        log.info(
            "ai_disclosure_set_and_validated",
            correlation_id=str(task.id),
            video_id=video_id,
        )
    except Exception as e:
        # AI disclosure failed - this is a compliance violation, must not publish
        log.error(
            "ai_disclosure_failed",
            correlation_id=str(task.id),
            video_id=video_id,
            error=str(e),
        )

        # Update task status to compliance violation
        task.status = TaskStatus.COMPLIANCE_VIOLATION
        task.error_log = (
            f"{task.error_log or ''}\n\n[{utcnow().isoformat()}] AI DISCLOSURE FAILED: {e!s}\n"
            f"Video uploaded but AI disclosure could not be set. Upload blocked to prevent policy violation." # noqa: E501
        )
        await db.commit()

        if webhook_url:
            await send_discord_alert(
                webhook_url=webhook_url,
                title="🚨 AI Disclosure Failed",
                description=f"Video {video_id} uploaded but AI disclosure could not be set",
                fields={
                    "Task ID": str(task.id),
                    "Video ID": video_id,
                    "Error": str(e)[:500],
                    "Action": "Manual intervention required - set AI disclosure via YouTube Studio",
                },
                color="error",
            )

        raise ValueError(f"AI disclosure failed for video {video_id}: {e!s}") from e

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

    # Fix Issue #8: Set compliance_validated_at AFTER successful upload + AI disclosure
    # Only mark as validated when the entire compliance flow (checks + upload + disclosure) succeeds
    task.compliance_validated_at = utcnow()

    await db.commit()

    log.info(
        "youtube_publish_complete",
        correlation_id=str(task.id),
        video_id=video_id,
        status=TaskStatus.PUBLISHED.value,
        compliance_validated=True,
    )

    return video_id
