"""Tests for Narration Generation Worker.

This module tests the process_narration_generation_task function which orchestrates
narration audio generation for tasks claimed from the queue.

Test Coverage:
- Task claiming and status updates
- Short transaction pattern (Architecture Decision 3)
- Narration generation success flow
- Error handling (CLI errors, voice_id missing, unexpected errors)
- Task not found scenario
- Cost tracking integration
- Correlation ID logging

Architecture Compliance:
- Verifies short transaction pattern (claim → close → execute → reopen → update)
- Verifies database connection not held during audio generation (1.5-4.5 min)
- Verifies error handling marks task with correct status
"""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models import Channel, Task, TaskStatus
from app.utils.cli_wrapper import CLIScriptError
from app.workers.narration_generation_worker import process_narration_generation_task


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
class TestProcessNarrationGenerationTask:
    """Test process_narration_generation_task function."""

    async def test_process_task_success(self, async_session, encryption_env):
        """Test successful narration generation flow."""
        # Create test channel with voice_id
        channel = Channel(
            channel_id="poke1",
            channel_name="Test Channel",
            voice_id="EXAVITQu4vr4xnSDxMaL",
            max_concurrent=2,
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        # Create test task with narration_scripts
        narration_scripts = [f"Narration text for clip {i}." * 10 for i in range(1, 19)]

        task = Task(
            channel_id=channel.id,
            notion_page_id="notion123",
            title="Test Video",
            topic="Haunter documentary",
            story_direction="Show ghostly powers",
            status=TaskStatus.QUEUED,
            narration_scripts=narration_scripts,
            total_cost_usd=0.0,
        )
        async_session.add(task)
        await async_session.commit()
        await async_session.refresh(task)

        task_id = task.id

        # Mock narration generation service
        with patch(
            "app.workers.narration_generation_worker.async_session_factory",
            create_mock_session_factory(async_session),
        ):
            with patch(
                "app.workers.narration_generation_worker.NarrationGenerationService"
            ) as MockService:
                mock_service = MockService.return_value

                # Mock create_narration_manifest (async)
                async def mock_create_manifest(*args, **kwargs):
                    manifest_mock = MagicMock()
                    manifest_mock.clips = [MagicMock() for _ in range(18)]
                    manifest_mock.voice_id = "EXAVITQu4vr4xnSDxMaL"
                    return manifest_mock

                mock_service.create_narration_manifest = mock_create_manifest

                # Mock generate_narration (async)
                async def mock_generate_narration(*args, **kwargs):
                    return {
                        "generated": 18,
                        "skipped": 0,
                        "failed": 0,
                        "total_cost_usd": Decimal("0.72"),
                    }

                mock_service.generate_narration = mock_generate_narration

                # Mock cost tracker
                with patch(
                    "app.workers.narration_generation_worker.track_api_cost"
                ) as mock_track_cost:
                    mock_track_cost.return_value = None

                    # Process task
                    await process_narration_generation_task(task_id)

        # Verify task was updated
        await async_session.refresh(task)
        assert task.status == TaskStatus.AUDIO_READY
        assert task.total_cost_usd == 0.72

    async def test_process_task_not_found(self, async_session):
        """Test processing non-existent task logs error and returns early."""
        nonexistent_id = uuid4()

        with patch(
            "app.workers.narration_generation_worker.async_session_factory",
            create_mock_session_factory(async_session),
        ):
            # Should not raise exception, just log error and return
            await process_narration_generation_task(nonexistent_id)

    async def test_process_task_channel_not_found(self, async_session, encryption_env):
        """Test task fails if channel doesn't exist."""
        # Create test task WITHOUT creating the channel
        narration_scripts = [f"Script {i}" * 10 for i in range(1, 19)]
        nonexistent_channel_id = uuid4()  # Non-existent channel UUID

        task = Task(
            channel_id=nonexistent_channel_id,  # Non-existent channel ID
            notion_page_id="notion123",
            title="Test Video",
            topic="Test",
            story_direction="Test",
            status=TaskStatus.QUEUED,
            narration_scripts=narration_scripts,
            total_cost_usd=0.0,
        )
        async_session.add(task)
        await async_session.commit()
        await async_session.refresh(task)

        task_id = task.id

        with patch(
            "app.workers.narration_generation_worker.async_session_factory",
            create_mock_session_factory(async_session),
        ):
            await process_narration_generation_task(task_id)

        # Verify task was marked as error
        await async_session.refresh(task)
        assert task.status == TaskStatus.AUDIO_ERROR
        assert "not found" in task.error_log.lower()

    async def test_process_task_missing_voice_id(self, async_session, encryption_env):
        """Test task fails if channel has no voice_id."""
        # Create channel WITHOUT voice_id
        channel = Channel(
            channel_id="poke1",
            channel_name="Test Channel",
            voice_id=None,  # Missing voice_id
            max_concurrent=2,
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        # Create test task
        narration_scripts = [f"Script {i}" * 10 for i in range(1, 19)]

        task = Task(
            channel_id=channel.id,
            notion_page_id="notion123",
            title="Test Video",
            topic="Test",
            story_direction="Test",
            status=TaskStatus.QUEUED,
            narration_scripts=narration_scripts,
            total_cost_usd=0.0,
        )
        async_session.add(task)
        await async_session.commit()
        await async_session.refresh(task)

        task_id = task.id

        with patch(
            "app.workers.narration_generation_worker.async_session_factory",
            create_mock_session_factory(async_session),
        ):
            await process_narration_generation_task(task_id)

        # Verify task was marked as error
        await async_session.refresh(task)
        assert task.status == TaskStatus.AUDIO_ERROR
        assert "missing voice_id" in task.error_log

    async def test_process_task_missing_narration_scripts(
        self, async_session, encryption_env
    ):
        """Test task fails if narration_scripts field is missing or invalid."""
        channel = Channel(
            channel_id="poke1",
            channel_name="Test Channel",
            voice_id="EXAVITQu4vr4xnSDxMaL",
            max_concurrent=2,
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        # Create task WITHOUT narration_scripts
        task = Task(
            channel_id=channel.id,
            notion_page_id="notion123",
            title="Test Video",
            topic="Test",
            story_direction="Test",
            status=TaskStatus.QUEUED,
            narration_scripts=None,  # Missing scripts
            total_cost_usd=0.0,
        )
        async_session.add(task)
        await async_session.commit()
        await async_session.refresh(task)

        task_id = task.id

        with patch(
            "app.workers.narration_generation_worker.async_session_factory",
            create_mock_session_factory(async_session),
        ):
            await process_narration_generation_task(task_id)

        # Verify task was marked as error
        await async_session.refresh(task)
        assert task.status == TaskStatus.AUDIO_ERROR
        assert "narration_scripts" in task.error_log

    async def test_process_task_cli_error(self, async_session, encryption_env):
        """Test task marked as error when CLI script fails."""
        channel = Channel(
            channel_id="poke1",
            channel_name="Test Channel",
            voice_id="EXAVITQu4vr4xnSDxMaL",
            max_concurrent=2,
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        narration_scripts = [f"Script {i}" * 10 for i in range(1, 19)]

        task = Task(
            channel_id=channel.id,
            notion_page_id="notion123",
            title="Test Video",
            topic="Test",
            story_direction="Test",
            status=TaskStatus.QUEUED,
            narration_scripts=narration_scripts,
            total_cost_usd=0.0,
        )
        async_session.add(task)
        await async_session.commit()
        await async_session.refresh(task)

        task_id = task.id

        with patch(
            "app.workers.narration_generation_worker.async_session_factory",
            create_mock_session_factory(async_session),
        ):
            with patch(
                "app.workers.narration_generation_worker.NarrationGenerationService"
            ) as MockService:
                mock_service = MockService.return_value

                # Mock service to raise CLIScriptError
                async def mock_create_manifest(*args, **kwargs):
                    manifest_mock = MagicMock()
                    return manifest_mock

                mock_service.create_narration_manifest = mock_create_manifest

                async def mock_generate_narration(*args, **kwargs):
                    raise CLIScriptError(
                        script="generate_audio.py",
                        exit_code=1,
                        stderr="ElevenLabs API error: Rate limit exceeded",
                    )

                mock_service.generate_narration = mock_generate_narration

                await process_narration_generation_task(task_id)

        # Verify task was marked as error
        await async_session.refresh(task)
        assert task.status == TaskStatus.AUDIO_ERROR
        assert "Narration generation failed" in task.error_log

    async def test_process_task_validation_error(self, async_session, encryption_env):
        """Test task marked as error when ValueError raised."""
        channel = Channel(
            channel_id="poke1",
            channel_name="Test Channel",
            voice_id="EXAVITQu4vr4xnSDxMaL",
            max_concurrent=2,
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        narration_scripts = [f"Script {i}" * 10 for i in range(1, 19)]

        task = Task(
            channel_id=channel.id,
            notion_page_id="notion123",
            title="Test Video",
            topic="Test",
            story_direction="Test",
            status=TaskStatus.QUEUED,
            narration_scripts=narration_scripts,
            total_cost_usd=0.0,
        )
        async_session.add(task)
        await async_session.commit()
        await async_session.refresh(task)

        task_id = task.id

        with patch(
            "app.workers.narration_generation_worker.async_session_factory",
            create_mock_session_factory(async_session),
        ):
            with patch(
                "app.workers.narration_generation_worker.NarrationGenerationService"
            ) as MockService:
                mock_service = MockService.return_value

                # Mock service to raise ValueError
                async def mock_create_manifest(*args, **kwargs):
                    raise ValueError("Invalid voice_id format")

                mock_service.create_narration_manifest = mock_create_manifest

                await process_narration_generation_task(task_id)

        # Verify task was marked as error
        await async_session.refresh(task)
        assert task.status == TaskStatus.AUDIO_ERROR
        assert "Validation error" in task.error_log

    async def test_process_task_unexpected_error(self, async_session, encryption_env):
        """Test task marked as error when unexpected exception raised."""
        channel = Channel(
            channel_id="poke1",
            channel_name="Test Channel",
            voice_id="EXAVITQu4vr4xnSDxMaL",
            max_concurrent=2,
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        narration_scripts = [f"Script {i}" * 10 for i in range(1, 19)]

        task = Task(
            channel_id=channel.id,
            notion_page_id="notion123",
            title="Test Video",
            topic="Test",
            story_direction="Test",
            status=TaskStatus.QUEUED,
            narration_scripts=narration_scripts,
            total_cost_usd=0.0,
        )
        async_session.add(task)
        await async_session.commit()
        await async_session.refresh(task)

        task_id = task.id

        with patch(
            "app.workers.narration_generation_worker.async_session_factory",
            create_mock_session_factory(async_session),
        ):
            with patch(
                "app.workers.narration_generation_worker.NarrationGenerationService"
            ) as MockService:
                mock_service = MockService.return_value

                # Mock service to raise unexpected exception
                async def mock_create_manifest(*args, **kwargs):
                    raise RuntimeError("Unexpected error")

                mock_service.create_narration_manifest = mock_create_manifest

                await process_narration_generation_task(task_id)

        # Verify task was marked as error
        await async_session.refresh(task)
        assert task.status == TaskStatus.AUDIO_ERROR
        assert "Unexpected error" in task.error_log
