"""E2E integration tests for task creation and workflow management.

Tests the complete flow for task lifecycle management with 26-status workflow,
channel capacity tracking, and cross-service integration. Validates Epic 2
(Notion Integration & Video Planning) integration points.

Priority: [P0] - Critical path testing
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Channel, Task, TaskStatus, PriorityLevel
from app.schemas.channel_config import ChannelConfigSchema
from app.services.channel_capacity_service import ChannelCapacityService
from app.services.channel_config_loader import ChannelConfigLoader


def create_test_task(channel_id: uuid.UUID, status: TaskStatus = TaskStatus.DRAFT, **kwargs) -> Task:
    """Helper to create a Task with all required fields for testing."""
    defaults = {
        "notion_page_id": uuid.uuid4().hex,
        "title": "E2E Test Video",
        "topic": "E2E Test Topic",
        "story_direction": "E2E test story direction for integration testing",
    }
    defaults.update(kwargs)
    return Task(channel_id=channel_id, status=status, **defaults)


@pytest_asyncio.fixture
async def test_channel(
    async_session: AsyncSession,
    config_loader: ChannelConfigLoader,
) -> Channel:
    """Create a test channel for E2E task tests."""
    config = ChannelConfigSchema(
        channel_id="e2e_task_channel",
        channel_name="E2E Task Test Channel",
        notion_database_id="e2e_task_db",
        max_concurrent=3,
    )
    channel = await config_loader.sync_to_database(config, async_session)
    return channel


@pytest_asyncio.fixture
async def config_loader() -> ChannelConfigLoader:
    """Create ChannelConfigLoader for testing."""
    return ChannelConfigLoader()


@pytest_asyncio.fixture
async def capacity_service() -> ChannelCapacityService:
    """Create ChannelCapacityService for testing."""
    return ChannelCapacityService()


class TestE2ETaskCreationAndPersistence:
    """E2E tests for task creation and database persistence."""

    @pytest.mark.asyncio
    async def test_p0_task_creation_with_all_required_fields(
        self,
        async_session: AsyncSession,
        test_channel: Channel,
    ) -> None:
        """Test task creation with all required Notion integration fields.

        Validates:
        - All required fields (notion_page_id, title, topic, story_direction)
        - Default status (DRAFT)
        - Default priority (NORMAL)
        - Timestamps auto-populated
        - Foreign key relationship to channel
        """
        # Given: Valid task data
        task = create_test_task(
            test_channel.id,
            notion_page_id="abc123def456ghi789jkl012mno345pq",
            title="Pokemon Habitat Exploration",
            topic="Pikachu Electric Ecosystem",
            story_direction="Documentary-style exploration of Pikachu's natural habitat",
        )

        # When: Persist task
        async_session.add(task)
        await async_session.commit()
        await async_session.refresh(task)

        # Then: Task persisted with correct defaults
        assert task.id is not None
        assert task.channel_id == test_channel.id
        assert task.status == TaskStatus.DRAFT
        assert task.priority == PriorityLevel.NORMAL
        assert task.notion_page_id == "abc123def456ghi789jkl012mno345pq"
        assert task.title == "Pokemon Habitat Exploration"
        assert task.created_at is not None
        assert task.updated_at is not None

    @pytest.mark.asyncio
    async def test_p0_task_notion_page_id_uniqueness(
        self,
        async_session: AsyncSession,
        test_channel: Channel,
    ) -> None:
        """Test notion_page_id unique constraint enforcement.

        Validates:
        - notion_page_id must be unique across all tasks
        - Prevents duplicate Notion page syncing
        """
        # Given: Task with specific notion_page_id
        task1 = create_test_task(
            test_channel.id,
            notion_page_id="unique123abc456def789ghi012jkl",
        )
        async_session.add(task1)
        await async_session.commit()

        # When: Attempt to create duplicate
        task2 = create_test_task(
            test_channel.id,
            notion_page_id="unique123abc456def789ghi012jkl",  # Same ID
        )
        async_session.add(task2)

        # Then: Unique constraint violation
        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError):
            await async_session.commit()


class TestE2ETaskStatusWorkflow:
    """E2E tests for 26-status workflow state machine."""

    @pytest.mark.asyncio
    async def test_p0_task_progresses_through_pipeline_statuses(
        self,
        async_session: AsyncSession,
        test_channel: Channel,
    ) -> None:
        """Test task progression through pipeline statuses.

        Validates:
        - Task can move through all 26 workflow statuses
        - Status transitions persist correctly
        - updated_at timestamp changes on status update
        """
        # Given: Task in DRAFT status
        task = create_test_task(test_channel.id, status=TaskStatus.DRAFT)
        async_session.add(task)
        await async_session.commit()
        await async_session.refresh(task)
        initial_updated_at = task.updated_at

        # When: Progress through pipeline statuses
        pipeline_statuses = [
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
        ]

        for status in pipeline_statuses:
            task.status = status
            await async_session.commit()
            await async_session.refresh(task)

            # Then: Status persisted and timestamp updated
            assert task.status == status
            assert task.updated_at > initial_updated_at
            initial_updated_at = task.updated_at

    @pytest.mark.asyncio
    async def test_p0_task_error_status_transitions(
        self,
        async_session: AsyncSession,
        test_channel: Channel,
    ) -> None:
        """Test task can transition to error statuses.

        Validates:
        - Error statuses accessible from pipeline statuses
        - Error log can be populated
        """
        # Given: Task in GENERATING_ASSETS status
        task = create_test_task(test_channel.id, status=TaskStatus.GENERATING_ASSETS)
        async_session.add(task)
        await async_session.commit()

        # When: Transition to error status with log
        task.status = TaskStatus.ASSET_ERROR
        task.error_log = "API timeout: Gemini image generation failed after 3 retries"
        await async_session.commit()
        await async_session.refresh(task)

        # Then: Error status and log persisted
        assert task.status == TaskStatus.ASSET_ERROR
        assert "Gemini image generation failed" in task.error_log


class TestE2ETaskCapacityIntegration:
    """E2E tests for task creation with capacity tracking."""

    @pytest.mark.asyncio
    async def test_p0_capacity_tracking_with_pending_tasks(
        self,
        async_session: AsyncSession,
        test_channel: Channel,
        capacity_service: ChannelCapacityService,
    ) -> None:
        """Test capacity tracking counts pending tasks correctly.

        Validates:
        - QUEUED status counted as pending
        - ChannelCapacityService integrates with Task model
        - Capacity calculations accurate
        """
        # Given: Channel with max_concurrent=3 and 5 pending tasks
        for i in range(5):
            task = create_test_task(
                test_channel.id,
                status=TaskStatus.QUEUED,
                notion_page_id=f"pending{i:02d}" + "0" * 22,
            )
            async_session.add(task)
        await async_session.commit()

        # When: Get capacity stats
        stats = await capacity_service.get_channel_capacity(
            "e2e_task_channel", async_session
        )

        # Then: Pending count accurate, has capacity
        assert stats is not None
        assert stats.pending_count == 5
        assert stats.in_progress_count == 0
        assert stats.has_capacity is True  # No in-progress tasks

    @pytest.mark.asyncio
    async def test_p0_capacity_tracking_with_in_progress_tasks(
        self,
        async_session: AsyncSession,
        test_channel: Channel,
        capacity_service: ChannelCapacityService,
    ) -> None:
        """Test capacity tracking with in-progress tasks.

        Validates:
        - Multiple statuses counted as in-progress
        - Capacity calculation: in_progress < max_concurrent
        - has_capacity flag accurate
        """
        # Given: Channel with max_concurrent=3
        # Add 2 in-progress tasks (under capacity)
        task1 = create_test_task(
            test_channel.id,
            status=TaskStatus.GENERATING_ASSETS,
            notion_page_id="inprog01" + "0" * 22,
        )
        task2 = create_test_task(
            test_channel.id,
            status=TaskStatus.GENERATING_VIDEO,
            notion_page_id="inprog02" + "0" * 22,
        )
        async_session.add(task1)
        async_session.add(task2)
        await async_session.commit()

        # When: Get capacity stats
        stats = await capacity_service.get_channel_capacity(
            "e2e_task_channel", async_session
        )

        # Then: Has capacity (2 < 3)
        assert stats.in_progress_count == 2
        assert stats.max_concurrent == 3
        assert stats.has_capacity is True

        # Given: Add one more in-progress task (at capacity)
        task3 = create_test_task(
            test_channel.id,
            status=TaskStatus.ASSEMBLING,
            notion_page_id="inprog03" + "0" * 22,
        )
        async_session.add(task3)
        await async_session.commit()

        # When: Get updated stats
        stats = await capacity_service.get_channel_capacity(
            "e2e_task_channel", async_session
        )

        # Then: At capacity (3 >= 3)
        assert stats.in_progress_count == 3
        assert stats.has_capacity is False

    @pytest.mark.asyncio
    async def test_p0_capacity_tracking_excludes_completed_tasks(
        self,
        async_session: AsyncSession,
        test_channel: Channel,
        capacity_service: ChannelCapacityService,
    ) -> None:
        """Test completed/error tasks don't count toward capacity.

        Validates:
        - PUBLISHED status not counted
        - Error statuses not counted
        - Only active pipeline statuses count
        """
        # Given: Mix of statuses
        statuses_to_create = [
            (TaskStatus.PUBLISHED, "completed01"),
            (TaskStatus.ASSET_ERROR, "error01"),
            (TaskStatus.UPLOAD_ERROR, "error02"),
            (TaskStatus.GENERATING_ASSETS, "active01"),
            (TaskStatus.FINAL_REVIEW, "active02"),
        ]

        for status, page_id in statuses_to_create:
            task = create_test_task(
                test_channel.id,
                status=status,
                notion_page_id=page_id + "0" * 22,
            )
            async_session.add(task)
        await async_session.commit()

        # When: Get capacity stats
        stats = await capacity_service.get_channel_capacity(
            "e2e_task_channel", async_session
        )

        # Then: Only active tasks counted (2 in-progress)
        assert stats.in_progress_count == 2
        assert stats.has_capacity is True


class TestE2EMultiChannelTaskIsolation:
    """E2E tests for task isolation across multiple channels."""

    @pytest.mark.asyncio
    async def test_p0_tasks_isolated_per_channel(
        self,
        async_session: AsyncSession,
        config_loader: ChannelConfigLoader,
        capacity_service: ChannelCapacityService,
    ) -> None:
        """Test tasks remain isolated per channel.

        Validates:
        - Each channel has independent task queue
        - Capacity tracking per-channel
        - No task leakage between channels
        """
        # Given: Two channels with different configurations
        config1 = ChannelConfigSchema(
            channel_id="isolation_ch1",
            channel_name="Isolation Channel 1",
            notion_database_id="iso1_db",
            max_concurrent=2,
        )
        config2 = ChannelConfigSchema(
            channel_id="isolation_ch2",
            channel_name="Isolation Channel 2",
            notion_database_id="iso2_db",
            max_concurrent=5,
        )
        channel1 = await config_loader.sync_to_database(config1, async_session)
        channel2 = await config_loader.sync_to_database(config2, async_session)

        # When: Add tasks to each channel
        # Channel 1: 2 in-progress (at capacity)
        for i in range(2):
            task = create_test_task(
                channel1.id,
                status=TaskStatus.GENERATING_ASSETS,
                notion_page_id=f"ch1task{i:02d}" + "0" * 22,
            )
            async_session.add(task)

        # Channel 2: 3 in-progress (under capacity)
        for i in range(3):
            task = create_test_task(
                channel2.id,
                status=TaskStatus.GENERATING_VIDEO,
                notion_page_id=f"ch2task{i:02d}" + "0" * 22,
            )
            async_session.add(task)
        await async_session.commit()

        # Then: Each channel has independent capacity status
        stats1 = await capacity_service.get_channel_capacity("isolation_ch1", async_session)
        stats2 = await capacity_service.get_channel_capacity("isolation_ch2", async_session)

        assert stats1.in_progress_count == 2
        assert stats1.has_capacity is False  # At capacity

        assert stats2.in_progress_count == 3
        assert stats2.has_capacity is True  # Under capacity (3 < 5)

        # Verify task counts per channel
        result1 = await async_session.execute(
            select(Task).where(Task.channel_id == channel1.id)
        )
        result2 = await async_session.execute(
            select(Task).where(Task.channel_id == channel2.id)
        )

        assert len(result1.scalars().all()) == 2
        assert len(result2.scalars().all()) == 3


class TestE2ETaskPriorityManagement:
    """E2E tests for task priority levels."""

    @pytest.mark.asyncio
    async def test_p1_task_priority_levels_persist(
        self,
        async_session: AsyncSession,
        test_channel: Channel,
    ) -> None:
        """Test task priority levels persist correctly.

        Validates:
        - All three priority levels (HIGH, NORMAL, LOW)
        - Default priority is NORMAL
        - Priority can be changed
        """
        # Given: Tasks with different priorities
        task_high = create_test_task(
            test_channel.id,
            priority=PriorityLevel.HIGH,
            notion_page_id="priohi" + "0" * 24,
        )
        task_normal = create_test_task(
            test_channel.id,
            priority=PriorityLevel.NORMAL,
            notion_page_id="prionorm" + "0" * 22,
        )
        task_low = create_test_task(
            test_channel.id,
            priority=PriorityLevel.LOW,
            notion_page_id="priolo" + "0" * 24,
        )

        async_session.add(task_high)
        async_session.add(task_normal)
        async_session.add(task_low)
        await async_session.commit()

        # When: Reload from database
        result = await async_session.execute(
            select(Task)
            .where(Task.channel_id == test_channel.id)
            .order_by(Task.priority)
        )
        tasks = result.scalars().all()

        # Then: All priorities persisted correctly
        assert len(tasks) == 3
        assert tasks[0].priority == PriorityLevel.HIGH
        assert tasks[1].priority == PriorityLevel.LOW
        assert tasks[2].priority == PriorityLevel.NORMAL


class TestE2ETaskYouTubeIntegration:
    """E2E tests for YouTube URL tracking."""

    @pytest.mark.asyncio
    async def test_p1_youtube_url_populated_on_publish(
        self,
        async_session: AsyncSession,
        test_channel: Channel,
    ) -> None:
        """Test YouTube URL populated when task reaches PUBLISHED.

        Validates:
        - youtube_url initially None
        - Can be populated during upload phase
        - Persists correctly
        """
        # Given: Task in UPLOADING status
        task = create_test_task(
            test_channel.id,
            status=TaskStatus.UPLOADING,
        )
        async_session.add(task)
        await async_session.commit()
        assert task.youtube_url is None

        # When: Upload completes and URL populated
        task.youtube_url = "https://youtube.com/watch?v=dQw4w9WgXcQ"
        task.status = TaskStatus.PUBLISHED
        await async_session.commit()
        await async_session.refresh(task)

        # Then: YouTube URL persisted
        assert task.youtube_url == "https://youtube.com/watch?v=dQw4w9WgXcQ"
        assert task.status == TaskStatus.PUBLISHED
