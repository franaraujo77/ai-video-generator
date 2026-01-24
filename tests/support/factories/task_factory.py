"""Task factories for test data generation (Story 6.5)."""

from uuid import uuid4, UUID
from app.models import Task, TaskStatus


def create_task(
    channel_id: UUID | str | None = None,
    notion_page_id: str | None = None,
    title: str = "Test Pokemon Documentary",
    topic: str = "Nature Documentary",
    story_direction: str = "Documentary about a wild Pokemon",
    status: TaskStatus = TaskStatus.QUEUED,
    correlation_id: UUID | None = None,
    retry_count: int = 0,
    **kwargs,
) -> Task:
    """Create a test task for use in tests.

    Args:
        channel_id: Channel identifier - accepts UUID, valid UUID string, or None (auto-generates)
        notion_page_id: Notion page UUID (auto-generated if None)
        title: Video title
        topic: Video topic
        story_direction: Story direction text
        status: Task status (default: QUEUED)
        correlation_id: Correlation ID for distributed tracing (uses task.id if None)
        retry_count: Number of retry attempts (default: 0)
        **kwargs: Additional Task fields (e.g., auto_recovered, error_category)

    Returns:
        Task instance (not committed to DB)

    Note:
        For correlation_id, we use task.id as the correlation since Task model
        doesn't have a separate correlation_id field yet.
    """
    # Convert channel_id to UUID if needed
    if channel_id is None:
        channel_id = uuid4()
    elif isinstance(channel_id, str):
        # Try to parse as UUID, or generate new if invalid format
        try:
            channel_id = UUID(channel_id)
        except ValueError:
            # Invalid UUID string (e.g., "poke1") - generate valid UUID
            channel_id = uuid4()

    # Generate notion_page_id if not provided
    if notion_page_id is None:
        notion_page_id = str(uuid4())

    # Create task with minimal required fields
    task = Task(
        id=correlation_id or uuid4(),  # Use correlation_id as task.id if provided
        channel_id=channel_id,  # Now guaranteed to be UUID
        notion_page_id=notion_page_id,
        title=title,
        topic=topic,
        story_direction=story_direction,
        status=status,
        retry_count=retry_count,
        **kwargs,
    )

    # Store correlation_id as task.id for testing (per Story 6.5 pattern)
    task.correlation_id = task.id

    return task
