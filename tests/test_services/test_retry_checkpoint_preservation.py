"""Tests for checkpoint preservation during retry (Story 6.3, Task 6).

Tests verify:
- completed_steps is preserved when task is claimed for retry
- step_metadata is preserved when task is claimed for retry
- Status transitions correctly from error state to QUEUED
- next_retry_at is cleared when task is claimed
"""

import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.models import Channel, Task, TaskStatus
from app.services.pipeline_orchestrator import PipelineStep
from app.services.retry_orchestrator import claim_retry_tasks


@pytest.mark.asyncio
async def test_preserve_completed_steps_during_retry(async_session):
    """Verify completed_steps preserved when claiming retry task."""
    # Create channel
    channel = Channel(
        channel_id="test_ch",
        channel_name="Test Channel",
        is_active=True,
    )
    async_session.add(channel)
    await async_session.flush()

    # Create task with completed steps and ready for retry
    completed_steps = [
        {
            "step_name": PipelineStep.ASSET_GENERATION.value,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": 120.5,
            "outputs": {"generated": 22, "skipped": 0},
        },
        {
            "step_name": PipelineStep.COMPOSITE_CREATION.value,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": 45.2,
            "outputs": {"generated": 18, "skipped": 0},
        },
    ]

    task = Task(
        id=uuid4(),
        channel_id=channel.id,
        notion_page_id="notion123",
        title="Test Video",
        topic="Testing",
        story_direction="Test story",
        status=TaskStatus.VIDEO_ERROR,  # Failed at video generation
        retry_count=1,
        next_retry_at=datetime.now(timezone.utc) - timedelta(minutes=1),  # Ready for retry
        completed_steps=completed_steps,  # Checkpoint data
        step_metadata={"completed_video_clips": [1, 2, 3]},  # Sub-step checkpoint
    )
    async_session.add(task)
    await async_session.commit()

    # Claim task for retry
    claimed_tasks = await claim_retry_tasks(async_session)
    await async_session.commit()

    # Verify task was claimed
    assert len(claimed_tasks) == 1
    claimed_task = claimed_tasks[0]

    # Verify checkpoint state preserved
    assert claimed_task.completed_steps == completed_steps
    assert claimed_task.step_metadata == {"completed_video_clips": [1, 2, 3]}

    # Verify status transition
    assert claimed_task.status == TaskStatus.QUEUED

    # Verify retry timestamp cleared
    assert claimed_task.next_retry_at is None

    # Verify retry count preserved
    assert claimed_task.retry_count == 1


@pytest.mark.asyncio
async def test_preserve_step_metadata_during_retry(async_session):
    """Verify step_metadata preserved when claiming retry task."""
    # Create channel
    channel = Channel(
        channel_id="test_ch",
        channel_name="Test Channel",
        is_active=True,
    )
    async_session.add(channel)
    await async_session.flush()

    # Create task with sub-step checkpoints and ready for retry
    step_metadata = {
        "completed_video_clips": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        "completed_narration_clips": [1, 2, 3, 4, 5],
        "completed_assets": ["char_1", "char_2", "env_1", "env_2"],
    }

    task = Task(
        id=uuid4(),
        channel_id=channel.id,
        notion_page_id="notion123",
        title="Test Video",
        topic="Testing",
        story_direction="Test story",
        status=TaskStatus.AUDIO_ERROR,  # Failed at audio generation
        retry_count=2,
        next_retry_at=datetime.now(timezone.utc) - timedelta(minutes=5),  # Ready for retry
        completed_steps=[],
        step_metadata=step_metadata,  # Sub-step checkpoint data
    )
    async_session.add(task)
    await async_session.commit()

    # Claim task for retry
    claimed_tasks = await claim_retry_tasks(async_session)
    await async_session.commit()

    # Verify task was claimed
    assert len(claimed_tasks) == 1
    claimed_task = claimed_tasks[0]

    # Verify step_metadata preserved with all keys
    assert claimed_task.step_metadata == step_metadata
    assert claimed_task.step_metadata["completed_video_clips"] == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    assert claimed_task.step_metadata["completed_narration_clips"] == [1, 2, 3, 4, 5]
    assert claimed_task.step_metadata["completed_assets"] == ["char_1", "char_2", "env_1", "env_2"]

    # Verify status transition
    assert claimed_task.status == TaskStatus.QUEUED

    # Verify retry count preserved
    assert claimed_task.retry_count == 2


@pytest.mark.asyncio
async def test_preserve_both_checkpoint_types_during_retry(async_session):
    """Verify both completed_steps and step_metadata preserved together."""
    # Create channel
    channel = Channel(
        channel_id="test_ch",
        channel_name="Test Channel",
        is_active=True,
    )
    async_session.add(channel)
    await async_session.flush()

    # Create task with both checkpoint types
    completed_steps = [
        {
            "step_name": PipelineStep.ASSET_GENERATION.value,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": 120.5,
            "outputs": {"generated": 22, "skipped": 0},
        },
    ]

    step_metadata = {
        "completed_video_clips": [1, 2, 3],
        "completed_assets": ["char_1", "env_1"],
    }

    task = Task(
        id=uuid4(),
        channel_id=channel.id,
        notion_page_id="notion123",
        title="Test Video",
        topic="Testing",
        story_direction="Test story",
        status=TaskStatus.VIDEO_ERROR,
        retry_count=0,
        next_retry_at=datetime.now(timezone.utc) - timedelta(seconds=30),
        completed_steps=completed_steps,
        step_metadata=step_metadata,
    )
    async_session.add(task)
    await async_session.commit()

    # Claim task for retry
    claimed_tasks = await claim_retry_tasks(async_session)
    await async_session.commit()

    # Verify both checkpoint types preserved
    claimed_task = claimed_tasks[0]
    assert claimed_task.completed_steps == completed_steps
    assert claimed_task.step_metadata == step_metadata


@pytest.mark.asyncio
async def test_multiple_tasks_checkpoint_preservation(async_session):
    """Verify checkpoint preservation works for multiple tasks."""
    # Create channel
    channel = Channel(
        channel_id="test_ch",
        channel_name="Test Channel",
        is_active=True,
    )
    async_session.add(channel)
    await async_session.flush()

    # Create multiple tasks with different checkpoint states
    task1 = Task(
        id=uuid4(),
        channel_id=channel.id,
        notion_page_id="notion123",
        title="Test Video 1",
        topic="Testing 1",
        story_direction="Test story 1",
        status=TaskStatus.VIDEO_ERROR,
        retry_count=1,
        next_retry_at=datetime.now(timezone.utc) - timedelta(minutes=2),
        completed_steps=[{"step_name": PipelineStep.ASSET_GENERATION.value}],
        step_metadata={"completed_video_clips": [1, 2, 3]},
    )

    task2 = Task(
        id=uuid4(),
        channel_id=channel.id,
        notion_page_id="notion456",
        title="Test Video 2",
        topic="Testing 2",
        story_direction="Test story 2",
        status=TaskStatus.AUDIO_ERROR,
        retry_count=2,
        next_retry_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        completed_steps=[
            {"step_name": PipelineStep.ASSET_GENERATION.value},
            {"step_name": PipelineStep.VIDEO_GENERATION.value},
        ],
        step_metadata={"completed_narration_clips": [1, 2, 3, 4, 5]},
    )

    async_session.add_all([task1, task2])
    await async_session.commit()

    # Claim tasks for retry
    claimed_tasks = await claim_retry_tasks(async_session)
    await async_session.commit()

    # Verify both tasks claimed
    assert len(claimed_tasks) == 2

    # Find tasks by their original IDs
    claimed_task1 = next(t for t in claimed_tasks if t.id == task1.id)
    claimed_task2 = next(t for t in claimed_tasks if t.id == task2.id)

    # Verify task1 checkpoint preserved
    assert len(claimed_task1.completed_steps) == 1
    assert claimed_task1.step_metadata["completed_video_clips"] == [1, 2, 3]

    # Verify task2 checkpoint preserved
    assert len(claimed_task2.completed_steps) == 2
    assert claimed_task2.step_metadata["completed_narration_clips"] == [1, 2, 3, 4, 5]
