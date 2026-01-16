"""Asset Generation Worker.

This module implements the worker process for the asset generation phase
(Step 1 of 8) of the video generation pipeline. It claims tasks from the queue
and orchestrates asset generation via the AssetGenerationService.

Architecture Pattern:
    - Short transactions (claim → close DB → execute → reopen DB → update)
    - Stateless worker (no shared state between tasks)
    - Async execution throughout (non-blocking)
    - Structured logging with correlation IDs (task_id)

Transaction Pattern (CRITICAL - Architecture Decision 3):
    1. Claim task (short transaction, set status="generating_assets")
    2. Close database connection
    3. Generate assets (long-running, outside transaction)
    4. Reopen database connection
    5. Update task (short transaction, set status="assets_ready" or "asset_error")

Error Handling:
    - CLIScriptError → Mark task "asset_error", log details, allow retry
    - asyncio.TimeoutError → Mark task "asset_error", log timeout
    - Exception → Mark task "asset_error", log unexpected error

Dependencies:
    - Story 3.3: AssetGenerationService (business logic layer)
    - Story 3.1: CLI wrapper (run_cli_script, CLIScriptError)
    - Story 3.2: Filesystem helpers (path construction)
    - Epic 1: Database models (Task, TaskStatus)
    - Epic 2: Notion API client (status updates)

Usage:
    from app.workers.asset_worker import process_asset_generation_task

    # Process single task
    await process_asset_generation_task(task_id="abc123")

    # Worker loop (not yet implemented in this story)
    while True:
        task_id = await claim_next_task()
        await process_asset_generation_task(task_id)
"""

import asyncio
from uuid import UUID

from app.database import async_session_factory
from app.models import Task, TaskStatus
from app.services.asset_generation import AssetGenerationService
from app.utils.cli_wrapper import CLIScriptError
from app.utils.logging import get_logger

log = get_logger(__name__)


async def process_asset_generation_task(task_id: str | UUID) -> None:
    """Process asset generation for a single task.

    This function implements the short transaction pattern (Architecture Decision 3):
    1. Claim task (short transaction, set status="generating_assets")
    2. Close database connection
    3. Generate assets (long-running, outside transaction)
    4. Reopen database connection
    5. Update task (short transaction, set status="assets_ready" or "asset_error")

    Args:
        task_id: Task UUID from database (string or UUID object)

    Flow:
        1. Load task from database (get channel_id, project_id, topic, story_direction)
        2. Initialize AssetGenerationService(channel_id, project_id)
        3. Create asset manifest from topic/story_direction
        4. Generate assets with CLI script invocations
        5. Update task status to "assets_ready"
        6. Update Notion status (async, non-blocking)

    Error Handling:
        - CLIScriptError → Mark task "asset_error", log details, allow retry
        - asyncio.TimeoutError → Mark task "asset_error", log timeout
        - Exception → Mark task "asset_error", log unexpected error

    Raises:
        No exceptions (catches all and logs errors)

    Example:
        >>> await process_asset_generation_task("abc123-def456-...")
        # Task claimed, assets generated, status updated to "assets_ready"
    """
    # Convert string to UUID if needed
    if isinstance(task_id, str):
        task_id = UUID(task_id)

    # Ensure session factory is configured
    if async_session_factory is None:
        raise RuntimeError("Database not configured. Set DATABASE_URL environment variable.")

    # Step 1: Claim task (short transaction)
    async with async_session_factory() as db, db.begin():
        task = await db.get(Task, task_id)
        if not task:
            log.error("task_not_found", task_id=str(task_id))
            return

        # Get channel_id string from relationship
        # Note: task.channel_id is UUID FK, need channel.channel_id string
        await db.refresh(task, ["channel"])  # Ensure relationship is loaded
        channel_id_str = task.channel.channel_id

        # Store task details for asset generation
        project_id = str(task.id)  # Use task UUID as project_id
        topic = task.topic
        story_direction = task.story_direction
        notion_page_id = task.notion_page_id

        # Claim task by updating status
        task.status = TaskStatus.GENERATING_ASSETS
        await db.commit()

        log.info(
            "task_claimed",
            task_id=str(task_id),
            channel_id=channel_id_str,
            status="generating_assets",
        )

    # Step 2: Generate assets (OUTSIDE transaction - DB connection closed)
    try:
        service = AssetGenerationService(channel_id_str, project_id)
        manifest = service.create_asset_manifest(topic, story_direction)

        log.info(
            "asset_generation_start",
            task_id=str(task_id),
            asset_count=len(manifest.assets),
            # Truncate atmosphere for logging
            global_atmosphere=manifest.global_atmosphere[:100] + "...",
        )

        result = await service.generate_assets(manifest, resume=False)

        log.info(
            "asset_generation_complete",
            task_id=str(task_id),
            generated=result["generated"],
            skipped=result["skipped"],
            failed=result["failed"],
            total_cost_usd=result["total_cost_usd"],
        )

        # Step 3: Update task (short transaction)
        async with async_session_factory() as db, db.begin():
            task = await db.get(Task, task_id)
            if not task:
                log.error("task_not_found_on_update", task_id=str(task_id))
                return

            task.status = TaskStatus.ASSETS_READY
            task.total_cost_usd += result["total_cost_usd"]
            await db.commit()

            log.info("task_updated", task_id=str(task_id), status="assets_ready")

        # Step 4: Update Notion (async, non-blocking)
        # Note: Notion sync service not yet implemented in Epic 2
        # This is a placeholder for future integration
        #
        # Pattern: Fire-and-forget task with exception suppression
        # The task is intentionally not awaited to avoid blocking the worker.
        # Exception handling is done via done_callback to prevent unhandled exceptions.
        # This is acceptable for placeholder code; production code should use task groups.
        notion_task = asyncio.create_task(
            _update_notion_status_async(notion_page_id, "Assets Ready")
        )

        def handle_notion_task_done(task: asyncio.Task[None]) -> None:
            try:
                task.result()  # Re-raise exception if occurred
            except Exception:
                # Notion updates are best-effort; don't fail task on Notion errors
                pass

        notion_task.add_done_callback(handle_notion_task_done)

    except CLIScriptError as e:
        log.error(
            "asset_generation_cli_error",
            task_id=str(task_id),
            script=e.script,
            exit_code=e.exit_code,
            # Truncate stderr to prevent log bloat
            stderr=e.stderr[:500] + "..." if len(e.stderr) > 500 else e.stderr,
        )

        # Update task with error status
        async with async_session_factory() as db, db.begin():
            task = await db.get(Task, task_id)
            if task:
                task.status = TaskStatus.ASSET_ERROR
                # Append to error_log (append-only pattern)
                error_msg = f"{e.script} exit {e.exit_code}\n{e.stderr[:500]}"
                error_entry = f"Asset generation CLI error: {error_msg}\n\n"
                task.error_log = (task.error_log or "") + error_entry
                await db.commit()

    except asyncio.TimeoutError:
        log.error("asset_generation_timeout", task_id=str(task_id), timeout=60)

        async with async_session_factory() as db, db.begin():
            task = await db.get(Task, task_id)
            if task:
                task.status = TaskStatus.ASSET_ERROR
                error_entry = "Asset generation timeout (60s per asset)\n\n"
                task.error_log = (task.error_log or "") + error_entry
                await db.commit()

    except Exception as e:
        log.error("asset_generation_unexpected_error", task_id=str(task_id), error=str(e))

        async with async_session_factory() as db, db.begin():
            task = await db.get(Task, task_id)
            if task:
                task.status = TaskStatus.ASSET_ERROR
                error_entry = f"Unexpected error: {e!s}\n\n"
                task.error_log = (task.error_log or "") + error_entry
                await db.commit()


async def _update_notion_status_async(notion_page_id: str, status: str) -> None:
    """Update Notion page status asynchronously (non-blocking).

    This is a placeholder for future Notion integration from Epic 2.
    Actual implementation will use NotionSyncService.

    Args:
        notion_page_id: Notion page UUID
        status: New status value to set in Notion

    Note:
        This function should NOT block the main worker flow. Notion updates
        are "fire and forget" - failures are logged but don't affect task status.
    """
    # TODO: Implement Notion status update using Epic 2 NotionSyncService
    # For now, just log the intent
    log.info("notion_status_update_placeholder", notion_page_id=notion_page_id, status=status)
    # In production, this would call:
    # await notion_client.update_page_status(notion_page_id, status)
