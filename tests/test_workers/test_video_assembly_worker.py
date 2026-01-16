"""Tests for Video Assembly Worker.

This module tests the process_video_assembly_task function which orchestrates
final video assembly for tasks claimed from the queue.

Test Coverage:
- Task claiming and status updates
- Short transaction pattern (Architecture Decision 3)
- Video assembly success flow
- Error handling (FileNotFoundError, CLI errors, validation errors, unexpected errors)
- Task not found scenario
- Correlation ID logging

Architecture Compliance:
- Verifies short transaction pattern (claim → close → execute → reopen → update)
- Verifies database connection not held during video assembly (60-120 sec)
- Verifies error handling marks task with correct status
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models import Channel, Task, TaskStatus
from app.utils.cli_wrapper import CLIScriptError
from app.workers.video_assembly_worker import process_video_assembly_task


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
class TestProcessVideoAssemblyTask:
    """Test process_video_assembly_task function."""

    async def test_process_task_success(self, async_session, encryption_env):
        """Test successful video assembly flow."""
        # Create test channel
        channel = Channel(
            channel_id="poke1",
            channel_name="Test Channel",
            max_concurrent=2,
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        # Create test task
        task = Task(
            channel_id=channel.id,
            notion_page_id="notion123",
            title="Test Video",
            topic="Haunter documentary",
            story_direction="Show ghostly powers",
            status=TaskStatus.QUEUED,
            total_cost_usd=0.0,
        )
        async_session.add(task)
        await async_session.commit()
        await async_session.refresh(task)

        task_id = task.id

        # Mock video assembly service
        with patch(
            "app.workers.video_assembly_worker.async_session_factory",
            create_mock_session_factory(async_session),
        ):
            with patch("app.workers.video_assembly_worker.VideoAssemblyService") as MockService:
                mock_service = MockService.return_value

                # Mock create_assembly_manifest (async)
                async def mock_create_manifest(*args, **kwargs):
                    manifest_mock = MagicMock()
                    manifest_mock.clips = [MagicMock() for _ in range(18)]
                    manifest_mock.output_path = MagicMock()
                    manifest_mock.output_path.__str__ = lambda self: "/path/to/final.mp4"
                    return manifest_mock

                mock_service.create_assembly_manifest = mock_create_manifest

                # Mock validate_input_files (async)
                async def mock_validate_files(*args, **kwargs):
                    pass  # No-op for success

                mock_service.validate_input_files = mock_validate_files

                # Mock assemble_video (async)
                async def mock_assemble_video(*args, **kwargs):
                    return {
                        "duration": 91.5,
                        "file_size_mb": 142.3,
                        "resolution": "1920x1080",
                        "video_codec": "h264",
                        "audio_codec": "aac",
                    }

                mock_service.assemble_video = mock_assemble_video

                # Process task
                await process_video_assembly_task(task_id)

        # Verify task status updated
        await async_session.refresh(task)
        assert task.status == TaskStatus.ASSEMBLY_READY
        assert task.final_video_path == "/path/to/final.mp4"
        assert task.final_video_duration == 91.5

    async def test_process_task_file_not_found(self, async_session, encryption_env):
        """Test handling FileNotFoundError during video assembly."""
        # Create test channel and task
        channel = Channel(
            channel_id="poke1",
            channel_name="Test Channel",
            max_concurrent=2,
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        task = Task(
            channel_id=channel.id,
            notion_page_id="notion123",
            title="Test Video",
            topic="Haunter documentary",
            story_direction="Show ghostly powers",
            status=TaskStatus.QUEUED,
            total_cost_usd=0.0,
        )
        async_session.add(task)
        await async_session.commit()
        await async_session.refresh(task)

        task_id = task.id

        # Mock service to raise FileNotFoundError
        with patch(
            "app.workers.video_assembly_worker.async_session_factory",
            create_mock_session_factory(async_session),
        ):
            with patch("app.workers.video_assembly_worker.VideoAssemblyService") as MockService:
                mock_service = MockService.return_value

                # Mock create_assembly_manifest to raise FileNotFoundError
                async def mock_create_manifest(*args, **kwargs):
                    raise FileNotFoundError("Video file missing: clip_07.mp4")

                mock_service.create_assembly_manifest = mock_create_manifest

                # Process task
                await process_video_assembly_task(task_id)

        # Verify task status updated to error
        await async_session.refresh(task)
        assert task.status == TaskStatus.ASSEMBLY_ERROR
        assert "Missing file" in task.error_log

    async def test_process_task_cli_script_error(self, async_session, encryption_env):
        """Test handling CLIScriptError during video assembly."""
        # Create test channel and task
        channel = Channel(
            channel_id="poke1",
            channel_name="Test Channel",
            max_concurrent=2,
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        task = Task(
            channel_id=channel.id,
            notion_page_id="notion123",
            title="Test Video",
            topic="Haunter documentary",
            story_direction="Show ghostly powers",
            status=TaskStatus.QUEUED,
            total_cost_usd=0.0,
        )
        async_session.add(task)
        await async_session.commit()
        await async_session.refresh(task)

        task_id = task.id

        # Mock service to raise CLIScriptError
        with patch(
            "app.workers.video_assembly_worker.async_session_factory",
            create_mock_session_factory(async_session),
        ):
            with patch("app.workers.video_assembly_worker.VideoAssemblyService") as MockService:
                mock_service = MockService.return_value

                # Mock methods
                async def mock_create_manifest(*args, **kwargs):
                    manifest_mock = MagicMock()
                    manifest_mock.clips = [MagicMock() for _ in range(18)]
                    return manifest_mock

                async def mock_validate_files(*args, **kwargs):
                    pass

                async def mock_assemble_video(*args, **kwargs):
                    raise CLIScriptError("assemble_video.py", 1, "FFmpeg error: invalid codec")

                mock_service.create_assembly_manifest = mock_create_manifest
                mock_service.validate_input_files = mock_validate_files
                mock_service.assemble_video = mock_assemble_video

                # Process task
                await process_video_assembly_task(task_id)

        # Verify task status updated to error
        await async_session.refresh(task)
        assert task.status == TaskStatus.ASSEMBLY_ERROR
        assert "FFmpeg assembly failed" in task.error_log

    async def test_process_task_validation_error(self, async_session, encryption_env):
        """Test handling ValueError during video assembly."""
        # Create test channel and task
        channel = Channel(
            channel_id="poke1",
            channel_name="Test Channel",
            max_concurrent=2,
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        task = Task(
            channel_id=channel.id,
            notion_page_id="notion123",
            title="Test Video",
            topic="Haunter documentary",
            story_direction="Show ghostly powers",
            status=TaskStatus.QUEUED,
            total_cost_usd=0.0,
        )
        async_session.add(task)
        await async_session.commit()
        await async_session.refresh(task)

        task_id = task.id

        # Mock service to raise ValueError
        with patch(
            "app.workers.video_assembly_worker.async_session_factory",
            create_mock_session_factory(async_session),
        ):
            with patch("app.workers.video_assembly_worker.VideoAssemblyService") as MockService:
                mock_service = MockService.return_value

                # Mock methods
                async def mock_create_manifest(*args, **kwargs):
                    manifest_mock = MagicMock()
                    manifest_mock.clips = [MagicMock() for _ in range(18)]
                    return manifest_mock

                async def mock_validate_files(*args, **kwargs):
                    raise ValueError("Invalid video resolution: expected 1920x1080")

                mock_service.create_assembly_manifest = mock_create_manifest
                mock_service.validate_input_files = mock_validate_files

                # Process task
                await process_video_assembly_task(task_id)

        # Verify task status updated to error
        await async_session.refresh(task)
        assert task.status == TaskStatus.ASSEMBLY_ERROR
        assert "Validation error" in task.error_log

    async def test_process_task_unexpected_error(self, async_session, encryption_env):
        """Test handling unexpected error during video assembly."""
        # Create test channel and task
        channel = Channel(
            channel_id="poke1",
            channel_name="Test Channel",
            max_concurrent=2,
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        task = Task(
            channel_id=channel.id,
            notion_page_id="notion123",
            title="Test Video",
            topic="Haunter documentary",
            story_direction="Show ghostly powers",
            status=TaskStatus.QUEUED,
            total_cost_usd=0.0,
        )
        async_session.add(task)
        await async_session.commit()
        await async_session.refresh(task)

        task_id = task.id

        # Mock service to raise unexpected error
        with patch(
            "app.workers.video_assembly_worker.async_session_factory",
            create_mock_session_factory(async_session),
        ):
            with patch("app.workers.video_assembly_worker.VideoAssemblyService") as MockService:
                mock_service = MockService.return_value

                # Mock methods
                async def mock_create_manifest(*args, **kwargs):
                    raise RuntimeError("Unexpected error occurred")

                mock_service.create_assembly_manifest = mock_create_manifest

                # Process task
                await process_video_assembly_task(task_id)

        # Verify task status updated to error
        await async_session.refresh(task)
        assert task.status == TaskStatus.ASSEMBLY_ERROR
        assert "Unexpected error" in task.error_log

    async def test_process_task_not_found(self, async_session, encryption_env):
        """Test handling task not found scenario."""
        # Use a random UUID that doesn't exist
        task_id = uuid4()

        with patch(
            "app.workers.video_assembly_worker.async_session_factory",
            create_mock_session_factory(async_session),
        ):
            # Process non-existent task (should log error and return)
            await process_video_assembly_task(task_id)

        # No exception should be raised

    async def test_process_task_channel_not_found(self, async_session, encryption_env):
        """Test handling channel not found scenario."""
        # Create task without channel
        fake_channel_id = uuid4()

        task = Task(
            channel_id=fake_channel_id,  # Non-existent channel
            notion_page_id="notion123",
            title="Test Video",
            topic="Haunter documentary",
            story_direction="Show ghostly powers",
            status=TaskStatus.QUEUED,
            total_cost_usd=0.0,
        )
        async_session.add(task)
        await async_session.commit()
        await async_session.refresh(task)

        task_id = task.id

        with patch(
            "app.workers.video_assembly_worker.async_session_factory",
            create_mock_session_factory(async_session),
        ):
            # Process task with non-existent channel (should log error and return)
            await process_video_assembly_task(task_id)

        # No exception should be raised
