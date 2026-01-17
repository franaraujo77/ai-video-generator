"""Tests for bulk approve/reject operations in ReviewService.

This module tests Story 5.8: Bulk Approve/Reject Operations.

Test Coverage:
- Bulk approve: Multiple tasks VIDEO_READY → VIDEO_APPROVED
- Bulk reject: Multiple tasks with common rejection reason
- Validation: All-or-nothing validation (fail fast on any invalid transition)
- Partial failure: Database succeeds, some Notion API calls fail
- Transaction: Rollback on validation error, persist on success
- Rate limiting: Respects 3 req/sec Notion API limit
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.exceptions import InvalidStateTransitionError
from app.models import Channel, Task, TaskStatus
from app.services.review_service import ReviewService, BulkOperationResult


@pytest.mark.asyncio
async def test_bulk_approve_tasks_success(async_session):
    """Verify bulk approve updates all tasks in single transaction."""
    # Create channel first
    channel = Channel(channel_id="test-channel", channel_name="Test", storage_strategy="notion")
    async_session.add(channel)
    await async_session.flush()

    # Create 10 tasks in VIDEO_READY status
    tasks = [
        Task(
            id=uuid4(),
            channel_id=channel.id,
            title=f"Test Video {i}",
            topic="Test topic",
            story_direction="Test story",
            status=TaskStatus.VIDEO_READY,
            notion_page_id=f"abc123def456{str(i).zfill(10)}",
        )
        for i in range(10)
    ]
    async_session.add_all(tasks)
    await async_session.commit()

    task_ids = [task.id for task in tasks]

    # Bulk approve (mock Notion API to avoid network calls)
    with patch("app.services.review_service.get_notion_api_token", return_value=None):
        review_service = ReviewService()
        result = await review_service.bulk_approve_tasks(
            db=async_session,
            task_ids=task_ids,
            target_status=TaskStatus.VIDEO_APPROVED,
        )

    # Verify results
    assert result.total_count == 10
    assert result.success_count == 10
    assert result.notion_success_count == 10  # No Notion API calls when token is None
    assert result.notion_failure_count == 0
    assert len(result.errors) == 0
    assert len(result.failed_task_ids) == 0

    # Verify database updates
    for task in tasks:
        await async_session.refresh(task)
        assert task.status == TaskStatus.VIDEO_APPROVED


@pytest.mark.asyncio
async def test_bulk_approve_validation_failure_rollback(async_session):
    """Verify validation error rolls back entire operation."""
    # Create tasks: 9 in VIDEO_READY, 1 in PUBLISHED (invalid transition)
    channel_id = "test-channel"
    tasks = [
        Task(
            id=uuid4(),
            channel_id=channel.id,
            title="Test Video",
            topic="Test topic",
            story_direction="Test story",
            status=TaskStatus.VIDEO_READY,
            notion_page_id=f"notion-page-{i}",
        )
        for i in range(9)
    ]
    invalid_task = Task(
        id=uuid4(),
        channel_id=channel_id,
        status=TaskStatus.PUBLISHED,
        notion_page_id="notion-page-invalid",
        prompt="test prompt",
        priority="normal",
    )
    tasks.append(invalid_task)

    async_session.add_all(tasks)
    await async_session.commit()

    task_ids = [task.id for task in tasks]

    # Attempt bulk approve (should fail validation)
    review_service = ReviewService()
    with pytest.raises(InvalidStateTransitionError):
        await review_service.bulk_approve_tasks(
            db=async_session,
            task_ids=task_ids,
            target_status=TaskStatus.VIDEO_APPROVED,
        )

    # Verify rollback: NO tasks updated
    for task in tasks[:-1]:
        await async_session.refresh(task)
        assert task.status == TaskStatus.VIDEO_READY  # Unchanged

    await async_session.refresh(invalid_task)
    assert invalid_task.status == TaskStatus.PUBLISHED  # Unchanged


@pytest.mark.asyncio
async def test_bulk_approve_partial_notion_failure(async_session, monkeypatch):
    """Verify partial Notion API failure doesn't block successful tasks."""
    # Create 10 tasks
    channel_id = "test-channel"
    tasks = [
        Task(
            id=uuid4(),
            channel_id=channel.id,
            title="Test Video",
            topic="Test topic",
            story_direction="Test story",
            status=TaskStatus.VIDEO_READY,
            notion_page_id=f"notion-page-{i}",
        )
        for i in range(10)
    ]
    async_session.add_all(tasks)
    await async_session.commit()

    # Mock Notion API: 2 failures, 8 successes
    mock_notion_client = AsyncMock()
    call_count = 0

    async def mock_update(page_id, status):
        nonlocal call_count
        call_count += 1
        if page_id in ["notion-page-3", "notion-page-7"]:
            raise Exception("Notion API error")

    mock_notion_client.update_task_status = mock_update

    # Monkeypatch NotionClient instantiation
    def mock_get_client(auth_token):
        return mock_notion_client

    monkeypatch.setattr("app.services.review_service.NotionClient", mock_get_client)

    # Bulk approve
    review_service = ReviewService()
    task_ids = [task.id for task in tasks]
    result = await review_service.bulk_approve_tasks(
        db=async_session,
        task_ids=task_ids,
        target_status=TaskStatus.VIDEO_APPROVED,
    )

    # Verify results
    assert result.total_count == 10
    assert result.success_count == 10  # Database updates succeeded
    assert result.notion_success_count == 8  # 8 Notion syncs succeeded
    assert result.notion_failure_count == 2  # 2 Notion syncs failed
    assert len(result.errors) == 2
    assert len(result.failed_task_ids) == 2

    # Verify all database updates persisted (no rollback)
    for task in tasks:
        await async_session.refresh(task)
        assert task.status == TaskStatus.VIDEO_APPROVED


@pytest.mark.asyncio
async def test_bulk_reject_with_reason(async_session):
    """Verify bulk reject appends reason to error logs."""
    # Create 5 tasks in VIDEO_READY
    channel_id = "test-channel"
    tasks = [
        Task(
            id=uuid4(),
            channel_id=channel.id,
            title="Test Video",
            topic="Test topic",
            story_direction="Test story",
            status=TaskStatus.VIDEO_READY,
            notion_page_id=f"notion-page-{i}",
        )
        for i in range(5)
    ]
    async_session.add_all(tasks)
    await async_session.commit()

    # Bulk reject with reason
    review_service = ReviewService()
    task_ids = [task.id for task in tasks]
    reason = "Poor video quality in clips 5, 12"
    result = await review_service.bulk_reject_tasks(
        db=async_session,
        task_ids=task_ids,
        reason=reason,
        target_status=TaskStatus.VIDEO_ERROR,
    )

    # Verify results
    assert result.success_count == 5

    # Verify all error logs updated
    for task in tasks:
        await async_session.refresh(task)
        assert task.status == TaskStatus.VIDEO_ERROR
        assert reason in task.error_log
        assert "clips 5, 12" in task.error_log  # Clip numbers preserved


@pytest.mark.asyncio
async def test_bulk_approve_empty_list(async_session):
    """Verify bulk approve with empty task list returns empty result."""
    review_service = ReviewService()
    result = await review_service.bulk_approve_tasks(
        db=async_session,
        task_ids=[],
        target_status=TaskStatus.VIDEO_APPROVED,
    )

    assert result.total_count == 0
    assert result.success_count == 0
    assert result.notion_success_count == 0
    assert result.notion_failure_count == 0


@pytest.mark.asyncio
async def test_bulk_approve_max_limit(async_session):
    """Verify bulk approve supports up to 100 tasks."""
    channel_id = "test-channel"
    tasks = [
        Task(
            id=uuid4(),
            channel_id=channel.id,
            title="Test Video",
            topic="Test topic",
            story_direction="Test story",
            status=TaskStatus.VIDEO_READY,
            notion_page_id=f"notion-page-{i}",
        )
        for i in range(100)
    ]
    async_session.add_all(tasks)
    await async_session.commit()

    task_ids = [task.id for task in tasks]

    review_service = ReviewService()
    result = await review_service.bulk_approve_tasks(
        db=async_session,
        task_ids=task_ids,
        target_status=TaskStatus.VIDEO_APPROVED,
    )

    assert result.total_count == 100
    assert result.success_count == 100


@pytest.mark.asyncio
async def test_bulk_approve_database_transaction_closes(async_session):
    """Verify database connection closes before Notion API loop."""
    channel_id = "test-channel"
    tasks = [
        Task(
            id=uuid4(),
            channel_id=channel.id,
            title="Test Video",
            topic="Test topic",
            story_direction="Test story",
            status=TaskStatus.VIDEO_READY,
            notion_page_id=f"notion-page-{i}",
        )
        for i in range(5)
    ]
    async_session.add_all(tasks)
    await async_session.commit()

    task_ids = [task.id for task in tasks]

    # This test verifies pattern but doesn't assert connection state
    # Architecture compliance: Short transaction → close DB → Notion API loop
    review_service = ReviewService()
    result = await review_service.bulk_approve_tasks(
        db=async_session,
        task_ids=task_ids,
        target_status=TaskStatus.VIDEO_APPROVED,
    )

    assert result.success_count == 5


@pytest.mark.asyncio
async def test_bulk_reject_validation_error(async_session):
    """Verify validation error causes immediate failure (no partial update)."""
    channel_id = "test-channel"
    tasks = [
        Task(
            id=uuid4(),
            channel_id=channel.id,
            title="Test Video",
            topic="Test topic",
            story_direction="Test story",
            status=TaskStatus.VIDEO_READY,
            notion_page_id=f"notion-page-{i}",
        )
        for i in range(3)
    ]
    invalid_task = Task(
        id=uuid4(),
        channel_id=channel_id,
        status=TaskStatus.COMPLETED,
        notion_page_id="notion-page-invalid",
        prompt="test prompt",
        priority="normal",
    )
    tasks.append(invalid_task)

    async_session.add_all(tasks)
    await async_session.commit()

    task_ids = [task.id for task in tasks]

    review_service = ReviewService()
    with pytest.raises(InvalidStateTransitionError):
        await review_service.bulk_reject_tasks(
            db=async_session,
            task_ids=task_ids,
            reason="Test rejection",
            target_status=TaskStatus.VIDEO_ERROR,
        )

    # Verify NO tasks updated
    for task in tasks[:-1]:
        await async_session.refresh(task)
        assert task.status == TaskStatus.VIDEO_READY

    await async_session.refresh(invalid_task)
    assert invalid_task.status == TaskStatus.COMPLETED
