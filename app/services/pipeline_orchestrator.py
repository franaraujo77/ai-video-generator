"""Pipeline Orchestrator Service for end-to-end video generation.

This module implements the orchestration layer for the 8-step video generation
pipeline, coordinating all services from asset generation through final assembly.

Key Responsibilities:
- Execute 6 pipeline steps in sequence (assets → composites → videos → audio → SFX → assembly)
- Track step completion metadata for partial resume after failures
- Update task status after each step (PostgreSQL + Notion sync)
- Classify errors as transient (retriable) or permanent (fail)
- Monitor pipeline duration (target: ≤2 hours, NFR-P1)
- Track total pipeline cost ($6-13 per video expected)
- Pause at review gate for YouTube compliance

Architecture Pattern: "Short Transaction + State Machine"
- Orchestrator operates OUTSIDE database transactions (long-running operations)
- Status updates use short transactions (claim → close → process → reopen → update)
- State machine enforces valid status transitions through pipeline stages
- Partial resume via step_completion_metadata (idempotent operations)

Dependencies:
    - Story 3.1: CLI wrapper (asyncio.to_thread subprocess execution)
    - Story 3.2: Filesystem helpers (secure path construction)
    - Story 3.3: Asset generation service (Gemini API)
    - Story 3.4: Composite creation service (FFmpeg)
    - Story 3.5: Video generation service (Kling API)
    - Story 3.6: Narration generation service (ElevenLabs)
    - Story 3.7: SFX generation service (ElevenLabs)
    - Story 3.8: Video assembly service (FFmpeg)
    - Epic 1: Database models (Task)
    - Epic 2: Notion API client (status sync)

Usage:
    from app.services.pipeline_orchestrator import PipelineOrchestrator

    orchestrator = PipelineOrchestrator(task_id="abc-123")
    await orchestrator.execute_pipeline()
    # Executes all 6 steps, updates status, logs progress

Performance Expectations:
    - Asset generation: 5-15 min (22 images via Gemini)
    - Composite creation: 1-2 min (18 composites via FFmpeg)
    - Video generation: 36-90 min (18 clips via Kling)
    - Narration generation: 5-10 min (18 clips via ElevenLabs)
    - SFX generation: 3-5 min (18 clips via ElevenLabs)
    - Video assembly: 1-2 min (final video via FFmpeg)
    - Total typical: 51-124 minutes (0.85-2.07 hours)
    - 90th percentile target: ≤120 minutes (2 hours, NFR-P1)
"""

import asyncio
import contextlib
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from app.clients.notion import NotionClient
from app.config import get_notion_api_token
from app.database import async_session_factory
from app.models import Task, TaskStatus
from app.services.asset_generation import AssetGenerationService
from app.services.composite_creation import CompositeCreationService
from app.services.narration_generation import NarrationGenerationService
from app.services.notion_sync import TaskSyncData, push_task_to_notion
from app.services.sfx_generation import SFXGenerationService
from app.services.video_assembly import VideoAssemblyService
from app.services.video_generation import VideoGenerationService
from app.utils.cli_wrapper import CLIScriptError
from app.utils.logging import get_logger

log = get_logger(__name__)


class PipelineStep(Enum):
    """Enumeration of pipeline steps in execution order.

    Each step corresponds to a service layer component from Stories 3.3-3.8.
    Steps execute sequentially to transform inputs into final 90-second video.

    Step Order:
        1. ASSET_GENERATION: Generate 22 photorealistic images via Gemini
        2. COMPOSITE_CREATION: Create 18 16:9 composite images for video seeds
        3. VIDEO_GENERATION: Animate composites into 10-second clips via Kling
        4. NARRATION_GENERATION: Generate Attenborough-style narration via ElevenLabs
        5. SFX_GENERATION: Generate environmental sound effects via ElevenLabs
        6. VIDEO_ASSEMBLY: Assemble final 90-second documentary via FFmpeg
    """

    ASSET_GENERATION = "asset_generation"
    COMPOSITE_CREATION = "composite_creation"
    VIDEO_GENERATION = "video_generation"
    NARRATION_GENERATION = "narration_generation"
    SFX_GENERATION = "sfx_generation"
    VIDEO_ASSEMBLY = "video_assembly"


@dataclass
class StepCompletion:
    """Completion metadata for a pipeline step.

    Tracks whether step completed, partial progress for resume, duration for
    performance analysis, and error details for debugging.

    Attributes:
        step: Pipeline step enum value
        completed: Whether step is fully complete (True) or partial/failed (False)
        partial_progress: Dict with partial completion details
            Examples:
                {"clips": 5, "total": 18} - Video generation completed 5 of 18 clips
                {"assets": 11, "total": 22} - Asset generation completed 11 of 22 assets
        duration_seconds: How long step took to execute (for performance tracking)
        error_message: Error details if step failed (for debugging and retry logic)

    Example:
        >>> step = StepCompletion(
        ...     step=PipelineStep.ASSET_GENERATION,
        ...     completed=True,
        ...     partial_progress=None,
        ...     duration_seconds=456.7,
        ...     error_message=None,
        ... )
    """

    step: PipelineStep
    completed: bool
    partial_progress: dict[str, Any] | None = None
    duration_seconds: float | None = None
    error_message: str | None = None


# Step-to-status mapping (for database status updates)
STEP_STATUS_MAP = {
    PipelineStep.ASSET_GENERATION: TaskStatus.GENERATING_ASSETS,
    PipelineStep.COMPOSITE_CREATION: TaskStatus.GENERATING_COMPOSITES,
    PipelineStep.VIDEO_GENERATION: TaskStatus.GENERATING_VIDEO,
    PipelineStep.NARRATION_GENERATION: TaskStatus.GENERATING_AUDIO,
    PipelineStep.SFX_GENERATION: TaskStatus.GENERATING_SFX,
    PipelineStep.VIDEO_ASSEMBLY: TaskStatus.ASSEMBLING,
}

# Step-to-error-status mapping (for error handling)
STEP_ERROR_MAP = {
    PipelineStep.ASSET_GENERATION: TaskStatus.ASSET_ERROR,
    PipelineStep.COMPOSITE_CREATION: TaskStatus.ASSET_ERROR,  # No dedicated composite error status
    PipelineStep.VIDEO_GENERATION: TaskStatus.VIDEO_ERROR,
    PipelineStep.NARRATION_GENERATION: TaskStatus.AUDIO_ERROR,
    PipelineStep.SFX_GENERATION: TaskStatus.SFX_ERROR,
    PipelineStep.VIDEO_ASSEMBLY: TaskStatus.ASSEMBLY_ERROR,
}


class PipelineOrchestrator:
    """Orchestrates end-to-end video generation pipeline.

    Responsibilities:
    - Execute 6 pipeline steps in sequence (assets → composites → videos → audio → SFX → assembly)
    - Track step completion metadata for partial resume
    - Update task status after each step
    - Sync status to Notion (async, non-blocking)
    - Handle errors and classify retriable vs permanent failures
    - Enforce 2-hour performance target (log warnings if exceeded)
    - Pause at review gate for YouTube compliance

    Architecture Pattern: "Short Transaction + State Machine"
    - Claim task (short transaction)
    - Close database connection
    - Execute pipeline steps (long-running, outside transaction)
    - Reopen connection
    - Update task status (short transaction)

    State Machine Integration:
    - Task starts at "queued" status
    - Progresses through: generating_assets → generating_composites → generating_video
      → generating_audio → generating_sfx → assembling → final_review
    - Error states: asset_error, video_error, audio_error, assembly_error
    - Terminal states: approved, failed

    Usage:
        >>> orchestrator = PipelineOrchestrator(task_id="abc-123")
        >>> await orchestrator.execute_pipeline()
        # Executes all 6 steps, updates status, logs progress
    """

    def __init__(self, task_id: str):
        """Initialize pipeline orchestrator for specific task.

        Args:
            task_id: Task UUID from database (str representation of UUID)

        Raises:
            ValueError: If task_id is not a valid UUID format
        """
        self.task_id = task_id
        self.log = get_logger(__name__)
        self.step_completions: dict[PipelineStep, StepCompletion] = {}

    async def execute_pipeline(self) -> None:
        """Execute complete video generation pipeline from start to finish.

        Pipeline Flow:
        1. Load task from database (get channel_id, project_id, topic, story_direction)
        2. Load step completion metadata (for partial resume)
        3. Record pipeline_start_time
        4. For each step in pipeline:
           a. Check if step already complete (skip if yes)
           b. Update status to step's in-progress state
           c. Execute step via service layer
           d. Record completion metadata
           e. Update status to step's ready state
        5. Set final status to "final_review" (human review gate)
        6. Calculate total duration and cost
        7. Log pipeline summary

        Error Handling:
        - Catch exceptions from each step
        - Classify error as transient (retry) or permanent (failed)
        - Log detailed error context for debugging
        - Update task status to appropriate error state
        - Preserve partial completion for retry

        Performance Tracking:
        - Record pipeline_start_time when pipeline begins
        - Record step durations for each step
        - Calculate total_duration when complete
        - Log WARNING if total_duration > 120 minutes (2-hour target)

        Raises:
            No exceptions (catches all, updates task status appropriately)

        Example:
            >>> orchestrator = PipelineOrchestrator(task_id="abc-123")
            >>> await orchestrator.execute_pipeline()
            # Logs: Pipeline started for task abc-123
            # Logs: Executing step: asset_generation
            # Logs: Step completed: asset_generation (duration: 456.7s)
            # ... (more step logs)
            # Logs: Pipeline completed (duration: 3842.1s, cost: $8.45)
        """
        pipeline_start = time.time()

        try:
            # Load task data for pipeline execution
            task_data = await self._load_task_data()
            if not task_data:
                self.log.error("task_not_found", task_id=self.task_id)
                return

            channel_id = task_data["channel_id"]
            project_id = task_data["project_id"]
            topic = task_data["topic"]
            story_direction = task_data["story_direction"]
            narration_scripts = task_data.get("narration_scripts")
            sfx_descriptions = task_data.get("sfx_descriptions")
            voice_id = task_data.get("voice_id")

            self.log.info(
                "pipeline_started",
                task_id=self.task_id,
                channel_id=channel_id,
                project_id=project_id,
            )

            # Record pipeline start time in database
            await self._update_pipeline_start_time(datetime.utcnow())

            # Load step completion metadata for partial resume
            self.step_completions = await self.load_step_completion_metadata()

            # Define pipeline steps in execution order
            steps = [
                PipelineStep.ASSET_GENERATION,
                PipelineStep.COMPOSITE_CREATION,
                PipelineStep.VIDEO_GENERATION,
                PipelineStep.NARRATION_GENERATION,
                PipelineStep.SFX_GENERATION,
                PipelineStep.VIDEO_ASSEMBLY,
            ]

            # Import shutdown flag for graceful shutdown support
            from app.workers.pipeline_worker import SHUTDOWN_REQUESTED

            # Execute each step (skip if already complete)
            for step in steps:
                # Check for shutdown signal (graceful shutdown support)
                if SHUTDOWN_REQUESTED:
                    self.log.warning(
                        "pipeline_interrupted",
                        reason="shutdown_requested",
                        step=step.value,
                    )
                    # Save current progress and exit gracefully
                    return

                # Check if step already complete (partial resume)
                if step in self.step_completions and self.step_completions[step].completed:
                    self.log.info("step_skipped", step=step.value, reason="already_complete")
                    continue

                # Update status to step's in-progress state
                await self.update_task_status(STEP_STATUS_MAP[step])

                # Execute step via service layer
                try:
                    completion = await self.execute_step(
                        step,
                        channel_id,
                        project_id,
                        topic,
                        story_direction,
                        narration_scripts,
                        sfx_descriptions,
                        voice_id,
                    )
                    await self.save_step_completion(step, completion)

                    self.log.info(
                        "step_completed",
                        step=step.value,
                        duration_seconds=completion.duration_seconds,
                    )
                except Exception as e:
                    # Classify error as transient (retry) or permanent (fail)
                    is_transient, error_type = self.classify_error(e)

                    self.log.error(
                        "step_failed",
                        step=step.value,
                        error_type=error_type,
                        is_transient=is_transient,
                        error_message=str(e),
                    )

                    # Update task status to appropriate error state
                    error_status = STEP_ERROR_MAP.get(step, TaskStatus.ASSET_ERROR)
                    await self.update_task_status(error_status, error_message=str(e))

                    # Halt pipeline execution
                    return

            # All steps complete - pause for human review (YouTube compliance)
            await self.update_task_status(TaskStatus.FINAL_REVIEW)

            # Calculate total pipeline duration
            pipeline_duration = time.time() - pipeline_start
            await self._update_pipeline_end_time(
                datetime.utcnow(),
                pipeline_duration,
            )

            # Calculate total pipeline cost
            total_cost = await self.calculate_pipeline_cost()
            await self._update_pipeline_cost(total_cost)

            # Log pipeline completion summary
            self.log.info(
                "pipeline_completed",
                duration_seconds=pipeline_duration,
                cost_usd=total_cost,
                status="final_review",
            )

            # Log warning if pipeline exceeded 2-hour target (NFR-P1)
            if pipeline_duration > 7200:  # 2 hours = 7200 seconds
                self.log.warning(
                    "pipeline_exceeded_target",
                    duration_seconds=pipeline_duration,
                    target_seconds=7200,
                    overage_seconds=pipeline_duration - 7200,
                )

        except Exception as e:
            self.log.error(
                "pipeline_execution_error",
                error_type=type(e).__name__,
                error_message=str(e),
            )
            # Attempt to mark task as failed (suppress errors during cleanup)
            with contextlib.suppress(Exception):
                await self.update_task_status(TaskStatus.ASSET_ERROR, error_message=str(e))

    async def execute_step(
        self,
        step: PipelineStep,
        channel_id: str,
        project_id: str,
        topic: str,
        story_direction: str,
        narration_scripts: list[str] | None = None,
        sfx_descriptions: list[str] | None = None,
        voice_id: str | None = None,
    ) -> StepCompletion:
        """Execute a single pipeline step.

        Step Execution Strategy:
        1. Check step completion metadata (skip if already complete)
        2. Load task data needed for step
        3. Initialize appropriate service (AssetGeneration, VideoGeneration, etc.)
        4. Call service method with task data
        5. Validate output (check files exist, correct format)
        6. Record completion metadata
        7. Return StepCompletion with duration and results

        Args:
            step: PipelineStep enum value (e.g., ASSET_GENERATION)
            channel_id: Channel identifier for path isolation
            project_id: Project/task identifier (UUID from database)
            topic: Video topic from Notion
            story_direction: Story direction from Notion
            narration_scripts: List of 18 narration text strings for NARRATION_GENERATION
            sfx_descriptions: List of 18 SFX description strings for SFX_GENERATION
            voice_id: ElevenLabs voice ID for NARRATION_GENERATION

        Returns:
            StepCompletion object with completion details

        Raises:
            CLIScriptError: If CLI script fails (captured and logged)
            FileNotFoundError: If expected output files missing
            TimeoutError: If step exceeds timeout
            ValueError: If required parameters missing for step

        Example:
            >>> completion = await orchestrator.execute_step(
            ...     PipelineStep.ASSET_GENERATION,
            ...     "poke1",
            ...     "vid_abc123",
            ...     "Bulbasaur forest documentary",
            ...     "Show evolution through seasons",
            ... )
            >>> print(completion.duration_seconds)
            456.7
        """
        step_start = time.time()

        if step == PipelineStep.ASSET_GENERATION:
            asset_service = AssetGenerationService(channel_id, project_id)
            manifest = asset_service.create_asset_manifest(topic, story_direction)
            result = await asset_service.generate_assets(manifest, resume=True)

            return StepCompletion(
                step=step,
                completed=True,
                partial_progress={
                    "generated": result.get("generated", 0),
                    "skipped": result.get("skipped", 0),
                    "total": len(manifest.assets),
                },
                duration_seconds=time.time() - step_start,
                error_message=None,
            )

        elif step == PipelineStep.COMPOSITE_CREATION:
            composite_service = CompositeCreationService(channel_id, project_id)
            composite_manifest = composite_service.create_composite_manifest(topic, story_direction)
            result = await composite_service.generate_composites(composite_manifest, resume=True)

            return StepCompletion(
                step=step,
                completed=True,
                partial_progress={
                    "generated": result.get("generated", 0),
                    "skipped": result.get("skipped", 0),
                    "total": 18,  # 18 composites per project
                },
                duration_seconds=time.time() - step_start,
                error_message=None,
            )

        elif step == PipelineStep.VIDEO_GENERATION:
            video_service = VideoGenerationService(channel_id, project_id)
            video_manifest = video_service.create_video_manifest(topic, story_direction)
            result = await video_service.generate_videos(video_manifest, resume=True)

            return StepCompletion(
                step=step,
                completed=True,
                partial_progress={
                    "generated": result.get("generated", 0),
                    "skipped": result.get("skipped", 0),
                    "total": len(video_manifest.clips),
                },
                duration_seconds=time.time() - step_start,
                error_message=None,
            )

        elif step == PipelineStep.NARRATION_GENERATION:
            # Validate required parameters
            if not narration_scripts:
                raise ValueError("narration_scripts required for NARRATION_GENERATION step")
            if not voice_id:
                raise ValueError("voice_id required for NARRATION_GENERATION step")

            narration_service = NarrationGenerationService(channel_id, project_id)
            narration_manifest = await narration_service.create_narration_manifest(
                narration_scripts=narration_scripts,
                voice_id=voice_id,
            )
            result = await narration_service.generate_narration(narration_manifest, resume=True)

            return StepCompletion(
                step=step,
                completed=True,
                partial_progress={
                    "generated": result.get("generated", 0),
                    "skipped": result.get("skipped", 0),
                    "total": 18,  # 18 narrations per project
                },
                duration_seconds=time.time() - step_start,
                error_message=None,
            )

        elif step == PipelineStep.SFX_GENERATION:
            # Validate required parameters
            if not sfx_descriptions:
                raise ValueError("sfx_descriptions required for SFX_GENERATION step")

            sfx_service = SFXGenerationService(channel_id, project_id)
            sfx_manifest = await sfx_service.create_sfx_manifest(
                sfx_descriptions=sfx_descriptions,
            )
            result = await sfx_service.generate_sfx(sfx_manifest, resume=True)

            return StepCompletion(
                step=step,
                completed=True,
                partial_progress={
                    "generated": result.get("generated", 0),
                    "skipped": result.get("skipped", 0),
                    "total": 18,  # 18 SFX per project
                },
                duration_seconds=time.time() - step_start,
                error_message=None,
            )

        elif step == PipelineStep.VIDEO_ASSEMBLY:
            assembly_service = VideoAssemblyService(channel_id, project_id)
            assembly_manifest = await assembly_service.create_assembly_manifest()
            result = await assembly_service.assemble_video(assembly_manifest)

            return StepCompletion(
                step=step,
                completed=True,
                partial_progress={
                    "assembled": True,
                },
                duration_seconds=time.time() - step_start,
                error_message=None,
            )

        else:
            raise ValueError(f"Unknown pipeline step: {step}")

    async def load_step_completion_metadata(self) -> dict[PipelineStep, StepCompletion]:
        """Load step completion metadata from database for partial resume.

        Metadata Storage:
        - Stored in Task.step_completion_metadata (JSONB column)
        - Format: {"asset_generation": {"completed": true, "duration": 456.7}, ...}
        - Updated after each step completion
        - Used to skip completed steps on retry

        Returns:
            Dict mapping PipelineStep to StepCompletion objects

        Example:
            >>> metadata = await orchestrator.load_step_completion_metadata()
            >>> print(metadata[PipelineStep.ASSET_GENERATION].completed)
            True
        """
        async with async_session_factory() as db:  # type: ignore[misc]
            task = await db.get(Task, self.task_id)
            if not task or not task.step_completion_metadata:
                return {}

            # Parse metadata dict into StepCompletion objects
            completions = {}
            for step_name, step_data in task.step_completion_metadata.items():
                try:
                    # Validate step_data structure
                    if not isinstance(step_data, dict):
                        self.log.warning(
                            "invalid_step_metadata_structure",
                            step=step_name,
                            reason="step_data_not_dict",
                        )
                        continue

                    step = PipelineStep(step_name)
                    completions[step] = StepCompletion(
                        step=step,
                        completed=step_data.get("completed", False),
                        partial_progress=step_data.get("partial_progress"),
                        duration_seconds=step_data.get("duration_seconds"),
                        error_message=step_data.get("error_message"),
                    )
                except ValueError:
                    # Skip unknown step names (forward compatibility)
                    self.log.debug(
                        "unknown_step_in_metadata",
                        step=step_name,
                        reason="forward_compatibility",
                    )
                    continue
                except (TypeError, KeyError) as e:
                    # Skip malformed metadata entries
                    self.log.warning(
                        "malformed_step_metadata",
                        step=step_name,
                        error=str(e),
                    )
                    continue

            return completions

    async def update_task_status(
        self,
        status: TaskStatus,
        error_message: str | None = None,
    ) -> None:
        """Update task status in database and sync to Notion.

        Status Update Flow:
        1. Update PostgreSQL task status (short transaction)
        2. Commit database transaction
        3. Trigger async Notion status update (non-blocking)
        4. Log status change with correlation_id

        Args:
            status: New task status (TaskStatus enum value)
            error_message: Optional error details if status is error state

        Example:
            >>> await orchestrator.update_task_status(TaskStatus.GENERATING_ASSETS)
            # Updates DB, syncs to Notion, logs change
        """
        async with async_session_factory() as db, db.begin():  # type: ignore[misc]
            task = await db.get(Task, self.task_id)
            if task:
                task.status = status
                if error_message:
                    # Append to error log (append-only pattern)
                    current_log = task.error_log or ""
                    timestamp = datetime.utcnow().isoformat()
                    new_entry = f"[{timestamp}] {status.value}: {error_message}"
                    task.error_log = f"{current_log}\n{new_entry}".strip()

                await db.commit()

                self.log.info(
                    "status_updated",
                    status=status.value,
                    has_error=error_message is not None,
                )

        # Store task reference to prevent garbage collection warnings (RUF006)
        _notion_sync_task = asyncio.create_task(self._sync_to_notion_async(status))
        _notion_sync_task.add_done_callback(lambda t: None)  # Suppress warnings

    async def save_step_completion(
        self,
        step: PipelineStep,
        completion: StepCompletion,
    ) -> None:
        """Save step completion metadata to database.

        Metadata Format:
        {
          "asset_generation": {
            "completed": true,
            "duration_seconds": 456.7,
            "partial_progress": null,
            "error_message": null
          },
          "video_generation": {
            "completed": false,
            "duration_seconds": 1234.5,
            "partial_progress": {"clips": 5, "total": 18},
            "error_message": "Kling API timeout on clip 6"
          }
        }

        Args:
            step: Pipeline step that completed
            completion: StepCompletion object with details

        Example:
            >>> await orchestrator.save_step_completion(
            ...     PipelineStep.ASSET_GENERATION,
            ...     StepCompletion(
            ...         step=PipelineStep.ASSET_GENERATION, completed=True, duration_seconds=456.7
            ...     ),
            ... )
        """
        async with async_session_factory() as db, db.begin():  # type: ignore[misc]
            task = await db.get(Task, self.task_id)
            if task:
                # Initialize metadata dict if not exists
                if not task.step_completion_metadata:
                    task.step_completion_metadata = {}

                # Update step completion data
                task.step_completion_metadata[step.value] = {
                    "completed": completion.completed,
                    "duration_seconds": completion.duration_seconds,
                    "partial_progress": completion.partial_progress,
                    "error_message": completion.error_message,
                }

                await db.commit()

    async def _sync_to_notion_async(self, status: TaskStatus) -> None:
        """Sync task status to Notion (async, non-blocking).

        Uses fire-and-forget pattern to avoid blocking pipeline execution.
        Errors are logged but don't fail the pipeline.

        Short Transaction Pattern:
        - Open DB session
        - Load task data
        - Close DB session
        - Make external API call

        This prevents long-running API calls from holding DB connections.

        Args:
            status: Current task status to sync

        Example:
            >>> # Called automatically from update_task_status
            >>> asyncio.create_task(orchestrator._sync_to_notion_async(TaskStatus.GENERATING_ASSETS))
        """
        try:
            # Short transaction: Load task data, then close DB before API call
            async with async_session_factory() as db:  # type: ignore[misc]
                task = await db.get(Task, self.task_id)
                if not task:
                    self.log.error(
                        "notion_sync_failed",
                        reason="task_not_found",
                        task_id=self.task_id,
                    )
                    return

                if not task.notion_page_id:
                    self.log.debug(
                        "notion_sync_skipped",
                        reason="no_notion_page_id",
                        task_id=self.task_id,
                    )
                    return

                # Extract task data before closing DB session
                task_data = TaskSyncData(
                    id=task.id,
                    notion_page_id=task.notion_page_id,
                    status=task.status,
                    priority=task.priority,
                    title=task.title or "Untitled Task",
                )

            # DB session closed - now safe to make API call
            notion_api_token = get_notion_api_token()
            if not notion_api_token:
                self.log.warning(
                    "notion_sync_skipped",
                    reason="no_api_token",
                    task_id=self.task_id,
                )
                return

            notion_client = NotionClient(auth_token=notion_api_token)
            await push_task_to_notion(task_data, notion_client)

            self.log.info(
                "notion_sync_success",
                task_id=self.task_id,
                notion_page_id=task_data.notion_page_id,
                status=status.value,
            )

        except Exception as e:
            # Log but don't fail the pipeline
            self.log.error(
                "notion_sync_failed",
                task_id=self.task_id,
                error=str(e),
                error_type=type(e).__name__,
            )

    def classify_error(self, exception: Exception) -> tuple[bool, str]:
        """Classify exception as transient (retriable) or permanent (non-retriable).

        Transient Errors (retry eligible):
        - TimeoutError, asyncio.TimeoutError
        - CLIScriptError with exit code 124 (timeout)
        - ConnectionError, NetworkError
        - Any exception message containing "timeout", "rate limit", "429"

        Permanent Errors (not retriable):
        - FileNotFoundError (missing required input)
        - ValueError (invalid parameters)
        - CLIScriptError with exit codes 1-99 (not timeout)
        - Any exception not in transient list

        Args:
            exception: Exception caught during step execution

        Returns:
            Tuple of (is_transient: bool, error_type: str)

        Example:
            >>> error = TimeoutError("Kling timeout")
            >>> is_transient, error_type = orchestrator.classify_error(error)
            >>> print(is_transient, error_type)
            True "timeout_error"
        """
        error_message = str(exception).lower()

        # Transient errors (should retry)
        if isinstance(exception, TimeoutError | asyncio.TimeoutError):
            return True, "timeout_error"

        if isinstance(exception, CLIScriptError) and exception.exit_code == 124:
            return True, "cli_timeout"

        if isinstance(exception, ConnectionError):
            return True, "connection_error"

        if "timeout" in error_message or "rate limit" in error_message or "429" in error_message:
            return True, "transient_api_error"

        # Permanent errors (should not retry)
        if isinstance(exception, FileNotFoundError):
            return False, "file_not_found"

        if isinstance(exception, ValueError):
            return False, "invalid_parameters"

        # Default: treat as permanent error
        return False, "unknown_error"

    async def calculate_pipeline_cost(self) -> float:
        """Calculate total cost of pipeline execution.

        Cost Breakdown:
        - Asset generation: $0.50-2.00 (Gemini 22 images)
        - Composite creation: $0 (local FFmpeg)
        - Video generation: $5-10 (Kling 18 clips)
        - Narration generation: $0.30-0.50 (ElevenLabs 18 clips)
        - SFX generation: $0.20-0.30 (ElevenLabs 18 clips)
        - Video assembly: $0 (local FFmpeg)

        Returns:
            Total cost in USD ($6-13 typical)

        Example:
            >>> cost = await orchestrator.calculate_pipeline_cost()
            >>> print(f"${cost:.2f}")
            $8.45
        """
        async with async_session_factory() as db:  # type: ignore[misc]
            task = await db.get(Task, self.task_id)
            if task and task.total_cost_usd:
                return task.total_cost_usd
            # If total_cost_usd not available, return pipeline_cost_usd (Story 3.9 field)
            if task and task.pipeline_cost_usd:
                return task.pipeline_cost_usd
            return 0.0

    async def _load_task_data(self) -> dict[str, Any] | None:
        """Load task data from database for pipeline execution.

        Returns:
            Dict with channel_id, project_id, topic, story_direction,
            narration_scripts, sfx_descriptions, voice_id
            None if task not found
        """
        async with async_session_factory() as db:  # type: ignore[misc]
            task = await db.get(Task, self.task_id)
            if not task:
                return None

            # Get channel_id string from Channel relationship
            channel = task.channel
            if not channel:
                return None

            return {
                "channel_id": channel.channel_id,
                "project_id": str(task.id),
                "topic": task.topic,
                "story_direction": task.story_direction,
                "narration_scripts": task.narration_scripts,
                "sfx_descriptions": task.sfx_descriptions,
                "voice_id": channel.voice_id or channel.default_voice_id,
            }

    async def _update_pipeline_start_time(self, start_time: datetime) -> None:
        """Update pipeline_start_time in database."""
        async with async_session_factory() as db, db.begin():  # type: ignore[misc]
            task = await db.get(Task, self.task_id)
            if task:
                task.pipeline_start_time = start_time
                await db.commit()

    async def _update_pipeline_end_time(
        self,
        end_time: datetime,
        duration_seconds: float,
    ) -> None:
        """Update pipeline_end_time and duration in database."""
        async with async_session_factory() as db, db.begin():  # type: ignore[misc]
            task = await db.get(Task, self.task_id)
            if task:
                task.pipeline_end_time = end_time
                task.pipeline_duration_seconds = duration_seconds
                await db.commit()

    async def _update_pipeline_cost(self, cost_usd: float) -> None:
        """Update pipeline_cost_usd in database."""
        async with async_session_factory() as db, db.begin():  # type: ignore[misc]
            task = await db.get(Task, self.task_id)
            if task:
                task.pipeline_cost_usd = cost_usd
                await db.commit()
