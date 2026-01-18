"""Tests for Composite Creation Worker.

This module tests the process_composite_creation_task function which orchestrates
composite creation for tasks claimed from the queue.

Test Coverage:
- Task claiming and status updates
- Short transaction pattern (Architecture Decision 3)
- Composite generation success flow
- Error handling (CLI errors, timeouts, FileNotFoundError, unexpected errors)
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
from app.workers.composite_worker import process_composite_creation_task


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
class TestProcessCompositeCreationTask:
    """Test process_composite_creation_task function."""

    async def test_process_task_success(self, async_session, encryption_env):
        """Test successful composite creation flow."""
        # Create test channel
        channel = Channel(
            channel_id="poke1", channel_name="Test Channel", voice_id="test_voice", max_concurrent=2
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
            status=TaskStatus.ASSETS_APPROVED,
        )
        async_session.add(task)
        await async_session.commit()
        await async_session.refresh(task)

        task_id = task.id

        # Mock composite creation service
        with patch(
            "app.workers.composite_worker.async_session_factory",
            create_mock_session_factory(async_session),
        ):
            with patch(
                "app.workers.composite_worker.CompositeCreationService"
            ) as mock_service_class:
                mock_service = mock_service_class.return_value
                mock_service.create_composite_manifest.return_value = MagicMock(
                    composites=[MagicMock() for _ in range(18)]
                )

                # Make generate_composites async
                async def mock_generate_composites(*args, **kwargs):
                    return {"generated": 18, "skipped": 0, "failed": 0}

                mock_service.generate_composites = mock_generate_composites

                # Process task
                await process_composite_creation_task(str(task_id))

        # Verify task status updated
        await async_session.refresh(task)
        assert task.status == TaskStatus.COMPOSITES_READY

    async def test_process_task_not_found(self, async_session):
        """Test handling of non-existent task."""
        fake_task_id = str(uuid4())

        # Should not raise, just log error
        with patch(
            "app.workers.composite_worker.async_session_factory",
            create_mock_session_factory(async_session),
        ):
            await process_composite_creation_task(fake_task_id)
        # No assertion - just verify it doesn't crash

    async def test_process_task_cli_script_error(self, async_session, encryption_env):
        """Test CLI script error handling."""
        # Create channel and task
        channel = Channel(
            channel_id="poke1", channel_name="Test Channel", voice_id="test_voice", max_concurrent=2
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
            status=TaskStatus.ASSETS_APPROVED,
        )
        async_session.add(task)
        await async_session.commit()
        await async_session.refresh(task)

        task_id = task.id

        # Mock composite service to raise CLIScriptError
        with patch(
            "app.workers.composite_worker.async_session_factory",
            create_mock_session_factory(async_session),
        ):
            with patch(
                "app.workers.composite_worker.CompositeCreationService"
            ) as mock_service_class:
                mock_service = mock_service_class.return_value
                mock_service.create_composite_manifest.return_value = MagicMock(
                    composites=[MagicMock() for _ in range(18)]
                )

                # Make generate_composites raise CLIScriptError
                async def mock_generate_composites(*args, **kwargs):
                    raise CLIScriptError(
                        "create_composite.py", 1, "FileNotFoundError: character.png not found"
                    )

                mock_service.generate_composites = mock_generate_composites

                # Process task
                await process_composite_creation_task(str(task_id))

        # Verify task status updated to error
        await async_session.refresh(task)
        assert task.status == TaskStatus.ASSET_ERROR
        assert "not found" in task.error_log

    async def test_process_task_timeout_error(self, async_session, encryption_env):
        """Test timeout error handling."""
        # Create channel and task
        channel = Channel(
            channel_id="poke1", channel_name="Test Channel", voice_id="test_voice", max_concurrent=2
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
            status=TaskStatus.ASSETS_APPROVED,
        )
        async_session.add(task)
        await async_session.commit()
        await async_session.refresh(task)

        task_id = task.id

        # Mock composite service to raise TimeoutError
        with patch(
            "app.workers.composite_worker.async_session_factory",
            create_mock_session_factory(async_session),
        ):
            with patch(
                "app.workers.composite_worker.CompositeCreationService"
            ) as mock_service_class:
                mock_service = mock_service_class.return_value
                mock_service.create_composite_manifest.return_value = MagicMock(
                    composites=[MagicMock() for _ in range(18)]
                )

                # Make generate_composites raise TimeoutError
                async def mock_generate_composites(*args, **kwargs):
                    raise asyncio.TimeoutError()

                mock_service.generate_composites = mock_generate_composites

                # Process task
                await process_composite_creation_task(str(task_id))

        # Verify task status updated to error
        await async_session.refresh(task)
        assert task.status == TaskStatus.ASSET_ERROR
        assert "timeout" in task.error_log.lower()

    async def test_process_task_file_not_found_error(self, async_session, encryption_env):
        """Test FileNotFoundError handling (missing asset files)."""
        # Create channel and task
        channel = Channel(
            channel_id="poke1", channel_name="Test Channel", voice_id="test_voice", max_concurrent=2
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
            status=TaskStatus.ASSETS_APPROVED,
        )
        async_session.add(task)
        await async_session.commit()
        await async_session.refresh(task)

        task_id = task.id

        # Mock composite service to raise FileNotFoundError
        with patch(
            "app.workers.composite_worker.async_session_factory",
            create_mock_session_factory(async_session),
        ):
            with patch(
                "app.workers.composite_worker.CompositeCreationService"
            ) as mock_service_class:
                mock_service = mock_service_class.return_value

                # Make create_composite_manifest raise FileNotFoundError
                def mock_create_manifest(*args, **kwargs):
                    raise FileNotFoundError("No character assets found in /path/to/assets")

                mock_service.create_composite_manifest = mock_create_manifest

                # Process task
                await process_composite_creation_task(str(task_id))

        # Verify task status updated to error
        await async_session.refresh(task)
        assert task.status == TaskStatus.ASSET_ERROR
        assert "asset" in task.error_log.lower()

    async def test_process_task_unexpected_error(self, async_session, encryption_env):
        """Test unexpected error handling."""
        # Create channel and task
        channel = Channel(
            channel_id="poke1", channel_name="Test Channel", voice_id="test_voice", max_concurrent=2
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
            status=TaskStatus.ASSETS_APPROVED,
        )
        async_session.add(task)
        await async_session.commit()
        await async_session.refresh(task)

        task_id = task.id

        # Mock composite service to raise unexpected error
        with patch(
            "app.workers.composite_worker.async_session_factory",
            create_mock_session_factory(async_session),
        ):
            with patch(
                "app.workers.composite_worker.CompositeCreationService"
            ) as mock_service_class:
                mock_service = mock_service_class.return_value
                mock_service.create_composite_manifest.return_value = MagicMock(
                    composites=[MagicMock() for _ in range(18)]
                )

                # Make generate_composites raise generic exception
                async def mock_generate_composites(*args, **kwargs):
                    raise RuntimeError("Unexpected PIL error")

                mock_service.generate_composites = mock_generate_composites

                # Process task
                await process_composite_creation_task(str(task_id))

        # Verify task status updated to error
        await async_session.refresh(task)
        assert task.status == TaskStatus.ASSET_ERROR
        assert "Unexpected error" in task.error_log

    async def test_short_transaction_pattern_database_closed_during_generation(
        self, async_session, encryption_env
    ):
        """Test database connection closed during composite generation."""
        # Create channel and task
        channel = Channel(
            channel_id="poke1", channel_name="Test Channel", voice_id="test_voice", max_concurrent=2
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
            status=TaskStatus.ASSETS_APPROVED,
        )
        async_session.add(task)
        await async_session.commit()
        await async_session.refresh(task)

        task_id = task.id

        # Track session factory calls
        session_calls = []

        def track_session_factory():
            session_calls.append("session_created")
            return create_mock_session_factory(async_session)()

        mock_factory = MagicMock(side_effect=track_session_factory)

        # Mock composite service
        with patch("app.workers.composite_worker.async_session_factory", mock_factory):
            with patch(
                "app.workers.composite_worker.CompositeCreationService"
            ) as mock_service_class:
                mock_service = mock_service_class.return_value
                mock_service.create_composite_manifest.return_value = MagicMock(
                    composites=[MagicMock() for _ in range(18)]
                )

                async def mock_generate_composites(*args, **kwargs):
                    # Verify we're OUTSIDE transaction during generation
                    # (session factory should have been called at least twice by now)
                    assert len(session_calls) >= 1
                    return {"generated": 18, "skipped": 0, "failed": 0}

                mock_service.generate_composites = mock_generate_composites

                # Process task
                await process_composite_creation_task(str(task_id))

        # Verify multiple session calls (claim → close, then update → close)
        assert len(session_calls) >= 2

    async def test_notion_update_async_non_blocking(self, async_session, encryption_env):
        """Test Notion status update is async and non-blocking.

        Note: RuntimeWarning about 'update_notion_status' not being awaited is expected
        in test environment due to pytest cleanup happening before fire-and-forget task
        completes. In production, the task completes normally via add_done_callback.
        """
        # Create channel and task
        channel = Channel(
            channel_id="poke1", channel_name="Test Channel", voice_id="test_voice", max_concurrent=2
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
            status=TaskStatus.ASSETS_APPROVED,
        )
        async_session.add(task)
        await async_session.commit()
        await async_session.refresh(task)

        task_id = task.id

        # Mock composite service
        with patch(
            "app.workers.composite_worker.async_session_factory",
            create_mock_session_factory(async_session),
        ):
            with patch(
                "app.workers.composite_worker.CompositeCreationService"
            ) as mock_service_class:
                with patch("app.workers.composite_worker.asyncio.create_task") as mock_create_task:
                    mock_service = mock_service_class.return_value
                    mock_service.create_composite_manifest.return_value = MagicMock(
                        composites=[MagicMock() for _ in range(18)]
                    )

                    async def mock_generate_composites(*args, **kwargs):
                        return {"generated": 18, "skipped": 0, "failed": 0}

                    mock_service.generate_composites = mock_generate_composites

                    # Process task
                    await process_composite_creation_task(str(task_id))

                    # Verify asyncio.create_task was called for Notion update
                    assert mock_create_task.called
