"""Tests for Task model and Channel-Task relationship.

Tests Task model creation, status values, and relationship to Channel.
"""

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Channel, Task, IN_PROGRESS_STATUSES, PENDING_STATUSES


@pytest_asyncio.fixture
async def test_channel(async_session: AsyncSession) -> Channel:
    """Create a test channel for Task tests."""
    channel = Channel(
        channel_id="testchan",
        channel_name="Test Channel",
        is_active=True,
        max_concurrent=2,
    )
    async_session.add(channel)
    await async_session.commit()
    await async_session.refresh(channel)
    return channel


class TestTaskModel:
    """Tests for Task model."""

    @pytest.mark.asyncio
    async def test_task_creation_with_defaults(
        self,
        async_session: AsyncSession,
        test_channel: Channel,
    ) -> None:
        """Test Task creation with default values."""
        task = Task(channel_id="testchan")
        async_session.add(task)
        await async_session.commit()
        await async_session.refresh(task)

        assert task.id is not None
        assert task.channel_id == "testchan"
        assert task.status == "pending"
        assert task.created_at is not None
        assert task.updated_at is not None

    @pytest.mark.asyncio
    async def test_task_creation_with_custom_status(
        self,
        async_session: AsyncSession,
        test_channel: Channel,
    ) -> None:
        """Test Task creation with custom status."""
        task = Task(channel_id="testchan", status="processing")
        async_session.add(task)
        await async_session.commit()
        await async_session.refresh(task)

        assert task.status == "processing"

    @pytest.mark.asyncio
    async def test_task_valid_status_values(
        self,
        async_session: AsyncSession,
        test_channel: Channel,
    ) -> None:
        """Test Task with all valid status values."""
        valid_statuses = [
            "pending",
            "claimed",
            "processing",
            "awaiting_review",
            "approved",
            "rejected",
            "completed",
            "failed",
            "retry",
        ]

        for status in valid_statuses:
            task = Task(channel_id="testchan", status=status)
            async_session.add(task)
        await async_session.commit()

        # Verify all were created
        result = await async_session.execute(select(Task).where(Task.channel_id == "testchan"))
        tasks = result.scalars().all()
        assert len(tasks) == len(valid_statuses)

    @pytest.mark.asyncio
    async def test_task_channel_relationship(
        self,
        async_session: AsyncSession,
        test_channel: Channel,
    ) -> None:
        """Test Task-Channel relationship works correctly."""
        task = Task(channel_id="testchan")
        async_session.add(task)
        await async_session.commit()

        # Use explicit eager loading for async access
        result = await async_session.execute(
            select(Task).options(selectinload(Task.channel)).where(Task.id == task.id)
        )
        loaded_task = result.scalar_one()

        # Access relationship
        assert loaded_task.channel is not None
        assert loaded_task.channel.channel_id == "testchan"
        assert loaded_task.channel.channel_name == "Test Channel"

    @pytest.mark.asyncio
    async def test_channel_tasks_relationship(
        self,
        async_session: AsyncSession,
        test_channel: Channel,
    ) -> None:
        """Test Channel.tasks relationship returns all related tasks."""
        # Add multiple tasks
        for _ in range(3):
            task = Task(channel_id="testchan")
            async_session.add(task)
        await async_session.commit()

        # Use explicit eager loading for async access
        result = await async_session.execute(
            select(Channel)
            .options(selectinload(Channel.tasks))
            .where(Channel.channel_id == "testchan")
        )
        loaded_channel = result.scalar_one()

        assert len(loaded_channel.tasks) == 3

    @pytest.mark.asyncio
    async def test_task_repr(
        self,
        async_session: AsyncSession,
        test_channel: Channel,
    ) -> None:
        """Test Task __repr__ method."""
        task = Task(channel_id="testchan", status="processing")
        async_session.add(task)
        await async_session.commit()
        await async_session.refresh(task)

        repr_str = repr(task)
        assert "Task" in repr_str
        assert "testchan" in repr_str
        assert "processing" in repr_str


class TestTaskStatusConstants:
    """Tests for task status constants."""

    def test_pending_statuses(self) -> None:
        """Test PENDING_STATUSES constant."""
        assert PENDING_STATUSES == ("pending",)

    def test_in_progress_statuses(self) -> None:
        """Test IN_PROGRESS_STATUSES constant."""
        assert "claimed" in IN_PROGRESS_STATUSES
        assert "processing" in IN_PROGRESS_STATUSES
        assert "awaiting_review" in IN_PROGRESS_STATUSES
        assert len(IN_PROGRESS_STATUSES) == 3


class TestMaxConcurrentSync:
    """Tests for max_concurrent sync from YAML to database.

    Tests both direct Channel model usage and the sync_to_database()
    integration path from ChannelConfigSchema.
    """

    @pytest.mark.asyncio
    async def test_channel_max_concurrent_default(
        self,
        async_session: AsyncSession,
    ) -> None:
        """Test Channel max_concurrent has default value of 2."""
        channel = Channel(
            channel_id="default_test",
            channel_name="Default Test",
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        assert channel.max_concurrent == 2

    @pytest.mark.asyncio
    async def test_channel_max_concurrent_custom(
        self,
        async_session: AsyncSession,
    ) -> None:
        """Test Channel max_concurrent can be set to custom value."""
        channel = Channel(
            channel_id="custom_test",
            channel_name="Custom Test",
            max_concurrent=5,
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        assert channel.max_concurrent == 5

    @pytest.mark.asyncio
    async def test_channel_repr_includes_max_concurrent(
        self,
        async_session: AsyncSession,
    ) -> None:
        """Test Channel __repr__ includes max_concurrent."""
        channel = Channel(
            channel_id="repr_test",
            channel_name="Repr Test",
            max_concurrent=3,
        )
        async_session.add(channel)
        await async_session.commit()

        repr_str = repr(channel)
        assert "max_concurrent=3" in repr_str


class TestMaxConcurrentSyncToDatabase:
    """Integration tests for max_concurrent sync via ChannelConfigLoader.sync_to_database().

    These tests verify the YAML → ChannelConfigSchema → sync_to_database() → Channel
    round-trip for max_concurrent (Story 1.6 Task 7.13, AC #3).
    """

    @pytest.mark.asyncio
    async def test_sync_to_database_persists_default_max_concurrent(
        self,
        async_session: AsyncSession,
    ) -> None:
        """Test sync_to_database persists default max_concurrent=2."""
        from app.schemas.channel_config import ChannelConfigSchema
        from app.services.channel_config_loader import ChannelConfigLoader

        config = ChannelConfigSchema(
            channel_id="sync_default_test",
            channel_name="Sync Default Test",
            notion_database_id="db123",
            # max_concurrent defaults to 2 in schema
        )

        loader = ChannelConfigLoader()
        channel = await loader.sync_to_database(config, async_session)

        assert channel.max_concurrent == 2

    @pytest.mark.asyncio
    async def test_sync_to_database_persists_custom_max_concurrent(
        self,
        async_session: AsyncSession,
    ) -> None:
        """Test sync_to_database persists custom max_concurrent value."""
        from app.schemas.channel_config import ChannelConfigSchema
        from app.services.channel_config_loader import ChannelConfigLoader

        config = ChannelConfigSchema(
            channel_id="sync_custom_test",
            channel_name="Sync Custom Test",
            notion_database_id="db123",
            max_concurrent=7,
        )

        loader = ChannelConfigLoader()
        channel = await loader.sync_to_database(config, async_session)

        assert channel.max_concurrent == 7

    @pytest.mark.asyncio
    async def test_sync_to_database_updates_max_concurrent(
        self,
        async_session: AsyncSession,
    ) -> None:
        """Test sync_to_database updates existing channel's max_concurrent."""
        from app.schemas.channel_config import ChannelConfigSchema
        from app.services.channel_config_loader import ChannelConfigLoader

        # Create initial channel with max_concurrent=2
        config_v1 = ChannelConfigSchema(
            channel_id="sync_update_test",
            channel_name="Sync Update Test",
            notion_database_id="db123",
            max_concurrent=2,
        )

        loader = ChannelConfigLoader()
        channel = await loader.sync_to_database(config_v1, async_session)
        assert channel.max_concurrent == 2

        # Update to max_concurrent=5
        config_v2 = ChannelConfigSchema(
            channel_id="sync_update_test",
            channel_name="Sync Update Test",
            notion_database_id="db123",
            max_concurrent=5,
        )

        channel = await loader.sync_to_database(config_v2, async_session)
        assert channel.max_concurrent == 5

    @pytest.mark.asyncio
    async def test_sync_to_database_max_concurrent_range_validation(
        self,
        async_session: AsyncSession,
    ) -> None:
        """Test max_concurrent schema validation (1-10 range)."""
        from pydantic import ValidationError

        from app.schemas.channel_config import ChannelConfigSchema

        # Test minimum boundary (1 is valid)
        config_min = ChannelConfigSchema(
            channel_id="range_min_test",
            channel_name="Range Min Test",
            notion_database_id="db123",
            max_concurrent=1,
        )
        assert config_min.max_concurrent == 1

        # Test maximum boundary (10 is valid)
        config_max = ChannelConfigSchema(
            channel_id="range_max_test",
            channel_name="Range Max Test",
            notion_database_id="db123",
            max_concurrent=10,
        )
        assert config_max.max_concurrent == 10

        # Test below minimum (0 is invalid)
        with pytest.raises(ValidationError):
            ChannelConfigSchema(
                channel_id="range_invalid_test",
                channel_name="Range Invalid Test",
                notion_database_id="db123",
                max_concurrent=0,
            )

        # Test above maximum (11 is invalid)
        with pytest.raises(ValidationError):
            ChannelConfigSchema(
                channel_id="range_invalid_test",
                channel_name="Range Invalid Test",
                notion_database_id="db123",
                max_concurrent=11,
            )
