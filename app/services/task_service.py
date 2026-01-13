"""Task enqueueing service for video generation pipeline.

This module provides task queue management functionality:
- Task enqueueing with duplicate detection
- Application-level idempotency checks
- Task status queries for workers

Architecture:
- Duplicate detection uses notion_page_id unique constraint
- Application-level checks prevent duplicate API calls
- Supports re-queueing of completed/failed tasks
- Short transaction pattern (no API calls during transactions)
"""

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Channel, PriorityLevel, Task, TaskStatus

log = structlog.get_logger()


async def enqueue_task(
    notion_page_id: str,
    channel_id: uuid.UUID,
    title: str,
    topic: str,
    story_direction: str,
    priority: PriorityLevel,
    session: AsyncSession,
) -> Task | None:
    """Enqueue task for processing, handling duplicates.

    This function implements application-level duplicate detection and
    re-queueing logic for video generation tasks.

    Duplicate Detection Strategy:
    - Check for existing task with same notion_page_id
    - Skip if task is in active states (pending, claimed, processing)
    - Allow re-queue if task was completed or failed

    Active States (skip duplicate):
    - queued, claimed, generating_*, assembling, uploading

    Re-queue States (allow duplicate):
    - published, asset_error, video_error, audio_error, upload_error

    Args:
        notion_page_id: Notion page ID (unique identifier)
        channel_id: Channel UUID from database (NOT channel_id string)
        title: Video title
        topic: Video topic
        story_direction: Narrative direction
        priority: Priority enum (high/normal/low)
        session: Database session (must be active transaction)

    Returns:
        Task if created/updated, None if duplicate skipped

    Raises:
        IntegrityError: If notion_page_id violates unique constraint (race condition)
    """
    correlation_id = str(uuid.uuid4())

    # Check for existing task
    result = await session.execute(
        select(Task).where(Task.notion_page_id == notion_page_id)
    )
    existing_task = result.scalar_one_or_none()

    if existing_task:
        # Define active states (prevent duplicate)
        active_states = {
            TaskStatus.QUEUED,
            TaskStatus.CLAIMED,
            TaskStatus.GENERATING_ASSETS,
            TaskStatus.ASSETS_READY,
            TaskStatus.ASSETS_APPROVED,
            TaskStatus.GENERATING_COMPOSITES,
            TaskStatus.COMPOSITES_READY,
            TaskStatus.GENERATING_VIDEO,
            TaskStatus.VIDEO_READY,
            TaskStatus.VIDEO_APPROVED,
            TaskStatus.GENERATING_AUDIO,
            TaskStatus.AUDIO_READY,
            TaskStatus.AUDIO_APPROVED,
            TaskStatus.GENERATING_SFX,
            TaskStatus.SFX_READY,
            TaskStatus.ASSEMBLING,
            TaskStatus.ASSEMBLY_READY,
            TaskStatus.FINAL_REVIEW,
            TaskStatus.APPROVED,
            TaskStatus.UPLOADING,
        }

        # Duplicate detection: Skip if task is in active state
        if existing_task.status in active_states:
            log.info(
                "task_already_queued",
                correlation_id=correlation_id,
                notion_page_id=notion_page_id,
                task_id=str(existing_task.id),
                status=existing_task.status.value,
            )
            return None  # Skip duplicate

        # Re-queue allowed for completed/failed tasks
        log.info(
            "task_requeued",
            correlation_id=correlation_id,
            notion_page_id=notion_page_id,
            task_id=str(existing_task.id),
            previous_status=existing_task.status.value,
        )

        # Update task to queued status
        existing_task.status = TaskStatus.QUEUED
        existing_task.title = title
        existing_task.topic = topic
        existing_task.story_direction = story_direction
        existing_task.priority = priority
        existing_task.updated_at = datetime.now(timezone.utc)

        return existing_task

    # Create new task
    task = Task(
        notion_page_id=notion_page_id,
        channel_id=channel_id,
        title=title,
        topic=topic,
        story_direction=story_direction,
        status=TaskStatus.QUEUED,
        priority=priority,
    )
    session.add(task)

    log.info(
        "task_enqueued",
        correlation_id=correlation_id,
        notion_page_id=notion_page_id,
        title=title,
        status="queued",
        priority=priority.value,
    )

    return task


async def get_tasks_by_status(
    status: TaskStatus,
    session: AsyncSession,
    limit: int | None = None,
) -> list[Task]:
    """Query tasks by status.

    Helper function for workers to query tasks in specific states.
    Supports FIFO ordering within status.

    Args:
        status: TaskStatus enum value to filter by
        session: Database session
        limit: Optional limit on number of tasks returned

    Returns:
        List of Task instances matching status, ordered by created_at (FIFO)
    """
    query = select(Task).where(Task.status == status).order_by(Task.created_at.asc())

    if limit:
        query = query.limit(limit)

    result = await session.execute(query)
    return list(result.scalars().all())


async def get_pending_tasks(
    session: AsyncSession,
    limit: int | None = None,
) -> list[Task]:
    """Get all pending tasks (queued status).

    Convenience wrapper for get_tasks_by_status(TaskStatus.QUEUED).
    Workers use this to query tasks ready for claiming.

    Args:
        session: Database session
        limit: Optional limit on number of tasks returned

    Returns:
        List of Task instances in queued status, ordered by created_at (FIFO)
    """
    return await get_tasks_by_status(TaskStatus.QUEUED, session, limit)


async def enqueue_task_from_notion_page(
    page: dict[str, Any],
    session: AsyncSession,
) -> Task | None:
    """Extract Notion page data and enqueue task.

    This function is a wrapper around enqueue_task() that handles:
    - Property extraction from Notion page
    - Channel lookup by channel_id string
    - Validation of required fields
    - Duplicate detection (via enqueue_task)

    Args:
        page: Notion page object from API
        session: Database session (must be active transaction)

    Returns:
        Task if created/updated, None if validation fails or duplicate

    Raises:
        ValueError: If channel_id not found in database
    """
    from app.services.notion_sync import (
        extract_rich_text,
        extract_select,
        map_notion_priority_to_internal,
        validate_notion_entry,
    )

    correlation_id = str(uuid.uuid4())
    notion_page_id = page["id"]
    properties = page.get("properties", {})

    # Validate required fields
    is_valid, error_msg = validate_notion_entry(page)
    if not is_valid:
        log.warning(
            "notion_entry_validation_failed",
            correlation_id=correlation_id,
            notion_page_id=notion_page_id,
            error=error_msg,
        )
        return None

    # Extract properties
    title = extract_rich_text(properties.get("Title"))
    topic = extract_rich_text(properties.get("Topic"))
    story_direction = extract_rich_text(properties.get("Story Direction", {}))
    channel_name = extract_select(properties.get("Channel"))
    notion_priority = extract_select(properties.get("Priority"))

    # Map priority to enum
    priority = map_notion_priority_to_internal(notion_priority)

    # Look up channel by channel_id string
    result = await session.execute(
        select(Channel).where(Channel.channel_id == channel_name)
    )
    channel = result.scalar_one_or_none()

    if not channel:
        log.error(
            "channel_not_found",
            correlation_id=correlation_id,
            notion_page_id=notion_page_id,
            channel_id=channel_name,
        )
        raise ValueError(f"Channel not found: {channel_name}")

    # Enqueue task
    task = await enqueue_task(
        notion_page_id=notion_page_id,
        channel_id=channel.id,  # Use Channel UUID, not string
        title=title,
        topic=topic,
        story_direction=story_direction or "",
        priority=priority,
        session=session,
    )

    return task
