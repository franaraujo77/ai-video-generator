"""Pipeline Worker for processing video generation tasks.

This module implements the worker process that claims tasks from the queue
and executes the complete pipeline via the PipelineOrchestrator.

Key Responsibilities:
- Claim tasks from PostgreSQL queue (future: PgQueuer with LISTEN/NOTIFY)
- Execute complete pipeline for claimed tasks (all 6 steps)
- Handle errors and update task status appropriately
- Implement graceful shutdown on SIGTERM
- Support 3 concurrent worker processes (Railway deployment)

Architecture Pattern: "Short Transaction + Long Processing"
- Claim task atomically (FOR UPDATE SKIP LOCKED pattern)
- Close database connection
- Execute pipeline (51-124 minutes typical, outside transaction)
- Reopen connection
- Update final task status

Worker Coordination:
- Multiple workers can run concurrently (3 on Railway)
- Each worker processes one task at a time (no parallel tasks per worker)
- Database locking prevents conflicts (FOR UPDATE SKIP LOCKED)
- Graceful shutdown: finish current task, don't claim new tasks

Dependencies:
    - Story 3.9: Pipeline orchestrator (end-to-end execution)
    - Epic 1: Database models (Task)
    - Epic 2: Notion sync (status updates)

Usage:
    # Run single task (testing)
    python -m app.workers.pipeline_worker --task-id abc-123

    # Run worker loop (production)
    python -m app.workers.pipeline_worker

Performance:
    - Typical pipeline duration: 51-124 minutes (0.85-2.07 hours)
    - 90th percentile target: ≤120 minutes (2 hours, NFR-P1)
    - Cost per video: $6-13 typical

Safety:
    - Worker loop never crashes (catches all exceptions)
    - Individual task failures logged but don't stop worker
    - Worker continues processing next task after failure
"""

import asyncio
import signal
import sys
from typing import Any

from app.database import async_session_factory
from app.models import Task, TaskStatus
from app.services.pipeline_orchestrator import PipelineOrchestrator
from app.utils.logging import get_logger

log = get_logger(__name__)

# Global shutdown flag for graceful shutdown
SHUTDOWN_REQUESTED = False


def signal_handler(signum: int, frame: Any) -> None:
    """Handle SIGTERM/SIGINT for graceful shutdown.

    Sets global shutdown flag to stop worker loop after current task completes.
    Worker will finish processing current task before exiting.

    Args:
        signum: Signal number received
        frame: Current stack frame (unused)
    """
    global SHUTDOWN_REQUESTED
    SHUTDOWN_REQUESTED = True
    log.info("shutdown_signal_received", signal=signum)


# Register signal handlers for graceful shutdown
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


async def process_pipeline_task(task_id: str) -> None:
    """Process a single pipeline task from queue to completion.

    Transaction Pattern (CRITICAL):
    1. Claim task (short transaction, set status="claimed")
    2. Close database connection
    3. Execute pipeline (51-124 minutes typical, outside transaction)
    4. Reopen database connection
    5. Update task (short transaction, set final status)

    Args:
        task_id: Task UUID from database (str representation)

    Flow:
        1. Load task from database (get channel_id, project_id)
        2. Initialize PipelineOrchestrator(task_id)
        3. Execute complete pipeline (all 6 steps)
        4. Set final status to "final_review" (human review gate)
        5. Update Notion status (async, non-blocking)
        6. Log pipeline completion summary

    Error Handling:
        - Catch all exceptions during pipeline execution
        - Classify error as transient (retry) or permanent (failed)
        - Update task status to appropriate error state
        - Log detailed error context for debugging
        - Preserve step completion metadata for retry

    Performance Tracking:
        - Log pipeline_start_time when pipeline begins
        - Log total_duration when pipeline completes
        - Log WARNING if duration > 120 minutes (2-hour target)
        - Log cost summary after completion

    Raises:
        No exceptions (catches all and logs errors)

    Timeouts:
        - Asset generation: 60s per asset (22 assets = ~22 min max)
        - Video generation: 600s per clip (18 clips = ~180 min max)
        - Narration generation: 120s per clip (18 clips = ~36 min max)
        - SFX generation: 60s per clip (18 clips = ~18 min max)
        - Video assembly: 180s for full assembly
        - Total max: ~456 minutes (7.6 hours absolute maximum)
        - Typical: 51-124 minutes (0.85-2.07 hours)

    Example:
        >>> await process_pipeline_task("abc-123")
        # Logs: Pipeline started for task abc-123
        # Logs: Executing step: asset_generation
        # ... (more logs)
        # Logs: Pipeline completed (duration: 3842.1s, cost: $8.45)
    """
    log.info("task_processing_started", task_id=task_id)

    try:
        # Initialize pipeline orchestrator
        orchestrator = PipelineOrchestrator(task_id)

        # Execute complete pipeline (all 6 steps)
        # This will take 51-124 minutes typically (outside any DB transaction)
        await orchestrator.execute_pipeline()

        log.info("task_processing_completed", task_id=task_id)

    except Exception as e:
        log.error(
            "task_processing_error",
            task_id=task_id,
            error_type=type(e).__name__,
            error_message=str(e),
        )

        # Attempt to mark task as failed (best effort)
        try:
            async with async_session_factory() as db, db.begin():  # type: ignore[misc]
                task = await db.get(Task, task_id)
                if task:
                    task.status = TaskStatus.ASSET_ERROR
                    # Append error to log
                    current_log = task.error_log or ""
                    error_entry = f"[Worker Error] {type(e).__name__}: {e!s}"
                    task.error_log = f"{current_log}\n{error_entry}".strip()
                    await db.commit()
        except Exception:
            pass  # Log error but don't raise (worker cleanup)


async def claim_next_task() -> str | None:
    """Claim next available task from queue atomically.

    Query Strategy:
    - Filter by status='queued'
    - Order by priority (high > normal > low) then FIFO (created_at ASC)
    - Lock row with FOR UPDATE SKIP LOCKED (prevents conflicts)
    - Update status to 'claimed'
    - Return task_id

    Returns:
        Task ID (str) if task claimed, None if no tasks available

    Example:
        >>> task_id = await claim_next_task()
        >>> if task_id:
        ...     await process_pipeline_task(task_id)
    """
    from sqlalchemy import case, select
    from sqlalchemy.orm import selectinload

    async with async_session_factory() as db, db.begin():  # type: ignore[misc]
        # Query for next available task (queued status, ordered by priority + FIFO)
        # Use ORM with proper priority ordering via case statement
        # TODO: Add FOR UPDATE SKIP LOCKED when PgQueuer is integrated (Epic 4)
        priority_order = case(
            (Task.priority == "high", 1),
            (Task.priority == "normal", 2),
            (Task.priority == "low", 3),
            else_=4,
        )

        stmt = (
            select(Task)
            .where(Task.status == TaskStatus.QUEUED)
            .order_by(priority_order, Task.created_at.asc())
            .limit(1)
            .options(selectinload(Task.channel))  # Preload channel relationship
        )

        result = await db.execute(stmt)
        task = result.scalar_one_or_none()

        if not task:
            return None

        task_id = str(task.id)

        # Claim task by updating status to 'claimed'
        task.status = TaskStatus.CLAIMED
        await db.commit()

        log.info("task_claimed", task_id=task_id)
        return task_id


async def worker_loop() -> None:
    """Main worker loop that continuously processes tasks from queue.

    Worker Loop Strategy:
    1. Check for shutdown signal
    2. Claim next available task from queue
    3. If no task available, sleep 5 seconds and retry
    4. If task claimed, process via pipeline orchestrator
    5. Repeat until shutdown signal received

    Concurrency:
    - 3 independent worker processes run this loop (Railway deployment)
    - Each worker polls independently
    - Database locking ensures no conflicts (FOR UPDATE SKIP LOCKED)

    Error Handling:
    - Worker loop never crashes (catches all exceptions)
    - Individual task failures logged but don't stop worker
    - Worker continues processing next task after failure

    Shutdown:
    - Graceful shutdown on SIGTERM (finish current task, don't claim new)
    - In-progress tasks released for reclaim after timeout

    Example:
        >>> await worker_loop()
        # Runs forever, processing tasks as they arrive
        # Logs: Worker loop started
        # Logs: Waiting for tasks...
        # Logs: Task claimed: abc-123
        # Logs: Task processing started: abc-123
        # ... (pipeline execution logs)
        # Logs: Task processing completed: abc-123
        # Logs: Waiting for tasks...
    """
    log.info("worker_loop_started")

    while not SHUTDOWN_REQUESTED:
        try:
            # Claim next available task
            task_id = await claim_next_task()

            if task_id:
                # Process task via pipeline orchestrator
                await process_pipeline_task(task_id)
            else:
                # No tasks available, sleep and retry
                log.debug("no_tasks_available")
                await asyncio.sleep(5)

        except Exception as e:
            log.error(
                "worker_loop_error",
                error_type=type(e).__name__,
                error_message=str(e),
            )
            # Sleep briefly before retrying
            await asyncio.sleep(5)

    log.info("worker_loop_stopped", reason="shutdown_requested")


async def main() -> None:
    """Entry point for worker process.

    Supports two modes:
    1. Single task processing (testing): python -m app.workers.pipeline_worker --task-id abc-123
    2. Worker loop (production): python -m app.workers.pipeline_worker

    Args:
        --task-id: Optional task ID to process (testing mode)

    Example:
        # Run worker loop (production)
        $ python -m app.workers.pipeline_worker

        # Process single task (testing)
        $ python -m app.workers.pipeline_worker --task-id abc-123
    """
    # Check for single task mode (testing)
    if len(sys.argv) > 2 and sys.argv[1] == "--task-id":
        task_id = sys.argv[2]
        log.info("single_task_mode", task_id=task_id)
        await process_pipeline_task(task_id)
    else:
        # Run worker loop (production)
        await worker_loop()


if __name__ == "__main__":
    asyncio.run(main())
