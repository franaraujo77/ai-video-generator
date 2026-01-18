"""Narration Generation Worker for ElevenLabs Audio Pipeline.

This worker processes narration generation tasks by orchestrating the
NarrationGenerationService to generate 18 audio clips per video. It follows
the short transaction pattern: claim task → close DB → generate audio →
reopen DB → update task.

Transaction Pattern (CRITICAL - from Architecture Decision 3):
    1. Claim task (short transaction, set status="processing")
    2. Close database connection
    3. Generate narration audio (1.5-4.5 minutes, outside transaction)
    4. Reopen database connection
    5. Update task (short transaction, set status="audio_ready" or "audio_error")

Worker Flow:
    1. Load task and channel from database (get narration_scripts, voice_id)
    2. Initialize NarrationGenerationService(channel_id, project_id)
    3. Create narration manifest (18 clips with voice_id)
    4. Generate 18 narration audio clips via CLI script invocations
    5. Track ElevenLabs API costs in database (stub for now)
    6. Update task status to "audio_ready" and total_cost_usd
    7. Update Notion status (async, non-blocking)

Error Handling:
    - CLIScriptError (non-retriable) → Mark "audio_error", log details, allow retry
    - ValueError (invalid voice_id) → Mark "audio_error", log validation error
    - Exception → Mark "audio_error", log unexpected error

Dependencies:
    - Story 3.1: CLI wrapper (run_cli_script, CLIScriptError)
    - Story 3.2: Filesystem helpers (get_audio_dir)
    - Story 3.6: NarrationGenerationService
    - app/database: AsyncSession factory
    - app/models: Task, Channel models
    - app/services/cost_tracker: track_api_cost (stub)

Usage:
    await process_narration_generation_task(task_id="uuid-here")
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select

from app.database import async_session_factory
from app.models import Channel, Task, TaskStatus
from app.services.cost_tracker import track_api_cost
from app.services.narration_generation import NarrationGenerationService
from app.utils.cli_wrapper import CLIScriptError
from app.utils.logging import get_logger

log = get_logger(__name__)


async def process_narration_generation_task(task_id: str | UUID) -> None:
    """Process narration generation for a single task.

    Transaction Pattern (CRITICAL - from Architecture Decision 3):
    1. Claim task (short transaction, set status="processing")
    2. Close database connection
    3. Generate narration audio (SHORT-RUNNING, 1.5-4.5 minutes, outside transaction)
    4. Reopen database connection
    5. Update task (short transaction, set status="audio_ready" or "audio_error")

    Args:
        task_id: Task UUID from database (string or UUID object)

    Flow:
        1. Load task from database (get channel_id, project_id, narration_scripts)
        2. Load channel from database (get voice_id for ElevenLabs)
        3. Initialize NarrationGenerationService(channel_id, project_id)
        4. Create narration manifest (18 clips with voice_id)
        5. Generate 18 narration audio clips with CLI script invocations
        6. Track ElevenLabs API costs (stub)
        7. Update task status to "audio_ready" and total_cost_usd
        8. Update Notion status (async, don't block)

    Error Handling:
        - CLIScriptError (non-retriable) → Mark "audio_error", log details, allow retry
        - ValueError (invalid voice_id) → Mark "audio_error", log validation error
        - Exception → Mark "audio_error", log unexpected error

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

        # Update task status to generating_audio (video_approved → generating_audio)
        task.status = TaskStatus.GENERATING_AUDIO
        await db.commit()
        log.info("task_claimed", task_id=str(task_id), status="generating_audio")

        # Load channel to get voice_id
        channel_result = await db.execute(select(Channel).where(Channel.id == task.channel_id))
        channel = channel_result.scalar_one_or_none()
        if not channel:
            log.error("channel_not_found", channel_id=str(task.channel_id))
            task.status = TaskStatus.AUDIO_ERROR
            task.error_log = f"Channel {task.channel_id} not found"
            await db.commit()
            return

        # Validate voice_id
        if not channel.voice_id:
            log.error("channel_voice_id_missing", channel_id=channel.channel_id)
            task.status = TaskStatus.AUDIO_ERROR
            task.error_log = f"Channel {channel.channel_id} missing voice_id"
            await db.commit()
            return

        voice_id: str = channel.voice_id
        channel_business_id: str = channel.channel_id  # Store string ID for service
        project_id: str = str(task.id)  # Use task ID as project ID

        # Get narration_scripts from task
        # NOTE: Task model needs narration_scripts field added (JSON column)
        # For now, using dummy data - will be populated by upstream pipeline
        narration_scripts = getattr(task, "narration_scripts", None)
        if not narration_scripts or len(narration_scripts) != 18:
            log.error(
                "narration_scripts_missing_or_invalid",
                task_id=str(task_id),
                scripts_count=len(narration_scripts) if narration_scripts else 0,
            )
            task.status = TaskStatus.AUDIO_ERROR
            task.error_log = "Task missing narration_scripts field or count != 18"
            await db.commit()
            return

    # Step 2: Generate narration audio (OUTSIDE transaction - SHORT-RUNNING 1.5-4.5 min)
    try:
        service = NarrationGenerationService(channel_business_id, project_id)

        manifest = await service.create_narration_manifest(
            narration_scripts=narration_scripts, voice_id=voice_id
        )

        log.info(
            "narration_generation_start",
            task_id=str(task_id),
            clip_count=len(manifest.clips),
            estimated_time_seconds=18 * 10,  # 18 clips x 10 sec average
        )

        generation_result = await service.generate_narration(
            manifest,
            resume=False,  # Future enhancement: detect retries and set resume=True
            max_concurrent=10,  # ElevenLabs rate limit (higher than Kling)
        )

        log.info(
            "narration_generation_complete",
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
                component="elevenlabs_narration",
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
                task.status = TaskStatus.AUDIO_READY
                # Note: Task model needs total_cost_usd field (will be added in schema update)
                if hasattr(task, "total_cost_usd") and task.total_cost_usd is not None:
                    # Convert to Decimal for consistent arithmetic
                    task.total_cost_usd = float(
                        Decimal(str(task.total_cost_usd)) + generation_result["total_cost_usd"]
                    )
                elif hasattr(task, "total_cost_usd"):
                    task.total_cost_usd = float(generation_result["total_cost_usd"])
                await db.commit()
                log.info("task_updated", task_id=str(task_id), status="audio_ready")

        # Step 5: Update Notion (async, non-blocking)
        # Future enhancement: Extract notion_page_id and update via Notion API
        # asyncio.create_task(update_notion_status(task.notion_page_id, "Audio Ready"))
        log.info(
            "notion_update_skipped",
            task_id=str(task_id),
            reason="Notion integration deferred to Story 5.6",
        )

    except CLIScriptError as e:
        log.error(
            "narration_generation_cli_error",
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
                task.error_log = f"Narration generation failed: {e.stderr}"
                await db.commit()

    except ValueError as e:
        log.error("narration_validation_error", task_id=str(task_id), error=str(e))

        async with async_session_factory() as db, db.begin():
            result_task = await db.execute(select(Task).where(Task.id == task_id))
            task = result_task.scalar_one_or_none()
            if task:
                task.status = TaskStatus.AUDIO_ERROR
                task.error_log = f"Validation error: {e!s}"
                await db.commit()

    except Exception as e:
        log.error("narration_generation_unexpected_error", task_id=str(task_id), error=str(e))

        async with async_session_factory() as db, db.begin():
            result_task = await db.execute(select(Task).where(Task.id == task_id))
            task = result_task.scalar_one_or_none()
            if task:
                task.status = TaskStatus.AUDIO_ERROR
                task.error_log = f"Unexpected error: {e!s}"
                await db.commit()
