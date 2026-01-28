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
    5. Track API cost (short transaction, Story 8.2)
    6. Update task (short transaction, set status="assets_ready" or "asset_error")

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
import contextlib
from decimal import Decimal
from uuid import UUID

from app.database import async_session_factory
from app.models import Task, TaskStatus
from app.services.asset_generation import AssetGenerationService
from app.services.asset_url_storage import record_asset_url
from app.services.cost_tracker import track_api_cost
from app.services.credential_service import CredentialService
from app.services.notion_asset_sync import sync_task_assets_to_notion
from app.utils.cli_wrapper import CLIScriptError
from app.utils.context import set_correlation_id
from app.utils.encryption import get_encryption_service
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
        channel = task.channel  # Store channel for Notion token access

        # Store task details for asset generation
        project_id = str(task.id)  # Use task UUID as project_id
        topic = task.topic
        story_direction = task.story_direction
        notion_page_id = task.notion_page_id

        # Claim task by updating status (queued → claimed → generating_assets)
        task.status = TaskStatus.CLAIMED
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

        # Step 2.5: Upload assets to R2 and record URLs (Story 8.4)
        async with async_session_factory() as db:
            # Get channel to check storage_strategy
            task = await db.get(Task, task_id)
            if not task:
                log.error("task_not_found_for_r2_upload", task_id=str(task_id))
                return

            await db.refresh(task, ["channel"])
            channel = task.channel
            storage_strategy = channel.storage_strategy

            if storage_strategy == "r2":
                log.info(
                    "r2_upload_start",
                    task_id=str(task_id),
                    channel_id=channel.channel_id,
                    asset_count=len(manifest.assets),
                )

                # Get R2 client with decrypted credentials
                credential_service = CredentialService()
                try:
                    r2_client = await credential_service.get_r2_client(
                        channel.channel_id, db
                    )
                except ValueError as e:
                    log.error(
                        "r2_client_initialization_failed",
                        task_id=str(task_id),
                        error=str(e),
                    )
                    # Continue without R2 upload - will fall back to Notion
                    storage_strategy = "notion"

                if storage_strategy == "r2":
                    # Upload each asset to R2
                    uploaded_count = 0
                    for asset_prompt in manifest.assets:
                        asset_path = asset_prompt.output_path
                        if not asset_path.exists():
                            log.warning(
                                "asset_file_missing",
                                task_id=str(task_id),
                                asset_path=str(asset_path),
                            )
                            continue

                        # Determine asset type from directory structure
                        # Path format: .../assets/{asset_type}/{filename}
                        asset_type = asset_path.parent.name  # "characters", "environments", etc.
                        asset_name = asset_path.name

                        # Construct R2 key
                        r2_key = (
                            f"{channel.channel_id}/{project_id}/assets/"
                            f"{asset_type}/{asset_name}"
                        )

                        try:
                            # Upload to R2
                            asset_url = await r2_client.upload_asset(
                                local_file_path=asset_path,
                                r2_key=r2_key,
                                content_type="image/png",
                            )

                            # Record asset URL in database (Story 8.3)
                            async with async_session_factory() as db2, db2.begin():
                                await record_asset_url(
                                    db=db2,
                                    task_id=task.id,
                                    channel_id=channel.id,
                                    asset_type=asset_type,
                                    asset_name=asset_name,
                                    storage_strategy="r2",
                                    asset_url=asset_url,
                                    local_file_path=str(asset_path),
                                )

                            uploaded_count += 1
                            log.info(
                                "asset_uploaded_to_r2",
                                task_id=str(task_id),
                                asset_name=asset_name,
                                asset_url=asset_url,
                            )

                        except Exception as e:
                            log.error(
                                "r2_asset_upload_failed",
                                task_id=str(task_id),
                                asset_name=asset_name,
                                error=str(e),
                            )
                            # Continue with next asset - don't fail entire task

                    log.info(
                        "r2_upload_complete",
                        task_id=str(task_id),
                        uploaded=uploaded_count,
                        total=len(manifest.assets),
                    )

        # Step 3: Track API cost (short transaction) - Story 8.2
        async with async_session_factory() as db, db.begin():
            task = await db.get(Task, task_id)
            if not task:
                log.error("task_not_found_for_cost_tracking", task_id=str(task_id))
                return

            await track_api_cost(
                db=db,
                task_id=task.id,
                component="gemini_assets",
                cost_usd=Decimal(str(result["total_cost_usd"])),
                api_calls=result["generated"],
                units_consumed=result["generated"],
            )
            # Note: track_api_cost() commits internally, no extra commit needed

        # Step 4: Update task (short transaction)
        async with async_session_factory() as db, db.begin():
            task = await db.get(Task, task_id)
            if not task:
                log.error("task_not_found_on_update", task_id=str(task_id))
                return

            task.status = TaskStatus.ASSETS_READY
            task.total_cost_usd += result["total_cost_usd"]
            await db.commit()

            log.info("task_updated", task_id=str(task_id), status="assets_ready")

        # Step 5: Sync asset URLs to Notion (fire-and-forget background job - Story 8.3)
        # Pattern: Fire-and-forget task with exception suppression
        # The task is intentionally not awaited to avoid blocking the worker.
        # Exception handling is done via done_callback to prevent unhandled exceptions.
        try:
            # Validate channel exists (Issue #4: Missing channel validation)
            if not channel:
                log.warning(
                    "notion_asset_sync_skipped_no_channel",
                    task_id=str(task_id),
                    reason="Channel not loaded",
                )
                # Don't raise - this is non-critical best-effort sync
                return

            # Validate Notion credentials exist (Issue #5: Missing credential validation)
            if not channel.notion_token_encrypted:
                log.info(
                    "notion_asset_sync_skipped_no_credentials",
                    task_id=str(task_id),
                    channel_id=channel.channel_id,
                    reason="Channel not configured with Notion credentials",
                )
                # Don't raise - channels may not use Notion integration
                return

            # Decrypt Notion token from channel
            encryption_service = get_encryption_service()
            notion_token = encryption_service.decrypt(channel.notion_token_encrypted)

            # Create fire-and-forget task for Notion asset sync
            async def _sync_assets_to_notion() -> None:
                # Set correlation ID for distributed tracing (Issue #3)
                set_correlation_id(str(task_id))
                async with async_session_factory() as db:
                    await sync_task_assets_to_notion(db, task_id, notion_token)

            notion_task = asyncio.create_task(_sync_assets_to_notion())

            def handle_notion_task_done(task: asyncio.Task[None]) -> None:
                # Notion updates are best-effort; don't fail task on Notion errors
                with contextlib.suppress(Exception):
                    task.result()  # Re-raise exception if occurred

            notion_task.add_done_callback(handle_notion_task_done)

            log.info(
                "notion_asset_sync_queued",
                task_id=str(task_id),
                notion_page_id=notion_page_id,
            )
        except Exception as e:
            # Log but don't fail task if Notion sync setup fails
            log.warning(
                "notion_asset_sync_setup_failed",
                task_id=str(task_id),
                error=str(e),
            )

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


