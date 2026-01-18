"""Task enqueueing service for video generation pipeline.

This module provides task queue management functionality:
- Task enqueueing with duplicate detection
- Application-level idempotency checks
- Task status queries for workers
- PgQueuer integration (Story 2.6)

Architecture:
- Duplicate detection uses notion_page_id unique constraint
- Application-level checks prevent duplicate API calls
- Supports re-queueing of completed/failed tasks
- Short transaction pattern (no API calls during transactions)
- PgQueuer for PostgreSQL-native task queue with FOR UPDATE SKIP LOCKED
"""

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Channel, PriorityLevel, Task, TaskStatus

log = structlog.get_logger()

# Task status categorization (Story 2.6)
# Active states: Prevent duplicate task creation
ACTIVE_TASK_STATUSES = {
    # Draft is NOT active - it's a Notion-only state before queuing
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

# Terminal states: Allow re-queue (manual retry)
TERMINAL_TASK_STATUSES = {
    TaskStatus.DRAFT,  # Notion-only state, not in DB (but included for completeness)
    TaskStatus.PUBLISHED,  # Successfully completed
    TaskStatus.CANCELLED,  # User cancelled task (allow re-queue if un-cancelled)
    TaskStatus.ASSET_ERROR,  # Failed states (recoverable)
    TaskStatus.VIDEO_ERROR,
    TaskStatus.AUDIO_ERROR,
    TaskStatus.UPLOAD_ERROR,
}


def priority_to_int(priority: PriorityLevel) -> int:
    """Convert task priority enum to integer for PgQueuer.

    PgQueuer uses integer priorities where higher values are processed first.

    Args:
        priority: PriorityLevel enum (HIGH, NORMAL, LOW)

    Returns:
        Integer priority (10=high, 5=normal, 1=low)
    """
    priority_map = {
        PriorityLevel.HIGH: 10,
        PriorityLevel.NORMAL: 5,
        PriorityLevel.LOW: 1,
    }
    return priority_map.get(priority, 5)  # Default to normal


async def check_existing_active_task(
    notion_page_id: str,
    session: AsyncSession,
) -> Task | None:
    """Check if active task exists for notion_page_id.

    Active task = status in ACTIVE_TASK_STATUSES (pending, claimed, processing, etc.)
    Terminal task = status in TERMINAL_TASK_STATUSES (completed, failed, etc.)

    This function implements Layer 2 of duplicate detection:
    - Layer 1: Database unique constraint (last line of defense)
    - Layer 2: Application-level check (fast path, prevents unnecessary inserts)
    - Layer 3: IntegrityError handling (race condition safety)

    Args:
        notion_page_id: Notion page ID (32-36 chars)
        session: Database session

    Returns:
        Existing active task, or None if safe to create new task
    """
    # Check for tasks with active status (using enum members, SQLAlchemy handles conversion)
    result = await session.execute(
        select(Task)
        .where(Task.notion_page_id == notion_page_id)
        .where(Task.status.in_(ACTIVE_TASK_STATUSES))
    )
    existing = result.scalar_one_or_none()

    if existing:
        log.info(
            "duplicate_active_task_detected",
            notion_page_id=notion_page_id,
            existing_task_id=str(existing.id),
            existing_status=existing.status.value,
            action="rejected",
        )

    return existing


async def enqueue_task_to_pgqueuer(task: Task) -> None:
    """Mark task as ready for PgQueuer worker consumption.

    Story 2.6: This function prepares tasks for worker claiming via PgQueuer.
    PgQueuer workers will use FOR UPDATE SKIP LOCKED to claim tasks with
    status='queued' directly from the tasks table.

    Pattern:
    - Task inserted into DB with status='queued'
    - Workers poll tasks table with status='queued'
    - PgQueuer FOR UPDATE SKIP LOCKED ensures atomic claiming
    - No separate queue table needed - tasks table IS the queue

    Implementation Note:
    PgQueuer 0.25.3 uses a decorator-based pattern with entrypoints.
    Workers will register an entrypoint function that queries tasks
    with status='queued' and processes them. This function is a
    placeholder for future worker integration in Epic 4.

    Args:
        task: Task instance (already in database with status='queued')
    """
    # PgQueuer integration deferred to Epic 4 (Worker Implementation)
    # For now, tasks with status='queued' are ready for workers
    log.debug(
        "task_ready_for_workers",
        task_id=str(task.id),
        notion_page_id=task.notion_page_id,
        status=task.status.value,
        priority=task.priority.value,
    )


async def enqueue_task(
    notion_page_id: str,
    channel_id: uuid.UUID,
    title: str,
    topic: str,
    story_direction: str,
    priority: PriorityLevel,
    session: AsyncSession,
) -> Task | None:
    """Enqueue task for processing with multi-layer duplicate detection.

    Story 2.6 Enhancements:
    - Multi-layer duplicate detection (app + DB constraint + IntegrityError)
    - PgQueuer integration for worker visibility
    - Manual retry support (terminal → new task)
    - IntegrityError race condition handling

    Duplicate Detection Strategy (3 Layers):
    1. Database unique constraint (notion_page_id) - last defense
    2. Application-level check (ACTIVE_TASK_STATUSES) - fast path
    3. IntegrityError handling - race condition safety

    Active States (reject duplicate):
    - queued, claimed, generating_*, assembling, uploading

    Terminal States (allow re-queue):
    - published, asset_error, video_error, audio_error, upload_error

    Args:
        notion_page_id: Notion page ID (unique identifier, 32-36 chars)
        channel_id: Channel UUID from database (NOT channel_id string)
        title: Video title
        topic: Video topic
        story_direction: Narrative direction
        priority: Priority enum (high/normal/low)
        session: Database session (must be active transaction)

    Returns:
        Task if created/updated, None if duplicate rejected

    Raises:
        RuntimeError: If PgQueuer is not configured
    """
    correlation_id = str(uuid.uuid4())

    # Layer 2: Application-level duplicate check (fast path)
    existing = await check_existing_active_task(notion_page_id, session)
    if existing:
        log.info(
            "duplicate_active_task_rejected",
            correlation_id=correlation_id,
            notion_page_id=notion_page_id,
            existing_task_id=str(existing.id),
            existing_status=existing.status.value,
            action="rejected",
        )
        return None  # Duplicate rejected

    # Check for terminal task (allow re-queue)
    result = await session.execute(
        select(Task)
        .where(Task.notion_page_id == notion_page_id)
        .where(Task.status.in_(TERMINAL_TASK_STATUSES))
    )
    existing_terminal = result.scalar_one_or_none()

    if existing_terminal:
        # Re-queue allowed for terminal tasks
        log.info(
            "task_requeued_after_terminal",
            correlation_id=correlation_id,
            notion_page_id=notion_page_id,
            previous_task_id=str(existing_terminal.id),
            previous_status=existing_terminal.status.value,
        )

        # Update existing terminal task to queued
        existing_terminal.status = TaskStatus.QUEUED
        existing_terminal.title = title
        existing_terminal.topic = topic
        existing_terminal.story_direction = story_direction
        existing_terminal.priority = priority
        existing_terminal.updated_at = datetime.now(timezone.utc)

        # Layer 4: Enqueue to PgQueuer
        await session.flush()  # Ensure task has ID
        await enqueue_task_to_pgqueuer(existing_terminal)

        log.info(
            "task_enqueued",
            correlation_id=correlation_id,
            task_id=str(existing_terminal.id),
            notion_page_id=notion_page_id,
            status="queued",
            priority=priority.value,
        )

        return existing_terminal

    # Create new task
    # Use enum members directly - SQLAlchemy will convert to database enum values
    task = Task(
        notion_page_id=notion_page_id,
        channel_id=channel_id,
        title=title,
        topic=topic,
        story_direction=story_direction,
        status=TaskStatus.QUEUED,  # Use enum member, SQLAlchemy converts to lowercase value
        priority=priority,  # Use enum member directly
    )
    session.add(task)

    # Layer 3: Handle race conditions with IntegrityError
    try:
        await session.flush()  # Force DB constraint check
    except IntegrityError as e:
        log.warning(
            "duplicate_task_race_condition",
            correlation_id=correlation_id,
            notion_page_id=notion_page_id,
            error_detail=str(e),
            action="rolled_back",
        )
        await session.rollback()
        return None

    # Layer 4: Enqueue to PgQueuer
    await enqueue_task_to_pgqueuer(task)

    log.info(
        "task_enqueued",
        correlation_id=correlation_id,
        task_id=str(task.id),
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
    result = await session.execute(select(Channel).where(Channel.channel_id == channel_name))
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


# Dashboard query helper functions (Story 5.7)


async def get_tasks_needing_review(session: AsyncSession) -> list[Task]:
    """Fetch tasks at review gates for dashboard view.

    Returns tasks in ASSETS_READY, VIDEO_READY, AUDIO_READY, FINAL_REVIEW statuses,
    sorted by priority (high first) and created_at (FIFO within priority).

    Uses ix_tasks_status index for optimal performance.

    Args:
        session: Database session

    Returns:
        List of Task instances at review gates, ordered by priority desc, created_at asc

    Example:
        async with AsyncSessionLocal() as db:
            review_tasks = await get_tasks_needing_review(db)
            for task in review_tasks:
                print(f"{task.title}: {task.status.value}")
    """
    from sqlalchemy import case

    from app.models import REVIEW_GATE_STATUSES

    # Map priority enum to sortable integer (high=10, normal=5, low=1)
    priority_order = case(
        (Task.priority == PriorityLevel.HIGH, 10),
        (Task.priority == PriorityLevel.NORMAL, 5),
        (Task.priority == PriorityLevel.LOW, 1),
        else_=5,
    )

    stmt = (
        select(Task)
        .where(Task.status.in_(REVIEW_GATE_STATUSES))
        .order_by(
            priority_order.desc(),  # High priority first (10 > 5 > 1)
            Task.created_at.asc(),  # FIFO within priority
        )
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_tasks_with_errors(session: AsyncSession) -> list[Task]:
    """Fetch tasks in error states for troubleshooting dashboard.

    Returns tasks in ASSET_ERROR, VIDEO_ERROR, AUDIO_ERROR, UPLOAD_ERROR statuses,
    sorted by updated_at (newest errors first).

    Uses ix_tasks_status index for optimal performance.

    Args:
        session: Database session

    Returns:
        List of Task instances in error states, ordered by updated_at desc

    Example:
        async with AsyncSessionLocal() as db:
            error_tasks = await get_tasks_with_errors(db)
            for task in error_tasks:
                print(f"{task.title}: {task.status.value} - {task.error_log}")
    """
    from app.models import ERROR_STATUSES

    stmt = (
        select(Task)
        .where(Task.status.in_(ERROR_STATUSES))
        .order_by(Task.updated_at.desc())  # Recent errors first
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_published_tasks(session: AsyncSession, limit: int = 100) -> list[Task]:
    """Fetch published tasks with YouTube URLs.

    Returns tasks in PUBLISHED status, sorted by updated_at (newest first).
    Limited to recent 100 by default to avoid loading entire archive.

    Uses ix_tasks_status index for optimal performance.

    Args:
        session: Database session
        limit: Maximum number of tasks to return (default: 100)

    Returns:
        List of Task instances in PUBLISHED status, ordered by updated_at desc

    Example:
        async with AsyncSessionLocal() as db:
            published = await get_published_tasks(db, limit=50)
            for task in published:
                print(f"{task.title}: {task.youtube_url}")
    """
    stmt = (
        select(Task)
        .where(Task.status == TaskStatus.PUBLISHED)
        .order_by(Task.updated_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_tasks_in_progress(session: AsyncSession) -> list[Task]:
    """Fetch tasks currently being processed.

    Returns tasks in IN_PROGRESS_STATUSES (18 statuses), sorted by time in status
    (calculated as now - updated_at) descending to surface stuck tasks.

    Uses ix_tasks_status index for optimal performance.

    Args:
        session: Database session

    Returns:
        List of Task instances in progress, ordered by updated_at asc (stuck longest first)

    Example:
        async with AsyncSessionLocal() as db:
            in_progress = await get_tasks_in_progress(db)
            for task in in_progress:
                duration = datetime.now(timezone.utc) - task.updated_at
                minutes = duration.total_seconds() / 60
                print(f"{task.title}: {minutes:.0f} minutes in {task.status.value}")
    """
    from app.models import IN_PROGRESS_STATUSES

    stmt = (
        select(Task)
        .where(Task.status.in_(IN_PROGRESS_STATUSES))
        .order_by(Task.updated_at.asc())  # Oldest updates first = stuck longest
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
