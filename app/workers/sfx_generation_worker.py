"""Sound Effects Generation Worker for ElevenLabs SFX Pipeline.

This worker processes SFX generation tasks by orchestrating the
SFXGenerationService to generate 18 sound effect clips per video. It follows
the short transaction pattern: claim task → close DB → generate SFX →
reopen DB → update task.

Transaction Pattern (CRITICAL - from Architecture Decision 3):
    1. Claim task (short transaction, set status="processing")
    2. Close database connection
    3. Generate SFX audio (1.5-4.5 minutes, outside transaction)
    4. Reopen database connection
    5. Update task (short transaction, set status="sfx_ready" or "sfx_error")

Worker Flow:
    1. Load task and channel from database (get sfx_descriptions)
    2. Initialize SFXGenerationService(channel_id, project_id)
    3. Create SFX manifest (18 clips)
    4. Generate 18 SFX audio clips via CLI script invocations
    5. Track ElevenLabs API costs in database (stub for now)
    6. Update task status to "sfx_ready" and total_cost_usd
    7. Update Notion status (async, non-blocking)

Error Handling:
    - CLIScriptError (non-retriable) → Mark "sfx_error", log details, allow retry
    - ValueError (invalid parameters) → Mark "sfx_error", log validation error
    - Exception → Mark "sfx_error", log unexpected error

Dependencies:
    - Story 3.1: CLI wrapper (run_cli_script, CLIScriptError)
    - Story 3.2: Filesystem helpers (get_sfx_dir)
    - Story 3.7: SFXGenerationService
    - app/database: AsyncSession factory
    - app/models: Task, Channel models
    - app/services/cost_tracker: track_api_cost (stub)

Usage:
    await process_sfx_generation_task(task_id="uuid-here")
"""

import asyncio
import contextlib
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select

from app.database import async_session_factory
from app.models import Channel, Task, TaskStatus
from app.services.asset_url_storage import record_asset_url
from app.services.cost_tracker import track_api_cost
from app.services.credential_service import CredentialService
from app.services.notion_asset_sync import sync_task_assets_to_notion
from app.services.sfx_generation import SFXGenerationService
from app.utils.cli_wrapper import CLIScriptError
from app.utils.context import set_correlation_id
from app.utils.encryption import get_encryption_service
from app.utils.logging import get_logger

log = get_logger(__name__)


async def process_sfx_generation_task(task_id: str | UUID) -> None:
    """Process SFX generation for a single task.

    Transaction Pattern (CRITICAL - from Architecture Decision 3):
    1. Claim task (short transaction, set status="processing")
    2. Close database connection
    3. Generate SFX audio (SHORT-RUNNING, 1.5-4.5 minutes, outside transaction)
    4. Reopen database connection
    5. Update task (short transaction, set status="sfx_ready" or "sfx_error")

    Args:
        task_id: Task UUID from database (string or UUID object)

    Flow:
        1. Load task from database (get channel_id, project_id, sfx_descriptions)
        2. Initialize SFXGenerationService(channel_id, project_id)
        3. Create SFX manifest (18 clips)
        4. Generate 18 SFX audio clips with CLI script invocations
        5. Track ElevenLabs API costs (stub)
        6. Update task status to "sfx_ready" and total_cost_usd
        7. Update Notion status (async, don't block)

    Error Handling:
        - CLIScriptError (non-retriable) → Mark "sfx_error", log details, allow retry
        - ValueError (invalid parameters) → Mark "sfx_error", log validation error
        - Exception → Mark "sfx_error", log unexpected error

    Raises:
        No exceptions (catches all and logs errors)

    Timeouts:
        - Per-clip timeout: 60 seconds (1 minute)
        - Total time: 90-270 seconds (18 clips x 5-15 sec each = 1.5-4.5 minutes)
    """
    # Convert task_id to UUID if it's a string
    if isinstance(task_id, str):
        task_id = UUID(task_id)

    # Initialize variables outside transaction scope
    channel = None  # Store for Notion sync (Issue #6: Standardized naming)
    notion_page_id = None

    # Step 1: Claim task (short transaction)
    if async_session_factory is None:
        log.error("database_not_configured", task_id=str(task_id))
        raise RuntimeError("Database not configured")

    async with async_session_factory() as db, db.begin():
        # Load task
        result = await db.execute(select(Task).where(Task.id == task_id))
        task = result.scalar_one_or_none()
        if not task:
            log.error("task_not_found", task_id=str(task_id))
            return

        # Store notion_page_id for later use
        notion_page_id = task.notion_page_id

        # Update task status to generating_sfx (audio_approved → generating_sfx)
        task.status = TaskStatus.GENERATING_SFX
        await db.commit()
        log.info("task_claimed", task_id=str(task_id), status="generating_sfx")

        # Load channel for channel_id and store for Notion sync (SFX doesn't require voice_id)
        channel_result = await db.execute(select(Channel).where(Channel.id == task.channel_id))
        channel = channel_result.scalar_one_or_none()
        if not channel:
            log.error("channel_not_found", channel_id=str(task.channel_id))
            task.status = TaskStatus.AUDIO_ERROR
            task.error_log = f"Channel {task.channel_id} not found"
            await db.commit()
            return

        channel_business_id: str = channel.channel_id  # Store string ID for service
        project_id: str = str(task.id)  # Use task ID as project ID

        # Get sfx_descriptions from task
        # NOTE: Task model needs sfx_descriptions field added (JSON column)
        # For now, using dummy data - will be populated by upstream pipeline
        sfx_descriptions = getattr(task, "sfx_descriptions", None)
        if not sfx_descriptions or len(sfx_descriptions) != 18:
            log.error(
                "sfx_descriptions_missing_or_invalid",
                task_id=str(task_id),
                descriptions_count=len(sfx_descriptions) if sfx_descriptions else 0,
            )
            task.status = TaskStatus.AUDIO_ERROR
            task.error_log = "Task missing sfx_descriptions field or count != 18"
            await db.commit()
            return

    # Step 2: Generate SFX audio (OUTSIDE transaction - SHORT-RUNNING 1.5-4.5 min)
    try:
        service = SFXGenerationService(channel_business_id, project_id)

        manifest = await service.create_sfx_manifest(sfx_descriptions=sfx_descriptions)

        log.info(
            "sfx_generation_start",
            task_id=str(task_id),
            clip_count=len(manifest.clips),
            estimated_time_seconds=18 * 10,  # 18 clips x 10 sec average
        )

        generation_result = await service.generate_sfx(
            manifest,
            resume=False,  # Future enhancement: detect retries and set resume=True
            max_concurrent=10,  # ElevenLabs rate limit (higher than Kling)
        )

        log.info(
            "sfx_generation_complete",
            task_id=str(task_id),
            generated=generation_result["generated"],
            skipped=generation_result["skipped"],
            failed=generation_result["failed"],
            total_cost=str(generation_result["total_cost_usd"]),
        )

        # Step 2.5: Upload SFX to R2 and record URLs (Story 8.4)
        async with async_session_factory() as db:
            result_task = await db.execute(select(Task).where(Task.id == task_id))
            task = result_task.scalar_one_or_none()
            if not task:
                log.error("task_not_found_for_r2_upload", task_id=str(task_id))
                return

            await db.refresh(task, ["channel"])
            channel = task.channel
            storage_strategy = channel.storage_strategy

            if storage_strategy == "r2":
                log.info(
                    "r2_sfx_upload_start",
                    task_id=str(task_id),
                    channel_id=channel.channel_id,
                    clip_count=len(manifest.clips),
                )

                credential_service = CredentialService()
                try:
                    r2_client = await credential_service.get_r2_client(channel.channel_id, db)
                except ValueError as e:
                    log.error(
                        "r2_client_initialization_failed",
                        task_id=str(task_id),
                        error=str(e),
                    )
                    storage_strategy = "notion"

                if storage_strategy == "r2":
                    uploaded_count = 0
                    for clip in manifest.clips:
                        if not clip.output_path.exists():
                            log.warning(
                                "sfx_file_missing",
                                task_id=str(task_id),
                                clip_number=clip.clip_number,
                            )
                            continue

                        asset_name = clip.output_path.name
                        r2_key = f"{channel.channel_id}/{project_id}/audio/sfx/{asset_name}"

                        try:
                            asset_url = await r2_client.upload_asset(
                                local_file_path=clip.output_path,
                                r2_key=r2_key,
                                content_type="audio/mpeg",
                            )

                            async with async_session_factory() as db2, db2.begin():
                                await record_asset_url(
                                    db=db2,
                                    task_id=task.id,
                                    channel_id=channel.id,
                                    asset_type="sfx",
                                    asset_name=asset_name,
                                    storage_strategy="r2",
                                    asset_url=asset_url,
                                    local_file_path=str(clip.output_path),
                                )

                            uploaded_count += 1
                            log.info(
                                "sfx_uploaded_to_r2",
                                task_id=str(task_id),
                                clip_number=clip.clip_number,
                                asset_url=asset_url,
                            )

                        except Exception as e:
                            log.error(
                                "r2_sfx_upload_failed",
                                task_id=str(task_id),
                                clip_number=clip.clip_number,
                                error=str(e),
                            )

                    log.info(
                        "r2_sfx_upload_complete",
                        task_id=str(task_id),
                        uploaded=uploaded_count,
                        total=len(manifest.clips),
                    )

        # Step 3: Track costs (short transaction)
        async with async_session_factory() as db, db.begin():
            await track_api_cost(
                db=db,
                task_id=task_id,
                component="elevenlabs_sfx",
                cost_usd=generation_result["total_cost_usd"],
                api_calls=generation_result["generated"],
                units_consumed=generation_result["generated"],
            )
            await db.commit()

        # Step 4: Update task (short transaction)
        async with async_session_factory() as db, db.begin():
            result_task = await db.execute(select(Task).where(Task.id == task_id))
            task = result_task.scalar_one_or_none()
            if task:
                task.status = TaskStatus.SFX_READY
                # Note: Task model needs total_cost_usd field (will be added in schema update)
                if hasattr(task, "total_cost_usd") and task.total_cost_usd is not None:
                    # Convert to Decimal for consistent arithmetic
                    task.total_cost_usd = float(
                        Decimal(str(task.total_cost_usd)) + generation_result["total_cost_usd"]
                    )
                elif hasattr(task, "total_cost_usd"):
                    task.total_cost_usd = float(generation_result["total_cost_usd"])
                await db.commit()
                log.info("task_updated", task_id=str(task_id), status="sfx_ready")

        # Step 5: Sync SFX URLs to Notion (fire-and-forget - Story 8.3)
        try:
            # Validate channel exists (Issue #4: Missing channel validation)
            if not channel:
                log.warning(
                    "notion_asset_sync_skipped_no_channel",
                    task_id=str(task_id),
                    reason="Channel not loaded",
                )
                return

            # Validate Notion credentials exist (Issue #5: Missing credential validation)
            if not channel.notion_token_encrypted:
                log.info(
                    "notion_asset_sync_skipped_no_credentials",
                    task_id=str(task_id),
                    channel_id=channel.channel_id,
                    reason="Channel not configured with Notion credentials",
                )
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
                    task.result()

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
            "sfx_generation_cli_error",
            task_id=str(task_id),
            script=e.script,
            exit_code=e.exit_code,
            stderr=e.stderr[:500],  # Truncate stderr
        )

        async with async_session_factory() as db, db.begin():
            result_task = await db.execute(select(Task).where(Task.id == task_id))
            task = result_task.scalar_one_or_none()
            if task:
                task.status = TaskStatus.AUDIO_ERROR
                task.error_log = f"SFX generation failed: {e.stderr}"
                await db.commit()

    except ValueError as e:
        log.error("sfx_validation_error", task_id=str(task_id), error=str(e))

        async with async_session_factory() as db, db.begin():
            result_task = await db.execute(select(Task).where(Task.id == task_id))
            task = result_task.scalar_one_or_none()
            if task:
                task.status = TaskStatus.AUDIO_ERROR
                task.error_log = f"Validation error: {e!s}"
                await db.commit()

    except Exception as e:
        log.error("sfx_generation_unexpected_error", task_id=str(task_id), error=str(e))

        async with async_session_factory() as db, db.begin():
            result_task = await db.execute(select(Task).where(Task.id == task_id))
            task = result_task.scalar_one_or_none()
            if task:
                task.status = TaskStatus.AUDIO_ERROR
                task.error_log = f"Unexpected error: {e!s}"
                await db.commit()
