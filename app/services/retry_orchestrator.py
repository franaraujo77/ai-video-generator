"""Task-level retry orchestration for exponential backoff (Story 6.2).

This module implements task-level retry with exponential backoff schedule:
    - Retry 2 (after 1st failure): Wait 1 minute
    - Retry 3 (after 2nd failure): Wait 5 minutes
    - Retry 4 (after 3rd failure): Wait 15 minutes
    - Retry 5 (after 4th failure): Wait 1 hour
    - After 5th failure: Terminal state + alert

This complements Story 6.1's operation-level retry (tenacity with 2-8s backoff).

Architecture Pattern:
    - Short transactions: claim → close → classify → open → update
    - Fire-and-forget error logging (won't fail pipeline)
    - Graceful degradation on classification errors
"""

import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Task, TaskStatus
from app.schemas.error_payload import ErrorPayload, FailureLocation
from app.services.alert_service import send_terminal_failure_alert
from app.services.checkpoint_service import extract_partial_progress_for_error
from app.services.error_classifier import ErrorAnalysis, ErrorCategory, ErrorContext, classify_error
from app.services.error_logger import (
    log_retry_claimed,
    log_retry_scheduled,
    log_terminal_failure,
)
from app.utils.logging import get_logger

# Get logger for this module
log = get_logger(__name__)


# FR28: Exponential backoff schedule (1min → 5min → 15min → 1hr)
# Index represents retry_count (0-indexed), value is wait time before next attempt
RETRY_SCHEDULE = [
    timedelta(minutes=1),  # After 1st failure → retry in 1 minute
    timedelta(minutes=5),  # After 2nd failure → retry in 5 minutes
    timedelta(minutes=15),  # After 3rd failure → retry in 15 minutes
    timedelta(hours=1),  # After 4th failure → retry in 1 hour
]

# Maximum retry attempts before terminal failure
MAX_RETRY_ATTEMPTS = 5


def should_retry_task(error_analysis: ErrorAnalysis, retry_count: int) -> bool:
    """Determine if task should be retried based on error classification and retry count.

    Args:
        error_analysis: Error classification from Story 6.1 error_classifier
        retry_count: Current number of retry attempts (0 = first failure)

    Returns:
        True if task should be retried, False if task should fail permanently

    Decision Logic:
        - Returns False if retry_count >= MAX_RETRY_ATTEMPTS (exhausted retries)
        - Returns False if error is PERMANENT (won't succeed on retry)
        - Returns True if error is TRANSIENT (temporary issue)
        - Returns True if error is UNKNOWN (conservative retry)

    Examples:
        >>> should_retry_task(transient_error, 0)  # First failure
        True
        >>> should_retry_task(transient_error, 4)  # Fifth failure (last retry)
        True
        >>> should_retry_task(transient_error, 5)  # Exhausted retries
        False
        >>> should_retry_task(permanent_error, 0)  # Permanent error
        False
    """
    # Check if retries exhausted
    if retry_count >= MAX_RETRY_ATTEMPTS:
        return False  # No more retries allowed

    # Permanent errors never retry
    if error_analysis.category == ErrorCategory.PERMANENT:
        return False  # Fail fast on auth errors, bad requests, etc.

    # Retry transient and unknown errors (conservative approach)
    return True


def calculate_next_retry(retry_count: int) -> datetime:
    """Calculate next retry timestamp using exponential backoff schedule.

    Args:
        retry_count: Current retry attempt (0-based: 0=first failure, 1=second failure, etc.)

    Returns:
        UTC datetime when next retry should be attempted

    Schedule:
        retry_count=0 (1st failure) → retry in 1 minute
        retry_count=1 (2nd failure) → retry in 5 minutes
        retry_count=2 (3rd failure) → retry in 15 minutes
        retry_count=3 (4th failure) → retry in 1 hour
        retry_count>=4 (5th+ failure) → fallback to last schedule (1 hour)

    Examples:
        >>> now = datetime(2026, 1, 18, 10, 0, 0, tzinfo=timezone.utc)
        >>> # First failure (retry_count=0) → retry at 10:01
        >>> calculate_next_retry(0)  # doctest: +SKIP
        datetime(2026, 1, 18, 10, 1, 0, tzinfo=timezone.utc)

        >>> # Fourth failure (retry_count=3) → retry at 11:00
        >>> calculate_next_retry(3)  # doctest: +SKIP
        datetime(2026, 1, 18, 11, 0, 0, tzinfo=timezone.utc)

    Note:
        Should not be called when retry_count >= MAX_RETRY_ATTEMPTS, but falls
        back to last schedule entry if this occurs.
    """
    # Get delay from schedule (fallback to last entry if out of bounds)
    if retry_count >= len(RETRY_SCHEDULE):
        delay = RETRY_SCHEDULE[-1]  # Use last schedule entry (1 hour)
    else:
        delay = RETRY_SCHEDULE[retry_count]

    return datetime.now(timezone.utc) + delay


async def schedule_retry(
    task_id: UUID, exception: Exception, db: AsyncSession, context: ErrorContext | None = None
) -> ErrorPayload | None:
    """Schedule task retry if error is transient and retry limit not reached.

    This function implements the core retry scheduling logic:
    1. Load task from database (short transaction)
    2. Classify error using Story 6.1 classifier (with optional context)
    3. Determine if task should retry (transient + retry limit)
    4. Calculate next retry time using exponential backoff
    5. Build rich ErrorPayload for Notion sync (Story 6.4)
    6. Update task with retry metadata
    7. If terminal failure, trigger alert (Story 6.5 stub)

    Args:
        task_id: UUID of task that failed
        exception: Exception raised during task execution
        db: Active database session (must commit after this function)
        context: Optional ErrorContext from service-level error handler (Story 6.4)

    Returns:
        ErrorPayload for Notion sync, or None if task not found

    Pattern:
        Short transaction for retry scheduling. Never holds DB during wait periods.

    Side Effects:
        - Increments task.retry_count
        - Sets task.next_retry_at to future timestamp
        - Appends to task.error_log (JSON lines format with rich ErrorPayload)
        - Triggers alert if terminal failure (via _handle_terminal_failure)

    Example:
        >>> async with async_session_factory() as db:
        ...     try:
        ...         result = await execute_pipeline_step(task_id)
        ...     except Exception as e:
        ...         error_payload = await schedule_retry(task_id, e, db, context)
        ...         await db.commit()
        ...         if error_payload:
        ...             await sync_error_to_notion(task, error_payload)
    """
    # Step 1: Load task in short transaction
    task = await db.get(Task, task_id)
    if not task:
        log.error(
            "task_not_found_for_retry",
            task_id=str(task_id),
            error="Task not found for retry scheduling",
        )
        return None

    # Step 2: Classify error using Story 6.1 classifier (with optional context from Story 6.4)
    error_analysis = classify_error(exception, context)

    # Story 6.10: Set error_category for auto-recovery metrics breakdown
    # Maps ErrorCategory enum to string for database storage (TRANSIENT/PERMANENT/UNKNOWN)
    task.error_category = error_analysis.category.value

    # Step 3: Determine if retry should happen
    if not should_retry_task(error_analysis, task.retry_count):
        # Terminal failure - all retries exhausted or permanent error
        return await _handle_terminal_failure(task, error_analysis, db, context)

    # Step 4: Calculate next retry time and update task
    task.retry_count += 1
    task.next_retry_at = calculate_next_retry(task.retry_count - 1)  # 0-indexed

    # Story 6.9: Set retry tracking fields
    task.last_error_timestamp = datetime.now(timezone.utc)
    # max_retry_attempts already has default value of 5 from model definition

    # Step 5: Build rich ErrorPayload for Notion sync (Story 6.4 Task 4)
    error_payload = _build_error_payload(
        task=task,
        error_analysis=error_analysis,
        context=context,
        next_retry_at=task.next_retry_at,
    )

    # Step 6: Append ErrorPayload to task.error_log (JSON lines format)
    error_log_entry = {
        "timestamp": error_payload.timestamp.isoformat(),
        "task_id": str(task.id),
        "retry_attempt": task.retry_count,
        "next_retry_at": task.next_retry_at.isoformat(),
        "error_type": error_analysis.error_type,
        "error_category": error_analysis.category.value,
        "api_service": error_analysis.api_service,
        "is_transient": error_analysis.category == ErrorCategory.TRANSIENT,
        "confidence": error_analysis.confidence,
        "failure_location": error_payload.failure_location.model_dump()
        if error_payload.failure_location
        else None,
        "partial_progress": error_payload.partial_progress,
        "recommendation": error_payload.recommendation,
    }

    # Append to existing error log (JSON lines format - one entry per line)
    if task.error_log:
        task.error_log += "\n" + json.dumps(error_log_entry)
    else:
        task.error_log = json.dumps(error_log_entry)

    # Log retry scheduling for observability
    log.info(
        "retry_scheduled_with_rich_context",
        task_id=str(task_id),
        channel_id=str(task.channel_id),
        retry_attempt=task.retry_count,
        max_retries=MAX_RETRY_ATTEMPTS,
        next_retry_at=task.next_retry_at.isoformat(),
        error_type=error_analysis.error_type,
        error_category=error_analysis.category.value,
        api_service=error_analysis.api_service,
        is_transient=True,
        failure_location=error_payload.failure_location.format()
        if error_payload.failure_location
        else None,
        recommendation=error_payload.recommendation,
    )

    # Story 6.5: Structured logging for Railway aggregation
    retry_delay_seconds = int((task.next_retry_at - datetime.now(timezone.utc)).total_seconds())
    await log_retry_scheduled(
        task_id=task.id,
        correlation_id=task.id,  # Use task.id as correlation_id
        retry_attempt=task.retry_count,
        next_retry_at=task.next_retry_at,
        retry_delay_seconds=retry_delay_seconds,
    )

    return error_payload


def _build_error_payload(
    task: Task,
    error_analysis: ErrorAnalysis,
    context: ErrorContext | None,
    next_retry_at: datetime | None,
) -> ErrorPayload:
    """Build rich ErrorPayload from task state, error analysis, and context.

    Args:
        task: Task that failed
        error_analysis: Error classification from Story 6.1
        context: Optional ErrorContext from service-level handler (Story 6.4)
        next_retry_at: When next retry scheduled (None for terminal failure)

    Returns:
        ErrorPayload with failure location, checkpoint progress, and recommendation

    Pattern:
        - Extract failure location from ErrorContext (clip/asset index)
        - Extract checkpoint progress from task.step_metadata
        - Get actionable recommendation from error_classifier
    """
    # Build failure location from ErrorContext or fall back to step name
    failure_location = None
    if context:
        failure_location = FailureLocation(
            step_name=context.step_name,
            item_index=context.clip_index or context.asset_index,
            total_items=context.total_clips or context.total_assets,
            item_name=context.asset_name,
        )
    else:
        # Fall back to current task status as step name
        failure_location = FailureLocation(step_name=task.status.value)

    # Extract checkpoint progress from task.step_metadata (Story 6.3 + 6.4 Task 7)
    step_name_for_checkpoint = context.step_name if context else task.status.value
    partial_progress = extract_partial_progress_for_error(task, step_name_for_checkpoint)

    # Get actionable recommendation from error_analysis.suggested_action (Story 6.4 Task 6)
    recommendation = error_analysis.suggested_action

    return ErrorPayload(
        timestamp=datetime.now(timezone.utc),
        correlation_id=task.id,
        step_name=context.step_name if context else task.status.value,
        failure_location=failure_location,
        error_category=error_analysis.category.value,
        error_message=error_analysis.error_message,
        api_service=error_analysis.api_service,
        retry_attempt=task.retry_count,
        next_retry_at=next_retry_at,
        partial_progress=partial_progress,
        recommendation=recommendation,
    )


async def _handle_terminal_failure(
    task: Task, error_analysis: ErrorAnalysis, db: AsyncSession, context: ErrorContext | None = None
) -> ErrorPayload:
    """Handle terminal failure after all retries exhausted or permanent error.

    Args:
        task: Task that has failed terminally
        error_analysis: Error classification from Story 6.1
        db: Active database session (must commit after this function)
        context: Optional ErrorContext from service-level handler (Story 6.4)

    Returns:
        ErrorPayload for Notion sync with terminal failure details

    Side Effects:
        - Sets task.retry_count = MAX_RETRY_ATTEMPTS
        - Clears task.next_retry_at (no more retries)
        - Appends ErrorPayload to task.error_log
        - Status remains in error state (ASSET_ERROR, VIDEO_ERROR, etc.)
        - Triggers alert via send_alert() (FR32 - Story 6.5)

    Note:
        Task status is NOT changed - it remains in the current error status
        (ASSET_ERROR, VIDEO_ERROR, AUDIO_ERROR, UPLOAD_ERROR) to indicate
        which step failed.
    """
    # Mark retries as exhausted
    task.retry_count = MAX_RETRY_ATTEMPTS
    task.next_retry_at = None  # No more retries

    # Story 6.9: Set retry tracking fields for terminal failure
    task.last_error_timestamp = datetime.now(timezone.utc)
    # max_retry_attempts already has default value of 5 from model definition

    # Build rich ErrorPayload for terminal failure (Story 6.4 Task 4)
    error_payload = _build_error_payload(
        task=task,
        error_analysis=error_analysis,
        context=context,
        next_retry_at=None,  # Terminal failure - no more retries
    )

    # Append ErrorPayload to task.error_log (JSON lines format)
    error_log_entry = {
        "timestamp": error_payload.timestamp.isoformat(),
        "task_id": str(task.id),
        "retry_attempt": task.retry_count,
        "next_retry_at": None,
        "error_type": error_analysis.error_type,
        "error_category": error_analysis.category.value,
        "api_service": error_analysis.api_service,
        "is_transient": False,
        "confidence": error_analysis.confidence,
        "terminal_failure": True,
        "failure_location": error_payload.failure_location.model_dump()
        if error_payload.failure_location
        else None,
        "partial_progress": error_payload.partial_progress,
        "recommendation": error_payload.recommendation,
    }

    # Append to existing error log
    if task.error_log:
        task.error_log += "\n" + json.dumps(error_log_entry)
    else:
        task.error_log = json.dumps(error_log_entry)

    # Story 6.6: Send Discord alert for terminal failure (FR32)
    # Alert sent AFTER database update (short transaction pattern)
    log.error(
        "terminal_failure_with_rich_context",
        task_id=str(task.id),
        channel_id=str(task.channel_id),
        status=task.status.value,
        retry_count=task.retry_count,
        max_retries=MAX_RETRY_ATTEMPTS,
        error_type=error_analysis.error_type,
        error_category=error_analysis.category.value,
        error_message=error_analysis.error_message,
        api_service=error_analysis.api_service,
        is_transient=False,
        failure_location=error_payload.failure_location.format()
        if error_payload.failure_location
        else None,
        partial_progress=error_payload.partial_progress,
        recommendation=error_payload.recommendation,
    )

    # Send Discord alert (fire-and-forget pattern - won't fail pipeline)
    await send_terminal_failure_alert(
        task_id=task.id,
        task_title=f"{task.channel_id} - {task.status.value}",
        channel_id=str(task.channel_id),
        failed_step=error_payload.step_name,
        error_type=error_payload.error_category,
        error_message=error_payload.error_message,
        retry_count=task.retry_count,
        correlation_id=task.id,
        recommendation=error_payload.recommendation,
        notion_url=None,  # TODO: Add Notion URL when available from task metadata
    )

    # Story 6.5: Structured logging for Railway aggregation
    await log_terminal_failure(
        task_id=task.id,
        correlation_id=task.id,  # Use task.id as correlation_id
        channel_id=str(task.channel_id),
        retry_attempts=task.retry_count,
        final_error_type=error_analysis.error_type,
        final_error_message=error_analysis.error_message,
    )

    return error_payload


async def claim_retry_tasks(db: AsyncSession) -> list[Task]:
    """Poll for tasks ready for retry (next_retry_at <= now).

    This function is called by worker processes to find tasks that need retry.
    Uses FOR UPDATE SKIP LOCKED to prevent duplicate claims across workers.

    Args:
        db: Active database session (must commit after this function)

    Returns:
        List of tasks claimed for retry (max 10 per poll)

    Query Strategy:
        - WHERE next_retry_at IS NOT NULL AND next_retry_at <= now()
        - ORDER BY next_retry_at ASC (FIFO - oldest retry first)
        - LIMIT 10 (batch size to prevent overwhelming single worker)
        - FOR UPDATE SKIP LOCKED (atomic claim, no duplicates)

    Side Effects:
        - Updates task.status to PROCESSING (from error status)
        - Clears task.next_retry_at (retry timestamp no longer needed)

    Example:
        >>> async with async_session_factory() as db:
        ...     retry_tasks = await claim_retry_tasks(db)
        ...     await db.commit()
        ...     for task in retry_tasks:
        ...         await execute_pipeline_step(task.id)
    """
    now = datetime.now(timezone.utc)

    # Query for tasks ready for retry
    query = (
        select(Task)
        .where(Task.next_retry_at <= now)
        .where(Task.next_retry_at.is_not(None))
        .order_by(Task.next_retry_at)  # FIFO - oldest retry first
        .limit(10)  # Batch size
        .with_for_update(skip_locked=True)  # Atomic claim
    )

    result = await db.execute(query)
    tasks = list(result.scalars().all())

    # Update claimed tasks
    for task in tasks:
        # Story 6.3: Preserve checkpoint state (completed_steps, step_metadata)
        # These fields enable resume-from-failure-point functionality:
        # - completed_steps: Step-level checkpoints (which steps completed successfully)
        # - step_metadata: Sub-step checkpoints (which clips/assets completed within a step)
        #
        # By preserving this data, the pipeline can resume from the failure point:
        # 1. Set status to QUEUED (per Task.VALID_TRANSITIONS: ERROR → QUEUED)
        # 2. Pipeline starts from step 1 but services check checkpoints:
        #    - If step_metadata shows sub-steps complete, skip them (Tasks 3-5)
        #    - If filesystem shows outputs exist, skip them (resume=True)
        # 3. Work resumes only from the point of failure
        #
        # Valid transition: ERROR states → QUEUED (per Task.VALID_TRANSITIONS)
        previous_status = task.status
        task.status = TaskStatus.QUEUED  # Reset to queue for retry
        task.next_retry_at = None  # Clear retry timestamp

        # Log checkpoint preservation for observability
        checkpoint_summary = {
            "completed_steps_count": len(task.completed_steps) if task.completed_steps else 0,
            "step_metadata_keys": list(task.step_metadata.keys()) if task.step_metadata else [],
        }
        log.info(
            "retry_task_claimed_with_checkpoint_preservation",
            task_id=str(task.id),
            channel_id=str(task.channel_id),
            previous_status=previous_status.value,
            new_status=TaskStatus.QUEUED.value,
            checkpoint_summary=checkpoint_summary,
        )

        # Story 6.5: Structured logging for Railway aggregation
        await log_retry_claimed(
            task_id=task.id,
            correlation_id=task.id,  # Use task.id as correlation_id
            retry_attempt=task.retry_count,
            worker_id="worker-1",  # TODO: Get actual worker ID from context
        )

    return tasks


async def mark_task_recovered(task_id: UUID, db: AsyncSession) -> None:
    """Mark task as successfully auto-recovered from error state (Story 6.10).

    This function tracks successful auto-recovery for FR35 metrics (80% target).
    Call this when a task reaches a successful state after retry.

    Conditions for Auto-Recovery:
        - Task had previous error (retry_count > 0)
        - Task was NOT manually retried (is_manual_retry=False)
        - Task reached successful status (PUBLISHED or other success state)

    Args:
        task_id: UUID of task that recovered successfully
        db: Active database session (must commit after this function)

    Side Effects:
        - Sets task.auto_recovered = True (used for metrics calculation)
        - Sets task.recovery_attempt_number = retry_count (which retry succeeded)
        - Logs auto-recovery event with structlog (observability)

    Pattern:
        Short transaction for auto-recovery marking. Called when task reaches
        successful state after error/retry.

    Example:
        >>> # In pipeline_orchestrator after successful step completion
        >>> async with async_session_factory() as db:
        ...     task = await db.get(Task, task_id)
        ...     task.status = TaskStatus.PUBLISHED
        ...     if task.retry_count > 0:
        ...         await mark_task_recovered(task_id, db)
        ...     await db.commit()

    Related:
        - Story 6.10: Auto-Recovery Success Rate Tracking
        - FR35: 80% auto-recovery target
        - Story 6.2: Exponential backoff retry logic
    """
    # Load task
    task = await db.get(Task, task_id)
    if not task:
        log.error(
            "task_not_found_for_recovery_marking",
            task_id=str(task_id),
            error="Task not found when marking auto-recovery",
        )
        return

    # Check if task recovered via automatic retry (not manual intervention)
    if task.retry_count > 0 and not task.is_manual_retry:
        # Mark auto-recovery for metrics tracking
        task.auto_recovered = True
        task.recovery_attempt_number = task.retry_count

        log.info(
            "task_auto_recovered",
            task_id=str(task.id),
            channel_id=str(task.channel_id),
            retry_count=task.retry_count,
            recovery_attempt=task.recovery_attempt_number,
            error_category=task.error_category,
            status=task.status.value,
        )
    elif task.retry_count > 0 and task.is_manual_retry:
        # Task recovered but via manual retry - don't count for auto-recovery metrics
        log.info(
            "task_recovered_via_manual_retry",
            task_id=str(task.id),
            channel_id=str(task.channel_id),
            retry_count=task.retry_count,
            is_manual_retry=True,
        )
    else:
        # Task succeeded on first attempt - no recovery needed
        log.debug(
            "task_succeeded_first_attempt",
            task_id=str(task.id),
            channel_id=str(task.channel_id),
        )
