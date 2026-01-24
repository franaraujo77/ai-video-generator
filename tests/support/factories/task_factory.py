"""Task factories for test data generation (Story 6.5)."""

from uuid import uuid4
from app.models import Task, TaskStatus


def create_task(
    channel_id: str = "poke1",
    notion_page_id: str | None = None,
    title: str = "Test Pokemon Documentary",
    topic: str = "Nature Documentary",
    story_direction: str = "Documentary about a wild Pokemon",
    status: TaskStatus = TaskStatus.QUEUED,
    correlation_id: uuid4 | None = None,
    retry_count: int = 0,
    **kwargs,
) -> Task:
    """Create a test task for use in tests.

    Args:
        channel_id: Channel identifier (UUID) - MUST be passed explicitly in tests
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
    # Generate notion_page_id if not provided
    if notion_page_id is None:
        notion_page_id = str(uuid4())

    # Create task with minimal required fields
    task = Task(
        id=correlation_id or uuid4(),  # Use correlation_id as task.id if provided
        channel_id=channel_id,  # Use provided channel_id (must be valid UUID)
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
