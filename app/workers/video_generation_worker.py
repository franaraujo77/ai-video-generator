"""Video Generation Worker.

This module implements the worker process for the video generation phase
(Step 3 of 8) of the video generation pipeline. It claims tasks from the queue
and orchestrates video generation via the VideoGenerationService.

Architecture Pattern:
    - Short transactions (claim → close DB → execute → reopen DB → update)
    - Stateless worker (no shared state between tasks)
    - Async execution throughout (non-blocking)
    - Structured logging with correlation IDs (task_id)

Transaction Pattern (CRITICAL - Architecture Decision 3):
    1. Claim task (short transaction, set status="generating_video")
    2. Close database connection
    3. Generate videos (36-90 minutes, outside transaction)
    4. Reopen database connection
    5. Update task (short transaction, set status="video_ready" or "video_error")

Error Handling:
    - CLIScriptError → Mark task "video_error", log details, allow retry
    - asyncio.TimeoutError → Mark task "video_error", log timeout
    - httpx.HTTPError → Mark task "video_error", log catbox upload failure
    - Exception → Mark task "video_error", log unexpected error

Dependencies:
    - Story 3.5: VideoGenerationService (business logic layer)
    - Story 3.1: CLI wrapper (run_cli_script, CLIScriptError)
    - Story 3.2: Filesystem helpers (path construction)
    - app/clients/catbox.py: Catbox image upload client
    - Epic 1: Database models (Task, TaskStatus)
    - Epic 2: Notion API client (status updates)

Usage:
    from app.workers.video_generation_worker import process_video_generation_task

    # Process single task
    await process_video_generation_task(task_id="abc123")

    # Worker loop (not yet implemented in this story)
    while True:
        task_id = await claim_next_task()
        await process_video_generation_task(task_id)
"""

import asyncio
from uuid import UUID

import httpx

from app.database import async_session_factory
from app.models import Task, TaskStatus
from app.services.cost_tracker import track_api_cost
from app.services.video_generation import VideoGenerationService
from app.utils.cli_wrapper import CLIScriptError
from app.utils.logging import get_logger

log = get_logger(__name__)


async def process_video_generation_task(task_id: str | UUID) -> None:
    """Process video generation for a single task.

    This function implements the short transaction pattern (Architecture Decision 3):
    1. Claim task (short transaction, set status="generating_video")
    2. Close database connection
    3. Generate videos (36-90 minutes, outside transaction)
    4. Reopen database connection
    5. Update task (short transaction, set status="video_ready" or "video_error")

    CRITICAL: NEVER hold DB connection during 36-90 minute video generation.

    Args:
        task_id: Task UUID from database (string or UUID object)

    Flow:
        1. Load task from database (get channel_id, project_id, topic, story_direction)
        2. Initialize VideoGenerationService(channel_id, project_id)
        3. Create video manifest (18 clips with motion prompts)
        4. Generate 18 video clips with CLI script invocations
        5. Update task status to "video_ready" and total_cost_usd
        6. Update Notion status (async, non-blocking)

    Error Handling:
        - CLIScriptError (non-retriable) → Mark "video_error", log details, allow retry
        - asyncio.TimeoutError → Mark "video_error", log timeout, allow retry
        - httpx.HTTPError (catbox upload) → Mark "video_error", allow retry
        - Exception → Mark "video_error", log unexpected error

    Raises:
        No exceptions (catches all and logs errors)

    Timeouts:
        - Per-clip timeout: 600 seconds (10 minutes)
        - Total time: 36-90 minutes (18 clips x 2-5 min each)

    Example:
        >>> await process_video_generation_task("abc123-def456-...")
        # Task claimed, videos generated, status updated to "video_ready"
    """
    # Convert string to UUID if needed
    if isinstance(task_id, str):
        task_id = UUID(task_id)

    # Ensure session factory is configured
    if async_session_factory is None:
        raise RuntimeError("Database not configured. Set DATABASE_URL environment variable.")

    # Initialize variables outside transaction scope
    channel_id_str = None
    project_id = None
    topic = None
    story_direction = None
    notion_page_id = None

    # Step 1: Claim task (short transaction)
    async with async_session_factory() as db, db.begin():
        task = await db.get(Task, task_id)
        if not task:
            log.error("task_not_found", task_id=str(task_id))
            return

        # Get channel_id string from relationship
        await db.refresh(task, ["channel"])  # Ensure relationship is loaded
        channel_id_str = task.channel.channel_id

        # Store task details for video generation
        project_id = str(task.id)  # Use task UUID as project_id
        topic = task.topic
        story_direction = task.story_direction
        notion_page_id = task.notion_page_id

        # Claim task by updating status
        task.status = TaskStatus.GENERATING_VIDEO
        await db.commit()

        log.info(
            "task_claimed",
            task_id=str(task_id),
            channel_id=channel_id_str,
            status="generating_video"
        )

    # Step 2: Generate videos (OUTSIDE transaction - DB connection closed)
    try:
        service = VideoGenerationService(channel_id_str, project_id)
        manifest = service.create_video_manifest(topic, story_direction)

        log.info(
            "video_generation_start",
            task_id=str(task_id),
            clip_count=len(manifest.clips),
            estimated_time_minutes=18 * 3.5  # 18 clips x 3.5 min average
        )

        result = await service.generate_videos(
            manifest,
            resume=False,  # Future enhancement: detect retries and set resume=True
            max_concurrent=5  # Kling rate limit
        )

        log.info(
            "video_generation_complete",
            task_id=str(task_id),
            generated=result["generated"],
            skipped=result["skipped"],
            failed=result["failed"],
            total_cost_usd=str(result["total_cost_usd"])
        )

        # Step 3: Track costs (short transaction)
        async with async_session_factory() as db, db.begin():
            task = await db.get(Task, task_id)
            if not task:
                log.error("task_not_found_for_cost_tracking", task_id=str(task_id))
                return

            await track_api_cost(
                db=db,
                task_id=task.id,
                component="kling_video_clips",
                cost_usd=result["total_cost_usd"],
                api_calls=result["generated"],
                units_consumed=result["generated"]
            )
            await db.commit()

        # Step 4: Update task (short transaction)
        async with async_session_factory() as db, db.begin():
            task = await db.get(Task, task_id)
            if not task:
                log.error("task_not_found_after_generation", task_id=str(task_id))
                return
            task.status = TaskStatus.VIDEO_READY
            task.total_cost_usd = task.total_cost_usd + float(result["total_cost_usd"])
            await db.commit()
            log.info("task_updated", task_id=str(task_id), status="video_ready")

        # Step 5: Cleanup service resources
        await service.cleanup()

        # Step 6: Update Notion (async, non-blocking)
        # Note: update_notion_status will be implemented in Epic 2 stories
        try:
            await update_notion_status(notion_page_id, "Video Ready")
        except Exception as e:
            log.warning("notion_update_failed", task_id=str(task_id), error=str(e))

    except CLIScriptError as e:
        log.error(
            "video_generation_cli_error",
            task_id=str(task_id),
            script=e.script,
            exit_code=e.exit_code,
            stderr=e.stderr[:500]  # Truncate stderr
        )

        async with async_session_factory() as db, db.begin():
            task = await db.get(Task, task_id)
            if task:
                task.status = TaskStatus.VIDEO_ERROR
                task.error_log = f"Video generation failed: {e.stderr}"
                await db.commit()

    except asyncio.TimeoutError:
        log.error("video_generation_timeout", task_id=str(task_id), timeout=600)

        async with async_session_factory() as db, db.begin():
            task = await db.get(Task, task_id)
            if task:
                task.status = TaskStatus.VIDEO_ERROR
                task.error_log = "Video generation timeout (10 minutes per clip exceeded)"
                await db.commit()

    except httpx.HTTPError as e:
        # Catbox upload or Kling API HTTP errors
        log.error(
            "video_generation_http_error",
            task_id=str(task_id),
            error=str(e),
            error_type=type(e).__name__
        )

        async with async_session_factory() as db, db.begin():
            task = await db.get(Task, task_id)
            if task:
                task.status = TaskStatus.VIDEO_ERROR
                task.error_log = f"HTTP error (catbox/Kling API): {e!s}"
                await db.commit()

    except Exception as e:
        log.error("video_generation_unexpected_error", task_id=str(task_id), error=str(e))

        async with async_session_factory() as db, db.begin():
            task = await db.get(Task, task_id)
            if task:
                task.status = TaskStatus.VIDEO_ERROR
                task.error_log = f"Unexpected error: {e!s}"
                await db.commit()


async def update_notion_status(notion_page_id: str, status: str) -> None:
    """Update Notion page status (stub for now).

    This function will be implemented in Epic 2 stories.
    For now, it's a no-op stub to prevent import errors.

    Args:
        notion_page_id: Notion page ID
        status: Status string to set

    Example:
        >>> await update_notion_status("page_123", "Video Ready")
    """
    # Stub implementation - will be replaced with actual Notion API call
    log.info("notion_status_update", page_id=notion_page_id, status=status)
