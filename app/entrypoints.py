"""PgQueuer entrypoint definitions for video generation pipeline.

This module defines entrypoints (task handlers) for each pipeline step.
Each entrypoint follows the short transaction pattern:
    1. Claim task (PgQueuer automatic)
    2. Update status to "processing" (short transaction, close DB)
    3. Execute pipeline step (OUTSIDE transaction)
    4. Update status to "completed" or "failed" (short transaction)

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
    - PgQueuer Documentation: https://pgqueuer.readthedocs.io/
"""

import os

from pgqueuer import PgQueuer
from pgqueuer.models import Job

from app.database import AsyncSessionLocal
from app.models import Task
from app.utils.logging import get_logger

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

            # Transition: pending → claimed → processing (per AC2)
            task.status = "claimed"
            await db.commit()

            task.status = "processing"
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
                    task.status = "retry" if is_retriable else "failed"
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

        # Step 3b: Update status to completed (short transaction)
        async with AsyncSessionLocal() as db:  # type: ignore[misc]
            task = await db.get(Task, task_id)
            if not task:
                raise ValueError(f"Task disappeared during processing: {task_id}")

            task.status = "completed"
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
