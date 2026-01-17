"""Tests for ReviewService.

Simplified tests focusing on critical paths.
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
    """ReviewService instance for testing."""
    return ReviewService()


@pytest.fixture
def db_session_mock():
    """Mock database session."""
    session = MagicMock(spec=AsyncSession)
    session.get = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    return session


class TestReviewService:
    """Test suite for ReviewService."""

    @pytest.mark.asyncio
    async def test_approve_videos_task_not_found(self, review_service, db_session_mock):
        """Test video approval fails when task not found."""
        # Arrange
        db_session_mock.get.return_value = None
        task_id = uuid4()

        # Act & Assert
        with pytest.raises(ValueError, match="Task not found"):
            await review_service.approve_videos(
                db=db_session_mock,
                task_id=task_id,
            )

    @pytest.mark.asyncio
    async def test_approve_videos_invalid_status(self, review_service, db_session_mock):
        """Test video approval fails when task is not in VIDEO_READY status."""
        # Arrange
        task = MagicMock(spec=Task)
        task.id = uuid4()
        task.status = TaskStatus.GENERATING_VIDEO
        db_session_mock.get.return_value = task

        # Act & Assert
        with pytest.raises(InvalidStateTransitionError, match="Cannot approve videos"):
            await review_service.approve_videos(
                db=db_session_mock,
                task_id=task.id,
            )

    @pytest.mark.asyncio
    async def test_reject_videos_task_not_found(self, review_service, db_session_mock):
        """Test video rejection fails when task not found."""
        # Arrange
        db_session_mock.get.return_value = None
        task_id = uuid4()

        # Act & Assert
        with pytest.raises(ValueError, match="Task not found"):
            await review_service.reject_videos(
                db=db_session_mock,
                task_id=task_id,
                reason="Quality issues",
            )

    @pytest.mark.asyncio
    async def test_reject_videos_empty_reason(self, review_service, db_session_mock):
        """Test video rejection fails with empty reason."""
        # Arrange
        task = MagicMock(spec=Task)
        task.id = uuid4()
        task.status = TaskStatus.VIDEO_READY
        db_session_mock.get.return_value = task

        # Act & Assert
        with pytest.raises(ValueError, match="Rejection reason is required"):
            await review_service.reject_videos(
                db=db_session_mock,
                task_id=task.id,
                reason="",
            )

    @pytest.mark.asyncio
    async def test_reject_videos_invalid_status(self, review_service, db_session_mock):
        """Test video rejection fails when task is not in VIDEO_READY status."""
        # Arrange
        task = MagicMock(spec=Task)
        task.id = uuid4()
        task.status = TaskStatus.GENERATING_VIDEO
        db_session_mock.get.return_value = task

        # Act & Assert
        with pytest.raises(InvalidStateTransitionError, match="Cannot reject videos"):
            await review_service.reject_videos(
                db=db_session_mock,
                task_id=task.id,
                reason="Quality issues",
            )

    @pytest.mark.asyncio
    async def test_update_notion_status_async_no_token(self, review_service):
        """Test Notion status update skips when token not configured."""
        # Arrange
        with patch("app.services.review_service.get_notion_api_token", return_value=None), \
             patch("app.services.review_service.NotionClient") as notion_client_class_mock:

            # Act
            await review_service._update_notion_status_async(
                notion_page_id="abc123",
                status=TaskStatus.VIDEO_APPROVED,
            )

            # Assert - NotionClient should not be instantiated
            notion_client_class_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_notion_status_async_error_handling(self, review_service):
        """Test Notion status update logs error but doesn't raise."""
        # Arrange
        with patch("app.services.review_service.get_notion_api_token", return_value="token_123"), \
             patch("app.services.review_service.NotionClient") as notion_client_class_mock:
            notion_client_mock = MagicMock()
            notion_client_mock.update_task_status = AsyncMock(side_effect=Exception("Notion API error"))
            notion_client_class_mock.return_value = notion_client_mock

            # Act - Should not raise, just log
            await review_service._update_notion_status_async(
                notion_page_id="abc123",
                status=TaskStatus.VIDEO_APPROVED,
            )

            # Assert - No exception raised


class TestReviewServiceIntegration:
    """Integration tests with real Task model and database session."""

    @pytest.mark.asyncio
    async def test_approve_videos_happy_path_with_real_task(self, review_service, async_session):
        """[P1] should successfully approve videos with real Task model."""
        # GIVEN: Task in VIDEO_READY status
        from app.models import Task, TaskStatus, Channel
        from uuid import uuid4

        # Create channel first to get a valid channel_id
        channel = Channel(channel_id="test_channel", channel_name="Test", storage_strategy="notion")
        async_session.add(channel)
        await async_session.flush()

        task = Task(
            id=uuid4(),
            channel_id=channel.id,
            title="Test Video",
            topic="Test topic",
            story_direction="Test story direction",
            status=TaskStatus.VIDEO_READY,
            notion_page_id="abc123def456",
        )
        async_session.add(task)
        await async_session.commit()

        # WHEN: Approving videos
        with patch("app.services.review_service.get_notion_api_token", return_value=None):
            result = await review_service.approve_videos(
                db=async_session,
                task_id=task.id,
                notion_page_id=task.notion_page_id,
            )

        # Commit the transaction
        await async_session.commit()

        # THEN: Task status transitions to VIDEO_APPROVED
        await async_session.refresh(task)
        assert task.status == TaskStatus.VIDEO_APPROVED
        assert result["status"] == "approved"
        assert result["previous_status"] == "video_ready"
        assert result["new_status"] == "video_approved"

    @pytest.mark.asyncio
    async def test_reject_videos_happy_path_with_real_task(self, review_service, async_session):
        """[P1] should successfully reject videos with real Task model and error_log."""
        # GIVEN: Task in VIDEO_READY status
        from app.models import Task, TaskStatus, Channel
        from uuid import uuid4

        # Create channel first to get a valid channel_id
        channel = Channel(channel_id="test_channel", channel_name="Test", storage_strategy="notion")
        async_session.add(channel)
        await async_session.flush()

        task = Task(
            id=uuid4(),
            channel_id=channel.id,
            title="Test Video",
            topic="Test topic",
            story_direction="Test story direction",
            status=TaskStatus.VIDEO_READY,
            notion_page_id="abc123def456",
            error_log=None,
        )
        async_session.add(task)
        await async_session.commit()

        rejection_reason = "Video quality issues: regenerate with better prompts"

        # WHEN: Rejecting videos
        with patch("app.services.review_service.get_notion_api_token", return_value=None):
            result = await review_service.reject_videos(
                db=async_session,
                task_id=task.id,
                reason=rejection_reason,
                notion_page_id=task.notion_page_id,
            )

        # Commit the transaction
        await async_session.commit()

        # THEN: Task status transitions to VIDEO_ERROR and error_log is populated
        await async_session.refresh(task)
        assert task.status == TaskStatus.VIDEO_ERROR
        assert rejection_reason in task.error_log
        assert result["status"] == "rejected"
        assert result["previous_status"] == "video_ready"
        assert result["new_status"] == "video_error"
        assert result["reason"] == rejection_reason

    @pytest.mark.asyncio
    async def test_reject_videos_appends_to_existing_error_log(self, review_service, async_session):
        """[P1] should append rejection reason to existing error_log."""
        # GIVEN: Task with existing error_log
        from app.models import Task, TaskStatus, Channel
        from uuid import uuid4

        # Create channel first to get a valid channel_id
        channel = Channel(channel_id="test_channel", channel_name="Test", storage_strategy="notion")
        async_session.add(channel)
        await async_session.flush()

        task = Task(
            id=uuid4(),
            channel_id=channel.id,
            title="Test Video",
            topic="Test topic",
            story_direction="Test story direction",
            status=TaskStatus.VIDEO_READY,
            notion_page_id="abc123def456",
            error_log="Previous error: API timeout during generation",
        )
        async_session.add(task)
        await async_session.commit()

        rejection_reason = "Review failure: incorrect scene composition"

        # WHEN: Rejecting videos
        with patch("app.services.review_service.get_notion_api_token", return_value=None):
            await review_service.reject_videos(
                db=async_session,
                task_id=task.id,
                reason=rejection_reason,
                notion_page_id=task.notion_page_id,
            )

        await async_session.commit()

        # THEN: Error log contains both old and new messages
        await async_session.refresh(task)
        assert "Previous error: API timeout" in task.error_log
        assert "Review failure: incorrect scene composition" in task.error_log
        assert task.error_log.count("\n") >= 1  # Appended with newlines

    @pytest.mark.asyncio
    async def test_notion_status_sync_with_valid_token(self, review_service, async_session):
        """[P1] should sync status to Notion when token configured."""
        # GIVEN: Task in VIDEO_READY status and Notion token configured
        from app.models import Task, TaskStatus, Channel
        from uuid import uuid4

        # Create channel first to get a valid channel_id
        channel = Channel(channel_id="test_channel", channel_name="Test", storage_strategy="notion")
        async_session.add(channel)
        await async_session.flush()

        task = Task(
            id=uuid4(),
            channel_id=channel.id,
            title="Test Video",
            topic="Test topic",
            story_direction="Test story direction",
            status=TaskStatus.VIDEO_READY,
            notion_page_id="abc123def456",
        )
        async_session.add(task)
        await async_session.commit()

        # WHEN: Approving videos with Notion token
        with patch("app.services.review_service.get_notion_api_token", return_value="notion_token_123"), \
             patch("app.services.review_service.NotionClient") as notion_client_class_mock:
            notion_client_mock = MagicMock()
            notion_client_mock.update_task_status = AsyncMock()
            notion_client_class_mock.return_value = notion_client_mock

            await review_service.approve_videos(
                db=async_session,
                task_id=task.id,
                notion_page_id=task.notion_page_id,
            )

            await async_session.commit()

            # THEN: Notion status is updated
            notion_client_class_mock.assert_called_once_with(auth_token="notion_token_123")
            notion_client_mock.update_task_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_notion_status_mapping_validation(self, review_service):
        """[P2] should handle unmapped internal status gracefully."""
        # GIVEN: Internal status that doesn't map to Notion status
        with patch("app.services.review_service.get_notion_api_token", return_value="token_123"), \
             patch("app.services.review_service.INTERNAL_TO_NOTION_STATUS", {}), \
             patch("app.services.review_service.NotionClient") as notion_client_class_mock:
            notion_client_mock = MagicMock()
            notion_client_mock.update_task_status = AsyncMock()
            notion_client_class_mock.return_value = notion_client_mock

            # WHEN: Updating Notion status with unmapped status
            await review_service._update_notion_status_async(
                notion_page_id="abc123",
                status=TaskStatus.VIDEO_APPROVED,
            )

            # THEN: Notion client is not called (mapping not found)
            notion_client_mock.update_task_status.assert_not_called()
