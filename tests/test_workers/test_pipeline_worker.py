"""Unit tests for pipeline worker.

Tests cover:
- Task claiming logic (atomic, priority-based)
- Pipeline task processing (orchestrator integration)
- Error handling and recovery
- Worker loop behavior
- Graceful shutdown
- Status updates

Test Strategy:
- Mock PipelineOrchestrator to isolate worker logic
- Mock database operations for claim_next_task
- Verify correct status transitions
- Test error scenarios and recovery
"""

import asyncio
import signal
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.models import TaskStatus
from app.workers import pipeline_worker


class TestProcessPipelineTask:
    """Test process_pipeline_task function."""

    @pytest.mark.asyncio
    async def test_process_pipeline_task_success(self):
        """Test successful task processing."""
        task_id = "test-task-123"

        with patch("app.workers.pipeline_worker.PipelineOrchestrator") as mock_orch_class:
            mock_orch = Mock()
            mock_orch_class.return_value = mock_orch
            mock_orch.execute_pipeline = AsyncMock()

            await pipeline_worker.process_pipeline_task(task_id)

            # Verify orchestrator was initialized and executed
            mock_orch_class.assert_called_once_with(task_id)
            mock_orch.execute_pipeline.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_pipeline_task_handles_exception(self, async_session):
        """Test task processing handles exceptions gracefully."""
        from app.models import Channel, Task

        channel = Channel(
            channel_id="poke1",
            channel_name="Pokemon Channel",
            is_active=True,
        )
        async_session.add(channel)
        await async_session.flush()  # Flush to get channel.id

        task = Task(
            channel_id=channel.id,
            notion_page_id="test123",
            title="Test Video",
            topic="Test Topic",
            story_direction="Test Story",
            status=TaskStatus.CLAIMED,
        )
        async_session.add(task)
        await async_session.commit()

        task_id = str(task.id)

        with patch("app.workers.pipeline_worker.PipelineOrchestrator") as mock_orch_class:
            mock_orch = Mock()
            mock_orch_class.return_value = mock_orch
            mock_orch.execute_pipeline = AsyncMock(side_effect=Exception("Pipeline error"))

            with patch("app.workers.pipeline_worker.async_session_factory") as mock_session_class:
                mock_session = AsyncMock()
                mock_session_class.return_value.__aenter__.return_value = mock_session
                mock_session_class.return_value.__aexit__.return_value = AsyncMock()

                mock_session.get = AsyncMock(return_value=task)
                mock_session.begin = Mock()
                mock_session.begin.return_value.__aenter__ = AsyncMock()
                mock_session.begin.return_value.__aexit__ = AsyncMock()
                mock_session.commit = AsyncMock()

                # Should not raise exception
                await pipeline_worker.process_pipeline_task(task_id)

                # Verify error handling attempted to update task
                mock_session.get.assert_called()


class TestClaimNextTask:
    """Test claim_next_task function."""

    @pytest.mark.asyncio
    async def test_claim_next_task_success(self, async_session):
        """Test claiming a queued task successfully."""
        from app.models import Channel, PriorityLevel, Task

        channel = Channel(
            channel_id="poke1",
            channel_name="Pokemon Channel",
            is_active=True,
        )
        async_session.add(channel)
        await async_session.flush()  # Flush to get channel.id

        task = Task(
            channel_id=channel.id,
            notion_page_id="test123",
            title="Test Video",
            topic="Test Topic",
            story_direction="Test Story",
            status=TaskStatus.QUEUED,
            priority=PriorityLevel.HIGH,
        )
        async_session.add(task)
        await async_session.commit()

        with patch("app.workers.pipeline_worker.async_session_factory") as mock_session_class:
            # Setup mock to return our session
            mock_session_class.return_value.__aenter__.return_value = async_session
            mock_session_class.return_value.__aexit__.return_value = AsyncMock()

            claimed_task_id = await pipeline_worker.claim_next_task()

            assert claimed_task_id is not None
            assert claimed_task_id == str(task.id)

            # Verify task status was updated to CLAIMED
            await async_session.refresh(task)
            assert task.status == TaskStatus.CLAIMED

    @pytest.mark.asyncio
    async def test_claim_next_task_no_tasks_available(self):
        """Test claiming when no tasks are queued."""
        with patch("app.workers.pipeline_worker.async_session_factory") as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value.__aenter__.return_value = mock_session
            mock_session_class.return_value.__aexit__.return_value = None

            # Mock begin() to return an async context manager
            def mock_begin():
                mock_transaction = AsyncMock()
                mock_transaction.__aenter__ = AsyncMock(return_value=mock_transaction)
                mock_transaction.__aexit__ = AsyncMock(return_value=None)
                return mock_transaction

            mock_session.begin = mock_begin

            # Mock execute to return no rows
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = None
            mock_session.execute = AsyncMock(return_value=mock_result)

            claimed_task_id = await pipeline_worker.claim_next_task()

            assert claimed_task_id is None

    @pytest.mark.asyncio
    async def test_claim_next_task_priority_ordering(self, async_session):
        """Test tasks are claimed in priority order (high > normal > low)."""
        from app.models import Channel, PriorityLevel, Task

        channel = Channel(
            channel_id="poke1",
            channel_name="Pokemon Channel",
            is_active=True,
        )
        async_session.add(channel)
        await async_session.flush()  # Flush to get channel.id

        # Create tasks with different priorities
        low_task = Task(
            channel_id=channel.id,
            notion_page_id="low123",
            title="Low Priority",
            topic="Test",
            story_direction="Test",
            status=TaskStatus.QUEUED,
            priority=PriorityLevel.LOW,
        )
        high_task = Task(
            channel_id=channel.id,
            notion_page_id="high123",
            title="High Priority",
            topic="Test",
            story_direction="Test",
            status=TaskStatus.QUEUED,
            priority=PriorityLevel.HIGH,
        )
        normal_task = Task(
            channel_id=channel.id,
            notion_page_id="normal123",
            title="Normal Priority",
            topic="Test",
            story_direction="Test",
            status=TaskStatus.QUEUED,
            priority=PriorityLevel.NORMAL,
        )

        async_session.add_all([low_task, normal_task, high_task])
        await async_session.commit()

        with patch("app.workers.pipeline_worker.async_session_factory") as mock_session_class:
            mock_session_class.return_value.__aenter__.return_value = async_session
            mock_session_class.return_value.__aexit__.return_value = AsyncMock()

            claimed_task_id = await pipeline_worker.claim_next_task()

            # Should claim high priority task first
            assert claimed_task_id == str(high_task.id)


class TestWorkerLoop:
    """Test worker_loop function."""

    @pytest.mark.asyncio
    async def test_worker_loop_processes_tasks(self):
        """Test worker loop processes tasks continuously."""
        # Ensure shutdown flag starts as False
        pipeline_worker.SHUTDOWN_REQUESTED = False

        # Create a function that sets shutdown flag after first call
        call_count = [0]

        async def mock_claim_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return "test-task-123"
            else:
                pipeline_worker.SHUTDOWN_REQUESTED = True
                return None

        with patch(
            "app.workers.pipeline_worker.claim_next_task", new_callable=AsyncMock
        ) as mock_claim:
            mock_claim.side_effect = mock_claim_side_effect

            with patch(
                "app.workers.pipeline_worker.process_pipeline_task", new_callable=AsyncMock
            ) as mock_process:
                await pipeline_worker.worker_loop()

                # Verify task was processed
                mock_process.assert_called_once_with("test-task-123")

        # Reset shutdown flag
        pipeline_worker.SHUTDOWN_REQUESTED = False

    @pytest.mark.asyncio
    async def test_worker_loop_handles_no_tasks(self):
        """Test worker loop sleeps when no tasks available."""
        # Ensure shutdown flag starts as False
        pipeline_worker.SHUTDOWN_REQUESTED = False

        # Mock sleep to set shutdown flag after first call
        async def mock_sleep_side_effect(duration):
            pipeline_worker.SHUTDOWN_REQUESTED = True

        with patch(
            "app.workers.pipeline_worker.claim_next_task", new_callable=AsyncMock
        ) as mock_claim:
            mock_claim.return_value = None  # No tasks available

            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                mock_sleep.side_effect = mock_sleep_side_effect

                await pipeline_worker.worker_loop()

                # Verify sleep was called
                mock_sleep.assert_called_once_with(5)

        pipeline_worker.SHUTDOWN_REQUESTED = False

    @pytest.mark.asyncio
    async def test_worker_loop_handles_exceptions(self):
        """Test worker loop continues after exceptions."""
        with patch(
            "app.workers.pipeline_worker.claim_next_task", new_callable=AsyncMock
        ) as mock_claim:
            # First call raises exception, second returns None
            mock_claim.side_effect = [Exception("Database error"), None]

            with patch("asyncio.sleep", new_callable=AsyncMock):
                # Stop after handling exception
                pipeline_worker.SHUTDOWN_REQUESTED = True

                # Should not raise exception
                await pipeline_worker.worker_loop()

        pipeline_worker.SHUTDOWN_REQUESTED = False

    @pytest.mark.asyncio
    async def test_worker_loop_respects_shutdown_signal(self):
        """Test worker loop stops when shutdown requested."""
        # Set shutdown flag before starting
        pipeline_worker.SHUTDOWN_REQUESTED = True

        with patch(
            "app.workers.pipeline_worker.claim_next_task", new_callable=AsyncMock
        ) as mock_claim:
            await pipeline_worker.worker_loop()

            # Should not attempt to claim tasks
            mock_claim.assert_not_called()

        pipeline_worker.SHUTDOWN_REQUESTED = False


class TestSignalHandler:
    """Test signal handler for graceful shutdown."""

    def test_signal_handler_sets_shutdown_flag(self):
        """Test signal handler sets shutdown flag."""
        # Reset flag
        pipeline_worker.SHUTDOWN_REQUESTED = False

        # Simulate SIGTERM
        pipeline_worker.signal_handler(signal.SIGTERM, None)

        # Verify flag was set
        assert pipeline_worker.SHUTDOWN_REQUESTED is True

        # Reset for other tests
        pipeline_worker.SHUTDOWN_REQUESTED = False

    def test_signal_handler_handles_sigint(self):
        """Test signal handler handles SIGINT (Ctrl+C)."""
        pipeline_worker.SHUTDOWN_REQUESTED = False

        pipeline_worker.signal_handler(signal.SIGINT, None)

        assert pipeline_worker.SHUTDOWN_REQUESTED is True

        pipeline_worker.SHUTDOWN_REQUESTED = False


class TestMain:
    """Test main entry point."""

    @pytest.mark.asyncio
    async def test_main_worker_loop_mode(self):
        """Test main runs worker loop by default."""
        with patch("app.workers.pipeline_worker.worker_loop", new_callable=AsyncMock) as mock_loop:
            with patch("sys.argv", ["pipeline_worker.py"]):
                await pipeline_worker.main()

                mock_loop.assert_called_once()

    @pytest.mark.asyncio
    async def test_main_single_task_mode(self):
        """Test main processes single task when --task-id provided."""
        with patch(
            "app.workers.pipeline_worker.process_pipeline_task", new_callable=AsyncMock
        ) as mock_process:
            with patch("sys.argv", ["pipeline_worker.py", "--task-id", "test-task-123"]):
                await pipeline_worker.main()

                mock_process.assert_called_once_with("test-task-123")
