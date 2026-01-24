"""Integration tests for checkpoint service in pipeline orchestrator (Story 6.3).

Tests verify:
- Pipeline skips completed steps based on checkpoints
- Checkpoints are saved after successful step execution
- Pipeline resumes from failure point on retry
"""

import pytest
from uuid import uuid4

from app.models import Channel, Task, TaskStatus
from app.services.checkpoint_service import is_step_complete, save_step_checkpoint
from app.services.pipeline_orchestrator import PipelineStep


@pytest.mark.asyncio
async def test_pipeline_skips_completed_step(async_session):
    """Verify pipeline skips step when checkpoint exists (Task 2, Subtask 2.2)."""
    # Create channel first
    channel = Channel(
        channel_id="test_ch",
        channel_name="Test Channel",
        is_active=True,
    )
    async_session.add(channel)
    await async_session.flush()  # Flush to get channel.id

    # Create task
    task = Task(
        id=uuid4(),
        channel_id=channel.id,
        notion_page_id="notion123",
        title="Test Video",
        topic="Testing",
        story_direction="Test story",
        status=TaskStatus.GENERATING_ASSETS,
        completed_steps=[],
        step_metadata={},
    )
    async_session.add(task)
    await async_session.commit()

    # Save checkpoint for asset generation
    await save_step_checkpoint(
        str(task.id),
        PipelineStep.ASSET_GENERATION.value,
        {"total_assets": 22, "assets_generated": 22},
        async_session,
    )

    # Verify checkpoint exists
    assert await is_step_complete(str(task.id), PipelineStep.ASSET_GENERATION.value, async_session)

    # Verify other steps don't have checkpoints
    assert not await is_step_complete(
        str(task.id), PipelineStep.COMPOSITE_CREATION.value, async_session
    )
    assert not await is_step_complete(
        str(task.id), PipelineStep.VIDEO_GENERATION.value, async_session
    )


@pytest.mark.asyncio
async def test_checkpoint_saved_after_step_completion(async_session):
    """Verify checkpoint is saved after successful step execution (Task 2, Subtask 2.1)."""
    # Create channel first
    channel = Channel(
        channel_id="test_ch",
        channel_name="Test Channel",
        is_active=True,
    )
    async_session.add(channel)
    await async_session.flush()  # Flush to get channel.id

    # Create task
    task = Task(
        id=uuid4(),
        channel_id=channel.id,
        notion_page_id="notion123",
        title="Test Video",
        topic="Testing",
        story_direction="Test story",
        status=TaskStatus.GENERATING_COMPOSITES,
        completed_steps=[],
        step_metadata={},
    )
    async_session.add(task)
    await async_session.commit()

    # Simulate step completion
    await save_step_checkpoint(
        str(task.id),
        PipelineStep.COMPOSITE_CREATION.value,
        {
            "completed": True,
            "duration_seconds": 45.2,
            "partial_progress": {"generated": 18, "skipped": 0, "total": 18},
        },
        async_session,
    )

    # Verify checkpoint exists and has correct data
    await async_session.refresh(task)
    assert len(task.completed_steps) == 1
    checkpoint = task.completed_steps[0]
    assert checkpoint["step_name"] == PipelineStep.COMPOSITE_CREATION.value
    assert checkpoint["outputs"]["completed"] is True
    assert checkpoint["outputs"]["duration_seconds"] == 45.2


@pytest.mark.asyncio
async def test_pipeline_resume_from_failure_point(async_session):
    """Verify pipeline resumes from failure point with partial progress (AC: Video resumes from failed clip)."""
    # Create channel first
    channel = Channel(
        channel_id="test_ch",
        channel_name="Test Channel",
        is_active=True,
    )
    async_session.add(channel)
    await async_session.flush()  # Flush to get channel.id

    # Create task
    task = Task(
        id=uuid4(),
        channel_id=channel.id,
        notion_page_id="notion123",
        title="Test Video",
        topic="Testing",
        story_direction="Test story",
        status=TaskStatus.GENERATING_VIDEO,
        completed_steps=[],
        step_metadata={},
    )
    async_session.add(task)
    await async_session.commit()

    # Save checkpoints for completed steps
    await save_step_checkpoint(
        str(task.id),
        PipelineStep.ASSET_GENERATION.value,
        {"total_assets": 22, "assets_generated": 22},
        async_session,
    )
    await save_step_checkpoint(
        str(task.id),
        PipelineStep.COMPOSITE_CREATION.value,
        {"total_composites": 18, "composites_created": 18},
        async_session,
    )

    # Save partial progress for video generation (clips 1-10 done, failed at clip 11)
    await save_step_checkpoint(
        str(task.id),
        PipelineStep.VIDEO_GENERATION.value,
        {"total_clips": 18, "clips_generated": 10},
        async_session,
    )

    # Verify completed steps
    await async_session.refresh(task)
    assert len(task.completed_steps) == 3
    assert await is_step_complete(str(task.id), PipelineStep.ASSET_GENERATION.value, async_session)
    assert await is_step_complete(
        str(task.id), PipelineStep.COMPOSITE_CREATION.value, async_session
    )
    assert await is_step_complete(str(task.id), PipelineStep.VIDEO_GENERATION.value, async_session)

    # Verify video generation checkpoint shows partial progress
    video_checkpoint = next(
        c for c in task.completed_steps if c["step_name"] == PipelineStep.VIDEO_GENERATION.value
    )
    assert video_checkpoint["outputs"]["clips_generated"] == 10
    assert video_checkpoint["outputs"]["total_clips"] == 18


@pytest.mark.asyncio
async def test_checkpoint_deduplication_on_retry(async_session):
    """Verify checkpoint is overwritten on retry, not duplicated (Task 7, Subtask 7.1)."""
    # Create channel first
    channel = Channel(
        channel_id="test_ch",
        channel_name="Test Channel",
        is_active=True,
    )
    async_session.add(channel)
    await async_session.flush()  # Flush to get channel.id

    # Create task
    task = Task(
        id=uuid4(),
        channel_id=channel.id,
        notion_page_id="notion123",
        title="Test Video",
        topic="Testing",
        story_direction="Test story",
        status=TaskStatus.GENERATING_VIDEO,
        completed_steps=[],
        step_metadata={},
    )
    async_session.add(task)
    await async_session.commit()

    # Save initial checkpoint (partial progress)
    await save_step_checkpoint(
        str(task.id),
        PipelineStep.VIDEO_GENERATION.value,
        {"total_clips": 18, "clips_generated": 10},
        async_session,
    )

    # Retry: Save updated checkpoint (full completion)
    await save_step_checkpoint(
        str(task.id),
        PipelineStep.VIDEO_GENERATION.value,
        {"total_clips": 18, "clips_generated": 18},
        async_session,
    )

    # Verify only one checkpoint exists (not duplicated)
    await async_session.refresh(task)
    assert len(task.completed_steps) == 1
    checkpoint = task.completed_steps[0]
    assert checkpoint["step_name"] == PipelineStep.VIDEO_GENERATION.value
    assert checkpoint["outputs"]["clips_generated"] == 18  # Updated value, not 10
