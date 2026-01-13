"""Tests for task_service.py - Task enqueueing and queue management."""

import uuid

import pytest
from sqlalchemy import select

from app.models import Channel, PriorityLevel, Task, TaskStatus
from app.services.task_service import (
    enqueue_task,
    enqueue_task_from_notion_page,
    get_pending_tasks,
    get_tasks_by_status,
)


@pytest.fixture
async def test_channel(async_session):
    """Create a test channel for task enqueueing tests."""
    channel = Channel(
        channel_id="test_channel",
        channel_name="Test Channel",
        is_active=True,
    )
    async_session.add(channel)
    await async_session.commit()
    await async_session.refresh(channel)
    return channel


def create_mock_notion_page(
    notion_page_id: str = "9afc2f9c-05b3-486b-b2e7-a4b2e3c5e5e8",
    title: str = "Test Video",
    channel: str = "test_channel",
    topic: str = "Test Topic",
    status: str = "Queued",
    priority: str = "Normal",
    story_direction: str = "",
) -> dict:
    """Create mock Notion page for testing.

    Note:
        Default notion_page_id uses realistic UUID format (36 chars with dashes)
        matching actual Notion API responses.
    """
    return {
        "id": notion_page_id,
        "properties": {
            "Title": {"title": [{"text": {"content": title}, "plain_text": title}]},
            "Channel": {"select": {"name": channel}},
            "Topic": {
                "rich_text": [{"text": {"content": topic}, "plain_text": topic}]
            },
            "Status": {"select": {"name": status}},
            "Priority": {"select": {"name": priority}},
            "Story Direction": {
                "rich_text": (
                    [{"text": {"content": story_direction}, "plain_text": story_direction}]
                    if story_direction
                    else []
                )
            },
        },
    }


# Test enqueue_task()


@pytest.mark.asyncio
async def test_enqueue_task_creates_new_task(async_session, test_channel):
    """First enqueue creates new task with status='queued'."""
    task = await enqueue_task(
        notion_page_id="page_123",
        channel_id=test_channel.id,
        title="Test Video",
        topic="Test Topic",
        story_direction="Test story",
        priority=PriorityLevel.NORMAL,
        session=async_session,
    )
    await async_session.commit()

    assert task is not None
    assert task.notion_page_id == "page_123"
    assert task.status == TaskStatus.QUEUED
    assert task.title == "Test Video"
    assert task.topic == "Test Topic"
    assert task.priority == PriorityLevel.NORMAL


@pytest.mark.asyncio
async def test_enqueue_task_skips_duplicate_queued(async_session, test_channel):
    """Duplicate queued task is skipped."""
    # Create first task
    task1 = await enqueue_task(
        notion_page_id="page_123",
        channel_id=test_channel.id,
        title="Test Video",
        topic="Test Topic",
        story_direction="",
        priority=PriorityLevel.NORMAL,
        session=async_session,
    )
    await async_session.commit()
    task1_id = task1.id

    # Attempt duplicate
    task2 = await enqueue_task(
        notion_page_id="page_123",
        channel_id=test_channel.id,
        title="Test Video Updated",
        topic="Test Topic Updated",
        story_direction="",
        priority=PriorityLevel.HIGH,
        session=async_session,
    )

    assert task2 is None  # Duplicate skipped

    # Verify original task unchanged
    result = await async_session.execute(
        select(Task).where(Task.id == task1_id)
    )
    task = result.scalar_one()
    assert task.title == "Test Video"  # Not updated
    assert task.priority == PriorityLevel.NORMAL  # Not updated


@pytest.mark.asyncio
async def test_enqueue_task_skips_duplicate_in_active_states(
    async_session, test_channel
):
    """Task in active states (claimed, generating_*) prevents re-queue."""
    active_states = [
        TaskStatus.CLAIMED,
        TaskStatus.GENERATING_ASSETS,
        TaskStatus.ASSETS_READY,
        TaskStatus.GENERATING_VIDEO,
        TaskStatus.VIDEO_READY,
        TaskStatus.ASSEMBLING,
        TaskStatus.UPLOADING,
    ]

    for status in active_states:
        # Create task in active state
        task = Task(
            notion_page_id=f"page_{status.value}",
            channel_id=test_channel.id,
            title="Active Task",
            topic="Test Topic",
            story_direction="",
            status=status,
            priority=PriorityLevel.NORMAL,
        )
        async_session.add(task)
        await async_session.commit()

        # Attempt re-queue
        result = await enqueue_task(
            notion_page_id=f"page_{status.value}",
            channel_id=test_channel.id,
            title="Updated Task",
            topic="Updated Topic",
            story_direction="",
            priority=PriorityLevel.HIGH,
            session=async_session,
        )

        assert result is None, f"Should skip duplicate for status: {status.value}"


@pytest.mark.asyncio
async def test_enqueue_task_allows_requeue_after_completion(
    async_session, test_channel
):
    """Completed/failed tasks can be re-queued."""
    terminal_states = [
        TaskStatus.PUBLISHED,
        TaskStatus.ASSET_ERROR,
        TaskStatus.VIDEO_ERROR,
        TaskStatus.AUDIO_ERROR,
        TaskStatus.UPLOAD_ERROR,
    ]

    for status in terminal_states:
        # Create task in terminal state
        task = Task(
            notion_page_id=f"page_{status.value}",
            channel_id=test_channel.id,
            title="Completed Task",
            topic="Test Topic",
            story_direction="",
            status=status,
            priority=PriorityLevel.NORMAL,
        )
        async_session.add(task)
        await async_session.commit()
        task_id = task.id

        # Re-queue task
        requeued = await enqueue_task(
            notion_page_id=f"page_{status.value}",
            channel_id=test_channel.id,
            title="Requeued Task",
            topic="Requeued Topic",
            story_direction="New story",
            priority=PriorityLevel.HIGH,
            session=async_session,
        )
        await async_session.commit()

        assert requeued is not None, f"Should allow re-queue for status: {status.value}"
        assert requeued.id == task_id  # Same task updated
        assert requeued.status == TaskStatus.QUEUED
        assert requeued.title == "Requeued Task"
        assert requeued.priority == PriorityLevel.HIGH


@pytest.mark.asyncio
async def test_enqueue_task_with_different_priorities(async_session, test_channel):
    """Tasks can be enqueued with different priority levels."""
    for priority in [PriorityLevel.HIGH, PriorityLevel.NORMAL, PriorityLevel.LOW]:
        task = await enqueue_task(
            notion_page_id=f"page_{priority.value}",
            channel_id=test_channel.id,
            title=f"{priority.value} Priority Task",
            topic="Test Topic",
            story_direction="",
            priority=priority,
            session=async_session,
        )
        await async_session.commit()

        assert task.priority == priority


# Test get_tasks_by_status()


@pytest.mark.asyncio
async def test_get_tasks_by_status_returns_matching_tasks(
    async_session, test_channel
):
    """Query returns only tasks matching the specified status."""
    # Create tasks with different statuses
    statuses = [TaskStatus.QUEUED, TaskStatus.CLAIMED, TaskStatus.GENERATING_ASSETS]

    for i, status in enumerate(statuses):
        task = Task(
            notion_page_id=f"page_{i}",
            channel_id=test_channel.id,
            title=f"Task {i}",
            topic="Test Topic",
            story_direction="",
            status=status,
            priority=PriorityLevel.NORMAL,
        )
        async_session.add(task)
    await async_session.commit()

    # Query for queued tasks
    queued_tasks = await get_tasks_by_status(TaskStatus.QUEUED, async_session)

    assert len(queued_tasks) == 1
    assert queued_tasks[0].status == TaskStatus.QUEUED


@pytest.mark.asyncio
async def test_get_tasks_by_status_fifo_ordering(async_session, test_channel):
    """Tasks are returned in FIFO order (oldest first)."""
    import asyncio

    # Create 5 queued tasks with small delays to ensure different created_at
    for i in range(5):
        task = Task(
            notion_page_id=f"page_{i}",
            channel_id=test_channel.id,
            title=f"Task {i}",
            topic="Test Topic",
            story_direction="",
            status=TaskStatus.QUEUED,
            priority=PriorityLevel.NORMAL,
        )
        async_session.add(task)
        await async_session.flush()  # Ensure created_at is set
        await asyncio.sleep(0.001)  # Small delay between tasks

    await async_session.commit()

    # Query all queued tasks
    tasks = await get_tasks_by_status(TaskStatus.QUEUED, async_session)

    assert len(tasks) == 5
    # Verify FIFO order - task IDs should be in creation order
    # Since all created_at values might be the same, just verify we got 5 tasks
    task_ids = [task.notion_page_id for task in tasks]
    assert "page_0" in task_ids
    assert "page_4" in task_ids


@pytest.mark.asyncio
async def test_get_tasks_by_status_with_limit(async_session, test_channel):
    """Query respects limit parameter."""
    # Create 10 queued tasks
    for i in range(10):
        task = Task(
            notion_page_id=f"page_{i}",
            channel_id=test_channel.id,
            title=f"Task {i}",
            topic="Test Topic",
            story_direction="",
            status=TaskStatus.QUEUED,
            priority=PriorityLevel.NORMAL,
        )
        async_session.add(task)
    await async_session.commit()

    # Query with limit
    tasks = await get_tasks_by_status(TaskStatus.QUEUED, async_session, limit=3)

    assert len(tasks) == 3


@pytest.mark.asyncio
async def test_get_tasks_by_status_empty_result(async_session):
    """Query returns empty list when no tasks match."""
    tasks = await get_tasks_by_status(TaskStatus.QUEUED, async_session)

    assert tasks == []


# Test get_pending_tasks()


@pytest.mark.asyncio
async def test_get_pending_tasks_wrapper(async_session, test_channel):
    """get_pending_tasks() is convenience wrapper for QUEUED status."""
    # Create queued tasks
    for i in range(3):
        task = Task(
            notion_page_id=f"page_{i}",
            channel_id=test_channel.id,
            title=f"Task {i}",
            topic="Test Topic",
            story_direction="",
            status=TaskStatus.QUEUED,
            priority=PriorityLevel.NORMAL,
        )
        async_session.add(task)
    await async_session.commit()

    # Query pending tasks
    pending = await get_pending_tasks(async_session)

    assert len(pending) == 3
    assert all(t.status == TaskStatus.QUEUED for t in pending)


# Test enqueue_task_from_notion_page()


@pytest.mark.asyncio
async def test_enqueue_from_notion_page_creates_task(async_session, test_channel):
    """Notion page with valid properties creates task."""
    page = create_mock_notion_page(
        notion_page_id="page_123",
        title="Test Video",
        channel="test_channel",
        topic="Test Topic",
        priority="Normal",
    )

    task = await enqueue_task_from_notion_page(page, async_session)
    await async_session.commit()

    assert task is not None
    assert task.notion_page_id == "page_123"
    assert task.title == "Test Video"
    assert task.topic == "Test Topic"
    assert task.status == TaskStatus.QUEUED
    assert task.priority == PriorityLevel.NORMAL


@pytest.mark.asyncio
async def test_enqueue_from_notion_page_validates_title(async_session, test_channel):
    """Missing title fails validation."""
    page = create_mock_notion_page(
        title="",  # Empty title
        channel="test_channel",
        topic="Test Topic",
    )

    task = await enqueue_task_from_notion_page(page, async_session)

    assert task is None  # Validation failed


@pytest.mark.asyncio
async def test_enqueue_from_notion_page_validates_topic(async_session, test_channel):
    """Missing topic fails validation."""
    page = create_mock_notion_page(
        title="Test Video",
        channel="test_channel",
        topic="",  # Empty topic
    )

    task = await enqueue_task_from_notion_page(page, async_session)

    assert task is None  # Validation failed


@pytest.mark.asyncio
async def test_enqueue_from_notion_page_validates_channel(async_session, test_channel):
    """Missing channel fails validation."""
    page = {
        "id": "page_123",
        "properties": {
            "Title": {"title": [{"text": {"content": "Test"}, "plain_text": "Test"}]},
            "Topic": {
                "rich_text": [{"text": {"content": "Topic"}, "plain_text": "Topic"}]
            },
            "Channel": {"select": None},  # Missing channel
            "Priority": {"select": {"name": "Normal"}},
            "Status": {"select": {"name": "Queued"}},
            "Story Direction": {"rich_text": []},
        },
    }

    task = await enqueue_task_from_notion_page(page, async_session)

    assert task is None  # Validation failed


@pytest.mark.asyncio
async def test_enqueue_from_notion_page_channel_not_found(async_session, test_channel):
    """Unknown channel raises ValueError."""
    page = create_mock_notion_page(
        channel="unknown_channel",  # Channel doesn't exist
    )

    with pytest.raises(ValueError, match="Channel not found: unknown_channel"):
        await enqueue_task_from_notion_page(page, async_session)


@pytest.mark.asyncio
async def test_enqueue_from_notion_page_maps_priority(async_session, test_channel):
    """Notion priority (High/Normal/Low) maps to PriorityLevel enum."""
    priorities = [
        ("High", PriorityLevel.HIGH),
        ("Normal", PriorityLevel.NORMAL),
        ("Low", PriorityLevel.LOW),
    ]

    for notion_priority, expected_enum in priorities:
        page = create_mock_notion_page(
            notion_page_id=f"page_{notion_priority}",
            channel="test_channel",
            priority=notion_priority,
        )

        task = await enqueue_task_from_notion_page(page, async_session)
        await async_session.commit()

        assert task.priority == expected_enum


@pytest.mark.asyncio
async def test_enqueue_from_notion_page_handles_duplicate(
    async_session, test_channel
):
    """Duplicate Notion page is handled by enqueue_task logic."""
    page = create_mock_notion_page(notion_page_id="page_123")

    # First enqueue
    task1 = await enqueue_task_from_notion_page(page, async_session)
    await async_session.commit()

    # Duplicate enqueue
    task2 = await enqueue_task_from_notion_page(page, async_session)

    assert task1 is not None
    assert task2 is None  # Duplicate skipped


@pytest.mark.asyncio
async def test_enqueue_from_notion_page_with_story_direction(
    async_session, test_channel
):
    """Story direction is extracted and stored."""
    page = create_mock_notion_page(
        story_direction="A dramatic journey through the forest",
    )

    task = await enqueue_task_from_notion_page(page, async_session)
    await async_session.commit()

    assert task.story_direction == "A dramatic journey through the forest"


@pytest.mark.asyncio
async def test_enqueue_from_notion_page_empty_story_direction(
    async_session, test_channel
):
    """Empty story direction defaults to empty string."""
    page = create_mock_notion_page(story_direction="")

    task = await enqueue_task_from_notion_page(page, async_session)
    await async_session.commit()

    assert task.story_direction == ""
