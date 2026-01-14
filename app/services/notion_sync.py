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
from datetime import datetime
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
    """

    id: uuid.UUID
    notion_page_id: str
    status: TaskStatus
    priority: PriorityLevel
    title: str


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

    # Update Notion page properties
    try:
        await notion_client.update_page_properties(
            task.notion_page_id,
            {
                "Status": {"select": {"name": notion_status}},
                "Priority": {"select": {"name": notion_priority}},
            },
        )

        log.info(
            "task_synced_to_notion",
            correlation_id=correlation_id,
            task_id=str(task.id),
            notion_page_id=task.notion_page_id,
            notion_status=notion_status,
            notion_priority=notion_priority,
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
