"""Tests for checkpoint progress display in Notion sync (Story 6.3, Task 9).

Tests verify:
- format_checkpoint_progress() formats progress strings correctly
- Progress shown only for error states
- Different progress types (video clips, audio clips, assets)
- Notion sync includes Progress field when checkpoint data available
"""

import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from datetime import datetime, timezone

from app.models import TaskStatus, PriorityLevel
from app.services.notion_sync import (
    format_checkpoint_progress,
    TaskSyncData,
    push_task_to_notion,
)


def test_format_checkpoint_progress_video_clips():
    """Verify video clip progress formatting (Subtask 9.1)."""
    step_metadata = {"completed_video_clips": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]}

    result = format_checkpoint_progress(step_metadata, TaskStatus.VIDEO_ERROR)

    assert result == "Video: 10/18 clips ✓"


def test_format_checkpoint_progress_audio_clips():
    """Verify audio clip progress formatting (Subtask 9.2)."""
    step_metadata = {"completed_narration_clips": [1, 2, 3, 4, 5]}

    result = format_checkpoint_progress(step_metadata, TaskStatus.AUDIO_ERROR)

    assert result == "Audio: 5/18 clips ✓"


def test_format_checkpoint_progress_assets():
    """Verify asset progress formatting (Subtask 9.3)."""
    step_metadata = {"completed_assets": ["char_1", "char_2", "env_1", "env_2", "env_3"]}

    result = format_checkpoint_progress(step_metadata, TaskStatus.ASSET_ERROR)

    assert result == "Assets: 5 complete ✓"


def test_format_checkpoint_progress_no_metadata():
    """Verify None returned when no metadata available."""
    result = format_checkpoint_progress(None, TaskStatus.VIDEO_ERROR)

    assert result is None


def test_format_checkpoint_progress_empty_metadata():
    """Verify None returned when metadata is empty dict."""
    result = format_checkpoint_progress({}, TaskStatus.VIDEO_ERROR)

    assert result is None


def test_format_checkpoint_progress_wrong_status():
    """Verify None returned when status doesn't match metadata."""
    # Has video clips but status is AUDIO_ERROR
    step_metadata = {"completed_video_clips": [1, 2, 3]}

    result = format_checkpoint_progress(step_metadata, TaskStatus.AUDIO_ERROR)

    assert result is None


def test_format_checkpoint_progress_non_error_status():
    """Verify None returned for non-error statuses (no progress shown)."""
    step_metadata = {"completed_video_clips": [1, 2, 3]}

    # Should return None for PROCESSING status
    result = format_checkpoint_progress(step_metadata, TaskStatus.GENERATING_VIDEO)

    assert result is None


def test_format_checkpoint_progress_all_clips_complete():
    """Verify progress shown when all clips complete (edge case)."""
    # All 18 video clips complete
    step_metadata = {"completed_video_clips": list(range(1, 19))}

    result = format_checkpoint_progress(step_metadata, TaskStatus.VIDEO_ERROR)

    assert result == "Video: 18/18 clips ✓"


@pytest.mark.asyncio
async def test_notion_sync_includes_checkpoint_progress():
    """Verify Notion sync includes Progress field when checkpoint available (Subtask 9.4)."""
    # Create mock Notion client
    mock_client = AsyncMock()
    mock_client.update_page_properties = AsyncMock()

    # Create task with checkpoint data
    task_data = TaskSyncData(
        id=uuid4(),
        notion_page_id="notion123",
        status=TaskStatus.VIDEO_ERROR,
        priority=PriorityLevel.HIGH,
        title="Test Video",
        updated_at=datetime.now(timezone.utc),
        retry_count=1,
        next_retry_at=None,
        completed_steps=[],
        step_metadata={"completed_video_clips": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]},
    )

    # Mock the status mapping function
    with patch("app.services.notion_sync.map_internal_status_to_notion", return_value="Error"):
        await push_task_to_notion(task_data, mock_client)

    # Verify Notion API was called
    assert mock_client.update_page_properties.called

    # Extract the properties argument (second argument, after page_id)
    call_args = mock_client.update_page_properties.call_args
    properties = call_args[0][1]  # First positional arg is page_id, second is properties

    # Verify Progress field exists and contains expected value
    assert "Progress" in properties
    assert properties["Progress"]["rich_text"][0]["text"]["content"] == "Video: 10/18 clips ✓"


@pytest.mark.asyncio
async def test_notion_sync_no_progress_without_checkpoint():
    """Verify Notion sync omits Progress field when no checkpoint data."""
    # Create mock Notion client
    mock_client = AsyncMock()
    mock_client.update_page_properties = AsyncMock()

    # Create task without checkpoint data
    task_data = TaskSyncData(
        id=uuid4(),
        notion_page_id="notion123",
        status=TaskStatus.VIDEO_ERROR,
        priority=PriorityLevel.HIGH,
        title="Test Video",
        updated_at=datetime.now(timezone.utc),
        retry_count=1,
        next_retry_at=None,
        completed_steps=[],
        step_metadata=None,  # No checkpoint data
    )

    # Mock the status mapping function
    with patch("app.services.notion_sync.map_internal_status_to_notion", return_value="Error"):
        await push_task_to_notion(task_data, mock_client)

    # Verify Notion API was called
    assert mock_client.update_page_properties.called

    # Extract the properties argument (second argument, after page_id)
    call_args = mock_client.update_page_properties.call_args
    properties = call_args[0][1]  # First positional arg is page_id, second is properties

    # Verify Progress field does NOT exist
    assert "Progress" not in properties


@pytest.mark.asyncio
async def test_notion_sync_audio_checkpoint_progress():
    """Verify audio checkpoint progress syncs correctly."""
    # Create mock Notion client
    mock_client = AsyncMock()
    mock_client.update_page_properties = AsyncMock()

    # Create task with audio checkpoint data
    task_data = TaskSyncData(
        id=uuid4(),
        notion_page_id="notion123",
        status=TaskStatus.AUDIO_ERROR,
        priority=PriorityLevel.NORMAL,
        title="Test Video",
        updated_at=datetime.now(timezone.utc),
        retry_count=2,
        next_retry_at=None,
        completed_steps=[],
        step_metadata={"completed_narration_clips": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]},
    )

    # Mock the status mapping function
    with patch("app.services.notion_sync.map_internal_status_to_notion", return_value="Error"):
        await push_task_to_notion(task_data, mock_client)

    # Extract the properties argument (second argument, after page_id)
    call_args = mock_client.update_page_properties.call_args
    properties = call_args[0][1]  # First positional arg is page_id, second is properties

    # Verify Progress field shows audio progress
    assert "Progress" in properties
    assert properties["Progress"]["rich_text"][0]["text"]["content"] == "Audio: 12/18 clips ✓"


@pytest.mark.asyncio
async def test_notion_sync_asset_checkpoint_progress():
    """Verify asset checkpoint progress syncs correctly."""
    # Create mock Notion client
    mock_client = AsyncMock()
    mock_client.update_page_properties = AsyncMock()

    # Create task with asset checkpoint data
    task_data = TaskSyncData(
        id=uuid4(),
        notion_page_id="notion123",
        status=TaskStatus.ASSET_ERROR,
        priority=PriorityLevel.LOW,
        title="Test Video",
        updated_at=datetime.now(timezone.utc),
        retry_count=0,
        next_retry_at=None,
        completed_steps=[],
        step_metadata={
            "completed_assets": ["char_1", "char_2", "env_1", "env_2", "env_3", "env_4", "env_5"]
        },
    )

    # Mock the status mapping function
    with patch("app.services.notion_sync.map_internal_status_to_notion", return_value="Error"):
        await push_task_to_notion(task_data, mock_client)

    # Extract the properties argument (second argument, after page_id)
    call_args = mock_client.update_page_properties.call_args
    properties = call_args[0][1]  # First positional arg is page_id, second is properties

    # Verify Progress field shows asset progress
    assert "Progress" in properties
    assert properties["Progress"]["rich_text"][0]["text"]["content"] == "Assets: 7 complete ✓"
