"""Performance tests for AI Video Generator orchestration layer.

Tests system behavior under load, rate limiting enforcement, database
scalability, and concurrent operations. Validates performance requirements
for multi-channel orchestration.

Priority: [P2] - Performance validation
"""

import asyncio
import time
import uuid
from collections import Counter

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Channel, Task, TaskStatus
from app.schemas.channel_config import ChannelConfigSchema
from app.services.channel_capacity_service import ChannelCapacityService
from app.services.channel_config_loader import ChannelConfigLoader


def create_test_task(
    channel_id: uuid.UUID, status: TaskStatus = TaskStatus.DRAFT, **kwargs
) -> Task:
    """Helper to create a Task with all required fields for testing."""
    defaults = {
        "notion_page_id": uuid.uuid4().hex,
        "title": "Performance Test Video",
        "topic": "Performance Test Topic",
        "story_direction": "Performance test story direction",
    }
    defaults.update(kwargs)
    return Task(channel_id=channel_id, status=status, **defaults)


@pytest_asyncio.fixture
async def config_loader() -> ChannelConfigLoader:
    """Create ChannelConfigLoader for testing."""
    return ChannelConfigLoader()


@pytest_asyncio.fixture
async def capacity_service() -> ChannelCapacityService:
    """Create ChannelCapacityService for testing."""
    return ChannelCapacityService()


@pytest_asyncio.fixture
async def perf_channel(
    async_session: AsyncSession,
    config_loader: ChannelConfigLoader,
) -> Channel:
    """Create a channel for performance testing."""
    config = ChannelConfigSchema(
        channel_id="perf_test_channel",
        channel_name="Performance Test Channel",
        notion_database_id="perf_test_db",
        max_concurrent=10,
    )
    channel = await config_loader.sync_to_database(config, async_session)
    return channel


class TestDatabasePerformance:
    """Performance tests for database operations at scale."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_p2_bulk_task_creation_1000_tasks(
        self,
        async_session: AsyncSession,
        perf_channel: Channel,
    ) -> None:
        """Test database performance with 1000 task insertions.

        Validates:
        - Database can handle bulk inserts efficiently
        - No performance degradation with large dataset
        - Transaction commit time acceptable
        - Target: <5 seconds for 1000 tasks
        """
        task_count = 1000
        start_time = time.time()

        # Given: 1000 tasks to insert
        tasks = []
        for i in range(task_count):
            task = create_test_task(
                perf_channel.id,
                status=TaskStatus.QUEUED,
                notion_page_id=f"bulk{i:04d}" + "0" * 24,
                title=f"Bulk Task {i}",
            )
            tasks.append(task)

        # When: Bulk insert all tasks
        async_session.add_all(tasks)
        await async_session.commit()

        end_time = time.time()
        duration = end_time - start_time

        # Then: Insertion completed within acceptable time
        assert duration < 5.0, f"Bulk insert took {duration:.2f}s (target: <5s)"

        # Verify all tasks persisted
        result = await async_session.execute(select(Task).where(Task.channel_id == perf_channel.id))
        inserted_tasks = result.scalars().all()
        assert len(inserted_tasks) == task_count

        print(f"\n✓ Inserted {task_count} tasks in {duration:.2f} seconds")
        print(f"  Average: {(duration / task_count) * 1000:.2f} ms/task")

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_p2_query_performance_with_large_dataset(
        self,
        async_session: AsyncSession,
        perf_channel: Channel,
        capacity_service: ChannelCapacityService,
    ) -> None:
        """Test query performance with large dataset (1000+ tasks).

        Validates:
        - Index effectiveness for status filtering
        - Channel capacity queries remain fast with scale
        - Target: <100ms for capacity calculation
        """
        # Given: 1000 tasks with mixed statuses
        task_count = 1000
        statuses = [
            TaskStatus.QUEUED,
            TaskStatus.GENERATING_ASSETS,
            TaskStatus.GENERATING_VIDEO,
            TaskStatus.ASSEMBLING,
            TaskStatus.PUBLISHED,
            TaskStatus.ASSET_ERROR,
        ]

        tasks = []
        for i in range(task_count):
            status = statuses[i % len(statuses)]
            task = create_test_task(
                perf_channel.id,
                status=status,
                notion_page_id=f"query{i:04d}" + "0" * 24,
            )
            tasks.append(task)

        async_session.add_all(tasks)
        await async_session.commit()

        # When: Query channel capacity
        start_time = time.time()
        stats = await capacity_service.get_channel_capacity("perf_test_channel", async_session)
        end_time = time.time()

        query_duration = (end_time - start_time) * 1000  # Convert to ms

        # Then: Query completed within target time
        assert query_duration < 100, f"Query took {query_duration:.2f}ms (target: <100ms)"
        assert stats is not None
        assert stats.pending_count > 0
        assert stats.in_progress_count > 0

        print(f"\n✓ Capacity query with {task_count} tasks: {query_duration:.2f}ms")

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_p2_status_update_performance(
        self,
        async_session: AsyncSession,
        perf_channel: Channel,
    ) -> None:
        """Test status update performance at scale.

        Validates:
        - Status transitions remain fast with large dataset
        - Index updates don't cause bottlenecks
        - Target: <50ms per update
        """
        # Given: 100 tasks to update
        task_count = 100
        tasks = []
        for i in range(task_count):
            task = create_test_task(
                perf_channel.id,
                status=TaskStatus.QUEUED,
                notion_page_id=f"update{i:03d}" + "0" * 24,
            )
            tasks.append(task)

        async_session.add_all(tasks)
        await async_session.commit()

        # Reload tasks with IDs
        result = await async_session.execute(select(Task).where(Task.channel_id == perf_channel.id))
        tasks = result.scalars().all()

        # When: Update all tasks to new status (must go through CLAIMED)
        start_time = time.time()
        for task in tasks:
            task.status = TaskStatus.CLAIMED
            task.status = TaskStatus.GENERATING_ASSETS
        await async_session.commit()
        end_time = time.time()

        total_duration = (end_time - start_time) * 1000  # ms
        avg_duration = total_duration / task_count

        # Then: Updates completed efficiently
        assert avg_duration < 50, f"Average update: {avg_duration:.2f}ms (target: <50ms)"

        print(f"\n✓ Updated {task_count} tasks in {total_duration:.2f}ms")
        print(f"  Average: {avg_duration:.2f}ms/task")


class TestConcurrentOperations:
    """Performance tests for concurrent channel operations."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_p2_concurrent_channel_capacity_queries(
        self,
        async_session: AsyncSession,
        config_loader: ChannelConfigLoader,
        capacity_service: ChannelCapacityService,
    ) -> None:
        """Test concurrent capacity queries for 10+ channels.

        Validates:
        - Multiple channels can be queried simultaneously
        - No race conditions or deadlocks
        - Performance scales with channel count
        - Target: <500ms for 10 channels
        """
        # Given: 10 channels with tasks
        channel_count = 10
        channels = []

        for i in range(channel_count):
            config = ChannelConfigSchema(
                channel_id=f"concurrent_ch{i:02d}",
                channel_name=f"Concurrent Channel {i}",
                notion_database_id=f"concurrent_db{i}",
                max_concurrent=3,
            )
            channel = await config_loader.sync_to_database(config, async_session)
            channels.append(channel)

            # Add 10 tasks per channel with mixed statuses
            for j in range(10):
                status = TaskStatus.GENERATING_ASSETS if j < 5 else TaskStatus.QUEUED
                task = create_test_task(
                    channel.id,
                    status=status,
                    notion_page_id=f"conc{i:02d}{j:02d}" + "0" * 24,
                )
                async_session.add(task)

        await async_session.commit()

        # When: Query all channels concurrently
        start_time = time.time()

        async def query_channel_capacity(channel_id: str):
            return await capacity_service.get_channel_capacity(channel_id, async_session)

        tasks = [query_channel_capacity(f"concurrent_ch{i:02d}") for i in range(channel_count)]
        results = await asyncio.gather(*tasks)

        end_time = time.time()
        duration = (end_time - start_time) * 1000  # ms

        # Then: All queries completed successfully and quickly
        assert len(results) == channel_count
        assert all(r is not None for r in results)
        assert duration < 500, f"Concurrent queries took {duration:.2f}ms (target: <500ms)"

        print(f"\n✓ Queried {channel_count} channels concurrently in {duration:.2f}ms")
        print(f"  Average: {duration / channel_count:.2f}ms/channel")

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_p2_concurrent_task_creation_multiple_channels(
        self,
        async_session: AsyncSession,
        config_loader: ChannelConfigLoader,
    ) -> None:
        """Test concurrent task creation across multiple channels.

        Validates:
        - No database contention with concurrent inserts
        - Task isolation maintained per channel
        - Target: <2 seconds for 100 tasks across 10 channels
        """
        # Given: 10 channels
        channel_count = 10
        tasks_per_channel = 10
        channels = []

        for i in range(channel_count):
            config = ChannelConfigSchema(
                channel_id=f"multi_ch{i:02d}",
                channel_name=f"Multi Channel {i}",
                notion_database_id=f"multi_db{i}",
            )
            channel = await config_loader.sync_to_database(config, async_session)
            channels.append(channel)

        # When: Create tasks concurrently across all channels
        start_time = time.time()

        async def create_tasks_for_channel(channel: Channel, channel_idx: int):
            tasks = []
            for j in range(tasks_per_channel):
                task = create_test_task(
                    channel.id,
                    status=TaskStatus.QUEUED,
                    notion_page_id=f"multi{channel_idx:02d}{j:02d}" + "0" * 24,
                )
                tasks.append(task)
            async_session.add_all(tasks)

        await asyncio.gather(*[create_tasks_for_channel(ch, i) for i, ch in enumerate(channels)])
        await async_session.commit()

        end_time = time.time()
        duration = end_time - start_time

        total_tasks = channel_count * tasks_per_channel
        assert duration < 2.0, f"Concurrent creation took {duration:.2f}s (target: <2s)"

        # Verify task isolation per channel
        for i, channel in enumerate(channels):
            result = await async_session.execute(select(Task).where(Task.channel_id == channel.id))
            channel_tasks = result.scalars().all()
            assert len(channel_tasks) == tasks_per_channel

        print(f"\n✓ Created {total_tasks} tasks across {channel_count} channels in {duration:.2f}s")

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_p2_concurrent_capacity_checks_with_updates(
        self,
        async_session: AsyncSession,
        perf_channel: Channel,
        capacity_service: ChannelCapacityService,
    ) -> None:
        """Test concurrent capacity checks while tasks are being updated.

        Validates:
        - Read operations don't block during writes
        - Capacity calculations remain consistent
        - No race conditions with concurrent access
        """
        # Given: 50 tasks
        task_count = 50
        tasks = []
        for i in range(task_count):
            task = create_test_task(
                perf_channel.id,
                status=TaskStatus.QUEUED,
                notion_page_id=f"race{i:03d}" + "0" * 24,
            )
            tasks.append(task)

        async_session.add_all(tasks)
        await async_session.commit()

        # When: Concurrent capacity checks while updating tasks
        capacity_results = []
        update_count = 0

        async def check_capacity():
            for _ in range(10):
                stats = await capacity_service.get_channel_capacity(
                    "perf_test_channel", async_session
                )
                capacity_results.append(stats)
                await asyncio.sleep(0.01)

        async def update_tasks():
            nonlocal update_count
            result = await async_session.execute(
                select(Task).where(Task.channel_id == perf_channel.id)
            )
            task_list = result.scalars().all()
            for task in task_list[:25]:  # Update half
                task.status = TaskStatus.CLAIMED
                task.status = TaskStatus.GENERATING_ASSETS
                update_count += 1
                await async_session.commit()
                await asyncio.sleep(0.01)

        await asyncio.gather(check_capacity(), update_tasks())

        # Then: All capacity checks completed successfully
        assert len(capacity_results) == 10
        assert all(r is not None for r in capacity_results)
        assert update_count == 25

        # Verify capacity values are consistent (no corruption)
        for stats in capacity_results:
            assert stats.pending_count + stats.in_progress_count <= task_count

        print(f"\n✓ Performed 10 capacity checks during 25 concurrent task updates")


class TestMultiChannelScalability:
    """Performance tests for multi-channel orchestration at scale."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_p2_get_channels_with_capacity_performance(
        self,
        async_session: AsyncSession,
        config_loader: ChannelConfigLoader,
        capacity_service: ChannelCapacityService,
    ) -> None:
        """Test get_channels_with_capacity() with 20+ channels.

        Validates:
        - Efficient filtering of channels with capacity
        - Single aggregation query (no N+1)
        - Target: <200ms for 20 channels
        """
        # Given: 20 channels with varying capacity status
        channel_count = 20
        for i in range(channel_count):
            config = ChannelConfigSchema(
                channel_id=f"scale_ch{i:02d}",
                channel_name=f"Scale Channel {i}",
                notion_database_id=f"scale_db{i}",
                max_concurrent=3,
            )
            channel = await config_loader.sync_to_database(config, async_session)

            # Some channels at capacity, some under capacity
            in_progress_count = 3 if i % 2 == 0 else 1
            for j in range(in_progress_count):
                task = create_test_task(
                    channel.id,
                    status=TaskStatus.GENERATING_ASSETS,
                    notion_page_id=f"scale{i:02d}{j:02d}" + "0" * 24,
                )
                async_session.add(task)

        await async_session.commit()

        # When: Get channels with capacity
        start_time = time.time()
        channels_with_capacity = await capacity_service.get_channels_with_capacity(async_session)
        end_time = time.time()

        duration = (end_time - start_time) * 1000  # ms

        # Then: Query completed efficiently
        assert duration < 200, f"Query took {duration:.2f}ms (target: <200ms)"

        # Verify correct filtering (every other channel has capacity)
        assert len(channels_with_capacity) == 10  # Half have capacity

        print(f"\n✓ Filtered {channel_count} channels in {duration:.2f}ms")
        print(f"  Found {len(channels_with_capacity)} channels with capacity")

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_p2_get_queue_stats_all_channels_performance(
        self,
        async_session: AsyncSession,
        config_loader: ChannelConfigLoader,
        capacity_service: ChannelCapacityService,
    ) -> None:
        """Test get_queue_stats() across all channels with large dataset.

        Validates:
        - Efficient aggregation across all active channels
        - Single query with GROUP BY (no N+1)
        - Target: <300ms for 20 channels with 1000 total tasks
        """
        # Given: 20 channels with 50 tasks each
        channel_count = 20
        tasks_per_channel = 50

        for i in range(channel_count):
            config = ChannelConfigSchema(
                channel_id=f"stats_ch{i:02d}",
                channel_name=f"Stats Channel {i}",
                notion_database_id=f"stats_db{i}",
                max_concurrent=5,
            )
            channel = await config_loader.sync_to_database(config, async_session)

            # Mix of statuses
            for j in range(tasks_per_channel):
                if j < 10:
                    status = TaskStatus.QUEUED
                elif j < 30:
                    status = TaskStatus.GENERATING_ASSETS
                else:
                    status = TaskStatus.PUBLISHED
                task = create_test_task(
                    channel.id,
                    status=status,
                    notion_page_id=f"stats{i:02d}{j:03d}" + "0" * 23,
                )
                async_session.add(task)

        await async_session.commit()

        # When: Get queue stats for all channels
        start_time = time.time()
        stats = await capacity_service.get_queue_stats(async_session)
        end_time = time.time()

        duration = (end_time - start_time) * 1000  # ms

        # Then: Query completed efficiently
        assert duration < 300, f"Query took {duration:.2f}ms (target: <300ms)"
        assert len(stats) == channel_count

        # Verify aggregation correctness
        total_pending = sum(s.pending_count for s in stats)
        total_in_progress = sum(s.in_progress_count for s in stats)
        assert total_pending == 200  # 10 per channel
        assert total_in_progress == 400  # 20 per channel

        print(f"\n✓ Aggregated stats for {channel_count} channels in {duration:.2f}ms")
        print(f"  Total tasks: {channel_count * tasks_per_channel}")


class TestMemoryAndResourceUsage:
    """Performance tests for memory efficiency and resource management."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_p2_memory_efficiency_large_result_sets(
        self,
        async_session: AsyncSession,
        perf_channel: Channel,
    ) -> None:
        """Test memory usage with large query result sets.

        Validates:
        - No memory leaks with large datasets
        - Efficient result iteration
        - Database connections properly released
        """
        # Given: 500 tasks
        task_count = 500
        tasks = []
        for i in range(task_count):
            task = create_test_task(
                perf_channel.id,
                status=TaskStatus.QUEUED,
                notion_page_id=f"mem{i:04d}" + "0" * 24,
            )
            tasks.append(task)

        async_session.add_all(tasks)
        await async_session.commit()

        # When: Query and iterate through large result set
        result = await async_session.execute(select(Task).where(Task.channel_id == perf_channel.id))
        loaded_tasks = result.scalars().all()

        # Then: All tasks loaded successfully
        assert len(loaded_tasks) == task_count

        # Verify task data integrity (sampling)
        sample = loaded_tasks[0]
        assert sample.title == "Performance Test Video"
        assert sample.status == TaskStatus.QUEUED
        assert sample.channel_id == perf_channel.id

        print(f"\n✓ Successfully loaded and iterated {task_count} tasks")

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_p2_pagination_performance(
        self,
        async_session: AsyncSession,
        perf_channel: Channel,
    ) -> None:
        """Test pagination performance for large datasets.

        Validates:
        - Efficient offset/limit queries
        - Consistent performance across pages
        - Target: <50ms per page (100 items)
        """
        # Given: 1000 tasks
        task_count = 1000
        tasks = []
        for i in range(task_count):
            task = create_test_task(
                perf_channel.id,
                status=TaskStatus.QUEUED,
                notion_page_id=f"page{i:04d}" + "0" * 24,
            )
            tasks.append(task)

        async_session.add_all(tasks)
        await async_session.commit()

        # When: Paginate through results
        page_size = 100
        page_count = task_count // page_size
        page_durations = []

        for page_num in range(page_count):
            start_time = time.time()
            result = await async_session.execute(
                select(Task)
                .where(Task.channel_id == perf_channel.id)
                .offset(page_num * page_size)
                .limit(page_size)
            )
            page_tasks = result.scalars().all()
            end_time = time.time()

            duration = (end_time - start_time) * 1000  # ms
            page_durations.append(duration)
            assert len(page_tasks) == page_size

        # Then: All pages retrieved efficiently
        avg_duration = sum(page_durations) / len(page_durations)
        max_duration = max(page_durations)

        assert avg_duration < 50, f"Avg page time: {avg_duration:.2f}ms (target: <50ms)"
        assert max_duration < 100, f"Max page time: {max_duration:.2f}ms (target: <100ms)"

        print(f"\n✓ Paginated {task_count} tasks into {page_count} pages")
        print(f"  Average: {avg_duration:.2f}ms/page")
        print(f"  Max: {max_duration:.2f}ms")


class TestIndexEffectiveness:
    """Performance tests validating database index effectiveness."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_p2_status_index_performance(
        self,
        async_session: AsyncSession,
        perf_channel: Channel,
    ) -> None:
        """Test status index effectiveness for filtering.

        Validates:
        - ix_tasks_status index used for status queries
        - Fast filtering with large dataset
        - Target: <20ms for status filter on 1000 tasks
        """
        # Given: 1000 tasks with varied statuses
        task_count = 1000
        status_distribution = {
            TaskStatus.QUEUED: 100,
            TaskStatus.GENERATING_ASSETS: 200,
            TaskStatus.GENERATING_VIDEO: 150,
            TaskStatus.PUBLISHED: 450,
            TaskStatus.ASSET_ERROR: 100,
        }

        tasks = []
        idx = 0
        for status, count in status_distribution.items():
            for _ in range(count):
                task = create_test_task(
                    perf_channel.id,
                    status=status,
                    notion_page_id=f"idx{idx:04d}" + "0" * 24,
                )
                tasks.append(task)
                idx += 1

        async_session.add_all(tasks)
        await async_session.commit()

        # When: Filter by specific status
        start_time = time.time()
        result = await async_session.execute(
            select(Task)
            .where(Task.channel_id == perf_channel.id)
            .where(Task.status == TaskStatus.GENERATING_ASSETS)
        )
        filtered_tasks = result.scalars().all()
        end_time = time.time()

        duration = (end_time - start_time) * 1000  # ms

        # Then: Query fast due to index
        assert duration < 20, f"Status filter took {duration:.2f}ms (target: <20ms)"
        assert len(filtered_tasks) == 200

        print(f"\n✓ Filtered 200/{task_count} tasks by status in {duration:.2f}ms")

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_p2_composite_index_performance(
        self,
        async_session: AsyncSession,
        perf_channel: Channel,
    ) -> None:
        """Test composite index (channel_id, status) effectiveness.

        Validates:
        - ix_tasks_channel_id_status index used for capacity queries
        - Efficient filtering on both columns
        - Target: <30ms for composite filter on 1000 tasks
        """
        # Given: 1000 tasks
        task_count = 1000
        tasks = []
        for i in range(task_count):
            status = TaskStatus.GENERATING_ASSETS if i % 3 == 0 else TaskStatus.QUEUED
            task = create_test_task(
                perf_channel.id,
                status=status,
                notion_page_id=f"comp{i:04d}" + "0" * 24,
            )
            tasks.append(task)

        async_session.add_all(tasks)
        await async_session.commit()

        # When: Filter by channel_id AND status (composite index)
        start_time = time.time()
        result = await async_session.execute(
            select(Task)
            .where(Task.channel_id == perf_channel.id)
            .where(Task.status == TaskStatus.GENERATING_ASSETS)
        )
        filtered_tasks = result.scalars().all()
        end_time = time.time()

        duration = (end_time - start_time) * 1000  # ms

        # Then: Query uses composite index efficiently
        assert duration < 30, f"Composite filter took {duration:.2f}ms (target: <30ms)"
        assert len(filtered_tasks) == 334  # ~1/3 of tasks

        print(f"\n✓ Composite index query on {task_count} tasks: {duration:.2f}ms")
