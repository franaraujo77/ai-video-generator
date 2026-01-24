"""Tests for checkpoint service error progress extraction (Story 6.4, Task 7).

This module tests extract_partial_progress_for_error() which centralizes the
logic for extracting checkpoint progress data for ErrorPayload population.

Test Coverage:
    - Video generation checkpoint extraction
    - Asset generation checkpoint extraction (with variable total_assets)
    - Narration generation checkpoint extraction
    - SFX generation checkpoint extraction
    - Empty metadata handling (returns empty dict)
    - Missing step-specific metadata (returns empty dict)
"""

import pytest
from uuid import uuid4

from app.models import Task, TaskStatus
from app.services.checkpoint_service import extract_partial_progress_for_error


class TestExtractPartialProgressForError:
    """Test extract_partial_progress_for_error() function."""

    def test_extract_video_generation_progress(self):
        """Verify video generation checkpoint extraction."""
        # Arrange
        task = Task(
            id=uuid4(),
            channel_id=uuid4(),
            notion_page_id="test-page-id",
            title="Test Video",
            topic="Test",
            story_direction="Test story",
            status=TaskStatus.VIDEO_ERROR,
            step_metadata={"completed_video_clips": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]},
        )

        # Act
        partial_progress = extract_partial_progress_for_error(task, "video_generation")

        # Assert
        assert partial_progress == {
            "completed_video_clips": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            "total_clips": 18,
        }

    def test_extract_asset_generation_progress(self):
        """Verify asset generation checkpoint extraction with total_assets."""
        # Arrange
        task = Task(
            id=uuid4(),
            channel_id=uuid4(),
            notion_page_id="test-page-id",
            title="Test Video",
            topic="Test",
            story_direction="Test story",
            status=TaskStatus.ASSET_ERROR,
            step_metadata={
                "completed_assets": [1, 2, 3, 4, 5],
                "total_assets": 22,
            },
        )

        # Act
        partial_progress = extract_partial_progress_for_error(task, "asset_generation")

        # Assert
        assert partial_progress == {
            "completed_assets": [1, 2, 3, 4, 5],
            "total_assets": 22,
        }

    def test_extract_asset_generation_progress_without_total(self):
        """Verify asset generation defaults to 0 if total_assets missing."""
        # Arrange
        task = Task(
            id=uuid4(),
            channel_id=uuid4(),
            notion_page_id="test-page-id",
            title="Test Video",
            topic="Test",
            story_direction="Test story",
            status=TaskStatus.ASSET_ERROR,
            step_metadata={"completed_assets": [1, 2, 3]},
        )

        # Act
        partial_progress = extract_partial_progress_for_error(task, "asset_generation")

        # Assert
        assert partial_progress == {
            "completed_assets": [1, 2, 3],
            "total_assets": 0,
        }

    def test_extract_narration_generation_progress(self):
        """Verify narration generation checkpoint extraction."""
        # Arrange
        task = Task(
            id=uuid4(),
            channel_id=uuid4(),
            notion_page_id="test-page-id",
            title="Test Video",
            topic="Test",
            story_direction="Test story",
            status=TaskStatus.AUDIO_ERROR,
            step_metadata={"completed_narration_clips": [1, 2, 3, 4, 5, 6, 7]},
        )

        # Act
        partial_progress = extract_partial_progress_for_error(task, "narration_generation")

        # Assert
        assert partial_progress == {
            "completed_narration_clips": [1, 2, 3, 4, 5, 6, 7],
            "total_clips": 18,
        }

    def test_extract_sfx_generation_progress(self):
        """Verify SFX generation checkpoint extraction."""
        # Arrange
        task = Task(
            id=uuid4(),
            channel_id=uuid4(),
            notion_page_id="test-page-id",
            title="Test Video",
            topic="Test",
            story_direction="Test story",
            status=TaskStatus.AUDIO_ERROR,  # SFX uses AUDIO_ERROR status
            step_metadata={"completed_sfx_clips": [1, 2, 3, 4, 5, 6, 7, 8, 9]},
        )

        # Act
        partial_progress = extract_partial_progress_for_error(task, "sfx_generation")

        # Assert
        assert partial_progress == {
            "completed_sfx_clips": [1, 2, 3, 4, 5, 6, 7, 8, 9],
            "total_clips": 18,
        }

    def test_extract_empty_metadata(self):
        """Verify returns empty dict when step_metadata is None."""
        # Arrange
        task = Task(
            id=uuid4(),
            channel_id=uuid4(),
            notion_page_id="test-page-id",
            title="Test Video",
            topic="Test",
            story_direction="Test story",
            status=TaskStatus.VIDEO_ERROR,
            step_metadata=None,
        )

        # Act
        partial_progress = extract_partial_progress_for_error(task, "video_generation")

        # Assert
        assert partial_progress == {}

    def test_extract_missing_step_specific_metadata(self):
        """Verify returns empty dict when step-specific metadata missing."""
        # Arrange
        task = Task(
            id=uuid4(),
            channel_id=uuid4(),
            notion_page_id="test-page-id",
            title="Test Video",
            topic="Test",
            story_direction="Test story",
            status=TaskStatus.VIDEO_ERROR,
            step_metadata={"some_other_key": "value"},
        )

        # Act
        partial_progress = extract_partial_progress_for_error(task, "video_generation")

        # Assert
        assert partial_progress == {}

    def test_extract_wrong_step_name(self):
        """Verify returns empty dict when step_name doesn't match metadata."""
        # Arrange
        task = Task(
            id=uuid4(),
            channel_id=uuid4(),
            notion_page_id="test-page-id",
            title="Test Video",
            topic="Test",
            story_direction="Test story",
            status=TaskStatus.VIDEO_ERROR,
            step_metadata={"completed_video_clips": [1, 2, 3]},
        )

        # Act - Ask for asset_generation progress but task has video_generation metadata
        partial_progress = extract_partial_progress_for_error(task, "asset_generation")

        # Assert
        assert partial_progress == {}
