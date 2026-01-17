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
from datetime import datetime, timezone
from uuid import UUID

import httpx

from app.clients.notion import NotionClient
from app.config import get_notion_api_token
from app.database import async_session_factory
from app.models import Task, TaskStatus
from app.services.cost_tracker import track_api_cost
from app.services.notion_video_service import NotionVideoService
from app.services.video_generation import VideoGenerationService
from app.utils.cli_wrapper import CLIScriptError
from app.utils.logging import get_logger
from app.utils.video_optimization import get_video_duration, optimize_video_for_streaming

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
            status="generating_video",
        )

    # Step 2: Generate videos (OUTSIDE transaction - DB connection closed)
    try:
        # Check for partial regeneration (Story 5.4 AC3)
        async with async_session_factory() as db:
            task = await db.get(Task, task_id)
            if not task:
                log.error("task_not_found_for_partial_regen_check", task_id=str(task_id))
                return
            metadata = task.step_completion_metadata or {}
            failed_clip_numbers = metadata.get("failed_clip_numbers", [])

        service = VideoGenerationService(channel_id_str, project_id)
        manifest = service.create_video_manifest(topic, story_direction)

        # Partial regeneration: only generate failed clips if specified
        if failed_clip_numbers:
            log.info(
                "video_generation_partial_start",
                task_id=str(task_id),
                failed_clips=failed_clip_numbers,
                clip_count=len(failed_clip_numbers),
                estimated_time_minutes=len(failed_clip_numbers) * 3.5,
            )
            # Filter manifest to only include failed clips
            manifest.clips = [c for c in manifest.clips if c["clip_number"] in failed_clip_numbers]
        else:
            log.info(
                "video_generation_start",
                task_id=str(task_id),
                clip_count=len(manifest.clips),
                estimated_time_minutes=18 * 3.5,  # 18 clips x 3.5 min average
            )

        result = await service.generate_videos(
            manifest,
            resume=False,  # Resume logic handled by partial regeneration
            max_concurrent=5,  # Kling rate limit
        )

        # Clear failed_clip_numbers after successful regeneration
        if failed_clip_numbers:
            async with async_session_factory() as db, db.begin():
                task = await db.get(Task, task_id)
                if task and task.step_completion_metadata:
                    task.step_completion_metadata.pop("failed_clip_numbers", None)
                    await db.commit()
                    log.info(
                        "video_partial_regeneration_cleared",
                        task_id=str(task_id),
                        regenerated_clips=failed_clip_numbers,
                    )

        log.info(
            "video_generation_complete",
            task_id=str(task_id),
            generated=result["generated"],
            skipped=result["skipped"],
            failed=result["failed"],
            total_cost_usd=str(result["total_cost_usd"]),
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
                units_consumed=result["generated"],
            )
            await db.commit()

        # Step 3.5: Optimize videos and populate Notion (Story 5.4)
        # Optimize videos for streaming playback (MP4 faststart)
        # Then populate Video entries in Notion database
        try:
            log.info(
                "video_optimization_started",
                task_id=str(task_id),
                video_count=len(manifest.clips),
            )

            # Optimize each video for streaming playback
            optimized_count = 0
            for clip in manifest.clips:
                video_path = service.get_video_path(clip["clip_number"])
                if video_path.exists():
                    try:
                        await optimize_video_for_streaming(video_path)
                        optimized_count += 1
                    except Exception as e:
                        log.warning(
                            "video_optimization_failed",
                            task_id=str(task_id),
                            clip_number=clip["clip_number"],
                            error=str(e),
                        )
                        # Continue with other videos - optimization failure is not critical

            log.info(
                "video_optimization_complete",
                task_id=str(task_id),
                optimized=optimized_count,
                total=len(manifest.clips),
            )

            # Populate Notion Videos database
            notion_token = get_notion_api_token()
            if notion_token and notion_page_id:
                # Load channel from database to get storage_strategy (SHORT transaction)
                async with async_session_factory() as db:
                    task = await db.get(Task, task_id)
                    if task:
                        await db.refresh(task, ["channel"])
                        channel = task.channel
                    else:
                        log.error("task_not_found_for_notion_population", task_id=str(task_id))
                        channel = None
                # DB connection closed - build video files list outside transaction

                if channel:
                    # Build video files list with durations
                    video_files = []
                    for clip in manifest.clips:
                        video_path = service.get_video_path(clip["clip_number"])
                        if video_path.exists():
                            try:
                                # Get actual duration after trimming
                                duration = await get_video_duration(video_path)
                                video_files.append(
                                    {
                                        "clip_number": clip["clip_number"],
                                        "output_path": video_path,
                                        "duration": duration,
                                    }
                                )
                            except Exception as e:
                                log.warning(
                                    "video_duration_probe_failed",
                                    task_id=str(task_id),
                                    clip_number=clip["clip_number"],
                                    error=str(e),
                                )
                                # Use default 10s duration if probe fails
                                video_files.append(
                                    {
                                        "clip_number": clip["clip_number"],
                                        "output_path": video_path,
                                        "duration": 10.0,
                                    }
                                )

                    # Populate Notion Videos database
                    notion_client = NotionClient(auth_token=notion_token)
                    video_service = NotionVideoService(notion_client, channel)

                    populate_result = await video_service.populate_videos(
                        task_id=task_id,
                        notion_page_id=notion_page_id,
                        video_files=video_files,
                        correlation_id=str(task_id),
                    )

                    log.info(
                        "notion_videos_populated",
                        task_id=str(task_id),
                        created=populate_result["created"],
                        failed=populate_result["failed"],
                        storage_strategy=populate_result["storage_strategy"],
                    )
                    # Notion population successful
                else:
                    log.warning(
                        "channel_not_found_for_notion_population",
                        task_id=str(task_id),
                    )
            else:
                log.info(
                    "notion_video_population_skipped",
                    task_id=str(task_id),
                    reason="notion_token_missing" if not notion_token else "notion_page_id_missing",
                )

        except Exception as e:
            # CRITICAL: If Notion population fails, don't mark VIDEO_READY
            # User won't be able to see videos for review
            log.error(
                "notion_video_population_error",
                task_id=str(task_id),
                error=str(e),
                exc_info=True,
            )
            # Mark as VIDEO_ERROR so user knows something went wrong
            async with async_session_factory() as db, db.begin():
                task = await db.get(Task, task_id)
                if task:
                    task.status = TaskStatus.VIDEO_ERROR
                    timestamp = datetime.now(timezone.utc).isoformat()
                    task.error_log = (
                        f"{task.error_log or ''}\n[{timestamp}] "
                        f"Notion video population failed: {e!s}"
                    ).strip()
                    await db.commit()
            return

        # Step 4: Update task (short transaction)
        # Only mark VIDEO_READY if Notion population succeeded or was skipped intentionally
        async with async_session_factory() as db, db.begin():
            task = await db.get(Task, task_id)
            if not task:
                log.error("task_not_found_after_generation", task_id=str(task_id))
                return

            # Set status to VIDEO_READY (triggers review gate - Story 5.2)
            task.status = TaskStatus.VIDEO_READY

            # Set review_started_at timestamp (Story 5.4 AC1)
            task.review_started_at = datetime.now(timezone.utc)

            # Update total cost
            task.total_cost_usd = task.total_cost_usd + float(result["total_cost_usd"])

            await db.commit()
            log.info(
                "task_updated_video_ready",
                task_id=str(task_id),
                status="video_ready",
                review_started_at=task.review_started_at.isoformat(),
            )

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
            stderr=e.stderr[:500],  # Truncate stderr
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
            error_type=type(e).__name__,
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
