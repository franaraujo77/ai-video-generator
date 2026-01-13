"""Tests for ChannelCapacityService.

Tests queue statistics, capacity calculations, and channel filtering.
Uses 26-status workflow (Story 2-1).
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Channel, Task, TaskStatus
from app.services.channel_capacity_service import ChannelCapacityService, ChannelQueueStats


def create_test_task(channel_id: uuid.UUID, status: TaskStatus = TaskStatus.DRAFT, **kwargs) -> Task:
    """Helper to create a Task with all required fields for testing."""
    defaults = {
        "notion_page_id": uuid.uuid4().hex,  # Generate unique 32-char hex
        "title": "Test Video",
        "topic": "Test Topic",
        "story_direction": "Test story direction",
    }
    defaults.update(kwargs)
    return Task(channel_id=channel_id, status=status, **defaults)


@pytest_asyncio.fixture
async def capacity_service() -> ChannelCapacityService:
    """Create a ChannelCapacityService instance for testing."""
    return ChannelCapacityService()


@pytest_asyncio.fixture
async def channel_poke1(async_session: AsyncSession) -> Channel:
    """Create a test channel 'poke1' with max_concurrent=2."""
    channel = Channel(
        channel_id="poke1",
        channel_name="Pokemon Channel 1",
        is_active=True,
        max_concurrent=2,
    )
    async_session.add(channel)
    await async_session.commit()
    await async_session.refresh(channel)
    return channel


@pytest_asyncio.fixture
async def channel_poke2(async_session: AsyncSession) -> Channel:
    """Create a test channel 'poke2' with max_concurrent=3."""
    channel = Channel(
        channel_id="poke2",
        channel_name="Pokemon Channel 2",
        is_active=True,
        max_concurrent=3,
    )
    async_session.add(channel)
    await async_session.commit()
    await async_session.refresh(channel)
    return channel


@pytest_asyncio.fixture
async def inactive_channel(async_session: AsyncSession) -> Channel:
    """Create an inactive test channel."""
    channel = Channel(
        channel_id="inactive1",
        channel_name="Inactive Channel",
        is_active=False,
        max_concurrent=2,
    )
    async_session.add(channel)
    await async_session.commit()
    await async_session.refresh(channel)
    return channel


class TestChannelCapacityService:
    """Tests for ChannelCapacityService methods."""

    @pytest.mark.asyncio
    async def test_get_queue_stats_empty(
        self,
        capacity_service: ChannelCapacityService,
        async_session: AsyncSession,
    ) -> None:
        """Test get_queue_stats with no channels returns empty list."""
        stats = await capacity_service.get_queue_stats(async_session)
        assert stats == []

    @pytest.mark.asyncio
    async def test_get_queue_stats_no_tasks(
        self,
        capacity_service: ChannelCapacityService,
        async_session: AsyncSession,
        channel_poke1: Channel,
    ) -> None:
        """Test get_queue_stats with channel but no tasks returns zero counts."""
        stats = await capacity_service.get_queue_stats(async_session)

        assert len(stats) == 1
        assert stats[0].channel_id == "poke1"
        assert stats[0].channel_name == "Pokemon Channel 1"
        assert stats[0].pending_count == 0
        assert stats[0].in_progress_count == 0
        assert stats[0].max_concurrent == 2
        assert stats[0].has_capacity is True

    @pytest.mark.asyncio
    async def test_get_queue_stats_with_pending_tasks(
        self,
        capacity_service: ChannelCapacityService,
        async_session: AsyncSession,
        channel_poke1: Channel,
    ) -> None:
        """Test get_queue_stats correctly counts pending tasks."""
        # Add 3 pending tasks
        for _ in range(3):
            task = create_test_task(channel_poke1.id, status=TaskStatus.QUEUED)
            async_session.add(task)
        await async_session.commit()

        stats = await capacity_service.get_queue_stats(async_session)

        assert len(stats) == 1
        assert stats[0].pending_count == 3
        assert stats[0].in_progress_count == 0
        assert stats[0].has_capacity is True

    @pytest.mark.asyncio
    async def test_get_queue_stats_with_in_progress_tasks(
        self,
        capacity_service: ChannelCapacityService,
        async_session: AsyncSession,
        channel_poke1: Channel,
    ) -> None:
        """Test get_queue_stats correctly counts in-progress tasks."""
        # Add tasks in different in-progress statuses
        statuses = [TaskStatus.CLAIMED, TaskStatus.GENERATING_ASSETS, TaskStatus.FINAL_REVIEW]
        for status in statuses:
            task = create_test_task(channel_poke1.id, status=status)
            async_session.add(task)
        await async_session.commit()

        stats = await capacity_service.get_queue_stats(async_session)

        assert len(stats) == 1
        assert stats[0].pending_count == 0
        assert stats[0].in_progress_count == 3
        # max_concurrent=2, in_progress=3 -> no capacity
        assert stats[0].has_capacity is False

    @pytest.mark.asyncio
    async def test_get_queue_stats_mixed_statuses(
        self,
        capacity_service: ChannelCapacityService,
        async_session: AsyncSession,
        channel_poke1: Channel,
    ) -> None:
        """Test get_queue_stats with mix of statuses."""
        # 2 pending, 1 processing, 1 completed (should not count)
        async_session.add(create_test_task(channel_poke1.id, status=TaskStatus.QUEUED))
        async_session.add(create_test_task(channel_poke1.id, status=TaskStatus.QUEUED))
        async_session.add(create_test_task(channel_poke1.id, status=TaskStatus.GENERATING_ASSETS))
        async_session.add(create_test_task(channel_poke1.id, status=TaskStatus.PUBLISHED))
        async_session.add(create_test_task(channel_poke1.id, status=TaskStatus.ASSET_ERROR))
        await async_session.commit()

        stats = await capacity_service.get_queue_stats(async_session)

        assert len(stats) == 1
        assert stats[0].pending_count == 2
        assert stats[0].in_progress_count == 1
        # max_concurrent=2, in_progress=1 -> has capacity
        assert stats[0].has_capacity is True

    @pytest.mark.asyncio
    async def test_get_queue_stats_multiple_channels(
        self,
        capacity_service: ChannelCapacityService,
        async_session: AsyncSession,
        channel_poke1: Channel,
        channel_poke2: Channel,
    ) -> None:
        """Test get_queue_stats returns stats for multiple channels."""
        # poke1: 1 pending, 2 processing (at capacity, max=2)
        async_session.add(create_test_task(channel_poke1.id, status=TaskStatus.QUEUED))
        async_session.add(create_test_task(channel_poke1.id, status=TaskStatus.GENERATING_ASSETS))
        async_session.add(create_test_task(channel_poke1.id, status=TaskStatus.GENERATING_ASSETS))

        # poke2: 2 pending, 1 processing (has capacity, max=3)
        async_session.add(create_test_task(channel_poke2.id, status=TaskStatus.QUEUED))
        async_session.add(create_test_task(channel_poke2.id, status=TaskStatus.QUEUED))
        async_session.add(create_test_task(channel_poke2.id, status=TaskStatus.GENERATING_ASSETS))
        await async_session.commit()

        stats = await capacity_service.get_queue_stats(async_session)

        assert len(stats) == 2

        # Find poke1 stats
        poke1_stats = next(s for s in stats if s.channel_id == "poke1")
        assert poke1_stats.pending_count == 1
        assert poke1_stats.in_progress_count == 2
        assert poke1_stats.max_concurrent == 2
        assert poke1_stats.has_capacity is False

        # Find poke2 stats
        poke2_stats = next(s for s in stats if s.channel_id == "poke2")
        assert poke2_stats.pending_count == 2
        assert poke2_stats.in_progress_count == 1
        assert poke2_stats.max_concurrent == 3
        assert poke2_stats.has_capacity is True

    @pytest.mark.asyncio
    async def test_get_queue_stats_excludes_inactive_channels(
        self,
        capacity_service: ChannelCapacityService,
        async_session: AsyncSession,
        channel_poke1: Channel,
        inactive_channel: Channel,
    ) -> None:
        """Test get_queue_stats excludes inactive channels."""
        stats = await capacity_service.get_queue_stats(async_session)

        assert len(stats) == 1
        assert stats[0].channel_id == "poke1"

    @pytest.mark.asyncio
    async def test_get_channel_capacity_found(
        self,
        capacity_service: ChannelCapacityService,
        async_session: AsyncSession,
        channel_poke1: Channel,
    ) -> None:
        """Test get_channel_capacity returns stats for existing channel."""
        async_session.add(create_test_task(channel_poke1.id, status=TaskStatus.QUEUED))
        async_session.add(create_test_task(channel_poke1.id, status=TaskStatus.GENERATING_ASSETS))
        await async_session.commit()

        stats = await capacity_service.get_channel_capacity("poke1", async_session)

        assert stats is not None
        assert stats.channel_id == "poke1"
        assert stats.pending_count == 1
        assert stats.in_progress_count == 1
        assert stats.has_capacity is True

    @pytest.mark.asyncio
    async def test_get_channel_capacity_not_found(
        self,
        capacity_service: ChannelCapacityService,
        async_session: AsyncSession,
    ) -> None:
        """Test get_channel_capacity returns None for non-existent channel."""
        stats = await capacity_service.get_channel_capacity("nonexistent", async_session)
        assert stats is None

    @pytest.mark.asyncio
    async def test_get_channel_capacity_inactive_channel(
        self,
        capacity_service: ChannelCapacityService,
        async_session: AsyncSession,
        inactive_channel: Channel,
    ) -> None:
        """Test get_channel_capacity returns None for inactive channel."""
        stats = await capacity_service.get_channel_capacity("inactive1", async_session)
        assert stats is None

    @pytest.mark.asyncio
    async def test_has_capacity_returns_true_when_under_limit(
        self,
        capacity_service: ChannelCapacityService,
        async_session: AsyncSession,
        channel_poke1: Channel,
    ) -> None:
        """Test has_capacity returns True when in_progress < max_concurrent."""
        # max_concurrent=2, add 1 processing task
        async_session.add(create_test_task(channel_poke1.id, status=TaskStatus.GENERATING_ASSETS))
        await async_session.commit()

        result = await capacity_service.has_capacity("poke1", async_session)
        assert result is True

    @pytest.mark.asyncio
    async def test_has_capacity_returns_false_when_at_limit(
        self,
        capacity_service: ChannelCapacityService,
        async_session: AsyncSession,
        channel_poke1: Channel,
    ) -> None:
        """Test has_capacity returns False when in_progress >= max_concurrent."""
        # max_concurrent=2, add 2 processing tasks
        async_session.add(create_test_task(channel_poke1.id, status=TaskStatus.GENERATING_ASSETS))
        async_session.add(create_test_task(channel_poke1.id, status=TaskStatus.CLAIMED))
        await async_session.commit()

        result = await capacity_service.has_capacity("poke1", async_session)
        assert result is False

    @pytest.mark.asyncio
    async def test_has_capacity_returns_false_when_over_limit(
        self,
        capacity_service: ChannelCapacityService,
        async_session: AsyncSession,
        channel_poke1: Channel,
    ) -> None:
        """Test has_capacity returns False when in_progress > max_concurrent."""
        # max_concurrent=2, add 3 processing tasks
        async_session.add(create_test_task(channel_poke1.id, status=TaskStatus.GENERATING_ASSETS))
        async_session.add(create_test_task(channel_poke1.id, status=TaskStatus.CLAIMED))
        async_session.add(create_test_task(channel_poke1.id, status=TaskStatus.FINAL_REVIEW))
        await async_session.commit()

        result = await capacity_service.has_capacity("poke1", async_session)
        assert result is False

    @pytest.mark.asyncio
    async def test_has_capacity_returns_false_for_nonexistent_channel(
        self,
        capacity_service: ChannelCapacityService,
        async_session: AsyncSession,
    ) -> None:
        """Test has_capacity returns False for non-existent channel."""
        result = await capacity_service.has_capacity("nonexistent", async_session)
        assert result is False

    @pytest.mark.asyncio
    async def test_get_channels_with_capacity_filters_correctly(
        self,
        capacity_service: ChannelCapacityService,
        async_session: AsyncSession,
        channel_poke1: Channel,
        channel_poke2: Channel,
    ) -> None:
        """Test get_channels_with_capacity returns only channels with capacity."""
        # poke1: 2 processing (at capacity, max=2)
        async_session.add(create_test_task(channel_poke1.id, status=TaskStatus.GENERATING_ASSETS))
        async_session.add(create_test_task(channel_poke1.id, status=TaskStatus.GENERATING_ASSETS))

        # poke2: 1 processing (has capacity, max=3)
        async_session.add(create_test_task(channel_poke2.id, status=TaskStatus.GENERATING_ASSETS))
        await async_session.commit()

        channels = await capacity_service.get_channels_with_capacity(async_session)

        assert len(channels) == 1
        assert "poke2" in channels
        assert "poke1" not in channels

    @pytest.mark.asyncio
    async def test_get_channels_with_capacity_returns_all_when_all_have_capacity(
        self,
        capacity_service: ChannelCapacityService,
        async_session: AsyncSession,
        channel_poke1: Channel,
        channel_poke2: Channel,
    ) -> None:
        """Test get_channels_with_capacity returns all channels when all have capacity."""
        # Both channels have no in-progress tasks
        channels = await capacity_service.get_channels_with_capacity(async_session)

        assert len(channels) == 2
        assert "poke1" in channels
        assert "poke2" in channels

    @pytest.mark.asyncio
    async def test_get_channels_with_capacity_returns_empty_when_all_at_capacity(
        self,
        capacity_service: ChannelCapacityService,
        async_session: AsyncSession,
        channel_poke1: Channel,
        channel_poke2: Channel,
    ) -> None:
        """Test get_channels_with_capacity returns empty when all at capacity."""
        # poke1: 2 processing (at capacity, max=2)
        async_session.add(create_test_task(channel_poke1.id, status=TaskStatus.GENERATING_ASSETS))
        async_session.add(create_test_task(channel_poke1.id, status=TaskStatus.GENERATING_ASSETS))

        # poke2: 3 processing (at capacity, max=3)
        async_session.add(create_test_task(channel_poke2.id, status=TaskStatus.GENERATING_ASSETS))
        async_session.add(create_test_task(channel_poke2.id, status=TaskStatus.CLAIMED))
        async_session.add(create_test_task(channel_poke2.id, status=TaskStatus.FINAL_REVIEW))
        await async_session.commit()

        channels = await capacity_service.get_channels_with_capacity(async_session)
        assert channels == []

    @pytest.mark.asyncio
    async def test_capacity_isolation_between_channels(
        self,
        capacity_service: ChannelCapacityService,
        async_session: AsyncSession,
        channel_poke1: Channel,
        channel_poke2: Channel,
    ) -> None:
        """Test that one channel at max capacity doesn't affect other channels."""
        # poke1: at capacity (max=2)
        async_session.add(create_test_task(channel_poke1.id, status=TaskStatus.GENERATING_ASSETS))
        async_session.add(create_test_task(channel_poke1.id, status=TaskStatus.GENERATING_ASSETS))
        await async_session.commit()

        # poke2 should still have capacity
        poke2_has_capacity = await capacity_service.has_capacity("poke2", async_session)
        assert poke2_has_capacity is True

        # Verify poke1 is at capacity
        poke1_has_capacity = await capacity_service.has_capacity("poke1", async_session)
        assert poke1_has_capacity is False


class TestChannelQueueStats:
    """Tests for ChannelQueueStats dataclass."""

    def test_channel_queue_stats_immutable(self) -> None:
        """Test that ChannelQueueStats is immutable (frozen)."""
        stats = ChannelQueueStats(
            channel_id="test",
            channel_name="Test Channel",
            pending_count=5,
            in_progress_count=2,
            max_concurrent=3,
            has_capacity=True,
        )

        # Attempting to modify should raise FrozenInstanceError
        with pytest.raises(AttributeError):
            stats.pending_count = 10  # type: ignore

    def test_channel_queue_stats_equality(self) -> None:
        """Test ChannelQueueStats equality comparison."""
        stats1 = ChannelQueueStats(
            channel_id="test",
            channel_name="Test Channel",
            pending_count=5,
            in_progress_count=2,
            max_concurrent=3,
            has_capacity=True,
        )
        stats2 = ChannelQueueStats(
            channel_id="test",
            channel_name="Test Channel",
            pending_count=5,
            in_progress_count=2,
            max_concurrent=3,
            has_capacity=True,
        )

        assert stats1 == stats2
