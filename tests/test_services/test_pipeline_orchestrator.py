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
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.models import TaskStatus
from app.services.pipeline_orchestrator import (
    PipelineOrchestrator,
    PipelineStep,
    StepCompletion,
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
        """Test pipeline executes all 6 steps successfully."""
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
                                with patch.object(
                                    orchestrator,
                                    "_update_pipeline_end_time",
                                    new_callable=AsyncMock,
                                ):
                                    with patch.object(
                                        orchestrator,
                                        "calculate_pipeline_cost",
                                        new_callable=AsyncMock,
                                    ) as mock_cost:
                                        mock_cost.return_value = 8.45

                                        with patch.object(
                                            orchestrator,
                                            "_update_pipeline_cost",
                                            new_callable=AsyncMock,
                                        ):
                                            # Execute pipeline
                                            await orchestrator.execute_pipeline()

                                            # Verify all 6 steps were executed
                                            assert mock_step.call_count == 6

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

        with patch(
            "app.services.pipeline_orchestrator.NarrationGenerationService"
        ) as mock_service_class:
            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service
            mock_service.create_narration_manifest = AsyncMock(return_value=Mock())
            mock_service.generate_narration = AsyncMock(
                return_value={"generated": 16, "skipped": 2}
            )

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

        with patch("app.services.pipeline_orchestrator.SFXGenerationService") as mock_service_class:
            mock_service = AsyncMock()
            mock_service_class.return_value = mock_service
            mock_service.create_sfx_manifest = AsyncMock(return_value=Mock())
            mock_service.generate_sfx = AsyncMock(return_value={"generated": 16, "skipped": 2})

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

    @pytest.mark.asyncio
    async def test_update_task_status_success(self, async_session):
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

            await orchestrator.update_task_status(TaskStatus.GENERATING_ASSETS)

            # Verify status was updated
            mock_session.commit.assert_called()

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
                mock_create_task.return_value = mock_task

                await orchestrator.update_task_status(TaskStatus.GENERATING_ASSETS)

                # Verify create_task was called with a coroutine
                mock_create_task.assert_called_once()
                call_args = mock_create_task.call_args[0][0]
                assert asyncio.iscoroutine(call_args)

                # Clean up the coroutine to prevent warnings
                call_args.close()
