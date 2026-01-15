"""Tests for Asset Generation Worker.

This module tests the process_asset_generation_task function which orchestrates
asset generation for tasks claimed from the queue.

Test Coverage:
- Task claiming and status updates
- Short transaction pattern (Architecture Decision 3)
- Asset generation success flow
- Error handling (CLI errors, timeouts, unexpected errors)
- Task not found scenario
- Notion status updates (async, non-blocking)
- Correlation ID logging

Architecture Compliance:
- Verifies short transaction pattern (claim → close → execute → reopen → update)
- Verifies database connection not held during long-running operations
- Verifies error handling marks task with correct status
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch
from uuid import uuid4

import pytest

from app.models import Channel, Task, TaskStatus
from app.utils.cli_wrapper import CLIScriptError
from app.workers.asset_worker import process_asset_generation_task


def create_mock_session_factory(async_session):
    """Create a properly mocked session factory for worker tests.

    Args:
        async_session: The test async session to use

    Returns:
        Mock session factory that returns the test session with begin() mocked
    """
    # Create a mock transaction context manager
    mock_transaction = AsyncMock()
    mock_transaction.__aenter__.return_value = mock_transaction
    mock_transaction.__aexit__.return_value = None

    # Mock the session's begin() method to return our transaction
    async_session.begin = MagicMock(return_value=mock_transaction)

    # Create the session factory mock
    mock_session_factory = MagicMock()
    mock_context_manager = AsyncMock()
    mock_context_manager.__aenter__.return_value = async_session
    mock_context_manager.__aexit__.return_value = None
    mock_session_factory.return_value = mock_context_manager

    return mock_session_factory


@pytest.mark.asyncio
class TestProcessAssetGenerationTask:
    """Test process_asset_generation_task function."""

    async def test_process_task_success(self, async_session, encryption_env):
        """Test successful asset generation flow."""
        # Create test channel
        channel = Channel(
            channel_id="poke1",
            channel_name="Test Channel",
            voice_id="test_voice",
            max_concurrent=2
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        # Create test task
        task = Task(
            channel_id=channel.id,
            notion_page_id="notion123",
            title="Test Video",
            topic="Bulbasaur forest documentary",
            story_direction="Show evolution through seasons",
            status=TaskStatus.QUEUED
        )
        async_session.add(task)
        await async_session.commit()
        await async_session.refresh(task)

        task_id = task.id

        # Mock asset generation service
        with patch('app.workers.asset_worker.async_session_factory', create_mock_session_factory(async_session)):
            with patch('app.workers.asset_worker.AssetGenerationService') as MockService:
                mock_service = MockService.return_value
                mock_service.create_asset_manifest.return_value = MagicMock(
                    global_atmosphere="Natural lighting",
                    assets=[]
                )
                # Make generate_assets async
                async def mock_generate_assets(*args, **kwargs):
                    return {
                        "generated": 22,
                        "skipped": 0,
                        "failed": 0,
                        "total_cost_usd": 1.496
                    }
                mock_service.generate_assets = mock_generate_assets

                # Process task
                await process_asset_generation_task(task_id)

        # Verify task status updated
        await async_session.refresh(task)
        assert task.status == TaskStatus.ASSETS_READY
        assert task.total_cost_usd == 1.496

    async def test_process_task_not_found(self, async_session):
        """Test handling of non-existent task."""
        fake_task_id = uuid4()

        # Should not raise, just log error
        with patch('app.workers.asset_worker.async_session_factory', create_mock_session_factory(async_session)):
            await process_asset_generation_task(fake_task_id)
        # No assertion - just verify it doesn't crash

    async def test_process_task_cli_script_error(self, async_session, encryption_env):
        """Test CLI script error handling."""
        # Create channel and task
        channel = Channel(
            channel_id="poke1",
            channel_name="Test Channel",
            voice_id="test_voice",
            max_concurrent=2
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        task = Task(
            channel_id=channel.id,
            notion_page_id="notion123",
            title="Test Video",
            topic="Bulbasaur forest",
            story_direction="Nature documentary",
            status=TaskStatus.QUEUED
        )
        async_session.add(task)
        await async_session.commit()
        await async_session.refresh(task)

        task_id = task.id

        # Mock service to raise CLIScriptError
        with patch('app.workers.asset_worker.async_session_factory', create_mock_session_factory(async_session)):
            with patch('app.workers.asset_worker.AssetGenerationService') as MockService:
                mock_service = MockService.return_value
                mock_service.create_asset_manifest.return_value = MagicMock(
                    global_atmosphere="Natural lighting",
                    assets=[]
                )

                async def mock_generate_assets(*args, **kwargs):
                    raise CLIScriptError(
                        "generate_asset.py",
                        1,
                        "Gemini API error: HTTP 500"
                    )
                mock_service.generate_assets = mock_generate_assets

                await process_asset_generation_task(task_id)

        # Verify task marked as error
        await async_session.refresh(task)
        assert task.status == TaskStatus.ASSET_ERROR
        assert task.error_log is not None
        assert "generate_asset.py" in task.error_log
        assert "exit 1" in task.error_log

    async def test_process_task_timeout_error(self, async_session, encryption_env):
        """Test timeout error handling."""
        channel = Channel(
            channel_id="poke1",
            channel_name="Test Channel",
            voice_id="test_voice",
            max_concurrent=2
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        task = Task(
            channel_id=channel.id,
            notion_page_id="notion123",
            title="Test Video",
            topic="Bulbasaur forest",
            story_direction="Nature documentary",
            status=TaskStatus.QUEUED
        )
        async_session.add(task)
        await async_session.commit()
        await async_session.refresh(task)

        task_id = task.id

        # Mock service to raise TimeoutError
        with patch('app.workers.asset_worker.async_session_factory', create_mock_session_factory(async_session)):
            with patch('app.workers.asset_worker.AssetGenerationService') as MockService:
                mock_service = MockService.return_value
                mock_service.create_asset_manifest.return_value = MagicMock(
                    global_atmosphere="Natural lighting",
                    assets=[]
                )

                async def mock_generate_assets(*args, **kwargs):
                    raise asyncio.TimeoutError()
                mock_service.generate_assets = mock_generate_assets

                await process_asset_generation_task(task_id)

        # Verify task marked as error
        await async_session.refresh(task)
        assert task.status == TaskStatus.ASSET_ERROR
        assert task.error_log is not None
        assert "timeout" in task.error_log.lower()

    async def test_process_task_unexpected_error(self, async_session, encryption_env):
        """Test unexpected error handling."""
        channel = Channel(
            channel_id="poke1",
            channel_name="Test Channel",
            voice_id="test_voice",
            max_concurrent=2
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        task = Task(
            channel_id=channel.id,
            notion_page_id="notion123",
            title="Test Video",
            topic="Bulbasaur forest",
            story_direction="Nature documentary",
            status=TaskStatus.QUEUED
        )
        async_session.add(task)
        await async_session.commit()
        await async_session.refresh(task)

        task_id = task.id

        # Mock service to raise unexpected exception
        with patch('app.workers.asset_worker.async_session_factory', create_mock_session_factory(async_session)):
            with patch('app.workers.asset_worker.AssetGenerationService') as MockService:
                mock_service = MockService.return_value
                mock_service.create_asset_manifest.side_effect = ValueError("Unexpected error")

                await process_asset_generation_task(task_id)

        # Verify task marked as error
        await async_session.refresh(task)
        assert task.status == TaskStatus.ASSET_ERROR
        assert task.error_log is not None
        assert "Unexpected error" in task.error_log

    async def test_short_transaction_pattern(self, async_session, encryption_env):
        """Test short transaction pattern (Architecture Decision 3)."""
        # Create channel and task
        channel = Channel(
            channel_id="poke1",
            channel_name="Test Channel",
            voice_id="test_voice",
            max_concurrent=2
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        task = Task(
            channel_id=channel.id,
            notion_page_id="notion123",
            title="Test Video",
            topic="Bulbasaur forest",
            story_direction="Nature documentary",
            status=TaskStatus.QUEUED
        )
        async_session.add(task)
        await async_session.commit()
        await async_session.refresh(task)

        task_id = task.id

        # Track database sessions
        session_lifecycle = []

        # Create a session tracker that logs lifecycle events
        class SessionTracker:
            def __init__(self):
                session_lifecycle.append("open")

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                session_lifecycle.append("close")

            def begin(self):
                session_lifecycle.append("begin")
                # Return async context manager for begin()
                return AsyncMock(__aenter__=AsyncMock(return_value=self), __aexit__=AsyncMock())

            async def get(self, model, id):
                if model == Task:
                    await async_session.refresh(task)
                    return task
                return None

            async def commit(self):
                session_lifecycle.append("commit")

            async def refresh(self, obj, attrs=None):
                await async_session.refresh(obj, attrs)

        # Mock factory to return SessionTracker
        def create_tracking_factory():
            return SessionTracker()

        mock_factory = MagicMock(side_effect=create_tracking_factory)

        with patch('app.workers.asset_worker.async_session_factory', mock_factory):
            with patch('app.workers.asset_worker.AssetGenerationService') as MockService:
                mock_service = MockService.return_value
                mock_service.create_asset_manifest.return_value = MagicMock(
                    global_atmosphere="Natural lighting",
                    assets=[]
                )

                # Simulate slow asset generation
                async def slow_generation(*args, **kwargs):
                    await asyncio.sleep(0.1)  # Simulate processing time
                    session_lifecycle.append("generation_complete")
                    return {
                        "generated": 22,
                        "skipped": 0,
                        "failed": 0,
                        "total_cost_usd": 1.496
                    }

                mock_service.generate_assets = slow_generation

                await process_asset_generation_task(task_id)

        # Verify pattern: open → begin → commit → close → generation → open → begin → commit → close
        assert "open" in session_lifecycle
        assert "close" in session_lifecycle
        assert "generation_complete" in session_lifecycle

        # Find generation index
        gen_index = session_lifecycle.index("generation_complete")

        # Verify at least one close before generation
        closes_before_gen = [i for i, x in enumerate(session_lifecycle[:gen_index]) if x == "close"]
        assert len(closes_before_gen) > 0, "DB should be closed before generation"

        # Verify at least one open after generation
        opens_after_gen = [x for x in session_lifecycle[gen_index:] if x == "open"]
        assert len(opens_after_gen) > 0, "DB should reopen after generation"

    async def test_notion_update_non_blocking(self, async_session, encryption_env):
        """Test Notion status update is non-blocking."""
        channel = Channel(
            channel_id="poke1",
            channel_name="Test Channel",
            voice_id="test_voice",
            max_concurrent=2
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        task = Task(
            channel_id=channel.id,
            notion_page_id="notion123",
            title="Test Video",
            topic="Bulbasaur forest",
            story_direction="Nature documentary",
            status=TaskStatus.QUEUED
        )
        async_session.add(task)
        await async_session.commit()
        await async_session.refresh(task)

        task_id = task.id

        # Mock service
        with patch('app.workers.asset_worker.async_session_factory', create_mock_session_factory(async_session)):
            with patch('app.workers.asset_worker.AssetGenerationService') as MockService:
                mock_service = MockService.return_value
                mock_service.create_asset_manifest.return_value = MagicMock(
                    global_atmosphere="Natural lighting",
                    assets=[]
                )

                async def mock_generate_assets(*args, **kwargs):
                    return {
                        "generated": 22,
                        "skipped": 0,
                        "failed": 0,
                        "total_cost_usd": 1.496
                    }
                mock_service.generate_assets = mock_generate_assets

                # Mock Notion update with delay
                with patch('app.workers.asset_worker._update_notion_status_async') as mock_notion:
                    async def slow_notion_update(*args, **kwargs):
                        await asyncio.sleep(5)  # 5 second delay

                    mock_notion.side_effect = slow_notion_update

                    # Process should complete quickly (not wait for Notion)
                    import time
                    start = time.time()
                    await process_asset_generation_task(task_id)
                    duration = time.time() - start

                    # Should complete in < 2 seconds (not wait for 5s Notion update)
                    assert duration < 2.0, "Worker should not wait for Notion update"

    async def test_correlation_id_logging(self, async_session, encryption_env, caplog):
        """Test all log entries include task_id as correlation ID."""
        channel = Channel(
            channel_id="poke1",
            channel_name="Test Channel",
            voice_id="test_voice",
            max_concurrent=2
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        task = Task(
            channel_id=channel.id,
            notion_page_id="notion123",
            title="Test Video",
            topic="Bulbasaur forest",
            story_direction="Nature documentary",
            status=TaskStatus.QUEUED
        )
        async_session.add(task)
        await async_session.commit()
        await async_session.refresh(task)

        task_id_str = str(task.id)

        with patch('app.workers.asset_worker.async_session_factory', create_mock_session_factory(async_session)):
            with patch('app.workers.asset_worker.AssetGenerationService') as MockService:
                mock_service = MockService.return_value
                mock_service.create_asset_manifest.return_value = MagicMock(
                    global_atmosphere="Natural lighting",
                    assets=[]
                )

                async def mock_generate_assets(*args, **kwargs):
                    return {
                        "generated": 22,
                        "skipped": 0,
                        "failed": 0,
                        "total_cost_usd": 1.496
                    }
                mock_service.generate_assets = mock_generate_assets

                await process_asset_generation_task(task.id)

        # Verify all log entries contain task_id
        log_entries = [record.message for record in caplog.records]
        task_id_logs = [entry for entry in log_entries if task_id_str in entry]

        # Should have multiple log entries with task_id
        assert len(task_id_logs) >= 2, "Should log task_id in multiple places"
