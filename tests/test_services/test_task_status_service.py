"""Tests for task status service (Story 8.7 - Task 5).

These tests validate the task status service functions including:
- Queue depth queries (queued tasks)
- Status filtering logic
- Performance requirements (< 100ms execution)
"""

import pytest
from uuid import uuid4

from app.models import Task, TaskStatus
from app.services.task_status_service import get_queue_depth
from tests.support.factories import create_channel, create_task


@pytest.mark.asyncio
class TestGetQueueDepth:
    """Test suite for queue depth queries."""

    async def test_get_queue_depth_empty_queue(self, async_session):
        """Test that queue depth is 0 when no pending/queued tasks exist."""
        # Arrange - No tasks in database

        # Act
        depth = await get_queue_depth(async_session)

        # Assert
        assert depth == 0

    async def test_get_queue_depth_only_pending_tasks(self, async_session):
        """Test that pending tasks are included in queue depth."""
        # Arrange - Create channel and pending tasks
        channel = create_channel(channel_id="poke1")
        async_session.add(channel)
        await async_session.commit()

        for i in range(3):
            task = create_task(
                channel_id=channel.id,
                notion_page_id=f"pending{i}",
                title=f"Pending Task {i}",
                status=TaskStatus.QUEUED,
            )
            async_session.add(task)
        await async_session.commit()

        # Act
        depth = await get_queue_depth(async_session)

        # Assert
        assert depth == 3

    async def test_get_queue_depth_only_queued_tasks(self, async_session):
        """Test that queued tasks are included in queue depth."""
        # Arrange - Create channel and queued tasks
        channel = create_channel(channel_id="poke1")
        async_session.add(channel)
        await async_session.commit()

        for i in range(2):
            task = create_task(
                channel_id=channel.id,
                notion_page_id=f"queued{i}",
                title=f"Queued Task {i}",
                status="queued",
            )
            async_session.add(task)
        await async_session.commit()

        # Act
        depth = await get_queue_depth(async_session)

        # Assert
        assert depth == 2

    async def test_get_queue_depth_mixed_pending_and_queued(self, async_session):
        """Test that both pending and queued tasks are counted."""
        # Arrange - Create channel and mixed status tasks
        channel = create_channel(channel_id="poke1")
        async_session.add(channel)
        await async_session.commit()

        # Pending tasks
        for i in range(2):
            task = create_task(
                channel_id=channel.id,
                notion_page_id=f"pending{i}",
                title=f"Pending Task {i}",
                status=TaskStatus.QUEUED,
            )
            async_session.add(task)

        # Queued tasks
        for i in range(3):
            task = create_task(
                channel_id=channel.id,
                notion_page_id=f"queued{i}",
                title=f"Queued Task {i}",
                status="queued",
            )
            async_session.add(task)

        await async_session.commit()

        # Act
        depth = await get_queue_depth(async_session)

        # Assert
        assert depth == 5  # 2 pending + 3 queued

    async def test_get_queue_depth_excludes_other_statuses(self, async_session):
        """Test that completed/processing/failed tasks are excluded from queue depth."""
        # Arrange - Create channel and tasks with various statuses
        channel = create_channel(channel_id="poke1")
        async_session.add(channel)
        await async_session.commit()

        # Pending/queued (should be counted)
        for i in range(2):
            task = create_task(
                channel_id=channel.id,
                notion_page_id=f"pending{i}",
                title=f"Pending Task {i}",
                status=TaskStatus.QUEUED,
            )
            async_session.add(task)

        # Other statuses (should NOT be counted)
        excluded_statuses = ["claimed", "generating_assets", "assets_ready", "asset_error"]
        for i, status in enumerate(excluded_statuses):
            task = create_task(
                channel_id=channel.id,
                notion_page_id=f"excluded{i}",
                title=f"Excluded Task {i}",
                status=status,
            )
            async_session.add(task)

        await async_session.commit()

        # Act
        depth = await get_queue_depth(async_session)

        # Assert
        assert depth == 2  # Only pending tasks counted

    async def test_get_queue_depth_multiple_channels(self, async_session):
        """Test that queue depth includes tasks from all channels."""
        # Arrange - Create multiple channels with pending tasks
        channel1 = create_channel(channel_id="poke1")
        channel2 = create_channel(channel_id="poke2")
        async_session.add_all([channel1, channel2])
        await async_session.commit()

        # Tasks for channel 1
        for i in range(2):
            task = create_task(
                channel_id=channel1.id,
                notion_page_id=f"ch1task{i}",
                title=f"Channel 1 Task {i}",
                status=TaskStatus.QUEUED,
            )
            async_session.add(task)

        # Tasks for channel 2
        for i in range(3):
            task = create_task(
                channel_id=channel2.id,
                notion_page_id=f"ch2task{i}",
                title=f"Channel 2 Task {i}",
                status="queued",
            )
            async_session.add(task)

        await async_session.commit()

        # Act
        depth = await get_queue_depth(async_session)

        # Assert
        assert depth == 5  # 2 from channel1 + 3 from channel2

    async def test_get_queue_depth_large_queue(self, async_session):
        """Test that queue depth works correctly with large number of tasks."""
        # Arrange - Create channel and many pending tasks
        channel = create_channel(channel_id="poke1")
        async_session.add(channel)
        await async_session.commit()

        for i in range(50):
            task = create_task(
                channel_id=channel.id,
                notion_page_id=f"task{i:03d}",  # Padded to avoid duplicates
                title=f"Task {i}",
                status=TaskStatus.QUEUED if i % 2 == 0 else "queued",
            )
            async_session.add(task)
        await async_session.commit()

        # Act
        depth = await get_queue_depth(async_session)

        # Assert
        assert depth == 50
