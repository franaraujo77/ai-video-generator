"""Tests for ReviewService audio approval/rejection methods.

This module tests the audio review workflow for Story 5.5: Audio Review Interface.
Tests cover approval flow (Task 4) and rejection flow with partial regeneration (Task 5).

Test Coverage:
- Audio approval (AUDIO_READY → AUDIO_APPROVED)
- Audio rejection (AUDIO_READY → AUDIO_ERROR)
- Partial regeneration support (failed_clip_numbers)
- Invalid state transition handling
- Notion status synchronization

Dependencies:
    - pytest-asyncio for async test support
    - unittest.mock for mocking
    - Factory functions for test data creation
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import InvalidStateTransitionError
from app.models import Task, TaskStatus
from app.services.review_service import ReviewService


@pytest.fixture
def review_service():
    """Create ReviewService instance for testing."""
    return ReviewService()


@pytest.fixture
def mock_db_session():
    """Mock AsyncSession for database operations."""
    session = MagicMock(spec=AsyncSession)
    session.flush = AsyncMock()
    return session


@pytest.fixture
def task_audio_ready():
    """Create a task in AUDIO_READY status."""
    task = MagicMock(spec=Task)
    task.id = uuid4()
    task.status = TaskStatus.AUDIO_READY
    task.notion_page_id = "abc123def456"
    task.error_log = None
    task.step_completion_metadata = {}
    return task


@pytest.fixture
def task_wrong_status():
    """Create a task in wrong status (not AUDIO_READY)."""
    task = MagicMock(spec=Task)
    task.id = uuid4()
    task.status = TaskStatus.GENERATING_AUDIO  # Wrong status
    task.notion_page_id = "abc123def456"
    task.error_log = None
    task.step_completion_metadata = {}
    return task


class TestAudioApproval:
    """Test suite for audio approval workflow (Task 4)."""

    @pytest.mark.asyncio
    async def test_approve_audio_success(self, review_service, mock_db_session, task_audio_ready):
        """Test successful audio approval from AUDIO_READY to AUDIO_APPROVED."""
        # Arrange
        mock_db_session.get = AsyncMock(return_value=task_audio_ready)

        with patch.object(review_service, "_update_notion_status_async", new=AsyncMock()):
            # Act
            result = await review_service.approve_audio(
                db=mock_db_session,
                task_id=task_audio_ready.id,
                notion_page_id=task_audio_ready.notion_page_id,
            )

        # Assert
        assert result["status"] == "approved"
        assert result["previous_status"] == "audio_ready"
        assert result["new_status"] == "audio_approved"
        assert task_audio_ready.status == TaskStatus.AUDIO_APPROVED
        mock_db_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_approve_audio_notion_sync_called(
        self, review_service, mock_db_session, task_audio_ready
    ):
        """Test that Notion status sync is called on approval."""
        # Arrange
        mock_db_session.get = AsyncMock(return_value=task_audio_ready)

        with patch.object(
            review_service, "_update_notion_status_async", new=AsyncMock()
        ) as mock_notion_sync:
            # Act
            await review_service.approve_audio(
                db=mock_db_session,
                task_id=task_audio_ready.id,
                notion_page_id=task_audio_ready.notion_page_id,
                correlation_id="test-123",
            )

        # Assert
        mock_notion_sync.assert_called_once_with(
            notion_page_id=task_audio_ready.notion_page_id,
            status=TaskStatus.AUDIO_APPROVED,
            correlation_id="test-123",
        )

    @pytest.mark.asyncio
    async def test_approve_audio_notion_sync_skipped_when_no_page_id(
        self, review_service, mock_db_session, task_audio_ready
    ):
        """Test that Notion sync is skipped when notion_page_id is None."""
        # Arrange
        mock_db_session.get = AsyncMock(return_value=task_audio_ready)

        with patch.object(
            review_service, "_update_notion_status_async", new=AsyncMock()
        ) as mock_notion_sync:
            # Act
            await review_service.approve_audio(
                db=mock_db_session,
                task_id=task_audio_ready.id,
                notion_page_id=None,  # No Notion page ID
            )

        # Assert
        mock_notion_sync.assert_not_called()

    @pytest.mark.asyncio
    async def test_approve_audio_invalid_status(
        self, review_service, mock_db_session, task_wrong_status
    ):
        """Test that approval fails if task is not in AUDIO_READY status."""
        # Arrange
        mock_db_session.get = AsyncMock(return_value=task_wrong_status)

        # Act & Assert
        with pytest.raises(
            InvalidStateTransitionError,
            match="Cannot approve audio: task status is generating_audio, expected AUDIO_READY",
        ):
            await review_service.approve_audio(
                db=mock_db_session,
                task_id=task_wrong_status.id,
            )

        # Verify status was not changed
        assert task_wrong_status.status == TaskStatus.GENERATING_AUDIO
        mock_db_session.flush.assert_not_called()

    @pytest.mark.asyncio
    async def test_approve_audio_task_not_found(self, review_service, mock_db_session):
        """Test that approval fails if task does not exist."""
        # Arrange
        mock_db_session.get = AsyncMock(return_value=None)
        task_id = uuid4()

        # Act & Assert
        with pytest.raises(ValueError, match=f"Task not found: {task_id}"):
            await review_service.approve_audio(
                db=mock_db_session,
                task_id=task_id,
            )


class TestAudioRejection:
    """Test suite for audio rejection workflow (Task 5)."""

    @pytest.mark.asyncio
    async def test_reject_audio_success(self, review_service, mock_db_session, task_audio_ready):
        """Test successful audio rejection from AUDIO_READY to AUDIO_ERROR."""
        # Arrange
        mock_db_session.get = AsyncMock(return_value=task_audio_ready)
        rejection_reason = "Audio quality issues on multiple clips"

        with patch.object(review_service, "_update_notion_status_async", new=AsyncMock()):
            # Act
            result = await review_service.reject_audio(
                db=mock_db_session,
                task_id=task_audio_ready.id,
                reason=rejection_reason,
                notion_page_id=task_audio_ready.notion_page_id,
            )

        # Assert
        assert result["status"] == "rejected"
        assert result["previous_status"] == "audio_ready"
        assert result["new_status"] == "audio_error"
        assert result["reason"] == rejection_reason
        assert result["failed_clip_numbers"] == []
        assert task_audio_ready.status == TaskStatus.AUDIO_ERROR
        assert rejection_reason in task_audio_ready.error_log
        mock_db_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_reject_audio_with_failed_clip_numbers(
        self, review_service, mock_db_session, task_audio_ready
    ):
        """Test audio rejection with partial regeneration support."""
        # Arrange
        mock_db_session.get = AsyncMock(return_value=task_audio_ready)
        rejection_reason = "Audio quality issues on clips 3, 7, 12"
        failed_clips = [3, 7, 12]

        with patch.object(review_service, "_update_notion_status_async", new=AsyncMock()):
            # Act
            result = await review_service.reject_audio(
                db=mock_db_session,
                task_id=task_audio_ready.id,
                reason=rejection_reason,
                failed_clip_numbers=failed_clips,
                notion_page_id=task_audio_ready.notion_page_id,
            )

        # Assert
        assert result["status"] == "rejected"
        assert result["failed_clip_numbers"] == failed_clips
        assert task_audio_ready.status == TaskStatus.AUDIO_ERROR

        # Verify error log includes clip numbers
        assert rejection_reason in task_audio_ready.error_log
        assert "clips 3, 7, 12 need regeneration" in task_audio_ready.error_log

        # Verify failed clips stored in metadata for partial regeneration
        assert (
            task_audio_ready.step_completion_metadata["failed_audio_clip_numbers"] == failed_clips
        )

    @pytest.mark.asyncio
    async def test_reject_audio_appends_to_existing_error_log(
        self, review_service, mock_db_session, task_audio_ready
    ):
        """Test that rejection appends to existing error log (preserves history)."""
        # Arrange
        task_audio_ready.error_log = "Previous error: Something went wrong"
        mock_db_session.get = AsyncMock(return_value=task_audio_ready)
        rejection_reason = "New audio quality issues"

        with patch.object(review_service, "_update_notion_status_async", new=AsyncMock()):
            # Act
            await review_service.reject_audio(
                db=mock_db_session,
                task_id=task_audio_ready.id,
                reason=rejection_reason,
            )

        # Assert
        assert "Previous error: Something went wrong" in task_audio_ready.error_log
        assert rejection_reason in task_audio_ready.error_log

    @pytest.mark.asyncio
    async def test_reject_audio_invalid_status(
        self, review_service, mock_db_session, task_wrong_status
    ):
        """Test that rejection fails if task is not in AUDIO_READY status."""
        # Arrange
        mock_db_session.get = AsyncMock(return_value=task_wrong_status)

        # Act & Assert
        with pytest.raises(
            InvalidStateTransitionError,
            match="Cannot reject audio: task status is generating_audio, expected AUDIO_READY",
        ):
            await review_service.reject_audio(
                db=mock_db_session,
                task_id=task_wrong_status.id,
                reason="Quality issues",
            )

        # Verify status was not changed
        assert task_wrong_status.status == TaskStatus.GENERATING_AUDIO
        mock_db_session.flush.assert_not_called()

    @pytest.mark.asyncio
    async def test_reject_audio_empty_reason(
        self, review_service, mock_db_session, task_audio_ready
    ):
        """Test that rejection fails if reason is empty."""
        # Arrange
        mock_db_session.get = AsyncMock(return_value=task_audio_ready)

        # Act & Assert
        with pytest.raises(ValueError, match="Rejection reason is required"):
            await review_service.reject_audio(
                db=mock_db_session,
                task_id=task_audio_ready.id,
                reason="",  # Empty reason
            )

    @pytest.mark.asyncio
    async def test_reject_audio_notion_sync_called(
        self, review_service, mock_db_session, task_audio_ready
    ):
        """Test that Notion status sync is called on rejection."""
        # Arrange
        mock_db_session.get = AsyncMock(return_value=task_audio_ready)

        with patch.object(
            review_service, "_update_notion_status_async", new=AsyncMock()
        ) as mock_notion_sync:
            # Act
            await review_service.reject_audio(
                db=mock_db_session,
                task_id=task_audio_ready.id,
                reason="Quality issues",
                notion_page_id=task_audio_ready.notion_page_id,
                correlation_id="test-456",
            )

        # Assert
        mock_notion_sync.assert_called_once_with(
            notion_page_id=task_audio_ready.notion_page_id,
            status=TaskStatus.AUDIO_ERROR,
            correlation_id="test-456",
        )

    @pytest.mark.asyncio
    async def test_reject_audio_task_not_found(self, review_service, mock_db_session):
        """Test that rejection fails if task does not exist."""
        # Arrange
        mock_db_session.get = AsyncMock(return_value=None)
        task_id = uuid4()

        # Act & Assert
        with pytest.raises(ValueError, match=f"Task not found: {task_id}"):
            await review_service.reject_audio(
                db=mock_db_session,
                task_id=task_id,
                reason="Quality issues",
            )
