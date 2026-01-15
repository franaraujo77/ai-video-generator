"""Composite Creation Worker for processing task queue.

This worker claims tasks from the queue and orchestrates composite creation by
invoking the CompositeCreationService. Follows the short transaction pattern
to prevent database connection pool exhaustion during long-running operations.

Transaction Pattern (CRITICAL - Architecture Decision 3):
1. Claim task (short transaction, set status="processing")
2. Close database connection
3. Generate composites (long-running, outside transaction)
4. Reopen database connection
5. Update task (short transaction, set status="composites_ready" or "error")

Dependencies:
    - Story 3.1: CLI wrapper (async subprocess execution)
    - Story 3.2: Filesystem helpers (path construction)
    - Story 3.4: Composite creation service
    - Epic 1: Database models (Task)
    - Epic 2: Notion API client

Usage:
    from app.workers.composite_worker import process_composite_creation_task

    # Called by worker process when task is claimed from queue
    await process_composite_creation_task("task_uuid_123")
"""

import asyncio
from uuid import UUID

from app.database import async_session_factory
from app.models import Task, TaskStatus
from app.services.composite_creation import CompositeCreationService
from app.utils.cli_wrapper import CLIScriptError
from app.utils.logging import get_logger

log = get_logger(__name__)


async def process_composite_creation_task(task_id: str) -> None:
    """Process composite creation for a single task.

    Transaction Pattern (CRITICAL - from Architecture Decision 3):
    1. Claim task (short transaction, set status="processing")
    2. Close database connection
    3. Generate composites (long-running, outside transaction)
    4. Reopen database connection
    5. Update task (short transaction, set status="composites_ready" or "error")

    Args:
        task_id: Task UUID from database

    Flow:
        1. Load task from database (get channel_id, project_id, topic, story_direction)
        2. Initialize CompositeCreationService(channel_id, project_id)
        3. Create composite manifest (18 scenes)
        4. Generate 18 composites with CLI script invocations
        5. Update task status to "Composites Ready"
        6. Update Notion status (async, don't block)

    Error Handling:
        - CLIScriptError → Mark task "Composite Error", log details, allow retry
        - asyncio.TimeoutError → Mark task "Composite Error", log timeout
        - Exception → Mark task "Composite Error", log unexpected error

    Raises:
        No exceptions (catches all and logs errors)
    """
    log.info("composite_task_start", task_id=task_id)

    # Convert string task_id to UUID
    task_uuid = UUID(task_id) if isinstance(task_id, str) else task_id

    # Step 1: Claim task (short transaction)
    if async_session_factory is None:
        raise RuntimeError("Database not configured. Set DATABASE_URL environment variable.")

    async with async_session_factory() as db, db.begin():
        task = await db.get(Task, task_uuid)
        if not task:
            log.error("task_not_found", task_id=task_id)
            return

        # Load channel relationship to get business identifier
        await db.refresh(task, ["channel"])
        if not task.channel:
            log.error(
                "task_missing_channel",
                task_id=task_id,
                channel_id=task.channel_id
            )
            task.status = TaskStatus.ASSET_ERROR
            task.error_log = "Channel not found"
            await db.commit()
            return

        task.status = TaskStatus.GENERATING_COMPOSITES
        await db.commit()

        # Store task details for use outside transaction
        # Use channel.channel_id (string business ID like "poke1")
        # Use task.id.hex as project_id (32-char hex string)
        channel_id = task.channel.channel_id
        project_id = task.id.hex
        topic = task.topic or ""
        story_direction = task.story_direction or ""
        notion_page_id = task.notion_page_id

        log.info(
            "task_claimed",
            task_id=task_id,
            channel_id=channel_id,
            project_id=project_id,
            status="processing"
        )

    # Step 2: Generate composites (OUTSIDE transaction - long-running operation)
    try:
        service = CompositeCreationService(channel_id, project_id)
        manifest = service.create_composite_manifest(topic, story_direction)

        log.info(
            "composite_creation_start",
            task_id=task_id,
            channel_id=channel_id,
            project_id=project_id,
            composite_count=len(manifest.composites)
        )

        result = await service.generate_composites(manifest, resume=False)

        log.info(
            "composite_creation_complete",
            task_id=task_id,
            generated=result["generated"],
            skipped=result["skipped"],
            failed=result["failed"]
        )

        # Step 3: Update task (short transaction)
        if async_session_factory is None:
            raise RuntimeError("Database not configured")

        async with async_session_factory() as db, db.begin():
            task = await db.get(Task, task_uuid)
            if not task:
                log.error("task_not_found_on_update", task_id=task_id)
                return

            task.status = TaskStatus.COMPOSITES_READY
            await db.commit()
            log.info("task_updated", task_id=task_id, status="composites_ready")

        # Step 4: Update Notion (async, non-blocking)
        if notion_page_id:
            # Create fire-and-forget task for Notion update
            notion_task = asyncio.create_task(
                update_notion_status(notion_page_id, "Composites Ready")
            )
            # Add done callback to prevent "coroutine never awaited" warning
            notion_task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)

    except CLIScriptError as e:
        log.error(
            "composite_creation_cli_error",
            task_id=task_id,
            script=e.script,
            exit_code=e.exit_code,
            stderr=e.stderr[:500]  # Truncate stderr
        )

        if async_session_factory is not None:
            async with async_session_factory() as db, db.begin():
                task = await db.get(Task, task_uuid)
                if task:
                    task.status = TaskStatus.ASSET_ERROR
                    task.error_log = f"Composite creation failed: {e.stderr}"
                    await db.commit()

    except asyncio.TimeoutError:
        log.error("composite_creation_timeout", task_id=task_id, timeout=30)

        if async_session_factory is not None:
            async with async_session_factory() as db, db.begin():
                task = await db.get(Task, task_uuid)
                if task:
                    task.status = TaskStatus.ASSET_ERROR
                    task.error_log = "Composite creation timeout (30s per composite)"
                    await db.commit()

    except FileNotFoundError as e:
        log.error(
            "composite_creation_file_not_found",
            task_id=task_id,
            error=str(e)
        )

        if async_session_factory is not None:
            async with async_session_factory() as db, db.begin():
                task = await db.get(Task, task_uuid)
                if task:
                    task.status = TaskStatus.ASSET_ERROR
                    task.error_log = f"Missing asset files: {e!s}"
                    await db.commit()

    except Exception as e:
        log.error(
            "composite_creation_unexpected_error",
            task_id=task_id,
            error=str(e),
            exc_info=True
        )

        if async_session_factory is not None:
            async with async_session_factory() as db, db.begin():
                task = await db.get(Task, task_uuid)
                if task:
                    task.status = TaskStatus.ASSET_ERROR
                    task.error_log = f"Unexpected error: {e!s}"
                    await db.commit()


async def update_notion_status(page_id: str, status: str) -> None:
    """Update Notion page status asynchronously.

    This is called as a background task (non-blocking) after composite creation
    completes successfully. Errors are logged but don't affect task processing.

    Args:
        page_id: Notion page ID
        status: Status string to set (e.g., "Composites Ready")
    """
    try:
        # TODO: Implement Notion API client integration (Epic 2)
        # from app.clients.notion import NotionClient
        # client = NotionClient(auth_token=get_notion_token())
        # await client.update_task_status(page_id, status)
        log.info("notion_status_update_placeholder", page_id=page_id, status=status)
    except Exception as e:
        log.error("notion_status_update_failed", page_id=page_id, status=status, error=str(e))
