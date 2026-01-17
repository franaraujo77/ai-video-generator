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

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select

from app.database import async_session_factory
from app.models import Channel, Task, TaskStatus
from app.services.cost_tracker import track_api_cost
from app.services.sfx_generation import SFXGenerationService
from app.utils.cli_wrapper import CLIScriptError
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

        # Update task status to generating_sfx (audio_approved → generating_sfx)
        task.status = TaskStatus.GENERATING_SFX
        await db.commit()
        log.info("task_claimed", task_id=str(task_id), status="generating_sfx")

        # Load channel for channel_id (SFX doesn't require voice_id)
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

        # Step 5: Update Notion (async, non-blocking)
        # Future enhancement: Extract notion_page_id and update via Notion API
        # asyncio.create_task(update_notion_status(task.notion_page_id, "SFX Ready"))
        log.info(
            "notion_update_skipped",
            task_id=str(task_id),
            reason="Notion integration deferred to Story 5.6",
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
