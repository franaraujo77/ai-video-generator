"""Tests for pipeline_orchestrator integration with error_logger (Story 6.5 Task 4).

Tests verify that pipeline step transitions are logged with structured format.
"""

import pytest
from uuid import uuid4
import json
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.pipeline_orchestrator import PipelineOrchestrator, PipelineStep
from app.models import TaskStatus
from tests.support.factories import create_task, create_channel


def create_mock_session_factory(async_session):
    """Create a mock async_session_factory that returns the test session."""
    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__ = AsyncMock(return_value=async_session)
    mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)
    return mock_factory


@pytest.mark.asyncio
async def test_pipeline_logs_step_started_event(async_session, caplog):
    """Verify execute_pipeline() calls log_pipeline_step_started() (AC: Step name in logs)."""
    # Create channel and task
    channel = create_channel(channel_id="poke1")
    task = create_task(channel_id="poke1", status=TaskStatus.QUEUED)
    task.channel_id = channel.id  # Link task to channel
    task.channel = channel  # Set relationship

    async_session.add(channel)
    async_session.add(task)
    await async_session.commit()

    # Mock async_session_factory to return test session
    with patch(
        "app.services.pipeline_orchestrator.async_session_factory",
        create_mock_session_factory(async_session),
    ):
        # Mock the services to avoid actual pipeline execution
        with patch("app.services.pipeline_orchestrator.AssetGenerationService") as mock_service:
            mock_service.return_value.create_asset_manifest.return_value = MagicMock(assets=[])
            mock_service.return_value.generate_assets = AsyncMock(
                return_value={"generated": 0, "skipped": 0}
            )

        # Mock checkpoint service to skip checkpoint check
        with patch("app.services.pipeline_orchestrator.is_step_complete", return_value=False):
            with patch(
                "app.services.pipeline_orchestrator.clear_step_metadata", new_callable=AsyncMock
            ):
                with patch(
                    "app.services.pipeline_orchestrator.save_step_checkpoint",
                    new_callable=AsyncMock,
                ):
                    orchestrator = PipelineOrchestrator(task_id=str(task.id))

                    # Mock _load_task_data and update methods to avoid database interactions
                    with patch.object(
                        orchestrator, "_load_task_data", new_callable=AsyncMock
                    ) as mock_load:
                        mock_load.return_value = {
                            "channel_id": "poke1",
                            "project_id": str(task.id),
                            "topic": "test topic",
                            "story_direction": "test direction",
                            "narration_scripts": [],
                            "sfx_descriptions": [],
                            "voice_id": "test_voice",
                        }

                        with patch.object(
                            orchestrator, "update_task_status", new_callable=AsyncMock
                        ):
                            with patch.object(
                                orchestrator, "_update_pipeline_start_time", new_callable=AsyncMock
                            ):
                                with patch.object(
                                    orchestrator,
                                    "_update_pipeline_end_time",
                                    new_callable=AsyncMock,
                                ):
                                    # Execute just the first step
                                    with caplog.at_level("INFO"):
                                        # Mock execute_step to return immediately after logging
                                        with patch.object(
                                            orchestrator, "execute_step", new_callable=AsyncMock
                                        ) as mock_exec:
                                            from app.services.pipeline_orchestrator import (
                                                StepCompletion,
                                            )

                                            mock_exec.return_value = StepCompletion(
                                                step=PipelineStep.ASSET_GENERATION,
                                                completed=True,
                                                duration_seconds=10.0,
                                            )

                                            # Run pipeline (will halt at first review gate)
                                            await orchestrator.execute_pipeline()

    # Verify log_pipeline_step_started was called
    step_started_logs = [r for r in caplog.records if "pipeline_step_started" in r.getMessage()]
    assert len(step_started_logs) > 0

    # Parse JSON log
    log_data = json.loads(step_started_logs[0].getMessage())

    # Verify structured log fields
    assert log_data["event"] == "pipeline_step_started"
    assert log_data["task_id"] == str(task.id)
    assert log_data["correlation_id"] == str(task.id)
    assert log_data["channel_id"] == "poke1"
    assert "step_name" in log_data
    assert "timestamp" in log_data


@pytest.mark.asyncio
async def test_pipeline_logs_step_completed_event(async_session, caplog):
    """Verify execute_pipeline() calls log_pipeline_step_completed() with duration (AC: Duration tracking)."""
    # Create channel and task
    channel = create_channel(channel_id="poke1")
    task = create_task(channel_id="poke1", status=TaskStatus.QUEUED)
    task.channel_id = channel.id
    task.channel = channel

    async_session.add(channel)
    async_session.add(task)
    await async_session.commit()

    # Mock async_session_factory to return test session
    with patch(
        "app.services.pipeline_orchestrator.async_session_factory",
        create_mock_session_factory(async_session),
    ):
        # Mock services
        with patch("app.services.pipeline_orchestrator.AssetGenerationService") as mock_service:
            mock_service.return_value.create_asset_manifest.return_value = MagicMock(assets=[])
        mock_service.return_value.generate_assets = AsyncMock(
            return_value={"generated": 0, "skipped": 0}
        )

        with patch("app.services.pipeline_orchestrator.is_step_complete", return_value=False):
            with patch(
                "app.services.pipeline_orchestrator.clear_step_metadata", new_callable=AsyncMock
            ):
                with patch(
                    "app.services.pipeline_orchestrator.save_step_checkpoint",
                    new_callable=AsyncMock,
                ):
                    orchestrator = PipelineOrchestrator(task_id=str(task.id))

                    # Mock _load_task_data and update methods
                    with patch.object(
                        orchestrator, "_load_task_data", new_callable=AsyncMock
                    ) as mock_load:
                        mock_load.return_value = {
                            "channel_id": "poke1",
                            "project_id": str(task.id),
                            "topic": "test topic",
                            "story_direction": "test direction",
                            "narration_scripts": [],
                            "sfx_descriptions": [],
                            "voice_id": "test_voice",
                        }

                        with patch.object(
                            orchestrator, "update_task_status", new_callable=AsyncMock
                        ):
                            with patch.object(
                                orchestrator, "_update_pipeline_start_time", new_callable=AsyncMock
                            ):
                                with patch.object(
                                    orchestrator,
                                    "_update_pipeline_end_time",
                                    new_callable=AsyncMock,
                                ):
                                    with caplog.at_level("INFO"):
                                        with patch.object(
                                            orchestrator, "execute_step", new_callable=AsyncMock
                                        ) as mock_exec:
                                            from app.services.pipeline_orchestrator import (
                                                StepCompletion,
                                            )

                                            mock_exec.return_value = StepCompletion(
                                                step=PipelineStep.ASSET_GENERATION,
                                                completed=True,
                                                duration_seconds=10.0,
                                            )

                                            await orchestrator.execute_pipeline()

    # Verify log_pipeline_step_completed was called
    step_completed_logs = [r for r in caplog.records if "pipeline_step_completed" in r.getMessage()]
    assert len(step_completed_logs) > 0

    # Parse JSON log
    log_data = json.loads(step_completed_logs[0].getMessage())

    # Verify structured log fields
    assert log_data["event"] == "pipeline_step_completed"
    assert log_data["task_id"] == str(task.id)
    assert log_data["correlation_id"] == str(task.id)
    assert log_data["channel_id"] == "poke1"
    assert "step_name" in log_data
    assert "duration_seconds" in log_data
    assert log_data["duration_seconds"] >= 0


@pytest.mark.asyncio
async def test_pipeline_logs_structured_error_on_step_failure(async_session, caplog):
    """Verify execute_pipeline() calls log_structured_error() when step fails (AC: Error context)."""
    # Create channel and task
    channel = create_channel(channel_id="poke1")
    task = create_task(channel_id="poke1", status=TaskStatus.QUEUED)
    task.channel_id = channel.id
    task.channel = channel

    async_session.add(channel)
    async_session.add(task)
    await async_session.commit()

    # Mock async_session_factory to return test session
    with patch(
        "app.services.pipeline_orchestrator.async_session_factory",
        create_mock_session_factory(async_session),
    ):
        # Mock services to raise exception
        with patch("app.services.pipeline_orchestrator.AssetGenerationService") as mock_service:
            mock_service.return_value.create_asset_manifest.return_value = MagicMock(assets=[])
            mock_service.return_value.generate_assets = AsyncMock(
                side_effect=TimeoutError("Gemini timeout")
            )

        with patch("app.services.pipeline_orchestrator.is_step_complete", return_value=False):
            with patch(
                "app.services.pipeline_orchestrator.clear_step_metadata", new_callable=AsyncMock
            ):
                with patch(
                    "app.services.pipeline_orchestrator.save_step_checkpoint",
                    new_callable=AsyncMock,
                ):
                    with patch(
                        "app.services.pipeline_orchestrator.schedule_retry", new_callable=AsyncMock
                    ):
                        orchestrator = PipelineOrchestrator(task_id=str(task.id))

                        # Mock _load_task_data and update methods
                        with patch.object(
                            orchestrator, "_load_task_data", new_callable=AsyncMock
                        ) as mock_load:
                            mock_load.return_value = {
                                "channel_id": "poke1",
                                "project_id": str(task.id),
                                "topic": "test topic",
                                "story_direction": "test direction",
                                "narration_scripts": [],
                                "sfx_descriptions": [],
                                "voice_id": "test_voice",
                            }

                            with patch.object(
                                orchestrator, "update_task_status", new_callable=AsyncMock
                            ):
                                with patch.object(
                                    orchestrator,
                                    "_update_pipeline_start_time",
                                    new_callable=AsyncMock,
                                ):
                                    with patch.object(
                                        orchestrator,
                                        "_update_pipeline_end_time",
                                        new_callable=AsyncMock,
                                    ):
                                        with caplog.at_level("ERROR"):
                                            await orchestrator.execute_pipeline()

    # Verify log_structured_error was called (pipeline_step_failed event)
    error_logs = [r for r in caplog.records if "pipeline_step_failed" in r.getMessage()]
    assert len(error_logs) > 0

    # Parse JSON log
    log_data = json.loads(error_logs[0].getMessage())

    # Verify structured error log fields
    assert log_data["event"] == "pipeline_step_failed"
    assert log_data["task_id"] == str(task.id)
    assert log_data["correlation_id"] == str(task.id)
    assert "step_name" in log_data
    assert "error_type" in log_data
    assert "error_message" in log_data
    assert "retry_attempt" in log_data


@pytest.mark.asyncio
async def test_correlation_id_propagates_through_pipeline_logs(async_session, caplog):
    """Verify correlation_id (task.id) is in all pipeline logs (AC: Distributed tracing)."""
    # Create channel and task
    channel = create_channel(channel_id="poke1")
    task = create_task(channel_id="poke1", status=TaskStatus.QUEUED)
    task.channel_id = channel.id
    task.channel = channel

    async_session.add(channel)
    async_session.add(task)
    await async_session.commit()

    # Mock async_session_factory to return test session
    with patch(
        "app.services.pipeline_orchestrator.async_session_factory",
        create_mock_session_factory(async_session),
    ):
        # Mock services
        with patch("app.services.pipeline_orchestrator.AssetGenerationService") as mock_service:
            mock_service.return_value.create_asset_manifest.return_value = MagicMock(assets=[])
        mock_service.return_value.generate_assets = AsyncMock(
            return_value={"generated": 0, "skipped": 0}
        )

        with patch("app.services.pipeline_orchestrator.is_step_complete", return_value=False):
            with patch(
                "app.services.pipeline_orchestrator.clear_step_metadata", new_callable=AsyncMock
            ):
                with patch(
                    "app.services.pipeline_orchestrator.save_step_checkpoint",
                    new_callable=AsyncMock,
                ):
                    orchestrator = PipelineOrchestrator(task_id=str(task.id))

                    # Mock _load_task_data and update methods
                    with patch.object(
                        orchestrator, "_load_task_data", new_callable=AsyncMock
                    ) as mock_load:
                        mock_load.return_value = {
                            "channel_id": "poke1",
                            "project_id": str(task.id),
                            "topic": "test topic",
                            "story_direction": "test direction",
                            "narration_scripts": [],
                            "sfx_descriptions": [],
                            "voice_id": "test_voice",
                        }

                        with patch.object(
                            orchestrator, "update_task_status", new_callable=AsyncMock
                        ):
                            with patch.object(
                                orchestrator, "_update_pipeline_start_time", new_callable=AsyncMock
                            ):
                                with patch.object(
                                    orchestrator,
                                    "_update_pipeline_end_time",
                                    new_callable=AsyncMock,
                                ):
                                    with caplog.at_level("INFO"):
                                        with patch.object(
                                            orchestrator, "execute_step", new_callable=AsyncMock
                                        ) as mock_exec:
                                            from app.services.pipeline_orchestrator import (
                                                StepCompletion,
                                            )

                                            mock_exec.return_value = StepCompletion(
                                                step=PipelineStep.ASSET_GENERATION,
                                                completed=True,
                                                duration_seconds=10.0,
                                            )

                                            await orchestrator.execute_pipeline()

    # Get all pipeline-related structured logs
    structured_logs = [
        r
        for r in caplog.records
        if any(
            event in r.getMessage()
            for event in ["pipeline_step_started", "pipeline_step_completed"]
        )
    ]

    # Verify all logs have correlation_id = task.id
    for record in structured_logs:
        log_data = json.loads(record.getMessage())
        assert log_data.get("correlation_id") == str(task.id)
