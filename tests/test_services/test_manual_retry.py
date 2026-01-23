"""Tests for manual retry logic (Story 6.7).

This test module validates:
- Manual retry transition detection (Task 1)
- Retry reset logic (Task 2)
- Error log preservation (Task 4)
- Smart retry routing (Task 5)
- Integration with Notion sync service (Task 3)

Test Coverage:
- 18+ unit and integration tests for comprehensive validation
- Edge cases and error scenarios
- Integration with Story 6.1, 6.2, 6.3, 6.5

Related:
    - Story 6.7 Task 7: Write comprehensive tests
    - Subtasks 7.1-7.5: Test all retry paths and behaviors
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from app.models import Task, TaskStatus, PriorityLevel
from app.services.notion_sync import (
    is_manual_retry_transition,
    get_failed_step_from_status,
    handle_manual_retry,
)
from app.services.checkpoint_service import (
    save_step_checkpoint,
    get_step_checkpoint,
    clear_step_checkpoint_for_retry,
)
from tests.support.factories import create_task


# =============================================================================
# Task 1 Tests: Manual Retry Transition Detection (Subtask 7.1)
# =============================================================================


def test_is_manual_retry_transition_asset_error_to_queued():
    """Test detection of ASSET_ERROR → QUEUED transition."""
    assert is_manual_retry_transition(
        TaskStatus.ASSET_ERROR,
        TaskStatus.QUEUED
    ) is True


def test_is_manual_retry_transition_video_error_to_queued():
    """Test detection of VIDEO_ERROR → QUEUED transition."""
    assert is_manual_retry_transition(
        TaskStatus.VIDEO_ERROR,
        TaskStatus.QUEUED
    ) is True


def test_is_manual_retry_transition_video_error_to_assets_approved():
    """Test detection of VIDEO_ERROR → ASSETS_APPROVED transition (partial retry)."""
    assert is_manual_retry_transition(
        TaskStatus.VIDEO_ERROR,
        TaskStatus.ASSETS_APPROVED
    ) is True


def test_is_manual_retry_transition_audio_error_to_video_approved():
    """Test detection of AUDIO_ERROR → VIDEO_APPROVED transition (partial retry)."""
    assert is_manual_retry_transition(
        TaskStatus.AUDIO_ERROR,
        TaskStatus.VIDEO_APPROVED
    ) is True


def test_is_manual_retry_transition_upload_error_to_approved():
    """Test detection of UPLOAD_ERROR → APPROVED transition (partial retry)."""
    assert is_manual_retry_transition(
        TaskStatus.UPLOAD_ERROR,
        TaskStatus.APPROVED
    ) is True




def test_is_manual_retry_transition_normal_progression_not_detected():
    """Test that normal status progression does NOT trigger manual retry."""
    # Normal pipeline flow should NOT be detected as manual retry
    assert is_manual_retry_transition(
        TaskStatus.GENERATING_VIDEO,
        TaskStatus.VIDEO_READY
    ) is False

    assert is_manual_retry_transition(
        TaskStatus.ASSETS_APPROVED,
        TaskStatus.GENERATING_VIDEO
    ) is False

    assert is_manual_retry_transition(
        TaskStatus.QUEUED,
        TaskStatus.CLAIMED
    ) is False


def test_is_manual_retry_transition_invalid_retry_target():
    """Test that invalid retry transitions are NOT detected."""
    # ASSET_ERROR → VIDEO_APPROVED is invalid (wrong step)
    assert is_manual_retry_transition(
        TaskStatus.ASSET_ERROR,
        TaskStatus.VIDEO_APPROVED
    ) is False

    # VIDEO_ERROR → UPLOADING is invalid (wrong step)
    assert is_manual_retry_transition(
        TaskStatus.VIDEO_ERROR,
        TaskStatus.UPLOADING
    ) is False


# =============================================================================
# Task 2 Tests: Retry Reset Logic (Subtask 7.2)
# =============================================================================


@pytest.mark.asyncio
async def test_handle_manual_retry_resets_retry_count(async_session):
    """Verify manual retry resets retry_count to 0."""
    # Create task with exhausted retries
    task = create_task(
        status=TaskStatus.VIDEO_ERROR,
        retry_count=3,
        error_log="Original error: Video generation timeout"
    )
    async_session.add(task)
    await async_session.commit()

    # Trigger manual retry
    await handle_manual_retry(
        task=task,
        old_status=TaskStatus.VIDEO_ERROR,
        new_status=TaskStatus.QUEUED,
        session=async_session,
    )

    # Verify retry_count reset
    assert task.retry_count == 0, "retry_count should be reset to 0"
    assert task.next_retry_at is None, "next_retry_at should be cleared"


@pytest.mark.asyncio
async def test_handle_manual_retry_preserves_error_log(async_session):
    """Verify manual retry preserves existing error log."""
    # Create task with existing error log
    original_log = "Original error: Video generation timeout\nRetry 1: Failed\nRetry 2: Failed"
    task = create_task(
        status=TaskStatus.VIDEO_ERROR,
        retry_count=3,
        error_log=original_log
    )
    async_session.add(task)
    await async_session.commit()

    # Trigger manual retry
    await handle_manual_retry(
        task=task,
        old_status=TaskStatus.VIDEO_ERROR,
        new_status=TaskStatus.QUEUED,
        session=async_session,
    )

    # Verify error log preserved AND manual retry marker added
    assert original_log in task.error_log, "Original error log should be preserved"
    assert "MANUAL RETRY TRIGGERED" in task.error_log, "Manual retry marker should be added"
    assert "previous status: video_error" in task.error_log.lower()
    assert "new status: queued" in task.error_log.lower()


@pytest.mark.asyncio
async def test_handle_manual_retry_appends_marker_to_empty_log(async_session):
    """Verify manual retry creates error log with marker if none exists."""
    # Create task with no error log
    task = create_task(
        status=TaskStatus.VIDEO_ERROR,
        retry_count=1,
        error_log=None
    )
    async_session.add(task)
    await async_session.commit()

    # Trigger manual retry
    await handle_manual_retry(
        task=task,
        old_status=TaskStatus.VIDEO_ERROR,
        new_status=TaskStatus.QUEUED,
        session=async_session,
    )

    # Verify error log created with marker
    assert task.error_log is not None, "Error log should be created"
    assert "MANUAL RETRY TRIGGERED" in task.error_log


@pytest.mark.asyncio
async def test_handle_manual_retry_updates_status(async_session):
    """Verify manual retry updates task status to new_status."""
    task = create_task(
        status=TaskStatus.VIDEO_ERROR,
        retry_count=2
    )
    async_session.add(task)
    await async_session.commit()

    # Trigger manual retry
    await handle_manual_retry(
        task=task,
        old_status=TaskStatus.VIDEO_ERROR,
        new_status=TaskStatus.QUEUED,
        session=async_session,
    )

    # Verify status updated
    assert task.status == TaskStatus.QUEUED


# =============================================================================
# Task 5 Tests: Smart Retry Routing (Subtask 7.3)
# =============================================================================


def test_get_failed_step_from_status_maps_error_statuses():
    """Verify error status → failed step mapping."""
    assert get_failed_step_from_status(TaskStatus.ASSET_ERROR) == "asset_generation"
    assert get_failed_step_from_status(TaskStatus.VIDEO_ERROR) == "video_generation"
    assert get_failed_step_from_status(TaskStatus.AUDIO_ERROR) == "audio_generation"
    assert get_failed_step_from_status(TaskStatus.UPLOAD_ERROR) == "youtube_upload"




@pytest.mark.asyncio
async def test_clear_step_checkpoint_for_retry_selective(async_session):
    """Verify selective checkpoint clearing preserves completed steps."""
    # Create task with checkpoints
    task = create_task(status=TaskStatus.VIDEO_ERROR)
    async_session.add(task)
    await async_session.commit()

    # Save checkpoints for asset and video steps
    await save_step_checkpoint(
        task_id=str(task.id),
        step_name="asset_generation",
        outputs={"total_assets": 20, "completed": True},
        db=async_session
    )
    await save_step_checkpoint(
        task_id=str(task.id),
        step_name="video_generation",
        outputs={"total_clips": 18, "completed_clips": 10},
        db=async_session
    )

    # Clear video checkpoint (failed step)
    await clear_step_checkpoint_for_retry(
        task_id=str(task.id),
        step_name="video_generation",
        db=async_session
    )

    # Verify asset checkpoint preserved
    asset_checkpoint = await get_step_checkpoint(
        task_id=str(task.id),
        step_name="asset_generation",
        db=async_session
    )
    assert asset_checkpoint is not None, "Asset checkpoint should be preserved"
    assert asset_checkpoint["outputs"]["completed"] is True

    # Verify video checkpoint cleared
    video_checkpoint = await get_step_checkpoint(
        task_id=str(task.id),
        step_name="video_generation",
        db=async_session
    )
    assert video_checkpoint is None, "Video checkpoint should be cleared"


@pytest.mark.asyncio
async def test_clear_step_checkpoint_for_retry_full_restart(async_session):
    """Verify full restart (None step_name) clears ALL checkpoints."""
    # Create task with multiple checkpoints
    task = create_task(status=TaskStatus.UPLOAD_ERROR)
    async_session.add(task)
    await async_session.commit()

    # Save checkpoints for multiple steps
    await save_step_checkpoint(
        task_id=str(task.id),
        step_name="asset_generation",
        outputs={"completed": True},
        db=async_session
    )
    await save_step_checkpoint(
        task_id=str(task.id),
        step_name="video_generation",
        outputs={"completed": True},
        db=async_session
    )

    # Clear all checkpoints (FAILED → full restart)
    await clear_step_checkpoint_for_retry(
        task_id=str(task.id),
        step_name=None,  # None = clear all
        db=async_session
    )

    # Verify all checkpoints cleared
    asset_checkpoint = await get_step_checkpoint(
        task_id=str(task.id),
        step_name="asset_generation",
        db=async_session
    )
    assert asset_checkpoint is None, "All checkpoints should be cleared"

    video_checkpoint = await get_step_checkpoint(
        task_id=str(task.id),
        step_name="video_generation",
        db=async_session
    )
    assert video_checkpoint is None, "All checkpoints should be cleared"


# =============================================================================
# Task 4 Tests: Error Log Preservation (Subtask 7.4)
# =============================================================================


@pytest.mark.asyncio
async def test_error_log_accumulation_across_multiple_retries(async_session):
    """Verify error log accumulates across multiple manual retries."""
    task = create_task(
        status=TaskStatus.VIDEO_ERROR,
        error_log="Initial failure: Timeout"
    )
    async_session.add(task)
    await async_session.commit()

    # First manual retry
    await handle_manual_retry(
        task=task,
        old_status=TaskStatus.VIDEO_ERROR,
        new_status=TaskStatus.QUEUED,
        session=async_session,
    )

    first_log = task.error_log
    assert "Initial failure: Timeout" in first_log
    assert first_log.count("MANUAL RETRY TRIGGERED") == 1

    # Simulate second failure and retry (bypass validator for test)
    # In real scenario, task would go through full pipeline: QUEUED → CLAIMED → ... → VIDEO_ERROR
    await async_session.refresh(task)
    # Use SQLAlchemy update to bypass status validator
    from sqlalchemy import update as sql_update
    from app.models import Task as TaskModel
    await async_session.execute(
        sql_update(TaskModel).where(TaskModel.id == task.id).values(
            status=TaskStatus.VIDEO_ERROR,
            retry_count=2
        )
    )
    await async_session.commit()
    await async_session.refresh(task)

    await handle_manual_retry(
        task=task,
        old_status=TaskStatus.VIDEO_ERROR,
        new_status=TaskStatus.QUEUED,
        session=async_session,
    )

    # Verify both manual retry markers present
    assert "Initial failure: Timeout" in task.error_log
    assert task.error_log.count("MANUAL RETRY TRIGGERED") == 2


@pytest.mark.asyncio
async def test_error_log_includes_timestamp_and_status_details(async_session):
    """Verify error log includes timestamp, old/new status, and retry count."""
    task = create_task(
        status=TaskStatus.ASSET_ERROR,
        retry_count=3,
        error_log="Asset generation failed: API timeout"
    )
    async_session.add(task)
    await async_session.commit()

    # Trigger manual retry
    await handle_manual_retry(
        task=task,
        old_status=TaskStatus.ASSET_ERROR,
        new_status=TaskStatus.QUEUED,
        session=async_session,
    )

    # Verify log includes required details
    assert "Timestamp:" in task.error_log
    assert "previous status: asset_error" in task.error_log.lower()
    assert "new status: queued" in task.error_log.lower()
    # Note: retry_count might be 0 by default in factory, so check for "reset automatic retry counter"
    assert "reset automatic retry counter" in task.error_log.lower()


# =============================================================================
# Integration Tests: End-to-End Manual Retry Flow (Subtask 7.5)
# =============================================================================


@pytest.mark.asyncio
async def test_end_to_end_manual_retry_from_video_error(async_session):
    """Test complete manual retry flow from VIDEO_ERROR → QUEUED."""
    # Setup: Task failed video generation with 3 retries exhausted
    task = create_task(
        status=TaskStatus.VIDEO_ERROR,
        retry_count=3,
        next_retry_at=None,  # Retries exhausted
        error_log="Video generation failed: KIE.ai timeout after 10 minutes"
    )
    async_session.add(task)
    await async_session.commit()

    # Save asset checkpoint (completed)
    await save_step_checkpoint(
        task_id=str(task.id),
        step_name="asset_generation",
        outputs={"total_assets": 22, "completed": True},
        db=async_session
    )

    # Save video checkpoint (partial - 10/18 clips)
    await save_step_checkpoint(
        task_id=str(task.id),
        step_name="video_generation",
        outputs={"total_clips": 18, "completed_clips": 10},
        db=async_session
    )

    # User triggers manual retry by changing status to QUEUED in Notion
    await handle_manual_retry(
        task=task,
        old_status=TaskStatus.VIDEO_ERROR,
        new_status=TaskStatus.QUEUED,
        session=async_session,
    )

    # Verify state after manual retry
    assert task.status == TaskStatus.QUEUED, "Status should be QUEUED for worker claiming"
    assert task.retry_count == 0, "retry_count should reset to 0"
    assert task.next_retry_at is None, "next_retry_at should be cleared"

    # Verify error log preserved with manual retry marker
    assert "Video generation failed" in task.error_log
    assert "MANUAL RETRY TRIGGERED" in task.error_log
    assert "previous status: video_error" in task.error_log.lower()

    # Verify asset checkpoint preserved
    asset_checkpoint = await get_step_checkpoint(
        task_id=str(task.id),
        step_name="asset_generation",
        db=async_session
    )
    assert asset_checkpoint is not None, "Asset checkpoint should be preserved"
    assert asset_checkpoint["outputs"]["completed"] is True

    # Verify video checkpoint cleared
    video_checkpoint = await get_step_checkpoint(
        task_id=str(task.id),
        step_name="video_generation",
        db=async_session
    )
    assert video_checkpoint is None, "Video checkpoint should be cleared for re-execution"


@pytest.mark.asyncio
async def test_clear_all_checkpoints_when_step_name_is_none(async_session):
    """Test that clear_step_checkpoint_for_retry clears ALL checkpoints when step_name=None."""
    # Setup: Task with multiple checkpoints
    task = create_task(
        status=TaskStatus.UPLOAD_ERROR,  # Use valid error status
        retry_count=3,
        error_log="Upload failed repeatedly"
    )
    async_session.add(task)
    await async_session.commit()

    # Save checkpoints for multiple steps
    await save_step_checkpoint(
        task_id=str(task.id),
        step_name="asset_generation",
        outputs={"completed": True},
        db=async_session
    )
    await save_step_checkpoint(
        task_id=str(task.id),
        step_name="video_generation",
        outputs={"completed": True},
        db=async_session
    )

    # Clear all checkpoints by passing step_name=None
    await clear_step_checkpoint_for_retry(
        task_id=str(task.id),
        step_name=None,  # None = clear all checkpoints
        db=async_session
    )

    # Verify all checkpoints cleared
    asset_checkpoint = await get_step_checkpoint(
        task_id=str(task.id),
        step_name="asset_generation",
        db=async_session
    )
    assert asset_checkpoint is None, "All checkpoints should be cleared"

    video_checkpoint = await get_step_checkpoint(
        task_id=str(task.id),
        step_name="video_generation",
        db=async_session
    )
    assert video_checkpoint is None, "All checkpoints should be cleared"
