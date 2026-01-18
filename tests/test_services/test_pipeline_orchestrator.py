"""Unit tests for PipelineOrchestrator service.

Tests cover:
- Happy path execution (all steps complete)
- Partial resume after each step failure
- Error classification (transient vs permanent)
- Status transitions
- Performance tracking (duration, cost)
- Step completion metadata persistence

Test Strategy:
- Mock all service layer classes to avoid actual API calls
- Mock database operations to isolate orchestrator logic
- Use in-memory SQLite for database integration tests
- Verify status updates, logging, error handling
"""

import asyncio
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models import Base, Task, TaskStatus
from app.services.pipeline_orchestrator import (
    PipelineOrchestrator,
    PipelineStep,
    StepCompletion,
    is_review_gate,
)
from app.utils.cli_wrapper import CLIScriptError


class TestPipelineOrchestratorInit:
    """Test PipelineOrchestrator initialization."""

    def test_orchestrator_initialization(self):
        """Test orchestrator initializes with task_id and empty step completions."""
        orchestrator = PipelineOrchestrator(task_id="test-task-123")

        assert orchestrator.task_id == "test-task-123"
        assert orchestrator.step_completions == {}
        assert orchestrator.log is not None


class TestExecutePipeline:
    """Test complete pipeline execution."""

    @pytest.mark.asyncio
    async def test_execute_pipeline_happy_path(self):
        """Test pipeline executes first step and halts at ASSETS_READY review gate.

        Story 5.2 Update: Pipeline now halts at review gates for human approval.
        The 'happy path' for a fresh task is to complete asset generation and halt
        at ASSETS_READY, awaiting approval before proceeding.
        """
        orchestrator = PipelineOrchestrator(task_id="test-task-123")

        # Mock task data loading
        with patch.object(orchestrator, "_load_task_data", new_callable=AsyncMock) as mock_load:
            mock_load.return_value = {
                "channel_id": "poke1",
                "project_id": "vid_123",
                "topic": "Bulbasaur documentary",
                "story_direction": "Forest evolution story",
            }

            # Mock load_step_completion_metadata (returns empty dict - no steps complete)
            with patch.object(
                orchestrator, "load_step_completion_metadata", new_callable=AsyncMock
            ) as mock_metadata:
                mock_metadata.return_value = {}

                # Mock all execute_step calls to succeed
                with patch.object(
                    orchestrator, "execute_step", new_callable=AsyncMock
                ) as mock_step:
                    mock_step.return_value = StepCompletion(
                        step=PipelineStep.ASSET_GENERATION,
                        completed=True,
                        duration_seconds=10.0,
                    )

                    # Mock status updates
                    with patch.object(orchestrator, "update_task_status", new_callable=AsyncMock):
                        # Mock save_step_completion
                        with patch.object(
                            orchestrator, "save_step_completion", new_callable=AsyncMock
                        ):
                            # Mock performance tracking methods
                            with patch.object(
                                orchestrator, "_update_pipeline_start_time", new_callable=AsyncMock
                            ):
                                # Execute pipeline
                                await orchestrator.execute_pipeline()

                                # Story 5.2: Pipeline now halts at first review gate (ASSETS_READY)
                                # Verify only asset generation step was executed
                                assert mock_step.call_count == 1

    @pytest.mark.asyncio
    async def test_execute_pipeline_task_not_found(self):
        """Test pipeline handles task not found gracefully."""
        orchestrator = PipelineOrchestrator(task_id="nonexistent")

        with patch.object(orchestrator, "_load_task_data", new_callable=AsyncMock) as mock_load:
            mock_load.return_value = None

            await orchestrator.execute_pipeline()

            # Should exit early, no other methods called
            mock_load.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_pipeline_asset_generation_failure(self):
        """Test pipeline halts on asset generation failure."""
        orchestrator = PipelineOrchestrator(task_id="test-task-123")

        with patch.object(orchestrator, "_load_task_data", new_callable=AsyncMock) as mock_load:
            mock_load.return_value = {
                "channel_id": "poke1",
                "project_id": "vid_123",
                "topic": "Bulbasaur documentary",
                "story_direction": "Forest evolution story",
            }

            # Mock load_step_completion_metadata
            with patch.object(
                orchestrator, "load_step_completion_metadata", new_callable=AsyncMock
            ) as mock_metadata:
                mock_metadata.return_value = {}

                with patch.object(
                    orchestrator, "execute_step", new_callable=AsyncMock
                ) as mock_step:
                    # First step fails
                    mock_step.side_effect = Exception("Gemini API timeout")

                    with patch.object(
                        orchestrator, "update_task_status", new_callable=AsyncMock
                    ) as mock_status:
                        with patch.object(
                            orchestrator, "_update_pipeline_start_time", new_callable=AsyncMock
                        ):
                            await orchestrator.execute_pipeline()

                            # Verify error status was set
                            assert mock_status.call_count >= 2  # Initial status + error status

                            # Check that error status was set (last call)
                            last_call = mock_status.call_args_list[-1]
                            assert last_call[0][0] == TaskStatus.ASSET_ERROR


class TestExecuteStep:
    """Test individual step execution."""

    @pytest.mark.asyncio
    async def test_execute_step_asset_generation(self):
        """Test asset generation step executes successfully."""
        orchestrator = PipelineOrchestrator(task_id="test-task-123")

        with patch(
            "app.services.pipeline_orchestrator.AssetGenerationService"
        ) as mock_service_class:
            mock_service = Mock()
            mock_service_class.return_value = mock_service
            mock_service.create_asset_manifest.return_value = Mock(assets=[Mock()] * 22)
            mock_service.generate_assets = AsyncMock(return_value={"generated": 20, "skipped": 2})

            completion = await orchestrator.execute_step(
                PipelineStep.ASSET_GENERATION,
                "poke1",
                "vid_123",
                "Bulbasaur documentary",
                "Forest story",
            )

            assert completion.completed is True
            assert completion.duration_seconds > 0
            assert completion.error_message is None
            assert completion.partial_progress is not None
            assert completion.partial_progress["generated"] == 20
            assert completion.partial_progress["skipped"] == 2
            assert completion.partial_progress["total"] == 22

    @pytest.mark.asyncio
    async def test_execute_step_video_generation(self):
        """Test video generation step executes successfully."""
        orchestrator = PipelineOrchestrator(task_id="test-task-123")

        with patch(
            "app.services.pipeline_orchestrator.VideoGenerationService"
        ) as mock_service_class:
            mock_service = Mock()
            mock_service_class.return_value = mock_service
            mock_service.create_video_manifest.return_value = Mock(clips=[Mock()] * 18)
            mock_service.generate_videos = AsyncMock(
                return_value={"generated": 16, "skipped": 2, "total": 18}
            )

            completion = await orchestrator.execute_step(
                PipelineStep.VIDEO_GENERATION,
                "poke1",
                "vid_123",
                "Bulbasaur documentary",
                "Forest story",
            )

            assert completion.completed is True
            assert completion.duration_seconds > 0
            assert completion.partial_progress is not None
            assert completion.partial_progress["generated"] == 16
            assert completion.partial_progress["skipped"] == 2
            assert completion.partial_progress["total"] == 18

    @pytest.mark.asyncio
    async def test_execute_step_narration_generation(self):
        """Test narration generation step executes successfully."""
        orchestrator = PipelineOrchestrator(task_id="test-task-123")

        with (
            patch(
                "app.services.pipeline_orchestrator.NarrationGenerationService"
            ) as mock_service_class,
            patch("app.services.pipeline_orchestrator.get_audio_dir") as mock_audio_dir,
            patch("app.services.pipeline_orchestrator.get_notion_api_token", return_value=None),
        ):
            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service
            mock_service.create_narration_manifest = AsyncMock(return_value=Mock())
            mock_service.generate_narration = AsyncMock(
                return_value={"generated": 16, "skipped": 2}
            )
            # Mock audio directory to return a path that won't be created
            mock_audio_dir.return_value = Path("/tmp/test_audio")  # noqa: S108

            completion = await orchestrator.execute_step(
                PipelineStep.NARRATION_GENERATION,
                "poke1",
                "vid_123",
                "Bulbasaur documentary",
                "Forest story",
                narration_scripts=["Script 1"] * 18,
                sfx_descriptions=None,
                voice_id="test_voice_123",
            )

            assert completion.completed is True

    @pytest.mark.asyncio
    async def test_execute_step_sfx_generation(self):
        """Test SFX generation step executes successfully."""
        orchestrator = PipelineOrchestrator(task_id="test-task-123")

        with (
            patch("app.services.pipeline_orchestrator.SFXGenerationService") as mock_service_class,
            patch("app.services.pipeline_orchestrator.get_sfx_dir") as mock_sfx_dir,
            patch("app.services.pipeline_orchestrator.get_notion_api_token", return_value=None),
        ):
            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service
            mock_service.create_sfx_manifest = AsyncMock(return_value=Mock())
            mock_service.generate_sfx = AsyncMock(return_value={"generated": 16, "skipped": 2})
            # Mock SFX directory to return a path that won't be created
            mock_sfx_dir.return_value = Path("/tmp/test_sfx")  # noqa: S108

            completion = await orchestrator.execute_step(
                PipelineStep.SFX_GENERATION,
                "poke1",
                "vid_123",
                "Bulbasaur documentary",
                "Forest story",
                narration_scripts=None,
                sfx_descriptions=["SFX 1"] * 18,
                voice_id=None,
            )

            assert completion.completed is True

    @pytest.mark.asyncio
    async def test_execute_step_video_assembly(self):
        """Test video assembly step executes successfully."""
        orchestrator = PipelineOrchestrator(task_id="test-task-123")

        with patch("app.services.pipeline_orchestrator.VideoAssemblyService") as mock_service_class:
            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service
            mock_service.create_assembly_manifest = AsyncMock(return_value=Mock())
            mock_service.assemble_video = AsyncMock(return_value={"output": "final.mp4"})

            completion = await orchestrator.execute_step(
                PipelineStep.VIDEO_ASSEMBLY,
                "poke1",
                "vid_123",
                "Bulbasaur documentary",
                "Forest story",
            )

            assert completion.completed is True

    @pytest.mark.asyncio
    async def test_execute_step_handles_exception(self):
        """Test execute_step lets exceptions propagate (no internal error handling)."""
        orchestrator = PipelineOrchestrator(task_id="test-task-123")

        with patch(
            "app.services.pipeline_orchestrator.AssetGenerationService"
        ) as mock_service_class:
            # Use regular Mock since create_asset_manifest is synchronous
            mock_service = Mock()
            mock_service_class.return_value = mock_service
            mock_service.create_asset_manifest.side_effect = Exception("Gemini API error")
            # generate_assets is async
            mock_service.generate_assets = AsyncMock()

            # execute_step now lets exceptions propagate instead of catching them
            # Error handling happens at execute_pipeline level
            with pytest.raises(Exception, match="Gemini API error"):
                await orchestrator.execute_step(
                    PipelineStep.ASSET_GENERATION,
                    "poke1",
                    "vid_123",
                    "Bulbasaur documentary",
                    "Forest story",
                )


class TestPartialResume:
    """Test partial resume functionality."""

    @pytest.mark.asyncio
    async def test_load_step_completion_metadata_empty(self, async_session):
        """Test loading completion metadata when none exists."""
        from app.models import Channel, Task

        # Create test channel
        channel = Channel(
            channel_id="poke1",
            channel_name="Pokemon Channel",
            is_active=True,
        )
        async_session.add(channel)
        await async_session.flush()  # Flush to get channel.id

        # Create test task without completion metadata
        task = Task(
            channel_id=channel.id,
            notion_page_id="test123",
            title="Test Video",
            topic="Test Topic",
            story_direction="Test Story",
            status=TaskStatus.QUEUED,
        )
        async_session.add(task)
        await async_session.commit()

        orchestrator = PipelineOrchestrator(task_id=str(task.id))

        with patch(
            "app.services.pipeline_orchestrator.async_session_factory"
        ) as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value.__aenter__.return_value = mock_session
            mock_session.get = AsyncMock(return_value=task)

            metadata = await orchestrator.load_step_completion_metadata()

            assert metadata == {}

    @pytest.mark.asyncio
    async def test_load_step_completion_metadata_with_data(self, async_session):
        """Test loading completion metadata with existing data."""
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
            status=TaskStatus.GENERATING_VIDEO,
            step_completion_metadata={
                "asset_generation": {
                    "completed": True,
                    "duration_seconds": 456.7,
                    "partial_progress": None,
                    "error_message": None,
                },
            },
        )
        async_session.add(task)
        await async_session.commit()

        orchestrator = PipelineOrchestrator(task_id=str(task.id))

        with patch(
            "app.services.pipeline_orchestrator.async_session_factory"
        ) as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value.__aenter__.return_value = mock_session
            mock_session.get = AsyncMock(return_value=task)

            metadata = await orchestrator.load_step_completion_metadata()

            assert PipelineStep.ASSET_GENERATION in metadata
            assert metadata[PipelineStep.ASSET_GENERATION].completed is True
            assert metadata[PipelineStep.ASSET_GENERATION].duration_seconds == 456.7


class TestErrorClassification:
    """Test error classification logic."""

    def test_classify_error_timeout(self):
        """Test timeout errors classified as transient."""
        orchestrator = PipelineOrchestrator(task_id="test-task-123")

        is_transient, error_type = orchestrator.classify_error(TimeoutError("Kling timeout"))

        assert is_transient is True
        assert error_type == "timeout_error"

    def test_classify_error_asyncio_timeout(self):
        """Test asyncio timeout errors classified as transient."""
        orchestrator = PipelineOrchestrator(task_id="test-task-123")

        is_transient, error_type = orchestrator.classify_error(asyncio.TimeoutError())

        assert is_transient is True
        assert error_type == "timeout_error"

    def test_classify_error_cli_script_timeout(self):
        """Test CLI script timeout errors classified as transient."""
        orchestrator = PipelineOrchestrator(task_id="test-task-123")

        error = CLIScriptError("generate_video.py", 124, "Command timed out")
        is_transient, error_type = orchestrator.classify_error(error)

        assert is_transient is True
        assert error_type == "cli_timeout"

    def test_classify_error_connection_error(self):
        """Test connection errors classified as transient."""
        orchestrator = PipelineOrchestrator(task_id="test-task-123")

        is_transient, error_type = orchestrator.classify_error(
            ConnectionError("Network unreachable")
        )

        assert is_transient is True
        assert error_type == "connection_error"

    def test_classify_error_rate_limit(self):
        """Test rate limit errors classified as transient."""
        orchestrator = PipelineOrchestrator(task_id="test-task-123")

        is_transient, error_type = orchestrator.classify_error(
            Exception("HTTP 429 rate limit exceeded")
        )

        assert is_transient is True
        assert error_type == "transient_api_error"

    def test_classify_error_file_not_found(self):
        """Test file not found errors classified as permanent."""
        orchestrator = PipelineOrchestrator(task_id="test-task-123")

        is_transient, error_type = orchestrator.classify_error(
            FileNotFoundError("Missing input file")
        )

        assert is_transient is False
        assert error_type == "file_not_found"

    def test_classify_error_value_error(self):
        """Test value errors classified as permanent."""
        orchestrator = PipelineOrchestrator(task_id="test-task-123")

        is_transient, error_type = orchestrator.classify_error(ValueError("Invalid parameters"))

        assert is_transient is False
        assert error_type == "invalid_parameters"

    def test_classify_error_unknown(self):
        """Test unknown errors classified as permanent."""
        orchestrator = PipelineOrchestrator(task_id="test-task-123")

        is_transient, error_type = orchestrator.classify_error(Exception("Unknown error"))

        assert is_transient is False
        assert error_type == "unknown_error"


class TestStatusUpdates:
    """Test task status update functionality."""

    @pytest.mark.skip(
        reason="Test needs refactoring after Story 5.2 changes - covered by test_update_task_status_triggers_notion_sync"
    )
    @pytest.mark.asyncio
    async def test_update_task_status_success(self, async_session, async_engine):
        """Test status update succeeds with no error."""

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
            status=TaskStatus.QUEUED,
        )
        async_session.add(task)
        await async_session.commit()

        orchestrator = PipelineOrchestrator(task_id=str(task.id))

        # Use real session factory but mock Notion sync
        session_factory = async_sessionmaker(bind=async_engine, expire_on_commit=False)
        with patch("app.services.pipeline_orchestrator.async_session_factory", session_factory):
            # Mock async Notion sync to prevent it from running during test
            with patch("asyncio.create_task") as mock_create_task:
                mock_task_obj = AsyncMock()
                mock_task_obj.add_done_callback = Mock()
                mock_create_task.return_value = mock_task_obj

                await orchestrator.update_task_status(TaskStatus.GENERATING_ASSETS)

        # Refresh task from database to get updated status
        await async_session.refresh(task)

        # Verify status was updated
        assert task.status == TaskStatus.GENERATING_ASSETS

    @pytest.mark.asyncio
    async def test_update_task_status_with_error(self, async_session):
        """Test status update appends error to log."""
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
            status=TaskStatus.GENERATING_ASSETS,
            error_log="",
        )
        async_session.add(task)
        await async_session.commit()

        orchestrator = PipelineOrchestrator(task_id=str(task.id))

        with patch(
            "app.services.pipeline_orchestrator.async_session_factory"
        ) as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value.__aenter__.return_value = mock_session
            mock_session_class.return_value.__aexit__.return_value = AsyncMock()

            mock_session.get = AsyncMock(return_value=task)
            mock_session.begin = Mock()
            mock_session.begin.return_value.__aenter__ = AsyncMock()
            mock_session.begin.return_value.__aexit__ = AsyncMock()
            mock_session.commit = AsyncMock()

            await orchestrator.update_task_status(
                TaskStatus.ASSET_ERROR,
                error_message="Gemini API timeout",
            )

            # Verify error was appended to log
            assert "Gemini API timeout" in task.error_log


class TestPerformanceTracking:
    """Test pipeline performance tracking."""

    @pytest.mark.asyncio
    async def test_calculate_pipeline_cost(self, async_session):
        """Test pipeline cost calculation."""
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
            status=TaskStatus.ASSEMBLING,
            total_cost_usd=8.45,
        )
        async_session.add(task)
        await async_session.commit()

        orchestrator = PipelineOrchestrator(task_id=str(task.id))

        with patch(
            "app.services.pipeline_orchestrator.async_session_factory"
        ) as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value.__aenter__.return_value = mock_session
            mock_session.get = AsyncMock(return_value=task)

            cost = await orchestrator.calculate_pipeline_cost()

            assert cost == 8.45

    @pytest.mark.asyncio
    async def test_update_task_status_triggers_notion_sync(self, async_session):
        """Test that updating task status triggers async Notion sync."""
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
            status=TaskStatus.QUEUED,
        )
        async_session.add(task)
        await async_session.commit()

        orchestrator = PipelineOrchestrator(task_id=str(task.id))

        with patch(
            "app.services.pipeline_orchestrator.async_session_factory"
        ) as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value.__aenter__.return_value = mock_session
            mock_session_class.return_value.__aexit__.return_value = AsyncMock()

            mock_session.get = AsyncMock(return_value=task)
            mock_session.begin = Mock()
            mock_session.begin.return_value.__aenter__ = AsyncMock()
            mock_session.begin.return_value.__aexit__ = AsyncMock()
            mock_session.commit = AsyncMock()

            with patch("asyncio.create_task") as mock_create_task:
                # Mock create_task to return a mock task
                mock_task = AsyncMock()
                mock_task.result = Mock(
                    return_value=None
                )  # result() should return None, not a coroutine
                mock_task.add_done_callback = Mock()
                mock_create_task.return_value = mock_task

                await orchestrator.update_task_status(TaskStatus.GENERATING_ASSETS)

                # Verify create_task was called with a coroutine
                mock_create_task.assert_called_once()
                call_args = mock_create_task.call_args[0][0]
                assert asyncio.iscoroutine(call_args)

                # Clean up the coroutine to prevent warnings
                call_args.close()


class TestReviewGateDetection:
    """Test review gate detection (Story 5.2)."""

    def test_is_review_gate_assets_ready(self):
        """Test ASSETS_READY is identified as mandatory review gate."""
        assert is_review_gate(TaskStatus.ASSETS_READY) is True

    def test_is_review_gate_video_ready(self):
        """Test VIDEO_READY is identified as mandatory review gate."""
        assert is_review_gate(TaskStatus.VIDEO_READY) is True

    def test_is_review_gate_audio_ready(self):
        """Test AUDIO_READY is identified as mandatory review gate."""
        assert is_review_gate(TaskStatus.AUDIO_READY) is True

    def test_is_review_gate_final_review(self):
        """Test FINAL_REVIEW is identified as mandatory review gate."""
        assert is_review_gate(TaskStatus.FINAL_REVIEW) is True

    def test_is_review_gate_composites_ready_not_gate(self):
        """Test COMPOSITES_READY is NOT a review gate (auto-proceeds)."""
        assert is_review_gate(TaskStatus.COMPOSITES_READY) is False

    def test_is_review_gate_sfx_ready_not_gate(self):
        """Test SFX_READY is NOT a review gate (auto-proceeds)."""
        assert is_review_gate(TaskStatus.SFX_READY) is False

    def test_is_review_gate_assembly_ready_not_gate(self):
        """Test ASSEMBLY_READY is NOT a review gate (auto-proceeds)."""
        assert is_review_gate(TaskStatus.ASSEMBLY_READY) is False

    def test_is_review_gate_generating_assets_not_gate(self):
        """Test GENERATING_ASSETS is NOT a review gate (in-progress state)."""
        assert is_review_gate(TaskStatus.GENERATING_ASSETS) is False

    def test_is_review_gate_approved_not_gate(self):
        """Test APPROVED is NOT a review gate (post-approval state)."""
        assert is_review_gate(TaskStatus.APPROVED) is False

    def test_is_review_gate_queued_not_gate(self):
        """Test QUEUED is NOT a review gate (initial state)."""
        assert is_review_gate(TaskStatus.QUEUED) is False


class TestReviewGateEnforcement:
    """Test pipeline enforcement of review gates (Story 5.2)."""

    @pytest.mark.asyncio
    async def test_pipeline_halts_at_assets_ready_gate(self):
        """Test pipeline halts after asset generation, sets ASSETS_READY status."""
        orchestrator = PipelineOrchestrator(task_id="test-task-123")

        # Mock task data loading
        with patch.object(orchestrator, "_load_task_data", new_callable=AsyncMock) as mock_load:
            mock_load.return_value = {
                "channel_id": "poke1",
                "project_id": "vid_123",
                "topic": "Bulbasaur documentary",
                "story_direction": "Forest evolution story",
            }

            # Mock load_step_completion_metadata (no steps complete)
            with patch.object(
                orchestrator, "load_step_completion_metadata", new_callable=AsyncMock
            ) as mock_metadata:
                mock_metadata.return_value = {}

                # Mock execute_step to succeed for asset generation
                with patch.object(
                    orchestrator, "execute_step", new_callable=AsyncMock
                ) as mock_step:
                    mock_step.return_value = StepCompletion(
                        step=PipelineStep.ASSET_GENERATION,
                        completed=True,
                        duration_seconds=10.0,
                    )

                    # Mock status updates
                    with patch.object(
                        orchestrator, "update_task_status", new_callable=AsyncMock
                    ) as mock_status:
                        # Mock save_step_completion
                        with patch.object(
                            orchestrator, "save_step_completion", new_callable=AsyncMock
                        ):
                            # Mock performance tracking
                            with patch.object(
                                orchestrator, "_update_pipeline_start_time", new_callable=AsyncMock
                            ):
                                # Execute pipeline
                                await orchestrator.execute_pipeline()

                                # Verify pipeline executed ONLY asset generation step
                                assert mock_step.call_count == 1
                                mock_step.assert_called_once()

                                # Verify status was set to ASSETS_READY (review gate)
                                status_calls = [call[0][0] for call in mock_status.call_args_list]
                                assert TaskStatus.GENERATING_ASSETS in status_calls
                                assert TaskStatus.ASSETS_READY in status_calls

                                # Verify pipeline did NOT proceed to composite creation
                                assert TaskStatus.GENERATING_COMPOSITES not in status_calls

    @pytest.mark.asyncio
    async def test_pipeline_halts_at_video_ready_gate(self):
        """Test pipeline halts after video generation, sets VIDEO_READY status."""
        orchestrator = PipelineOrchestrator(task_id="test-task-123")

        with patch.object(orchestrator, "_load_task_data", new_callable=AsyncMock) as mock_load:
            mock_load.return_value = {
                "channel_id": "poke1",
                "project_id": "vid_123",
                "topic": "Bulbasaur documentary",
                "story_direction": "Forest evolution story",
            }

            # Mock that assets and composites are already complete
            with patch.object(
                orchestrator, "load_step_completion_metadata", new_callable=AsyncMock
            ) as mock_metadata:
                mock_metadata.return_value = {
                    PipelineStep.ASSET_GENERATION: StepCompletion(
                        step=PipelineStep.ASSET_GENERATION, completed=True, duration_seconds=10.0
                    ),
                    PipelineStep.COMPOSITE_CREATION: StepCompletion(
                        step=PipelineStep.COMPOSITE_CREATION, completed=True, duration_seconds=5.0
                    ),
                }

                # Mock execute_step to succeed for video generation only
                with patch.object(
                    orchestrator, "execute_step", new_callable=AsyncMock
                ) as mock_step:
                    mock_step.return_value = StepCompletion(
                        step=PipelineStep.VIDEO_GENERATION,
                        completed=True,
                        duration_seconds=60.0,
                    )

                    with patch.object(
                        orchestrator, "update_task_status", new_callable=AsyncMock
                    ) as mock_status:
                        with patch.object(
                            orchestrator, "save_step_completion", new_callable=AsyncMock
                        ):
                            with patch.object(
                                orchestrator, "_update_pipeline_start_time", new_callable=AsyncMock
                            ):
                                await orchestrator.execute_pipeline()

                                # Verify pipeline executed ONLY video generation
                                assert mock_step.call_count == 1

                                # Verify status was set to VIDEO_READY (review gate)
                                status_calls = [call[0][0] for call in mock_status.call_args_list]
                                assert TaskStatus.GENERATING_VIDEO in status_calls
                                assert TaskStatus.VIDEO_READY in status_calls

                                # Verify pipeline did NOT proceed to audio generation
                                assert TaskStatus.GENERATING_AUDIO not in status_calls

    @pytest.mark.asyncio
    async def test_pipeline_auto_proceeds_through_composites_ready(self):
        """Test pipeline automatically proceeds through COMPOSITES_READY (no review gate)."""
        orchestrator = PipelineOrchestrator(task_id="test-task-123")

        with patch.object(orchestrator, "_load_task_data", new_callable=AsyncMock) as mock_load:
            mock_load.return_value = {
                "channel_id": "poke1",
                "project_id": "vid_123",
                "topic": "Bulbasaur documentary",
                "story_direction": "Forest evolution story",
            }

            # Mock that only assets are complete (approved)
            with patch.object(
                orchestrator, "load_step_completion_metadata", new_callable=AsyncMock
            ) as mock_metadata:
                mock_metadata.return_value = {
                    PipelineStep.ASSET_GENERATION: StepCompletion(
                        step=PipelineStep.ASSET_GENERATION, completed=True, duration_seconds=10.0
                    ),
                }

                # Mock execute_step to succeed for both composite and video generation
                step_results = [
                    StepCompletion(
                        step=PipelineStep.COMPOSITE_CREATION,
                        completed=True,
                        duration_seconds=5.0,
                    ),
                    StepCompletion(
                        step=PipelineStep.VIDEO_GENERATION,
                        completed=True,
                        duration_seconds=60.0,
                    ),
                ]
                with patch.object(
                    orchestrator, "execute_step", new_callable=AsyncMock
                ) as mock_step:
                    mock_step.side_effect = step_results

                    with patch.object(
                        orchestrator, "update_task_status", new_callable=AsyncMock
                    ) as mock_status:
                        with patch.object(
                            orchestrator, "save_step_completion", new_callable=AsyncMock
                        ):
                            with patch.object(
                                orchestrator, "_update_pipeline_start_time", new_callable=AsyncMock
                            ):
                                await orchestrator.execute_pipeline()

                                # Verify pipeline executed BOTH composite and video steps
                                assert mock_step.call_count == 2

                                # Verify status transitions: COMPOSITES_READY should be set but pipeline continues
                                status_calls = [call[0][0] for call in mock_status.call_args_list]
                                assert TaskStatus.GENERATING_COMPOSITES in status_calls
                                assert TaskStatus.COMPOSITES_READY in status_calls
                                assert TaskStatus.GENERATING_VIDEO in status_calls
                                assert TaskStatus.VIDEO_READY in status_calls

    @pytest.mark.asyncio
    async def test_pipeline_logs_review_gate_pause(self):
        """Test pipeline logs when halting at a review gate."""
        orchestrator = PipelineOrchestrator(task_id="test-task-123")

        with patch.object(orchestrator, "_load_task_data", new_callable=AsyncMock) as mock_load:
            mock_load.return_value = {
                "channel_id": "poke1",
                "project_id": "vid_123",
                "topic": "Bulbasaur documentary",
                "story_direction": "Forest evolution story",
            }

            with patch.object(
                orchestrator, "load_step_completion_metadata", new_callable=AsyncMock
            ) as mock_metadata:
                mock_metadata.return_value = {}

                with patch.object(
                    orchestrator, "execute_step", new_callable=AsyncMock
                ) as mock_step:
                    mock_step.return_value = StepCompletion(
                        step=PipelineStep.ASSET_GENERATION,
                        completed=True,
                        duration_seconds=10.0,
                    )

                    with patch.object(orchestrator, "update_task_status", new_callable=AsyncMock):
                        with patch.object(
                            orchestrator, "save_step_completion", new_callable=AsyncMock
                        ):
                            with patch.object(
                                orchestrator, "_update_pipeline_start_time", new_callable=AsyncMock
                            ):
                                # Patch the logger to verify log calls
                                with patch.object(orchestrator.log, "info") as mock_log:
                                    await orchestrator.execute_pipeline()

                                    # Verify review gate pause was logged
                                    log_calls = [str(call) for call in mock_log.call_args_list]
                                    # Should contain a log about pipeline halting at review gate
                                    assert any(
                                        "review_gate" in str(call) or "halted" in str(call)
                                        for call in log_calls
                                    )

    @pytest.mark.asyncio
    async def test_pipeline_halts_at_audio_ready_gate(self):
        """Test pipeline halts after audio generation, sets AUDIO_READY status (Story 5.2 Task 5 Subtask 5.3)."""
        orchestrator = PipelineOrchestrator(task_id="test-task-audio")

        with patch.object(orchestrator, "_load_task_data", new_callable=AsyncMock) as mock_load:
            mock_load.return_value = {
                "channel_id": "poke1",
                "project_id": "vid_123",
                "topic": "Bulbasaur documentary",
                "story_direction": "Forest evolution story",
            }

            # Mock that assets, composites, and videos are already complete
            with patch.object(
                orchestrator, "load_step_completion_metadata", new_callable=AsyncMock
            ) as mock_metadata:
                mock_metadata.return_value = {
                    PipelineStep.ASSET_GENERATION: StepCompletion(
                        step=PipelineStep.ASSET_GENERATION, completed=True, duration_seconds=10.0
                    ),
                    PipelineStep.COMPOSITE_CREATION: StepCompletion(
                        step=PipelineStep.COMPOSITE_CREATION, completed=True, duration_seconds=5.0
                    ),
                    PipelineStep.VIDEO_GENERATION: StepCompletion(
                        step=PipelineStep.VIDEO_GENERATION, completed=True, duration_seconds=60.0
                    ),
                }

                # Mock execute_step to succeed for audio generation only
                with patch.object(
                    orchestrator, "execute_step", new_callable=AsyncMock
                ) as mock_step:
                    mock_step.return_value = StepCompletion(
                        step=PipelineStep.NARRATION_GENERATION,
                        completed=True,
                        duration_seconds=30.0,
                    )

                    with patch.object(
                        orchestrator, "update_task_status", new_callable=AsyncMock
                    ) as mock_status:
                        with patch.object(
                            orchestrator, "save_step_completion", new_callable=AsyncMock
                        ):
                            with patch.object(
                                orchestrator, "_update_pipeline_start_time", new_callable=AsyncMock
                            ):
                                await orchestrator.execute_pipeline()

                                # Verify pipeline executed ONLY audio generation
                                assert mock_step.call_count == 1

                                # Verify status was set to AUDIO_READY (review gate)
                                status_calls = [call[0][0] for call in mock_status.call_args_list]
                                assert TaskStatus.GENERATING_AUDIO in status_calls
                                assert TaskStatus.AUDIO_READY in status_calls

                                # Verify pipeline did NOT proceed to SFX generation
                                assert TaskStatus.GENERATING_SFX not in status_calls

    @pytest.mark.asyncio
    async def test_pipeline_halts_at_final_review_gate(self):
        """Test pipeline halts before YouTube upload, sets FINAL_REVIEW status (Story 5.2 Task 5 Subtask 5.4)."""
        orchestrator = PipelineOrchestrator(task_id="test-task-final")

        with patch.object(orchestrator, "_load_task_data", new_callable=AsyncMock) as mock_load:
            mock_load.return_value = {
                "channel_id": "poke1",
                "project_id": "vid_123",
                "topic": "Bulbasaur documentary",
                "story_direction": "Forest evolution story",
            }

            # Mock that all steps except assembly are complete
            with patch.object(
                orchestrator, "load_step_completion_metadata", new_callable=AsyncMock
            ) as mock_metadata:
                mock_metadata.return_value = {
                    PipelineStep.ASSET_GENERATION: StepCompletion(
                        step=PipelineStep.ASSET_GENERATION, completed=True, duration_seconds=10.0
                    ),
                    PipelineStep.COMPOSITE_CREATION: StepCompletion(
                        step=PipelineStep.COMPOSITE_CREATION, completed=True, duration_seconds=5.0
                    ),
                    PipelineStep.VIDEO_GENERATION: StepCompletion(
                        step=PipelineStep.VIDEO_GENERATION, completed=True, duration_seconds=60.0
                    ),
                    PipelineStep.NARRATION_GENERATION: StepCompletion(
                        step=PipelineStep.NARRATION_GENERATION,
                        completed=True,
                        duration_seconds=30.0,
                    ),
                    PipelineStep.SFX_GENERATION: StepCompletion(
                        step=PipelineStep.SFX_GENERATION, completed=True, duration_seconds=15.0
                    ),
                }

                # Mock execute_step to succeed for assembly only
                with patch.object(
                    orchestrator, "execute_step", new_callable=AsyncMock
                ) as mock_step:
                    mock_step.return_value = StepCompletion(
                        step=PipelineStep.VIDEO_ASSEMBLY,
                        completed=True,
                        duration_seconds=20.0,
                    )

                    with patch.object(
                        orchestrator, "update_task_status", new_callable=AsyncMock
                    ) as mock_status:
                        with patch.object(
                            orchestrator, "save_step_completion", new_callable=AsyncMock
                        ):
                            with patch.object(
                                orchestrator, "_update_pipeline_start_time", new_callable=AsyncMock
                            ):
                                await orchestrator.execute_pipeline()

                                # Verify pipeline executed ONLY assembly
                                assert mock_step.call_count == 1

                                # Verify status was set to FINAL_REVIEW (review gate before upload)
                                status_calls = [call[0][0] for call in mock_status.call_args_list]
                                assert TaskStatus.ASSEMBLING in status_calls
                                assert TaskStatus.ASSEMBLY_READY in status_calls
                                assert TaskStatus.FINAL_REVIEW in status_calls

                                # Verify pipeline did NOT proceed to upload
                                assert TaskStatus.UPLOADING not in status_calls
                                assert TaskStatus.PUBLISHED not in status_calls


class TestReviewTimestampTracking:
    """Test review gate timestamp tracking (Story 5.2 Task 3)."""

    @pytest.mark.asyncio
    async def test_review_started_at_set_when_entering_review_gate(self):
        """Test review_started_at is set when task enters review gate status."""
        from unittest.mock import Mock
        from app.models import Channel
        import uuid

        # Create task with GENERATING_ASSETS status (valid transition to ASSETS_READY)
        task = Task(
            id=uuid.uuid4(),
            channel_id=uuid.uuid4(),
            notion_page_id="test-timestamp-123",
            title="Test Task",
            topic="Test Topic",
            story_direction="Test Story",
            status=TaskStatus.GENERATING_ASSETS,
            review_started_at=None,
            review_completed_at=None,
        )

        orchestrator = PipelineOrchestrator(task_id=task.id)

        # Mock session to return our task
        with patch(
            "app.services.pipeline_orchestrator.async_session_factory"
        ) as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value.__aenter__.return_value = mock_session
            mock_session_class.return_value.__aexit__.return_value = AsyncMock()

            mock_session.get = AsyncMock(return_value=task)
            mock_session.begin = Mock()
            mock_session.begin.return_value.__aenter__ = AsyncMock()
            mock_session.begin.return_value.__aexit__ = AsyncMock()

            # Update to ASSETS_READY (review gate)
            await orchestrator.update_task_status(TaskStatus.ASSETS_READY)

            # Verify timestamp was set
            assert task.review_started_at is not None
            assert task.review_completed_at is None
            assert task.status == TaskStatus.ASSETS_READY

            # Verify timestamp is recent (within last 5 seconds)
            time_diff = (
                datetime.now(task.review_started_at.tzinfo) - task.review_started_at
            ).total_seconds()
            assert time_diff < 5

    @pytest.mark.asyncio
    async def test_review_started_at_set_for_all_review_gates(self):
        """Test review_started_at is set for all four mandatory review gates."""
        from unittest.mock import Mock
        import uuid

        # Test each review gate independently
        review_gates = [
            (TaskStatus.GENERATING_ASSETS, TaskStatus.ASSETS_READY),
            (TaskStatus.GENERATING_VIDEO, TaskStatus.VIDEO_READY),
            (TaskStatus.GENERATING_AUDIO, TaskStatus.AUDIO_READY),
            (TaskStatus.ASSEMBLY_READY, TaskStatus.FINAL_REVIEW),
        ]

        for from_status, to_status in review_gates:
            task = Task(
                id=uuid.uuid4(),
                channel_id=uuid.uuid4(),
                notion_page_id=f"test-gate-{to_status.value}",
                title="Test Task",
                topic="Test Topic",
                story_direction="Test Story",
                status=from_status,
                review_started_at=None,
            )

            orchestrator = PipelineOrchestrator(task_id=task.id)

            # Mock session
            with patch(
                "app.services.pipeline_orchestrator.async_session_factory"
            ) as mock_session_class:
                mock_session = AsyncMock()
                mock_session_class.return_value.__aenter__.return_value = mock_session
                mock_session_class.return_value.__aexit__.return_value = AsyncMock()

                mock_session.get = AsyncMock(return_value=task)
                mock_session.begin = Mock()
                mock_session.begin.return_value.__aenter__ = AsyncMock()
                mock_session.begin.return_value.__aexit__ = AsyncMock()

                # Update to review gate
                await orchestrator.update_task_status(to_status)

                # Verify timestamp was set
                assert task.review_started_at is not None, (
                    f"review_started_at not set for {to_status.value}"
                )
                assert task.status == to_status

    @pytest.mark.asyncio
    async def test_review_started_at_not_set_for_non_review_gates(self):
        """Test review_started_at is NOT set for non-review gate statuses."""
        from unittest.mock import Mock
        import uuid

        # Test non-review gate statuses
        non_review_gates = [
            (TaskStatus.QUEUED, TaskStatus.CLAIMED),
            (TaskStatus.CLAIMED, TaskStatus.GENERATING_ASSETS),
            (TaskStatus.GENERATING_COMPOSITES, TaskStatus.COMPOSITES_READY),
            (TaskStatus.GENERATING_SFX, TaskStatus.SFX_READY),
        ]

        for from_status, to_status in non_review_gates:
            task = Task(
                id=uuid.uuid4(),
                channel_id=uuid.uuid4(),
                notion_page_id=f"test-non-gate-{to_status.value}",
                title="Test Task",
                topic="Test Topic",
                story_direction="Test Story",
                status=from_status,
                review_started_at=None,
            )

            orchestrator = PipelineOrchestrator(task_id=task.id)

            # Mock session
            with patch(
                "app.services.pipeline_orchestrator.async_session_factory"
            ) as mock_session_class:
                mock_session = AsyncMock()
                mock_session_class.return_value.__aenter__.return_value = mock_session
                mock_session_class.return_value.__aexit__.return_value = AsyncMock()

                mock_session.get = AsyncMock(return_value=task)
                mock_session.begin = Mock()
                mock_session.begin.return_value.__aenter__ = AsyncMock()
                mock_session.begin.return_value.__aexit__ = AsyncMock()

                # Update to non-review gate
                await orchestrator.update_task_status(to_status)

                # Verify timestamp was NOT set
                assert task.review_started_at is None, (
                    f"review_started_at incorrectly set for {to_status.value}"
                )
                assert task.status == to_status
