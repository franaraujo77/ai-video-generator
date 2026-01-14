"""Tests for Task model and Channel-Task relationship.

Tests Task model creation, status values, and relationship to Channel.
Uses 26-status workflow (Story 2-1).
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Channel, Task, TaskStatus, IN_PROGRESS_STATUSES, PENDING_STATUSES


def create_test_task(
    channel_id: uuid.UUID, status: TaskStatus = TaskStatus.DRAFT, **kwargs
) -> Task:
    """Helper to create a Task with all required fields for testing."""
    import uuid

    defaults = {
        "notion_page_id": uuid.uuid4().hex,  # Generate unique 32-char hex
        "title": "Test Video",
        "topic": "Test Topic",
        "story_direction": "Test story direction",
    }
    defaults.update(kwargs)
    return Task(channel_id=channel_id, status=status, **defaults)


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
        """Test Task creation with default status (DRAFT)."""
        task = create_test_task(test_channel.id)  # Uses default status=DRAFT
        async_session.add(task)
        await async_session.commit()
        await async_session.refresh(task)

        assert task.id is not None
        assert task.channel_id == test_channel.id
        assert task.status == TaskStatus.DRAFT
        assert task.created_at is not None
        assert task.updated_at is not None

    @pytest.mark.asyncio
    async def test_task_creation_with_custom_status(
        self,
        async_session: AsyncSession,
        test_channel: Channel,
    ) -> None:
        """Test Task creation with custom status."""
        task = create_test_task(test_channel.id, status=TaskStatus.GENERATING_ASSETS)
        async_session.add(task)
        await async_session.commit()
        await async_session.refresh(task)

        assert task.status == TaskStatus.GENERATING_ASSETS

    @pytest.mark.asyncio
    async def test_task_valid_status_values(
        self,
        async_session: AsyncSession,
        test_channel: Channel,
    ) -> None:
        """Test Task with all valid 26-status workflow values."""
        valid_statuses = [
            TaskStatus.DRAFT,
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
            TaskStatus.PUBLISHED,
            TaskStatus.ASSET_ERROR,
            TaskStatus.VIDEO_ERROR,
            TaskStatus.AUDIO_ERROR,
            TaskStatus.UPLOAD_ERROR,
        ]

        for status in valid_statuses:
            task = create_test_task(test_channel.id, status=status)
            async_session.add(task)
        await async_session.commit()

        # Verify all 26 statuses were created
        result = await async_session.execute(select(Task).where(Task.channel_id == test_channel.id))
        tasks = result.scalars().all()
        assert len(tasks) == 26

    @pytest.mark.asyncio
    async def test_task_channel_relationship(
        self,
        async_session: AsyncSession,
        test_channel: Channel,
    ) -> None:
        """Test Task-Channel relationship works correctly."""
        task = create_test_task(test_channel.id)
        async_session.add(task)
        await async_session.commit()

        # Use explicit eager loading for async access
        result = await async_session.execute(
            select(Task).options(selectinload(Task.channel)).where(Task.id == task.id)
        )
        loaded_task = result.scalar_one()

        # Access relationship
        assert loaded_task.channel is not None
        assert loaded_task.channel.channel_id == "testchan"  # Business ID
        assert loaded_task.channel.channel_name == "Test Channel"
        assert loaded_task.channel_id == test_channel.id  # Database ID (UUID)

    @pytest.mark.asyncio
    async def test_channel_tasks_relationship(
        self,
        async_session: AsyncSession,
        test_channel: Channel,
    ) -> None:
        """Test Channel.tasks relationship returns all related tasks."""
        # Add multiple tasks
        for _ in range(3):
            task = create_test_task(test_channel.id)
            async_session.add(task)
        await async_session.commit()

        # Use explicit eager loading for async access
        result = await async_session.execute(
            select(Channel)
            .options(selectinload(Channel.tasks))
            .where(Channel.id == test_channel.id)
        )
        loaded_channel = result.scalar_one()

        assert len(loaded_channel.tasks) == 3
        assert loaded_channel.channel_id == "testchan"  # Verify business ID

    @pytest.mark.asyncio
    async def test_task_repr(
        self,
        async_session: AsyncSession,
        test_channel: Channel,
    ) -> None:
        """Test Task __repr__ method."""
        task = create_test_task(test_channel.id, status=TaskStatus.GENERATING_ASSETS)
        async_session.add(task)
        await async_session.commit()
        await async_session.refresh(task)

        repr_str = repr(task)
        assert "Task" in repr_str
        assert "Test Video" in repr_str
        assert "generating_assets" in repr_str


class TestTaskStatusConstants:
    """Tests for task status constants (26-status workflow)."""

    def test_pending_statuses(self) -> None:
        """Test PENDING_STATUSES constant contains queued status."""
        assert TaskStatus.QUEUED in PENDING_STATUSES
        assert len(PENDING_STATUSES) == 1

    def test_in_progress_statuses(self) -> None:
        """Test IN_PROGRESS_STATUSES constant contains pipeline statuses."""
        # Verify key pipeline statuses are included
        assert TaskStatus.CLAIMED in IN_PROGRESS_STATUSES
        assert TaskStatus.GENERATING_ASSETS in IN_PROGRESS_STATUSES
        assert TaskStatus.GENERATING_VIDEO in IN_PROGRESS_STATUSES
        assert TaskStatus.GENERATING_AUDIO in IN_PROGRESS_STATUSES
        assert TaskStatus.ASSEMBLING in IN_PROGRESS_STATUSES
        assert TaskStatus.FINAL_REVIEW in IN_PROGRESS_STATUSES
        # Verify correct count (14 in-progress statuses)
        assert len(IN_PROGRESS_STATUSES) == 14


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
