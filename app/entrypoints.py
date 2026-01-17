"""PgQueuer entrypoint definitions for video generation pipeline.

This module defines entrypoints (task handlers) for each pipeline step.
Each entrypoint follows the short transaction pattern:
    1. Claim task (PgQueuer automatic)
    2. Check rate limits (YouTube quota, Gemini/Kling worker-local state)
    3. Update status to "processing" (short transaction, close DB)
    4. Execute pipeline step (OUTSIDE transaction)
    5. Update status to "completed" or "failed" (short transaction)

Rate Limit Awareness (Story 4.5):
    - YouTube quota: Check database before upload tasks
    - Gemini quota: Check worker_state flag before asset tasks
    - Kling concurrency: Check worker_state counter before video tasks
    - If rate limit hit: Release task back to queue, skip processing

Entrypoints:
    - process_video: Orchestrate entire video generation pipeline

Future Entrypoints (Story 4.8):
    - process_asset_generation
    - process_composite_creation
    - process_video_generation
    - process_narration_generation
    - process_sound_effects_generation
    - process_video_assembly

References:
    - Architecture: Short Transaction Pattern (Architecture Decision 3)
    - Story 4.5: Rate Limit Aware Task Selection
    - PgQueuer Documentation: https://pgqueuer.readthedocs.io/
"""

import os

from pgqueuer import PgQueuer
from pgqueuer.models import Job

from app.database import AsyncSessionLocal
from app.models import Task, TaskStatus
from app.services.quota_manager import check_youtube_quota, get_required_api
from app.utils.logging import get_logger
from app.worker import worker_state

log = get_logger(__name__)


def register_entrypoints(pgq: PgQueuer) -> None:
    """Register all entrypoints with PgQueuer instance.

    This function must be called after PgQueuer is initialized.
    Separates entrypoint registration from module import to avoid
    AttributeError when pgq global is None at import time.

    Args:
        pgq: Initialized PgQueuer instance
    """

    @pgq.entrypoint("process_video")
    async def process_video(job: Job) -> None:
        """Process video generation task with priority awareness (Story 4.3).

        This is a placeholder entrypoint for Story 4.2-4.3.
        Full pipeline orchestration will be implemented in Story 4.8.

        Priority Context (Story 4.3):
            Priority level is logged for observability. Priority ordering is handled
            automatically by PgQueuer custom query (high → normal → low + FIFO).

        Args:
            job: PgQueuer Job object with task_id as payload

        Raises:
            ValueError: If task_id is invalid or task not found
            Exception: Any exception marks job as failed (automatic retry via PgQueuer)
        """
        # Validate payload
        if job.payload is None:
            raise ValueError("Job payload is None")

        task_id_bytes = job.payload
        if not isinstance(task_id_bytes, bytes):
            raise ValueError(f"Job payload must be bytes, got {type(task_id_bytes)}")

        task_id = task_id_bytes.decode()

        # Validate task_id format (alphanumeric + hyphens only)
        if not task_id.replace("-", "").replace("_", "").isalnum():
            raise ValueError(f"Invalid task_id format: {task_id}")

        worker_id = os.getenv("RAILWAY_SERVICE_NAME", "worker-local")

        # Initialize required_api for finally block (Story 4.5)
        required_api = None

        # Step 1: Claim and log with priority context (short transaction)
        async with AsyncSessionLocal() as db:  # type: ignore[misc]
            task = await db.get(Task, task_id)
            if not task:
                log.error("task_not_found", task_id=task_id)
                raise ValueError(f"Task not found: {task_id}")

            # Log claim with priority context (Story 4.3)
            log.info(
                "task_claimed",
                worker_id=worker_id,
                task_id=task_id,
                priority=task.priority,  # Story 4.3: Log priority level
                channel_id=task.channel_id,
                pgqueuer_job_id=str(job.id),
            )

            # Step 1.5: Rate limit awareness - double-check quota (Story 4.5)
            # Determine which API this task requires based on its status
            required_api = get_required_api(task.status.value)

            rate_limit_hit = False

            if required_api == "youtube":
                # Check YouTube quota before upload
                quota_available = await check_youtube_quota(
                    channel_id=task.channel_id, operation="upload", db=db
                )
                if not quota_available:
                    rate_limit_hit = True
                    log.warning(
                        "youtube_quota_exhausted_releasing_task",
                        task_id=task_id,
                        channel_id=task.channel_id,
                        status=task.status.value,
                    )

            elif required_api == "gemini":
                # Check asset generation concurrency limit first (Story 4.6 - cheaper check)
                if not worker_state.can_claim_asset_task():
                    rate_limit_hit = True
                    log.warning(
                        "asset_concurrency_limit_releasing_task",
                        task_id=task_id,
                        active_tasks=worker_state.active_asset_tasks,
                        max_concurrent=worker_state.max_concurrent_asset_gen,
                    )
                # Then check Gemini quota flag (worker-local) with auto-reset (Story 4.5)
                elif not worker_state.check_gemini_quota_available():
                    rate_limit_hit = True
                    log.warning(
                        "gemini_quota_exhausted_releasing_task",
                        task_id=task_id,
                        status=task.status.value,
                        reset_time=worker_state.gemini_quota_reset_time.isoformat()
                        if worker_state.gemini_quota_reset_time
                        else None,
                    )

            elif required_api == "kling":
                # Check Kling concurrency limit (worker-local)
                if not worker_state.can_claim_video_task():
                    rate_limit_hit = True
                    log.warning(
                        "kling_concurrency_limit_releasing_task",
                        task_id=task_id,
                        active_tasks=worker_state.active_video_tasks,
                        max_concurrent=worker_state.max_concurrent_video,
                    )

            elif required_api == "elevenlabs":
                # Check audio generation concurrency limit (Story 4.6)
                if not worker_state.can_claim_audio_task():
                    rate_limit_hit = True
                    log.warning(
                        "audio_concurrency_limit_releasing_task",
                        task_id=task_id,
                        active_tasks=worker_state.active_audio_tasks,
                        max_concurrent=worker_state.max_concurrent_audio_gen,
                    )

            # If rate limit hit, release task back to queue
            if rate_limit_hit:
                # Do NOT update task status - leave it in current state
                # PgQueuer will make it available for other workers
                log.info(
                    "task_released_due_to_rate_limit",
                    task_id=task_id,
                    required_api=required_api,
                    worker_id=worker_id,
                )
                # Return early - don't process this task
                return

            # Increment task counters for tracked API types
            # (Story 4.5: video, Story 4.6: asset/audio)
            if required_api == "kling":
                worker_state.increment_video_tasks()
            elif required_api == "gemini":
                worker_state.increment_asset_tasks()
            elif required_api == "elevenlabs":
                worker_state.increment_audio_tasks()

            # Transition: claimed → processing (with dynamic status based on task type)
            task.status = TaskStatus.CLAIMED
            await db.commit()

            # Determine next processing status based on current status
            status_transitions = {
                TaskStatus.QUEUED: TaskStatus.GENERATING_ASSETS,
                TaskStatus.COMPOSITES_READY: TaskStatus.GENERATING_VIDEO,
                TaskStatus.VIDEO_APPROVED: TaskStatus.GENERATING_AUDIO,
                TaskStatus.FINAL_REVIEW: TaskStatus.UPLOADING,
            }
            next_status = status_transitions.get(task.status, TaskStatus.GENERATING_ASSETS)
            task.status = next_status
            await db.commit()

        log.info(
            "task_processing_started",
            worker_id=worker_id,
            task_id=task_id,
        )

        # Step 2: Execute pipeline (OUTSIDE transaction)
        # Placeholder: Full pipeline orchestration in Story 4.8
        # For now, just mark as completed
        try:
            # Future: await orchestrate_pipeline(task_id)
            pass
        except Exception as e:
            # Step 3a: Mark as failed or retry (short transaction)
            async with AsyncSessionLocal() as db:  # type: ignore[misc]
                task = await db.get(Task, task_id)
                if task:
                    # Classify error: retriable vs non-retriable (AC10)
                    is_retriable = _is_retriable_error(e)
                    # Determine appropriate error status based on current processing phase
                    if is_retriable:
                        task.status = TaskStatus.QUEUED  # Retry from beginning
                    else:
                        # Map current status to appropriate error status
                        error_status_map = {
                            TaskStatus.GENERATING_ASSETS: TaskStatus.ASSET_ERROR,
                            TaskStatus.GENERATING_VIDEO: TaskStatus.VIDEO_ERROR,
                            TaskStatus.GENERATING_AUDIO: TaskStatus.AUDIO_ERROR,
                            TaskStatus.UPLOADING: TaskStatus.UPLOAD_ERROR,
                        }
                        task.status = error_status_map.get(task.status, TaskStatus.ASSET_ERROR)
                    await db.commit()

                    # Log failure with priority context (Story 4.3)
                    log.error(
                        "task_failed",
                        worker_id=worker_id,
                        task_id=task_id,
                        priority=task.priority,  # Story 4.3: Include priority in error log
                        error=str(e),
                        is_retriable=is_retriable,
                    )
            raise
        finally:
            # Decrement task counters for tracked API types
            # (Story 4.5: video, Story 4.6: asset/audio)
            if required_api == "kling":
                worker_state.decrement_video_tasks()
            elif required_api == "gemini":
                worker_state.decrement_asset_tasks()
            elif required_api == "elevenlabs":
                worker_state.decrement_audio_tasks()

        # Step 3b: Update status to completed (short transaction)
        # NOTE: This is placeholder code - in production, workers handle status transitions
        async with AsyncSessionLocal() as db:  # type: ignore[misc]
            task = await db.get(Task, task_id)
            if not task:
                raise ValueError(f"Task disappeared during processing: {task_id}")

            # Mark as published (terminal success state) for placeholder testing
            task.status = TaskStatus.PUBLISHED
            await db.commit()

            # Log completion with priority context (Story 4.3)
            log.info(
                "task_completed",
                worker_id=worker_id,
                task_id=task_id,
                priority=task.priority,  # Story 4.3: Include priority in completion log
            )


def _is_retriable_error(error: Exception) -> bool:
    """Classify error as retriable or non-retriable (AC10).

    Args:
        error: Exception raised during pipeline execution

    Returns:
        True if error is retriable (temporary failure), False otherwise

    Classification:
        - Non-retriable: ValueError, KeyError, FileNotFoundError
        - Retriable: ConnectionError, TimeoutError, OSError, and unknown errors
    """
    # Non-retriable errors (permanent failures)
    non_retriable_errors = (
        ValueError,  # Invalid input data
        KeyError,  # Missing required data
        FileNotFoundError,  # Missing resource
    )

    # Default: retriable (safer to retry than fail permanently)
    # Includes: ConnectionError, TimeoutError, OSError, and unknown error types
    return not isinstance(error, non_retriable_errors)
