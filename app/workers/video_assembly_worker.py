"""Video Assembly Worker for FFmpeg Final Video Assembly Pipeline.

This worker processes video assembly tasks by orchestrating the
VideoAssemblyService to assemble 18 clips into a final 90-second documentary.
It follows the short transaction pattern: claim task → close DB → assemble video →
reopen DB → update task.

Transaction Pattern (CRITICAL - from Architecture Decision 3):
    1. Claim task (short transaction, set status="assembling")
    2. Close database connection
    3. Assemble video (SHORT-RUNNING, 60-120 seconds typical, outside transaction)
    4. Reopen database connection
    5. Update task (short transaction, set status="assembly_ready" or "assembly_error")

Worker Flow:
    1. Load task and channel from database (get channel_id, project_id)
    2. Initialize VideoAssemblyService(channel_id, project_id)
    3. Create assembly manifest (probe audio durations, validate files)
    4. Validate all 54 input files exist (18 video + 18 audio + 18 SFX)
    5. Assemble video with FFmpeg CLI script invocation (60-120 seconds)
    6. Validate final video output (codec, duration, playability)
    7. Update task status to "assembly_ready" with final_video_path and final_video_duration
    8. Update Notion status (async, non-blocking)

Error Handling:
    - FileNotFoundError (missing input) → Mark "assembly_error", log details
    - CLIScriptError (FFmpeg failure) → Mark "assembly_error", log stderr
    - ValueError (invalid output) → Mark "assembly_error", log validation error
    - Exception → Mark "assembly_error", log unexpected error

Dependencies:
    - Story 3.1: CLI wrapper (run_cli_script, CLIScriptError)
    - Story 3.2: Filesystem helpers (get_project_dir, get_video_dir, get_audio_dir, get_sfx_dir)
    - Story 3.8: VideoAssemblyService
    - app/database: AsyncSession factory
    - app/models: Task, Channel models

Usage:
    await process_video_assembly_task(task_id="uuid-here")
"""

import asyncio
from uuid import UUID

from sqlalchemy import select

from app.database import async_session_factory
from app.models import Channel, Task, TaskStatus
from app.services.video_assembly import VideoAssemblyService
from app.utils.cli_wrapper import CLIScriptError
from app.utils.logging import get_logger

log = get_logger(__name__)


async def process_video_assembly_task(task_id: str | UUID) -> None:
    """Process video assembly for a single task.

    Transaction Pattern (CRITICAL - from Architecture Decision 3):
    1. Claim task (short transaction, set status="assembling")
    2. Close database connection
    3. Assemble video (60-120 seconds typical, outside transaction)
    4. Reopen database connection
    5. Update task (short transaction, set status="assembly_ready" or "assembly_error")

    Args:
        task_id: Task UUID from database (string or UUID object)

    Flow:
        1. Load task from database (get channel_id, project_id)
        2. Initialize VideoAssemblyService(channel_id, project_id)
        3. Create assembly manifest (probe audio durations, validate files)
        4. Validate all 54 input files exist (18 video + 18 audio + 18 SFX)
        5. Assemble video with FFmpeg CLI script invocation
        6. Validate final video output (codec, duration, playability)
        7. Update task status to "assembly_ready" (pauses for human review)
        8. Update Notion status (async, don't block)

    Error Handling:
        - FileNotFoundError (missing input) → Mark "assembly_error", log details
        - CLIScriptError (FFmpeg failure) → Mark "assembly_error", log stderr
        - ValueError (invalid output) → Mark "assembly_error", log validation error
        - Exception → Mark "assembly_error", log unexpected error

    Raises:
        No exceptions (catches all and logs errors)

    Timeouts:
        - FFmpeg assembly timeout: 180 seconds (3 minutes max)
        - Typical time: 60-120 seconds for 18-clip assembly
    """
    # Convert task_id to UUID if it's a string
    if isinstance(task_id, str):
        task_id = UUID(task_id)

    # Step 1: Claim task (short transaction)
    if async_session_factory is None:
        log.error("database_not_configured", task_id=str(task_id))
        raise RuntimeError("Database not configured")

    async with async_session_factory() as db, db.begin():
        # Load task with channel relationship
        result = await db.execute(select(Task).where(Task.id == task_id))
        task = result.scalar_one_or_none()

        if not task:
            log.error("task_not_found", task_id=str(task_id))
            return

        # Load channel to get channel_id string
        channel_result = await db.execute(select(Channel).where(Channel.id == task.channel_id))
        channel = channel_result.scalar_one_or_none()

        if not channel:
            log.error(
                "channel_not_found",
                task_id=str(task_id),
                channel_id=str(task.channel_id),
            )
            return

        # Update task status to "assembling"
        task.status = TaskStatus.ASSEMBLING
        await db.commit()

        log.info(
            "task_claimed",
            task_id=str(task_id),
            channel_id=channel.channel_id,
            project_id=str(task.id),
            status="assembling",
        )

        # Store channel_id and project_id for service initialization
        channel_id_str = channel.channel_id
        project_id_str = str(task.id)

    # Step 2: Assemble video (OUTSIDE transaction - 60-120 seconds)
    try:
        service = VideoAssemblyService(channel_id_str, project_id_str)

        log.info(
            "video_assembly_start",
            task_id=str(task_id),
            channel_id=channel_id_str,
            project_id=project_id_str,
            estimated_time_seconds=90,  # 60-120 seconds typical
        )

        # Create assembly manifest with audio duration probing
        manifest = await service.create_assembly_manifest(clip_count=18)

        # Validate all input files before calling FFmpeg
        await service.validate_input_files(manifest)

        # Assemble video with FFmpeg CLI script
        result = await service.assemble_video(manifest)

        log.info(
            "video_assembly_complete",
            task_id=str(task_id),
            duration=result["duration"],
            file_size_mb=result["file_size_mb"],
            resolution=result["resolution"],
            codec=result.get("video_codec", "unknown")
            + "/"
            + result.get("audio_codec", "unknown"),
        )

        # Step 3: Update task (short transaction)
        async with async_session_factory() as db, db.begin():
            # Reload task
            result_task = await db.execute(select(Task).where(Task.id == task_id))
            task = result_task.scalar_one_or_none()

            if not task:
                log.error("task_disappeared", task_id=str(task_id))
                return

            # Update task with assembly results
            task.status = TaskStatus.ASSEMBLY_READY  # Pauses for human review
            task.final_video_path = str(manifest.output_path)
            task.final_video_duration = result["duration"]

            await db.commit()

            log.info(
                "task_updated",
                task_id=str(task_id),
                status="assembly_ready",
                final_video_path=str(manifest.output_path),
                final_video_duration=result["duration"],
            )

        # Note: Notion status update will be implemented in Epic 5 (Review Gates)

    except FileNotFoundError as e:
        log.error(
            "video_assembly_missing_file",
            task_id=str(task_id),
            channel_id=channel_id_str,
            project_id=project_id_str,
            error=str(e),
        )

        async with async_session_factory() as db, db.begin():
            result_task = await db.execute(select(Task).where(Task.id == task_id))
            task = result_task.scalar_one_or_none()

            if task:
                task.status = TaskStatus.ASSEMBLY_ERROR
                error_msg = f"Missing file: {str(e)}"
                task.error_log = (
                    (task.error_log or "") + "\n" + error_msg
                    if task.error_log
                    else error_msg
                )
                await db.commit()

    except CLIScriptError as e:
        log.error(
            "video_assembly_cli_error",
            task_id=str(task_id),
            channel_id=channel_id_str,
            project_id=project_id_str,
            script=e.script,
            exit_code=e.exit_code,
            stderr=e.stderr[:500],  # Truncate stderr
        )

        async with async_session_factory() as db, db.begin():
            result_task = await db.execute(select(Task).where(Task.id == task_id))
            task = result_task.scalar_one_or_none()

            if task:
                task.status = TaskStatus.ASSEMBLY_ERROR
                error_msg = f"FFmpeg assembly failed: {e.stderr}"
                task.error_log = (
                    (task.error_log or "") + "\n" + error_msg
                    if task.error_log
                    else error_msg
                )
                await db.commit()

    except ValueError as e:
        log.error(
            "video_assembly_validation_error",
            task_id=str(task_id),
            channel_id=channel_id_str,
            project_id=project_id_str,
            error=str(e),
        )

        async with async_session_factory() as db, db.begin():
            result_task = await db.execute(select(Task).where(Task.id == task_id))
            task = result_task.scalar_one_or_none()

            if task:
                task.status = TaskStatus.ASSEMBLY_ERROR
                error_msg = f"Validation error: {str(e)}"
                task.error_log = (
                    (task.error_log or "") + "\n" + error_msg
                    if task.error_log
                    else error_msg
                )
                await db.commit()

    except Exception as e:
        log.error(
            "video_assembly_unexpected_error",
            task_id=str(task_id),
            channel_id=channel_id_str,
            project_id=project_id_str,
            error=str(e),
            exc_info=True,  # Include stack trace
        )

        async with async_session_factory() as db, db.begin():
            result_task = await db.execute(select(Task).where(Task.id == task_id))
            task = result_task.scalar_one_or_none()

            if task:
                task.status = TaskStatus.ASSEMBLY_ERROR
                error_msg = f"Unexpected error: {str(e)}"
                task.error_log = (
                    (task.error_log or "") + "\n" + error_msg
                    if task.error_log
                    else error_msg
                )
                await db.commit()
