"""Checkpoint service for step-level and sub-step resume (Story 6.3).

This service manages checkpoint save/load/query operations for the video
generation pipeline. Checkpoints enable resuming from failure points without
re-running completed steps.

Checkpoint Granularity:
    - Step-level (Coarse): Asset generation complete, video generation complete
    - Sub-step (Fine-grained): Video clip indices [1, 2, 3, ..., 10]

Transaction Pattern:
    All checkpoint operations use SHORT TRANSACTIONS (< 100ms) and never hold
    database connections during CLI script execution. Checkpoints are saved
    AFTER step completion, not during execution.

Usage:
    # Save step checkpoint after completion
    await save_step_checkpoint(
        task_id="123",
        step_name="video_generation",
        outputs={"total_clips": 18, "clips_generated": 18},
        db=db
    )

    # Check if step completed
    if await is_step_complete(task_id, "asset_generation", db):
        # Skip step
        pass

    # Update sub-step progress
    await update_step_metadata(
        task_id="123",
        metadata_key="completed_video_clips",
        metadata_value=[1, 2, 3, 4, 5],
        db=db
    )

Related:
    - Story 6.1: Error classification (only checkpoint retriable errors)
    - Story 6.2: Retry orchestrator (preserve checkpoints during retry)
    - Architecture: Short transaction pattern (never hold DB during CLI scripts)
"""

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Task

logger = logging.getLogger(__name__)


async def save_step_checkpoint(
    task_id: str, step_name: str, outputs: dict[str, Any], db: AsyncSession
) -> None:
    """Record successful completion of a pipeline step.

    This function saves a step-level checkpoint indicating that a major pipeline
    step (asset generation, video generation, etc.) has completed successfully.
    Checkpoints enable resume from failure point on retry.

    Args:
        task_id: Task UUID as string
        step_name: Pipeline step name (asset_generation, video_generation, etc.)
        outputs: Step output metadata (asset count, clip indices, etc.)
        db: Async database session

    Example:
        await save_step_checkpoint(
            task_id="123",
            step_name="video_generation",
            outputs={"total_clips": 18, "clips_generated": 10},
            db=db
        )

    Note:
        - Checkpoints are deduplicated by step_name (overwrites previous)
        - Uses short transaction pattern (< 100ms)
        - Called AFTER step completion, not during execution
        - Logs error if task not found (fire-and-forget pattern)

    Related:
        - Task 1: Design checkpoint/resume state model
        - Task 2: Implement step-level checkpoint recording
        - Subtask 6.1: Preserve completed_steps during retry
    """
    try:
        task_uuid = UUID(task_id)
    except (ValueError, AttributeError) as e:
        logger.error("invalid_task_id_format_for_checkpoint", task_id=task_id, error=str(e))
        return

    task = await db.get(Task, task_uuid)
    if not task:
        logger.error("task_not_found_for_checkpoint", task_id=task_id, step_name=step_name)
        return

    checkpoint = {
        "step_name": step_name,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "outputs": outputs,
    }

    # Append to completed_steps (deduplicate by step_name)
    completed_steps = task.completed_steps or []
    # Remove old checkpoint for same step (retry scenario)
    completed_steps = [c for c in completed_steps if c["step_name"] != step_name]
    completed_steps.append(checkpoint)

    # Update with explicit transaction (short transaction pattern)
    task.completed_steps = completed_steps
    await db.commit()

    logger.info("checkpoint_saved", task_id=task_id, step_name=step_name, outputs=outputs)


async def update_step_metadata(
    task_id: str, metadata_key: str, metadata_value: Any, db: AsyncSession
) -> None:
    """Update fine-grained step progress metadata.

    This function updates sub-step progress tracking within a pipeline step.
    For example, tracking which video clips have been generated (1-10 of 18).
    Metadata is cleared when step is re-run from beginning.

    Args:
        task_id: Task UUID as string
        metadata_key: Metadata key (e.g., "completed_video_clips")
        metadata_value: Value to store (e.g., [1, 2, 3])
        db: Async database session

    Example:
        await update_step_metadata(
            task_id="123",
            metadata_key="completed_video_clips",
            metadata_value=[1, 2, 3, 4, 5],
            db=db
        )

    Note:
        - Metadata is stored in JSONB for flexible schema
        - Uses short transaction pattern (< 100ms)
        - Logs error if task not found (fire-and-forget pattern)
        - Metadata cleared when step re-run (old sub-step data invalid)

    Related:
        - Task 3: Implement video generation sub-step checkpointing
        - Task 4: Implement asset generation sub-step checkpointing
        - Task 5: Implement audio generation sub-step checkpointing
    """
    try:
        task_uuid = UUID(task_id)
    except (ValueError, AttributeError) as e:
        logger.error("invalid_task_id_format_for_metadata", task_id=task_id, error=str(e))
        return

    task = await db.get(Task, task_uuid)
    if not task:
        logger.error(
            "task_not_found_for_metadata_update", task_id=task_id, metadata_key=metadata_key
        )
        return

    step_metadata = task.step_metadata or {}
    step_metadata[metadata_key] = metadata_value
    task.step_metadata = step_metadata

    await db.commit()

    logger.info(
        "step_metadata_updated",
        task_id=task_id,
        metadata_key=metadata_key,
        metadata_value=metadata_value,
    )


async def is_step_complete(task_id: str, step_name: str, db: AsyncSession) -> bool:
    """Check if a step has already been completed (checkpoint exists).

    Args:
        task_id: Task UUID as string
        step_name: Pipeline step name
        db: Async database session

    Returns:
        True if step completed, False otherwise

    Example:
        if await is_step_complete(task_id, "asset_generation", db):
            logger.info("Skipping asset generation (checkpoint exists)")

    Note:
        - Returns False if task not found (step not complete)
        - Fast query using JSONB containment check
        - Used before executing each step to enable skip

    Related:
        - Task 6: Implement resume logic in retry orchestrator
        - Subtask 6.2: Check completed_steps before executing each step
    """
    try:
        task_uuid = UUID(task_id)
    except (ValueError, AttributeError):
        return False  # Invalid UUID format, step cannot be complete

    task = await db.get(Task, task_uuid)
    if not task or not task.completed_steps:
        return False

    return any(c["step_name"] == step_name for c in task.completed_steps)


async def get_step_checkpoint(
    task_id: str, step_name: str, db: AsyncSession
) -> dict[str, Any] | None:
    """Retrieve checkpoint for specific step.

    Args:
        task_id: Task UUID as string
        step_name: Pipeline step name
        db: Async database session

    Returns:
        Checkpoint dict if found, None otherwise

    Example:
        checkpoint = await get_step_checkpoint(task_id, "video_generation", db)
        if checkpoint:
            clips_generated = checkpoint["outputs"]["clips_generated"]
            logger.info(f"Video generation checkpoint: {clips_generated}/18 clips")

    Note:
        - Returns None if task or checkpoint not found
        - Fast query using JSONB containment check
        - Used for observability and debugging

    Related:
        - Task 2: Implement step-level checkpoint recording
        - Task 9: Update Notion sync for checkpoint visibility
    """
    try:
        task_uuid = UUID(task_id)
    except (ValueError, AttributeError):
        return None  # Invalid UUID format, checkpoint not found

    task = await db.get(Task, task_uuid)
    if not task or not task.completed_steps:
        return None

    for checkpoint in task.completed_steps:
        if checkpoint["step_name"] == step_name:
            return checkpoint

    return None


async def clear_step_metadata(task_id: str, db: AsyncSession) -> None:
    """Clear step metadata (sub-step checkpoints).

    Called when step is re-run from beginning (old sub-step checkpoints invalid).
    Step-level checkpoints (completed_steps) are preserved, only fine-grained
    metadata (step_metadata) is cleared.

    Args:
        task_id: Task UUID as string
        db: Async database session

    Example:
        # When re-running video generation step
        await clear_step_metadata(task_id, db)
        # Now step_metadata is {}, but completed_steps still has old checkpoints

    Note:
        - Only clears step_metadata, not completed_steps
        - Uses short transaction pattern (< 100ms)
        - Logs error if task not found (fire-and-forget pattern)
        - Called when step transitions to new execution

    Related:
        - Task 6: Implement resume logic in retry orchestrator
        - Subtask 6.4: Clear step_metadata when step re-run
    """
    try:
        task_uuid = UUID(task_id)
    except (ValueError, AttributeError) as e:
        logger.error("invalid_task_id_format_for_metadata_clear", task_id=task_id, error=str(e))
        return

    task = await db.get(Task, task_uuid)
    if not task:
        logger.error("task_not_found_for_metadata_clear", task_id=task_id)
        return

    task.step_metadata = {}
    await db.commit()

    logger.info("step_metadata_cleared", task_id=task_id)


async def clear_step_checkpoint_for_retry(
    task_id: str, step_name: str | None, db: AsyncSession
) -> None:
    """Clear checkpoint for failed step during manual retry (Story 6.7, Task 2).

    Manual retries need to clear the checkpoint for the failed step so it re-executes,
    while preserving checkpoints for successfully completed steps. This enables
    resume-from-failure behavior where only the failed step is retried.

    Args:
        task_id: Task UUID as string
        step_name: Pipeline step name to clear (e.g., "video_generation")
                   If None, clears ALL checkpoints (for full restart scenarios)
        db: Async database session

    Example:
        # Clear video generation checkpoint, preserve asset generation
        await clear_step_checkpoint_for_retry(
            task_id="123",
            step_name="video_generation",
            db=db
        )
        # Result: asset_generation checkpoint preserved, video_generation cleared

        # Full restart (FAILED status)
        await clear_step_checkpoint_for_retry(
            task_id="123",
            step_name=None,
            db=db
        )
        # Result: ALL checkpoints cleared

    Note:
        - Uses short transaction pattern (< 100ms)
        - Logs error if task not found (fire-and-forget pattern)
        - Removes failed step from completed_steps list
        - Also clears step_metadata (sub-step checkpoints invalid after failure)

    Integration:
        - Story 6.3: Resume from failure point logic
        - Story 6.7 Task 2: Manual retry reset logic
        - Task 5: Smart retry routing

    Related:
        - Subtask 2.3: Clear checkpoint metadata for failed step
        - Subtask 2.5: Preserve completed step checkpoints
    """
    try:
        task_uuid = UUID(task_id)
    except (ValueError, AttributeError) as e:
        logger.error("invalid_task_id_format_for_checkpoint_clear", task_id=task_id, error=str(e))
        return

    task = await db.get(Task, task_uuid)
    if not task:
        logger.error("task_not_found_for_checkpoint_clear", task_id=task_id)
        return

    if step_name is None:
        # Full restart: Clear ALL checkpoints
        task.completed_steps = []
        task.step_metadata = {}
        logger.info(
            "all_checkpoints_cleared_for_manual_retry",
            task_id=task_id,
            reason="terminal_failure_full_restart",
        )
    else:
        # Selective clear: Remove failed step, preserve others
        if task.completed_steps:
            original_count = len(task.completed_steps)
            task.completed_steps = [
                c for c in task.completed_steps if c.get("step_name") != step_name
            ]
            removed = original_count - len(task.completed_steps)

            if removed > 0:
                logger.info(
                    "step_checkpoint_cleared_for_manual_retry",
                    task_id=task_id,
                    cleared_step=step_name,
                    preserved_steps=[c["step_name"] for c in task.completed_steps],
                )

        # Also clear step_metadata (sub-step checkpoints invalid)
        task.step_metadata = {}

    await db.commit()


def extract_partial_progress_for_error(task: Task, step_name: str) -> dict[str, Any]:
    """Extract partial progress from checkpoints for error reporting (Story 6.4 Task 7).

    This function centralizes the logic for extracting checkpoint progress data
    from task.step_metadata and formatting it for ErrorPayload. Different pipeline
    steps track progress in different ways:

    - video_generation: completed_video_clips (list of indices)
    - asset_generation: completed_assets (list of indices)
    - narration_generation: completed_narration_clips (list of indices)
    - sfx_generation: completed_sfx_clips (list of indices)

    Args:
        task: Task model instance
        step_name: Pipeline step name (video_generation, asset_generation, etc.)

    Returns:
        Dict with partial progress data for ErrorPayload, including:
        - completed items list (e.g., completed_video_clips)
        - total items count (e.g., total_clips)

    Example:
        partial_progress = extract_partial_progress_for_error(task, "video_generation")
        # Returns: {"completed_video_clips": [1,2,3,4,5], "total_clips": 18}

        error_payload = ErrorPayload(
            ...,
            partial_progress=partial_progress,
        )

    Note:
        - Returns empty dict if no checkpoint data available
        - Step metadata is JSONB, so flexible schema
        - Total counts are hardcoded (18 clips standard for all clip-based steps)
        - Asset total comes from step_metadata if available

    Related:
        - Story 6.4 Task 4: retry_orchestrator builds ErrorPayload
        - Story 6.4 Task 5: Notion sync displays partial progress
        - Story 6.3: Checkpoint service design
    """
    partial_progress = {}

    if not task.step_metadata:
        return partial_progress

    # Video generation checkpoints
    if step_name == "video_generation" and "completed_video_clips" in task.step_metadata:
        partial_progress["completed_video_clips"] = task.step_metadata["completed_video_clips"]
        partial_progress["total_clips"] = 18

    # Asset generation checkpoints
    elif step_name == "asset_generation" and "completed_assets" in task.step_metadata:
        partial_progress["completed_assets"] = task.step_metadata["completed_assets"]
        # Asset count varies per project, stored in step_metadata
        partial_progress["total_assets"] = task.step_metadata.get("total_assets", 0)

    # Narration generation checkpoints
    elif step_name == "narration_generation" and "completed_narration_clips" in task.step_metadata:
        partial_progress["completed_narration_clips"] = task.step_metadata[
            "completed_narration_clips"
        ]
        partial_progress["total_clips"] = 18

    # SFX generation checkpoints
    elif step_name == "sfx_generation" and "completed_sfx_clips" in task.step_metadata:
        partial_progress["completed_sfx_clips"] = task.step_metadata["completed_sfx_clips"]
        partial_progress["total_clips"] = 18

    return partial_progress
