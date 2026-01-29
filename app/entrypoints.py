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

YouTube Integration (Story 7.2):
    - YouTubeService initialized in worker startup
    - Workers use get_youtube_service() to access service instance
    - YouTubeAuthError handled by skipping YouTube tasks for that channel

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
    - Story 7.2: OAuth Token Refresh Automation
    - PgQueuer Documentation: https://pgqueuer.readthedocs.io/
"""

import os
from typing import TYPE_CHECKING
from uuid import UUID

from pgqueuer import PgQueuer
from pgqueuer.models import Job

from app.database import AsyncSessionLocal
from app.models import Task, TaskStatus
from app.services.quota_manager import check_youtube_quota, get_required_api
from app.services.retry_orchestrator import mark_task_recovered
from app.utils.context import clear_correlation_context, set_channel_id, set_correlation_id
from app.utils.logging import get_logger

if TYPE_CHECKING:
    from app.services.youtube_service import YouTubeService
from app.worker import worker_state

log = get_logger(__name__)


def get_youtube_service() -> "YouTubeService | None":
    """Get YouTubeService instance initialized in worker startup.

    Returns:
        YouTubeService instance if initialized, None if not available.

    Usage:
        youtube_service = get_youtube_service()
        if youtube_service:
            youtube = await youtube_service.build_youtube_client(channel_id, db)

    Note:
        This function imports from app.worker which initializes the service
        during worker startup. Returns None if initialization failed or
        credentials not configured.

    Story: 7.2 - OAuth Token Refresh Automation (Task 5)
    """
    from app.worker import youtube_service

    return youtube_service


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

        try:
            # Step 1: Claim and log with priority context (short transaction)
            async with AsyncSessionLocal() as db:  # type: ignore[misc]
                task = await db.get(Task, task_id)
                if not task:
                    log.error("task_not_found", task_id=task_id)
                    raise ValueError(f"Task not found: {task_id}")

                # Story 8.1: Bind correlation_id and channel_id to async context
                # This makes them available to all logs throughout task processing
                set_correlation_id(str(task.id))
                set_channel_id(str(task.channel_id))

                # Log claim with priority context (Story 4.3)
                # Note: correlation_id, channel_id, worker_id auto-injected by structlog processors
                log.info(
                    "task_claimed",
                    worker_id=worker_id,
                    task_id=task_id,
                    priority=task.priority,  # Story 4.3: Log priority level
                    channel_id=task.channel_id,
                    pgqueuer_job_id=str(job.id),
                )

                # Step 1.4: Retry eligibility check (Story 6.9, Task 5)
                # Don't claim tasks that are waiting for their retry time
                from app.services.error_logger import log_retry_started
                from app.services.retry_state_service import should_retry

                # Check if task has retry_count > 0 (indicating it's in retry state)
                if task.retry_count > 0:
                    # Use should_retry to check eligibility (retry time must have arrived)
                    if not should_retry(
                        retry_attempt=task.retry_count,
                        next_retry_at=task.next_retry_at,
                        max_attempts=task.max_retry_attempts,
                    ):
                        # Task is waiting for retry - release back to queue
                        next_retry_iso = (
                            task.next_retry_at.isoformat() if task.next_retry_at else None
                        )
                        log.info(
                            "task_retry_not_ready_releasing",
                            task_id=task_id,
                            retry_count=task.retry_count,
                            next_retry_at=next_retry_iso,
                            max_retry_attempts=task.max_retry_attempts,
                        )
                        # Return early - don't process this task yet
                        return

                    # Retry time has arrived - log retry started (Story 6.9, Task 7)
                    await log_retry_started(
                        task_id=task.id,
                        correlation_id=task.id,
                        channel_id=str(task.channel_id),
                        retry_attempt=task.retry_count,
                        step_name=task.status.value,  # Current step being retried
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
                        reset_time_iso = (
                            worker_state.gemini_quota_reset_time.isoformat()
                            if worker_state.gemini_quota_reset_time
                            else None
                        )
                        log.warning(
                            "gemini_quota_exhausted_releasing_task",
                            task_id=task_id,
                            status=task.status.value,
                            reset_time=reset_time_iso,
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
                # Save original status BEFORE changing to CLAIMED
                original_status = task.status
                task.status = TaskStatus.CLAIMED
                await db.commit()

                # Determine next processing status based on original status
                status_transitions = {
                    TaskStatus.QUEUED: TaskStatus.GENERATING_ASSETS,
                    TaskStatus.COMPOSITES_READY: TaskStatus.GENERATING_VIDEO,
                    TaskStatus.VIDEO_APPROVED: TaskStatus.GENERATING_AUDIO,
                    TaskStatus.FINAL_REVIEW: TaskStatus.UPLOADING,
                }
                next_status = status_transitions.get(original_status, TaskStatus.GENERATING_ASSETS)
                task.status = next_status
                await db.commit()

            log.info(
                "task_processing_started",
                worker_id=worker_id,
                task_id=task_id,
            )

            # Step 2: Execute pipeline (OUTSIDE transaction)
            # TODO Story 4.8: Implement full pipeline orchestration with exception handling
            # When implemented, the pipeline will:
            #   1. Call: await orchestrate_pipeline(task_id)
            #   2. Handle YouTubeAuthError (Story 7.2) - mark as UPLOAD_ERROR, skip retry
            #   3. Handle other exceptions - classify as retriable/non-retriable (AC10)
            #   4. Decrement task counters in finally block
            # For now, this is a placeholder that immediately marks tasks as completed.

            # Decrement task counters for tracked API types
            # (Story 4.5: video, Story 4.6: asset/audio)
            if required_api == "kling":
                worker_state.decrement_video_tasks()
            elif required_api == "gemini":
                worker_state.decrement_asset_tasks()
            elif required_api == "elevenlabs":
                worker_state.decrement_audio_tasks()

            # Step 3: Update status to completed (short transaction)
            # NOTE: This is placeholder code - in production, workers handle status transitions
            async with AsyncSessionLocal() as db:  # type: ignore[misc]
                task = await db.get(Task, task_id)
                if not task:
                    raise ValueError(f"Task disappeared during processing: {task_id}")

                task.status = TaskStatus.PUBLISHED

                # Story 6.10: Mark auto-recovery if task recovered from error via retry
                if task.retry_count > 0:
                    await mark_task_recovered(UUID(task_id), db)

                await db.commit()

                # Log completion with priority context (Story 4.3)
                log.info(
                    "task_completed",
                    worker_id=worker_id,
                    task_id=task_id,
                    priority=task.priority,  # Story 4.3: Include priority in completion log
                    auto_recovered=task.auto_recovered,  # Story 6.10: Log recovery status
                    retry_count=task.retry_count,
                )

        except Exception as e:
            # Log error and re-raise for pgqueuer to handle
            log.error(
                "task_processing_failed",
                worker_id=worker_id,
                task_id=task_id,
                error=str(e),
                exc_info=True,
            )
            raise
        finally:
            # Story 8.1: Clear correlation context after task completion
            # Prevents correlation_id leakage between tasks (good hygiene)
            clear_correlation_context()


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
