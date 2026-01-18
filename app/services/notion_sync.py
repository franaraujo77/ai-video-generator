"""Notion sync service - Bidirectional sync between Notion and PostgreSQL.

This service implements:
- Polling loop (60s) to push Task status updates to Notion
- Property mapping from Notion pages to Task model
- Validation of required fields
- Status mapping between 26-option Notion and 26-status Task enum

Architecture Compliance:
- Short transactions ONLY (claim → close → process → reopen)
- NEVER hold DB connection during Notion API calls
- Use NotionClient with automatic 3 req/sec rate limiting
- Structured logging with correlation IDs
"""

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.notion import NotionAPIError, NotionClient
from app.config import get_notion_database_ids, get_notion_sync_interval
from app.constants import (
    INTERNAL_TO_NOTION_STATUS,
    NOTION_PRIORITY_OPTIONS,
    NOTION_TO_INTERNAL_STATUS,
)
from app.database import async_session_factory
from app.models import PriorityLevel, Task, TaskStatus

log = structlog.get_logger()


def is_approval_transition(old_status: TaskStatus, new_status: TaskStatus) -> bool:
    """Check if a status change represents an approval transition at a review gate.

    Approval transitions occur when a user reviews content at a review gate and approves it,
    transitioning from a *_READY status to a *_APPROVED status. These transitions require
    the pipeline to resume execution from the next step.

    Mandatory Review Gates (AC from Story 5.2):
        - ASSETS_READY → ASSETS_APPROVED (approve expensive video generation)
        - VIDEO_READY → VIDEO_APPROVED (approve after video generation)
        - AUDIO_READY → AUDIO_APPROVED (approve before final assembly)
        - FINAL_REVIEW → APPROVED (approve before YouTube upload)

    Args:
        old_status: Previous task status (before sync)
        new_status: New task status (from Notion)

    Returns:
        True if this is an approval transition, False otherwise

    Example:
        >>> is_approval_transition(TaskStatus.ASSETS_READY, TaskStatus.ASSETS_APPROVED)
        True
        >>> is_approval_transition(TaskStatus.QUEUED, TaskStatus.CLAIMED)
        False

    Related:
        - Story 5.2: Review Gate Enforcement
        - AC4: Detect approval transitions
        - AC5: Re-enqueue tasks after approval
    """
    approval_transitions = {
        (TaskStatus.ASSETS_READY, TaskStatus.ASSETS_APPROVED),
        (TaskStatus.VIDEO_READY, TaskStatus.VIDEO_APPROVED),
        (TaskStatus.AUDIO_READY, TaskStatus.AUDIO_APPROVED),
        (TaskStatus.FINAL_REVIEW, TaskStatus.APPROVED),
    }
    return (old_status, new_status) in approval_transitions


def is_rejection_transition(old_status: TaskStatus, new_status: TaskStatus) -> bool:
    """Check if a status change represents a rejection transition at a review gate.

    Rejection transitions occur when a user reviews content at a review gate and rejects it,
    transitioning from a *_READY status to a *_ERROR status. These transitions require
    logging the rejection reason and allowing manual retry.

    Mandatory Review Gates (Task 4 from Story 5.2):
        - ASSETS_READY → ASSET_ERROR (reject before video generation)
        - VIDEO_READY → VIDEO_ERROR (reject after video generation)
        - AUDIO_READY → AUDIO_ERROR (reject before final assembly)
        - FINAL_REVIEW → UPLOAD_ERROR (reject before YouTube upload)

    Args:
        old_status: Previous task status (before sync)
        new_status: New task status (from Notion)

    Returns:
        True if this is a rejection transition, False otherwise

    Example:
        >>> is_rejection_transition(TaskStatus.ASSETS_READY, TaskStatus.ASSET_ERROR)
        True
        >>> is_rejection_transition(TaskStatus.QUEUED, TaskStatus.CLAIMED)
        False

    Related:
        - Story 5.2 Task 4: Rejection Handling
        - Subtask 4.1: Detect rejection transitions
    """
    rejection_transitions = {
        (TaskStatus.ASSETS_READY, TaskStatus.ASSET_ERROR),
        (TaskStatus.VIDEO_READY, TaskStatus.VIDEO_ERROR),
        (TaskStatus.AUDIO_READY, TaskStatus.AUDIO_ERROR),
        (TaskStatus.FINAL_REVIEW, TaskStatus.UPLOAD_ERROR),
    }
    return (old_status, new_status) in rejection_transitions


@dataclass
class TaskSyncData:
    """Minimal task data for syncing to Notion.

    This dataclass is used to extract task data from the database,
    close the connection, then sync to Notion API without holding
    the database connection during API calls.

    Attributes:
        id: Task UUID
        notion_page_id: Notion page UUID
        status: Current task status
        priority: Task priority level
        title: Video title (for logging)
        updated_at: Timestamp of last task update (Story 5.6, AC2, FR55)
        retry_count: Number of retry attempts (Story 6.2)
        next_retry_at: Timestamp for next retry attempt (Story 6.2)
        completed_steps: Step-level checkpoints (Story 6.3, Task 9)
        step_metadata: Sub-step checkpoints (Story 6.3, Task 9)
    """

    id: uuid.UUID
    notion_page_id: str
    status: TaskStatus
    priority: PriorityLevel
    title: str
    updated_at: datetime
    retry_count: int = 0
    next_retry_at: datetime | None = None
    completed_steps: list[dict[str, Any]] | None = None
    step_metadata: dict[str, Any] | None = None


# Property extraction helpers


def extract_rich_text(prop: dict[str, Any] | None) -> str:
    """Extract plain text from Notion rich text or title property.

    Args:
        prop: Notion property object (rich_text or title type)

    Returns:
        Concatenated plain text content, empty string if None or no content
    """
    if not prop:
        return ""

    # Handle title property (array of rich text objects)
    if "title" in prop:
        texts = prop["title"]
    # Handle rich_text property (array of rich text objects)
    elif "rich_text" in prop:
        texts = prop["rich_text"]
    else:
        return ""

    # Extract text content from each rich text object
    return "".join(text.get("plain_text", "") for text in texts if text)


def extract_select(prop: dict[str, Any] | None) -> str | None:
    """Extract value from Notion select property.

    Args:
        prop: Notion select property object

    Returns:
        Selected value name, None if not set or invalid
    """
    if not prop or "select" not in prop:
        return None

    select_obj = prop["select"]
    if not select_obj or "name" not in select_obj:
        return None

    return str(select_obj["name"])


def extract_date(prop: dict[str, Any] | None) -> datetime | None:
    """Extract datetime from Notion date property.

    Args:
        prop: Notion date property object

    Returns:
        Parsed datetime, None if not set or invalid
    """
    if not prop or "date" not in prop:
        return None

    date_obj = prop["date"]
    if not date_obj or "start" not in date_obj:
        return None

    # Parse ISO 8601 date string
    try:
        return datetime.fromisoformat(date_obj["start"].replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def map_notion_status_to_internal(notion_status: str) -> str:
    """Map Notion status to TaskStatus enum value.

    Args:
        notion_status: Status value from Notion database

    Returns:
        TaskStatus enum value string

    Raises:
        ValueError: If notion_status is not a valid Notion status
    """
    if notion_status not in NOTION_TO_INTERNAL_STATUS:
        raise ValueError(f"Unknown Notion status: {notion_status}")

    return NOTION_TO_INTERNAL_STATUS[notion_status]


def map_internal_status_to_notion(task_status: TaskStatus) -> str:
    """Map TaskStatus enum to Notion status value.

    Args:
        task_status: TaskStatus enum instance

    Returns:
        Notion status value string

    Raises:
        ValueError: If task_status value is not mapped
    """
    status_value = task_status.value
    if status_value not in INTERNAL_TO_NOTION_STATUS:
        raise ValueError(f"No Notion mapping for TaskStatus: {status_value}")

    return INTERNAL_TO_NOTION_STATUS[status_value]


def map_notion_priority_to_internal(notion_priority: str | None) -> PriorityLevel:
    """Map Notion priority to PriorityLevel enum.

    Args:
        notion_priority: Priority value from Notion (High/Normal/Low)

    Returns:
        PriorityLevel enum instance, defaults to NORMAL if invalid
    """
    if not notion_priority or notion_priority not in NOTION_PRIORITY_OPTIONS:
        return PriorityLevel.NORMAL

    # Map Notion priority to enum
    priority_map = {
        "High": PriorityLevel.HIGH,
        "Normal": PriorityLevel.NORMAL,
        "Low": PriorityLevel.LOW,
    }
    return priority_map[notion_priority]


def validate_notion_entry(page: dict[str, Any]) -> tuple[bool, str | None]:
    """Validate Notion entry has required fields for task creation.

    Validates:
    - Title: Must not be empty
    - Topic: Must not be empty
    - Channel: Must be present (validation against configured channels happens elsewhere)

    Args:
        page: Notion page object from API

    Returns:
        Tuple of (is_valid, error_message)
        - (True, None) if valid
        - (False, error_message) if validation fails
    """
    properties = page.get("properties", {})

    # Extract required fields
    title = extract_rich_text(properties.get("Title"))
    topic = extract_rich_text(properties.get("Topic"))
    channel = extract_select(properties.get("Channel"))

    # Validate Title
    if not title or not title.strip():
        return False, "Missing Title - cannot queue"

    # Validate Topic
    if not topic or not topic.strip():
        return False, "Missing Topic - cannot queue"

    # Validate Channel
    if not channel:
        return False, "Missing Channel - cannot queue"

    return True, None


async def handle_approval_transition(task: Task, session: AsyncSession) -> None:
    """Handle approval transition by re-enqueueing task for pipeline continuation.

    When a user approves content at a review gate (e.g., ASSETS_READY → ASSETS_APPROVED),
    the task needs to be re-enqueued so a worker can claim it and resume the pipeline
    from the next step.

    The pipeline orchestrator will:
    - Load step_completion_metadata to see which steps are complete
    - Skip already-completed steps
    - Resume from the next uncompleted step

    Args:
        task: Task instance with approved status (*_APPROVED)
        session: Active async database session

    Note:
        This function is called by the Notion sync loop when an approval transition
        is detected. The task status is reset to QUEUED so workers can claim it.
    """
    correlation_id = str(uuid.uuid4())

    # Story 5.2 Task 3: Set review_completed_at timestamp for observability
    old_status = task.status
    now = datetime.now(timezone.utc)
    task.review_completed_at = now
    task.updated_at = now

    # Calculate review duration for logging
    review_duration = None
    if task.review_started_at:
        delta = task.review_completed_at - task.review_started_at
        review_duration = int(delta.total_seconds())

    # Set status to QUEUED so workers can claim task
    task.status = TaskStatus.QUEUED

    await session.flush()

    log.info(
        "task_requeued_after_approval",
        correlation_id=correlation_id,
        task_id=str(task.id),
        notion_page_id=task.notion_page_id,
        approval_status=old_status.value,
        new_status=task.status.value,
        review_duration_seconds=review_duration,
        message="Task re-enqueued for pipeline continuation",
    )


async def handle_rejection_transition(
    task: Task, notion_page: dict[str, Any], session: AsyncSession
) -> None:
    """Handle rejection transition by moving task to error state and logging reason.

    When a user rejects content at a review gate (e.g., ASSETS_READY → ASSET_ERROR),
    the task needs to be moved to the appropriate error state. The rejection reason
    from the Notion "Error Log" property should be captured for debugging.

    The user can manually retry by changing the status back to QUEUED in Notion.
    The pipeline orchestrator will then resume from the beginning of the failed step.

    Args:
        task: Task instance with error status (*_ERROR)
        notion_page: Notion page object (to extract Error Log property)
        session: Active async database session

    Note:
        This function is called by the Notion sync loop when a rejection transition
        is detected. The task status is already set to the error state.

    Related:
        - Story 5.2 Task 4: Rejection Handling
        - Subtask 4.2: Move task to appropriate error state
        - Subtask 4.3: Log rejection reason from Notion Error Log property
    """
    correlation_id = str(uuid.uuid4())

    # Story 5.2 Task 4: Set review_completed_at timestamp for observability
    old_status = task.status
    now = datetime.now(timezone.utc)
    task.review_completed_at = now
    task.updated_at = now

    # Calculate review duration for logging
    review_duration = None
    if task.review_started_at:
        delta = task.review_completed_at - task.review_started_at
        review_duration = int(delta.total_seconds())

    # Story 5.2 Task 4 Subtask 4.3: Extract rejection reason from Notion Error Log property
    properties = notion_page.get("properties", {})
    error_log_prop = properties.get("Error Log")
    rejection_reason = extract_rich_text(error_log_prop) if error_log_prop else None

    # Append rejection reason to task error log if provided
    if rejection_reason:
        current_log = task.error_log or ""
        timestamp = now.isoformat()
        new_entry = f"[{timestamp}] Review Rejection: {rejection_reason}"
        task.error_log = f"{current_log}\n{new_entry}".strip()

    await session.flush()

    log.warning(
        "task_rejected_at_review_gate",
        correlation_id=correlation_id,
        task_id=str(task.id),
        notion_page_id=task.notion_page_id,
        error_status=old_status.value,
        rejection_reason=rejection_reason or "No reason provided",
        review_duration_seconds=review_duration,
        message="Task rejected at review gate - manual retry available",
    )


async def sync_notion_page_to_task(
    notion_page: dict[str, Any],
    session: AsyncSession,
) -> Task:
    """Create or update Task from Notion page.

    This function implements the Notion → Database sync direction.
    It maps all Notion properties to Task model fields and creates/updates
    the task record.

    Transaction Pattern:
    - This function expects an active database session
    - Caller is responsible for transaction management
    - Short transaction: Extract data, create/update task, commit

    Args:
        notion_page: Notion page object from API
        session: Active async database session

    Returns:
        Created or updated Task instance (for existing tasks only).

    Raises:
        ValueError: If required fields are missing or invalid
        IntegrityError: If notion_page_id already exists (idempotent)
        NotImplementedError: If creating new task (channel lookup not implemented)

    Note:
        Story 2.3 focuses on property mapping and validation.
        Full task creation requires channel lookup implementation (future story).
    """
    correlation_id = str(uuid.uuid4())
    notion_page_id = notion_page["id"]
    properties = notion_page.get("properties", {})

    # Extract all properties
    title = extract_rich_text(properties.get("Title"))
    topic = extract_rich_text(properties.get("Topic"))
    story_direction = extract_rich_text(properties.get("Story Direction", {}))
    # channel_name = extract_select(properties.get("Channel"))  # Extracted for validation
    notion_status = extract_select(properties.get("Status"))
    notion_priority = extract_select(properties.get("Priority"))

    # Validate required fields
    is_valid, error_msg = validate_notion_entry(notion_page)
    if not is_valid:
        log.warning(
            "notion_entry_validation_failed",
            correlation_id=correlation_id,
            notion_page_id=notion_page_id,
            title=title,
            error=error_msg,
        )
        raise ValueError(error_msg)

    # Map status to internal enum
    try:
        internal_status = map_notion_status_to_internal(notion_status or "Draft")
        status_enum = TaskStatus(internal_status)
    except (ValueError, KeyError) as e:
        log.error(
            "status_mapping_failed",
            correlation_id=correlation_id,
            notion_page_id=notion_page_id,
            notion_status=notion_status,
            error=str(e),
        )
        # Default to draft if status mapping fails
        status_enum = TaskStatus.DRAFT

    # Map priority to internal enum
    priority_enum = map_notion_priority_to_internal(notion_priority)

    # Query for existing task by notion_page_id
    result = await session.execute(select(Task).where(Task.notion_page_id == notion_page_id))
    existing_task = result.scalar_one_or_none()

    if existing_task:
        # Store old status for approval transition detection (Story 5.2)
        old_status = existing_task.status

        # Update existing task
        existing_task.title = title
        existing_task.topic = topic
        existing_task.story_direction = story_direction or ""
        existing_task.status = status_enum
        existing_task.priority = priority_enum

        log.info(
            "notion_entry_updated",
            correlation_id=correlation_id,
            notion_page_id=notion_page_id,
            task_id=str(existing_task.id),
            title=title,
            status=status_enum.value,
        )

        # Story 5.2: Check for approval transition and re-enqueue if needed
        if is_approval_transition(old_status, status_enum):
            await handle_approval_transition(existing_task, session)

        # Story 5.2 Task 4: Check for rejection transition and log rejection reason
        if is_rejection_transition(old_status, status_enum):
            await handle_rejection_transition(existing_task, notion_page, session)

        return existing_task
    else:
        # NOTE: This is a simplified implementation for Story 2.3
        # In a real implementation, we would need to:
        # 1. Look up the Channel by channel_name
        # 2. Get the Channel.id (UUID) to use as foreign key
        # For now, we'll raise an error to indicate incomplete implementation
        raise NotImplementedError(
            "Channel lookup by name not yet implemented. "
            "Story 2.3 focuses on property mapping and validation. "
            "Full task creation requires channel lookup from channel_configs."
        )


def format_retry_display(retry_count: int, next_retry_at: datetime) -> str:
    """Format retry info for user display in Notion.

    Args:
        retry_count: Current retry attempt number (1-5)
        next_retry_at: Timestamp when next retry will occur

    Returns:
        Formatted string like "Retrying in 15 min (Attempt 3/5)"

    Example:
        >>> from datetime import datetime, timedelta, timezone
        >>> next_retry = datetime.now(timezone.utc) + timedelta(minutes=15)
        >>> format_retry_display(3, next_retry)
        'Retrying in 15 min (Attempt 3/5)'
    """
    from app.services.retry_orchestrator import MAX_RETRY_ATTEMPTS

    now = datetime.now(timezone.utc)

    # Handle timezone-naive datetimes (SQLite compatibility)
    retry_time = next_retry_at
    if retry_time.tzinfo is None:
        retry_time = retry_time.replace(tzinfo=timezone.utc)

    time_remaining = retry_time - now

    # Format time remaining
    total_seconds = time_remaining.total_seconds()
    if total_seconds < 60:
        time_str = f"{int(total_seconds)}s"
    elif total_seconds < 3600:
        time_str = f"{int(total_seconds / 60)} min"
    else:
        hours = int(total_seconds / 3600)
        time_str = f"{hours} hr" if hours == 1 else f"{hours} hrs"

    return f"Retrying in {time_str} (Attempt {retry_count}/{MAX_RETRY_ATTEMPTS})"


def format_checkpoint_progress(
    step_metadata: dict[str, Any] | None,
    status: TaskStatus,
) -> str | None:
    """Format checkpoint progress for Notion Progress field (Story 6.3, Task 9).

    Creates a human-readable progress summary showing completed sub-steps
    for the current pipeline step. This helps users see exactly which clips/assets
    completed before a failure, enabling them to understand resume-from-failure behavior.

    Args:
        step_metadata: Sub-step checkpoint data (completed clips/assets)
        status: Current task status to determine which progress to show

    Returns:
        Formatted progress string or None if no relevant checkpoints

    Examples:
        >>> # Video generation with 10/18 clips complete
        >>> format_checkpoint_progress(
        ...     {"completed_video_clips": [1,2,3,4,5,6,7,8,9,10]},
        ...     TaskStatus.VIDEO_ERROR
        ... )
        'Video: 10/18 clips ✓'

        >>> # Audio generation with 5/18 clips complete
        >>> format_checkpoint_progress(
        ...     {"completed_narration_clips": [1,2,3,4,5]},
        ...     TaskStatus.AUDIO_ERROR
        ... )
        'Audio: 5/18 clips ✓'

        >>> # Asset generation with 15 assets complete
        >>> format_checkpoint_progress(
        ...     {"completed_assets": ["char_1", "char_2", ...]},  # 15 items
        ...     TaskStatus.ASSET_ERROR
        ... )
        'Assets: 15 complete ✓'

    Related:
        - Story 6.3 Task 9: Show checkpoint progress in Notion
        - Tasks 3-5: Sub-step checkpointing implementation
    """
    if not step_metadata:
        return None

    # Video generation progress (18 clips total)
    if status == TaskStatus.VIDEO_ERROR and "completed_video_clips" in step_metadata:
        completed = len(step_metadata["completed_video_clips"])
        return f"Video: {completed}/18 clips ✓"

    # Audio generation progress (18 clips total)
    # AUDIO_ERROR can come from either narration or SFX generation (both produce audio)
    if status == TaskStatus.AUDIO_ERROR:
        # Check for narration progress
        if "completed_narration_clips" in step_metadata:
            completed = len(step_metadata["completed_narration_clips"])
            # If SFX also in progress, show both
            if "completed_sfx_clips" in step_metadata:
                sfx_completed = len(step_metadata["completed_sfx_clips"])
                return f"Audio: {completed}/18 clips ✓ | SFX: {sfx_completed}/18 clips ✓"
            return f"Audio: {completed}/18 clips ✓"

        # Check for SFX progress (if narration complete, only SFX in progress)
        if "completed_sfx_clips" in step_metadata:
            completed = len(step_metadata["completed_sfx_clips"])
            return f"SFX: {completed}/18 clips ✓"

    # Asset generation progress (variable count)
    if status == TaskStatus.ASSET_ERROR and "completed_assets" in step_metadata:
        completed = len(step_metadata["completed_assets"])
        return f"Assets: {completed} complete ✓"

    return None


async def push_task_to_notion(task: Task | TaskSyncData, notion_client: NotionClient) -> None:
    """Push Task status/priority updates back to Notion.

    This function implements the Database → Notion sync direction.
    It updates the Notion page properties to reflect current Task state.

    Transaction Pattern:
    - This function does NOT hold database session
    - Caller should extract task data before closing DB connection
    - Only makes Notion API call (no DB operations)

    Args:
        task: Task instance or TaskSyncData to sync to Notion
        notion_client: NotionClient with rate limiting

    Raises:
        NotionAPIError: On non-retriable API errors
        NotionRateLimitError: After retry exhaustion
    """
    correlation_id = str(uuid.uuid4())

    if not task.notion_page_id:
        log.warning(
            "task_missing_notion_page_id",
            correlation_id=correlation_id,
            task_id=str(task.id),
            title=task.title,
        )
        return

    # Map internal status to Notion status
    try:
        notion_status = map_internal_status_to_notion(task.status)
    except ValueError as e:
        log.error(
            "status_mapping_failed",
            correlation_id=correlation_id,
            task_id=str(task.id),
            internal_status=task.status.value,
            error=str(e),
        )
        return

    # Map priority to Notion priority
    priority_map = {
        PriorityLevel.HIGH: "High",
        PriorityLevel.NORMAL: "Normal",
        PriorityLevel.LOW: "Low",
    }
    notion_priority = priority_map[task.priority]

    # Build properties dict with Status, Priority, and Updated timestamp
    properties = {
        "Status": {"select": {"name": notion_status}},
        "Priority": {"select": {"name": notion_priority}},
    }

    # Add Updated timestamp if available (Story 5.6, AC2, FR55)
    # Format as ISO 8601 for Notion date property
    if task.updated_at:
        properties["Updated"] = {"date": {"start": task.updated_at.isoformat()}}

    # Add retry info if task is retrying (Story 6.2)
    # Display as "Retrying in 15 min (Attempt 3/5)" in Notion Error Log field
    if task.retry_count > 0 and task.next_retry_at:
        retry_display = format_retry_display(task.retry_count, task.next_retry_at)
        properties["Error Log"] = {
            "rich_text": [{"text": {"content": retry_display}}]
        }

    # Add checkpoint progress if available (Story 6.3, Task 9)
    # Display as "Video: 10/18 clips ✓" in Notion Progress field
    # This shows users which sub-steps completed before failure, helping them
    # understand resume-from-failure behavior
    checkpoint_progress = format_checkpoint_progress(
        getattr(task, "step_metadata", None),
        task.status
    )
    if checkpoint_progress:
        properties["Progress"] = {
            "rich_text": [{"text": {"content": checkpoint_progress}}]
        }

    # Update Notion page properties
    try:
        await notion_client.update_page_properties(
            task.notion_page_id,
            properties,
        )

        log.info(
            "task_synced_to_notion",
            correlation_id=correlation_id,
            task_id=str(task.id),
            notion_page_id=task.notion_page_id,
            notion_status=notion_status,
            notion_priority=notion_priority,
            updated_at=task.updated_at.isoformat() if task.updated_at else None,
        )
    except NotionAPIError as e:
        log.error(
            "notion_sync_failed",
            correlation_id=correlation_id,
            task_id=str(task.id),
            notion_page_id=task.notion_page_id,
            error=str(e),
            status_code=e.status_code,
        )
        raise


async def sync_notion_queued_to_database(
    notion_client: NotionClient,
    notion_database_id: str,
) -> None:
    """Poll Notion database for videos with Status = 'Queued' and enqueue tasks.

    This implements the Notion → Database sync direction for batch queuing.
    It queries all pages from a Notion database, filters for "Queued" status,
    and enqueues each as a task.

    Architecture:
    - Short transactions per page (query → close → API call → reopen)
    - Graceful error handling (skip invalid pages, continue processing)
    - Duplicate detection via enqueue_task_from_notion_page

    Args:
        notion_client: NotionClient with rate limiting
        notion_database_id: Notion database ID to poll
    """
    from app.services.task_service import enqueue_task_from_notion_page

    correlation_id = str(uuid.uuid4())

    try:
        # Get all pages from database (rate limited automatically)
        pages = await notion_client.get_database_pages(notion_database_id)

        # Filter for Queued status
        queued_pages = [
            p for p in pages if extract_select(p.get("properties", {}).get("Status")) == "Queued"
        ]

        if not queued_pages:
            return

        log.info(
            "batch_enqueue_started",
            correlation_id=correlation_id,
            database_id=notion_database_id,
            queued_count=len(queued_pages),
        )

        # Process each queued page
        enqueued_count = 0
        skipped_count = 0

        for page in queued_pages:
            try:
                # Short transaction per page
                if async_session_factory is None:
                    raise RuntimeError("Database not configured")
                async with async_session_factory() as session, session.begin():
                    task = await enqueue_task_from_notion_page(page, session)

                    if task:
                        enqueued_count += 1
                        log.info(
                            "task_enqueued_from_notion",
                            correlation_id=correlation_id,
                            notion_page_id=page["id"],
                            task_id=str(task.id),
                            title=task.title,
                        )
                    else:
                        skipped_count += 1

            except (ValueError, KeyError, AttributeError) as e:
                # Log validation/data errors but continue processing
                log.warning(
                    "notion_page_enqueue_failed",
                    correlation_id=correlation_id,
                    notion_page_id=page.get("id"),
                    error=str(e),
                    exc_info=True,
                )
                skipped_count += 1

        log.info(
            "batch_enqueue_completed",
            correlation_id=correlation_id,
            database_id=notion_database_id,
            enqueued=enqueued_count,
            skipped=skipped_count,
            total=len(queued_pages),
        )

    except NotionAPIError as e:
        log.error(
            "notion_database_query_failed",
            correlation_id=correlation_id,
            database_id=notion_database_id,
            error=str(e),
            status_code=e.status_code,
        )


async def sync_database_status_to_notion(notion_client: NotionClient) -> None:
    """Push task status updates back to Notion (Database → Notion direction).

    This implements the existing Database → Notion sync direction.
    Queries all tasks with notion_page_id and pushes status/priority updates.

    Architecture:
    - Short transaction to query tasks
    - No DB connection held during Notion API calls
    - Graceful error handling per task

    Args:
        notion_client: NotionClient with rate limiting
    """
    # Step 1: Query tasks to sync (short transaction)
    if async_session_factory is None:
        raise RuntimeError("Database not configured")
    async with async_session_factory() as session:
        # Query all tasks with notion_page_id set
        result = await session.execute(select(Task).where(Task.notion_page_id.isnot(None)))
        tasks = result.scalars().all()

        # Extract minimal data needed for sync using dataclass
        # This allows us to close DB connection before API calls
        task_data = [
            TaskSyncData(
                id=task.id,
                notion_page_id=task.notion_page_id,
                status=task.status,
                priority=task.priority,
                title=task.title,
                updated_at=task.updated_at,
                retry_count=task.retry_count,
                next_retry_at=task.next_retry_at,
                completed_steps=task.completed_steps,  # Story 6.3, Task 9: Checkpoint fields
                step_metadata=task.step_metadata,      # Story 6.3, Task 9: Checkpoint fields
            )
            for task in tasks
        ]

    # Step 2: Sync to Notion (NO DB connection held)
    for task_sync in task_data:
        try:
            await push_task_to_notion(task_sync, notion_client)

        except (NotionAPIError, ValueError, KeyError, AttributeError) as e:
            # Log error but continue with other tasks
            # Only catch expected errors (API, data validation, missing attributes)
            log.error(
                "task_sync_failed",
                correlation_id=str(uuid.uuid4()),
                task_id=str(task_sync.id),
                notion_page_id=task_sync.notion_page_id,
                error=str(e),
                exc_info=True,
            )


async def sync_database_to_notion_loop(notion_client: NotionClient) -> None:
    """Background task: Bidirectional sync between Notion and PostgreSQL.

    This is the main sync loop that runs continuously as a background task.
    It implements two sync directions:
    1. Notion → Database: Poll Notion for "Queued" status, enqueue tasks
    2. Database → Notion: Push task status updates back to Notion

    Architecture:
    - Runs as FastAPI lifespan background task
    - Uses short transactions (query → close → API call → repeat)
    - Never holds DB connection during Notion API calls
    - Gracefully handles errors and continues loop

    Args:
        notion_client: NotionClient instance (shared across loop iterations)

    Note:
        This function runs indefinitely until cancelled by FastAPI shutdown.
        Errors are logged but do not stop the loop.
    """
    # Load configuration from environment
    sync_interval = get_notion_sync_interval()
    notion_database_ids = get_notion_database_ids()

    log.info(
        "notion_sync_loop_started",
        interval_seconds=sync_interval,
        database_count=len(notion_database_ids),
        database_ids=notion_database_ids if notion_database_ids else None,
    )

    if not notion_database_ids:
        log.warning(
            "notion_sync_no_databases_configured",
            message="NOTION_DATABASE_IDS not set - sync loop will run but skip Notion → DB sync",
        )

    while True:
        try:
            # Direction 1: Notion → Database (detect "Queued" status changes)
            for database_id in notion_database_ids:
                await sync_notion_queued_to_database(notion_client, database_id)

            # Direction 2: Database → Notion (push task status updates)
            await sync_database_status_to_notion(notion_client)

            # Wait before next sync cycle
            await asyncio.sleep(sync_interval)

        except asyncio.CancelledError:
            # Graceful shutdown
            log.info("notion_sync_loop_cancelled")
            break
        except NotionAPIError as e:
            # Log Notion API errors but keep loop running
            log.error(
                "notion_sync_api_error",
                correlation_id=str(uuid.uuid4()),
                error=str(e),
                status_code=e.status_code,
                exc_info=True,
            )
            # Wait before retry to avoid tight error loop
            await asyncio.sleep(10)
        except (RuntimeError, OSError, TimeoutError) as e:
            # Log database/network errors but keep loop running
            # Does NOT catch system exceptions (KeyboardInterrupt, SystemExit)
            log.error(
                "notion_sync_loop_error",
                correlation_id=str(uuid.uuid4()),
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            # Wait before retry to avoid tight error loop
            await asyncio.sleep(10)
