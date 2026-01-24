"""Tests for checkpoint integration in PipelineOrchestrator (Story 6.3, Task 10).

Tests verify:
- is_step_complete() called before executing each step
- Steps skipped when checkpoint exists
- save_step_checkpoint() called after successful step completion
- Checkpoint data properly formatted and saved
- Integration with service-level checkpointing (resume parameter)
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch, call
from uuid import uuid4

from app.models import Channel, Task, TaskStatus
from app.services.pipeline_orchestrator import (
    PipelineOrchestrator,
    PipelineStep,
    StepCompletion,
)


def create_mock_session_factory(async_session):
    """Helper to create async_session_factory mock."""
    # Create async context manager mock
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = async_session
    mock_cm.__aexit__.return_value = None

    # Create factory that returns the context manager
    mock_factory = Mock(return_value=mock_cm)
    return mock_factory


@pytest.mark.asyncio
async def test_pipeline_checks_step_checkpoint_before_execution(async_session):
    """Verify is_step_complete() called before executing each step (Subtask 10.1)."""
    # Create test data
    channel = Channel(channel_id="test_ch", channel_name="Test Channel", is_active=True)
    async_session.add(channel)
    await async_session.flush()

    task = Task(
        id=uuid4(),
        channel_id=channel.id,
        notion_page_id="notion123",
        title="Test Video",
        topic="Testing",
        story_direction="Test story",
        status=TaskStatus.QUEUED,
    )
    async_session.add(task)
    await async_session.commit()

    orchestrator = PipelineOrchestrator(task_id=str(task.id))

    # Setup mocks
    with patch.object(orchestrator, "_load_task_data", new_callable=AsyncMock) as mock_load:
        mock_load.return_value = {
            "channel_id": "test_ch",
            "project_id": str(task.id),
            "topic": "Testing",
            "story_direction": "Test story",
        }

        with patch(
            "app.services.pipeline_orchestrator.async_session_factory",
            create_mock_session_factory(async_session),
        ):
            with patch(
                "app.services.pipeline_orchestrator.is_step_complete", new_callable=AsyncMock
            ) as mock_check:
                mock_check.return_value = False

                with patch.object(
                    orchestrator, "execute_step", new_callable=AsyncMock
                ) as mock_step:
                    mock_step.return_value = StepCompletion(
                        step=PipelineStep.ASSET_GENERATION, completed=True, duration_seconds=10.0
                    )

                    with patch(
                        "app.services.pipeline_orchestrator.save_step_checkpoint",
                        new_callable=AsyncMock,
                    ):
                        with patch.object(
                            orchestrator, "update_task_status", new_callable=AsyncMock
                        ):
                            with patch.object(
                                orchestrator, "_update_pipeline_start_time", new_callable=AsyncMock
                            ):
                                await orchestrator.execute_pipeline()

                # Verify is_step_complete was called
                assert mock_check.called
                call_args = mock_check.call_args_list[0]
                assert call_args[0][0] == str(task.id)
                assert call_args[0][1] == PipelineStep.ASSET_GENERATION.value


@pytest.mark.asyncio
async def test_pipeline_skips_step_when_checkpoint_exists(async_session):
    """Verify step skipped when checkpoint exists (Subtask 10.2)."""
    channel = Channel(channel_id="test_ch", channel_name="Test Channel", is_active=True)
    async_session.add(channel)
    await async_session.flush()

    task = Task(
        id=uuid4(),
        channel_id=channel.id,
        notion_page_id="notion123",
        title="Test Video",
        topic="Testing",
        story_direction="Test story",
        status=TaskStatus.QUEUED,
    )
    async_session.add(task)
    await async_session.commit()

    orchestrator = PipelineOrchestrator(task_id=str(task.id))

    with patch.object(orchestrator, "_load_task_data", new_callable=AsyncMock) as mock_load:
        mock_load.return_value = {
            "channel_id": "test_ch",
            "project_id": str(task.id),
            "topic": "Testing",
            "story_direction": "Test story",
        }

        with patch(
            "app.services.pipeline_orchestrator.async_session_factory",
            create_mock_session_factory(async_session),
        ):
            with patch(
                "app.services.pipeline_orchestrator.is_step_complete", new_callable=AsyncMock
            ) as mock_check:
                # First call (asset) returns True (skip), second (composite) returns False (execute)
                mock_check.side_effect = [True, False]

                with patch.object(
                    orchestrator, "execute_step", new_callable=AsyncMock
                ) as mock_step:
                    mock_step.return_value = StepCompletion(
                        step=PipelineStep.COMPOSITE_CREATION, completed=True, duration_seconds=5.0
                    )

                    with patch(
                        "app.services.pipeline_orchestrator.save_step_checkpoint",
                        new_callable=AsyncMock,
                    ):
                        with patch.object(
                            orchestrator, "update_task_status", new_callable=AsyncMock
                        ):
                            with patch.object(
                                orchestrator, "_update_pipeline_start_time", new_callable=AsyncMock
                            ):
                                await orchestrator.execute_pipeline()

                # Verify asset generation was skipped (only composite executed)
                assert mock_step.call_count == 1
                assert mock_step.call_args[0][0] == PipelineStep.COMPOSITE_CREATION


@pytest.mark.asyncio
async def test_pipeline_saves_checkpoint_after_successful_step(async_session):
    """Verify save_step_checkpoint() called after successful step (Subtask 10.3)."""
    channel = Channel(channel_id="test_ch", channel_name="Test Channel", is_active=True)
    async_session.add(channel)
    await async_session.flush()

    task = Task(
        id=uuid4(),
        channel_id=channel.id,
        notion_page_id="notion123",
        title="Test Video",
        topic="Testing",
        story_direction="Test story",
        status=TaskStatus.QUEUED,
    )
    async_session.add(task)
    await async_session.commit()

    orchestrator = PipelineOrchestrator(task_id=str(task.id))

    with patch.object(orchestrator, "_load_task_data", new_callable=AsyncMock) as mock_load:
        mock_load.return_value = {
            "channel_id": "test_ch",
            "project_id": str(task.id),
            "topic": "Testing",
            "story_direction": "Test story",
        }

        with patch(
            "app.services.pipeline_orchestrator.async_session_factory",
            create_mock_session_factory(async_session),
        ):
            with patch(
                "app.services.pipeline_orchestrator.is_step_complete", new_callable=AsyncMock
            ) as mock_check:
                mock_check.return_value = False

                with patch.object(
                    orchestrator, "execute_step", new_callable=AsyncMock
                ) as mock_step:
                    mock_step.return_value = StepCompletion(
                        step=PipelineStep.ASSET_GENERATION,
                        completed=True,
                        duration_seconds=120.5,
                        partial_progress={"generated": 22, "skipped": 0, "total": 22},
                    )

                    with patch(
                        "app.services.pipeline_orchestrator.save_step_checkpoint",
                        new_callable=AsyncMock,
                    ) as mock_save:
                        with patch.object(
                            orchestrator, "update_task_status", new_callable=AsyncMock
                        ):
                            with patch.object(
                                orchestrator, "_update_pipeline_start_time", new_callable=AsyncMock
                            ):
                                await orchestrator.execute_pipeline()

                # Verify save_step_checkpoint was called with correct data
                assert mock_save.called
                call_args = mock_save.call_args
                assert call_args[0][0] == str(task.id)
                assert call_args[0][1] == PipelineStep.ASSET_GENERATION.value
                checkpoint_data = call_args[0][2]
                assert checkpoint_data["completed"] is True
                assert checkpoint_data["duration_seconds"] == 120.5
                assert checkpoint_data["partial_progress"]["generated"] == 22


@pytest.mark.asyncio
async def test_checkpoint_data_properly_formatted(async_session):
    """Verify checkpoint data includes all required fields (Subtask 10.4)."""
    channel = Channel(channel_id="test_ch", channel_name="Test Channel", is_active=True)
    async_session.add(channel)
    await async_session.flush()

    task = Task(
        id=uuid4(),
        channel_id=channel.id,
        notion_page_id="notion123",
        title="Test Video",
        topic="Testing",
        story_direction="Test story",
        status=TaskStatus.QUEUED,
    )
    async_session.add(task)
    await async_session.commit()

    orchestrator = PipelineOrchestrator(task_id=str(task.id))

    with patch.object(orchestrator, "_load_task_data", new_callable=AsyncMock) as mock_load:
        mock_load.return_value = {
            "channel_id": "test_ch",
            "project_id": str(task.id),
            "topic": "Testing",
            "story_direction": "Test story",
        }

        with patch(
            "app.services.pipeline_orchestrator.async_session_factory",
            create_mock_session_factory(async_session),
        ):
            with patch(
                "app.services.pipeline_orchestrator.is_step_complete", new_callable=AsyncMock
            ) as mock_check:
                mock_check.return_value = False

                with patch.object(
                    orchestrator, "execute_step", new_callable=AsyncMock
                ) as mock_step:
                    mock_step.return_value = StepCompletion(
                        step=PipelineStep.VIDEO_GENERATION,
                        completed=True,
                        duration_seconds=300.5,
                        partial_progress={"generated": 16, "skipped": 2, "total": 18},
                    )

                    with patch(
                        "app.services.pipeline_orchestrator.save_step_checkpoint",
                        new_callable=AsyncMock,
                    ) as mock_save:
                        with patch.object(
                            orchestrator, "update_task_status", new_callable=AsyncMock
                        ):
                            with patch.object(
                                orchestrator, "_update_pipeline_start_time", new_callable=AsyncMock
                            ):
                                await orchestrator.execute_pipeline()

                # Verify checkpoint data structure
                checkpoint_data = mock_save.call_args[0][2]
                assert "completed" in checkpoint_data
                assert "duration_seconds" in checkpoint_data
                assert "partial_progress" in checkpoint_data
                assert isinstance(checkpoint_data["completed"], bool)
                assert isinstance(checkpoint_data["duration_seconds"], int | float)
                assert isinstance(checkpoint_data["partial_progress"], dict)
                assert checkpoint_data["partial_progress"]["generated"] == 16


@pytest.mark.asyncio
async def test_checkpoint_not_saved_on_step_failure(async_session):
    """Verify checkpoint NOT saved when step fails (Subtask 10.5)."""
    channel = Channel(channel_id="test_ch", channel_name="Test Channel", is_active=True)
    async_session.add(channel)
    await async_session.flush()

    task = Task(
        id=uuid4(),
        channel_id=channel.id,
        notion_page_id="notion123",
        title="Test Video",
        topic="Testing",
        story_direction="Test story",
        status=TaskStatus.QUEUED,
    )
    async_session.add(task)
    await async_session.commit()

    orchestrator = PipelineOrchestrator(task_id=str(task.id))

    with patch.object(orchestrator, "_load_task_data", new_callable=AsyncMock) as mock_load:
        mock_load.return_value = {
            "channel_id": "test_ch",
            "project_id": str(task.id),
            "topic": "Testing",
            "story_direction": "Test story",
        }

        with patch(
            "app.services.pipeline_orchestrator.async_session_factory",
            create_mock_session_factory(async_session),
        ):
            with patch(
                "app.services.pipeline_orchestrator.is_step_complete", new_callable=AsyncMock
            ) as mock_check:
                mock_check.return_value = False

                with patch.object(
                    orchestrator, "execute_step", new_callable=AsyncMock
                ) as mock_step:
                    mock_step.side_effect = Exception("Gemini API timeout")

                    with patch(
                        "app.services.pipeline_orchestrator.save_step_checkpoint",
                        new_callable=AsyncMock,
                    ) as mock_save:
                        with patch.object(
                            orchestrator, "update_task_status", new_callable=AsyncMock
                        ):
                            with patch.object(
                                orchestrator, "_update_pipeline_start_time", new_callable=AsyncMock
                            ):
                                await orchestrator.execute_pipeline()

                # Verify save_step_checkpoint was NOT called (step failed)
                assert not mock_save.called


@pytest.mark.asyncio
async def test_multiple_steps_checkpoint_correctly(async_session):
    """Verify multiple steps can be checkpointed in sequence (Subtask 10.6)."""
    channel = Channel(channel_id="test_ch", channel_name="Test Channel", is_active=True)
    async_session.add(channel)
    await async_session.flush()

    task = Task(
        id=uuid4(),
        channel_id=channel.id,
        notion_page_id="notion123",
        title="Test Video",
        topic="Testing",
        story_direction="Test story",
        status=TaskStatus.QUEUED,
    )
    async_session.add(task)
    await async_session.commit()

    orchestrator = PipelineOrchestrator(task_id=str(task.id))

    with patch.object(orchestrator, "_load_task_data", new_callable=AsyncMock) as mock_load:
        mock_load.return_value = {
            "channel_id": "test_ch",
            "project_id": str(task.id),
            "topic": "Testing",
            "story_direction": "Test story",
        }

        with patch(
            "app.services.pipeline_orchestrator.async_session_factory",
            create_mock_session_factory(async_session),
        ):
            with patch(
                "app.services.pipeline_orchestrator.is_step_complete", new_callable=AsyncMock
            ) as mock_check:
                # Assets complete (skip), composite and video not complete (execute)
                mock_check.side_effect = [True, False, False]

                step_results = [
                    StepCompletion(
                        step=PipelineStep.COMPOSITE_CREATION, completed=True, duration_seconds=5.0
                    ),
                    StepCompletion(
                        step=PipelineStep.VIDEO_GENERATION, completed=True, duration_seconds=300.0
                    ),
                ]

                with patch.object(
                    orchestrator, "execute_step", new_callable=AsyncMock
                ) as mock_step:
                    mock_step.side_effect = step_results

                    with patch(
                        "app.services.pipeline_orchestrator.save_step_checkpoint",
                        new_callable=AsyncMock,
                    ) as mock_save:
                        with patch.object(
                            orchestrator, "update_task_status", new_callable=AsyncMock
                        ):
                            with patch.object(
                                orchestrator, "_update_pipeline_start_time", new_callable=AsyncMock
                            ):
                                await orchestrator.execute_pipeline()

                # Verify two checkpoints saved (composite + video)
                assert mock_save.call_count == 2
                assert mock_save.call_args_list[0][0][1] == PipelineStep.COMPOSITE_CREATION.value
                assert mock_save.call_args_list[1][0][1] == PipelineStep.VIDEO_GENERATION.value


@pytest.mark.asyncio
async def test_checkpoint_skip_logging(async_session):
    """Verify step skip is logged when checkpoint exists (Subtask 10.7)."""
    channel = Channel(channel_id="test_ch", channel_name="Test Channel", is_active=True)
    async_session.add(channel)
    await async_session.flush()

    task = Task(
        id=uuid4(),
        channel_id=channel.id,
        notion_page_id="notion123",
        title="Test Video",
        topic="Testing",
        story_direction="Test story",
        status=TaskStatus.QUEUED,
    )
    async_session.add(task)
    await async_session.commit()

    orchestrator = PipelineOrchestrator(task_id=str(task.id))

    with patch.object(orchestrator, "_load_task_data", new_callable=AsyncMock) as mock_load:
        mock_load.return_value = {
            "channel_id": "test_ch",
            "project_id": str(task.id),
            "topic": "Testing",
            "story_direction": "Test story",
        }

        with patch(
            "app.services.pipeline_orchestrator.async_session_factory",
            create_mock_session_factory(async_session),
        ):
            with patch(
                "app.services.pipeline_orchestrator.is_step_complete", new_callable=AsyncMock
            ) as mock_check:
                # Assets complete (skip), composite not complete (execute)
                mock_check.side_effect = [True, False]

                with patch.object(
                    orchestrator, "execute_step", new_callable=AsyncMock
                ) as mock_step:
                    mock_step.return_value = StepCompletion(
                        step=PipelineStep.COMPOSITE_CREATION, completed=True, duration_seconds=5.0
                    )

                    with patch(
                        "app.services.pipeline_orchestrator.save_step_checkpoint",
                        new_callable=AsyncMock,
                    ):
                        with patch.object(
                            orchestrator, "update_task_status", new_callable=AsyncMock
                        ):
                            with patch.object(
                                orchestrator, "_update_pipeline_start_time", new_callable=AsyncMock
                            ):
                                with patch.object(orchestrator.log, "info") as mock_log:
                                    await orchestrator.execute_pipeline()

                                    # Verify step skip was logged
                                    skip_logs = [
                                        call
                                        for call in mock_log.call_args_list
                                        if len(call[0]) > 0 and call[0][0] == "step_skipped"
                                    ]
                                    assert len(skip_logs) > 0
                                    assert skip_logs[0][1].get("reason") == "checkpoint_exists"
                                    assert (
                                        skip_logs[0][1].get("step")
                                        == PipelineStep.ASSET_GENERATION.value
                                    )
