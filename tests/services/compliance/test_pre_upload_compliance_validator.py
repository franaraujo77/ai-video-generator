"""Tests for Pre-Upload Compliance Validator Orchestrator (Story 7.7)."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, AsyncMock, patch
from uuid import uuid4

from app.services.compliance.pre_upload_compliance_validator import (
    PreUploadComplianceValidator,
)
from app.services.compliance.exceptions import ComplianceViolationError
from app.models import Task, Channel, TaskStatus


@pytest.fixture
def validator():
    """Create PreUploadComplianceValidator instance."""
    return PreUploadComplianceValidator()


@pytest.fixture
def mock_task():
    """Mock Task object."""
    task = Mock(spec=Task)
    task.id = uuid4()
    task.channel_id = uuid4()
    task.story_direction = "Pikachu explores forest and hunts for food"
    task.metadata = {
        "thumbnail_path": "/tmp/test.png",
        "title": "Pikachu Forest Adventure",
        "description": "Nature documentary",
        "tags": ["pokemon", "nature"],
    }
    task.updated_at = datetime.now(timezone.utc)
    task.compliance_evidence = None
    return task


@pytest.fixture
def mock_channel():
    """Mock Channel object."""
    channel = Mock(spec=Channel)
    channel.id = uuid4()
    channel.created_at = datetime.now(timezone.utc) - timedelta(days=365)
    return channel


@pytest.fixture
def video_metadata():
    """Sample video metadata for validation."""
    return {
        "title": "Pikachu's Forest Adventure",
        "description": "Pokemon nature documentary",
        "tags": ["pokemon", "nature", "forest"],
        "thumbnail_path": "/tmp/test.png",
        "story_script": "Pikachu explores forest",
    }


@pytest.fixture
def mock_db():
    """Mock AsyncSession database."""
    db = AsyncMock()
    db.get = AsyncMock()
    db.commit = AsyncMock()

    # Mock execute() to return a result with scalars() method
    mock_result = Mock()
    mock_result.scalars = Mock()
    db.execute = AsyncMock(return_value=mock_result)

    return db


class TestCompleteComplianceFlow:
    """Test complete compliance validation orchestration."""

    @pytest.mark.asyncio
    async def test_all_checks_pass_first_video(
        self, validator, mock_task, mock_channel, video_metadata, mock_db
    ):
        """Test compliance validation passes for first video on channel."""
        # Mock channel lookup
        mock_db.get.return_value = mock_channel

        # Mock no recent uploads (first video)
        mock_db.execute.return_value.scalars.return_value.all.return_value = []

        result = await validator.validate_before_upload(mock_task, video_metadata, mock_db)

        # All checks should pass for first video
        assert result["compliance_validated"] is True
        assert "uniqueness_scores" in result
        assert "scheduled_upload_time" in result
        assert result["evidence_verified"] is True

    @pytest.mark.asyncio
    async def test_uniqueness_failure_raises_violation(
        self, validator, mock_task, mock_channel, video_metadata, mock_db
    ):
        """Test uniqueness check failure raises ComplianceViolationError."""
        # Mock channel lookup
        mock_db.get.return_value = mock_channel

        # Create mock recent upload with identical content
        identical_task = Mock(spec=Task)
        identical_task.id = uuid4()
        identical_task.metadata = video_metadata
        identical_task.story_direction = video_metadata["story_script"]
        identical_task.updated_at = datetime.now(timezone.utc) - timedelta(hours=12)

        mock_db.execute.return_value.scalars.return_value.all.return_value = [
            identical_task
        ]

        # Should raise ComplianceViolationError due to low uniqueness
        with pytest.raises(ComplianceViolationError) as exc_info:
            await validator.validate_before_upload(mock_task, video_metadata, mock_db)

        assert exc_info.value.violation_type in ["uniqueness_failure", "duplicate_content"]

    @pytest.mark.asyncio
    async def test_evidence_auto_generation(
        self, validator, mock_task, mock_channel, video_metadata, mock_db
    ):
        """Test automatic evidence generation when missing."""
        # Mock channel lookup
        mock_db.get.return_value = mock_channel

        # Mock no recent uploads
        mock_db.execute.return_value.scalars.return_value.all.return_value = []

        # Task has no compliance_evidence
        assert mock_task.compliance_evidence is None

        result = await validator.validate_before_upload(mock_task, video_metadata, mock_db)

        # Evidence should be auto-generated
        assert result["evidence_verified"] is True
        assert mock_task.compliance_evidence is not None
        assert "creative_decisions" in mock_task.compliance_evidence


class TestUniquenessValidation:
    """Test content uniqueness validation integration."""

    @pytest.mark.asyncio
    async def test_uniqueness_passes_different_content(
        self, validator, mock_task, mock_channel, video_metadata, mock_db
    ):
        """Test uniqueness passes with sufficiently different content."""
        mock_db.get.return_value = mock_channel

        # Create different recent upload
        different_task = Mock(spec=Task)
        different_task.id = uuid4()
        different_task.metadata = {
            "title": "Charizard Mountain Flight",
            "description": "Dragon Pokemon soaring",
            "tags": ["pokemon", "flying", "mountain"],
        }
        different_task.story_direction = "Charizard flies over mountains"
        different_task.updated_at = datetime.now(timezone.utc) - timedelta(days=1)

        mock_db.execute.return_value.scalars.return_value.all.return_value = [
            different_task
        ]

        result = await validator.validate_before_upload(mock_task, video_metadata, mock_db)

        # Should pass - content is different enough
        assert result["compliance_validated"] is True
        assert result["uniqueness_scores"]["narrative_uniqueness"] > 0.5


class TestRecentUploadsQuery:
    """Test recent uploads database query."""

    @pytest.mark.asyncio
    async def test_get_recent_uploads(self, validator, mock_db):
        """Test fetching recent uploads from database."""
        channel_id = uuid4()

        # Mock database query result
        mock_tasks = [Mock(spec=Task) for _ in range(5)]
        mock_db.execute.return_value.scalars.return_value.all.return_value = mock_tasks

        result = await validator.get_recent_uploads(channel_id, mock_db, days=30)

        assert len(result) == 5
        assert result == mock_tasks

    @pytest.mark.asyncio
    async def test_get_recent_uploads_filters_by_date(self, validator, mock_db):
        """Test recent uploads filtered by date range."""
        channel_id = uuid4()

        # Mock result with empty task list
        mock_db.execute.return_value.scalars.return_value.all.return_value = []

        # Mock 10 days lookback
        result = await validator.get_recent_uploads(channel_id, mock_db, days=10)

        # Verify database query was called
        assert mock_db.execute.called
        assert result == []


class TestTaskConversion:
    """Test Task to dict conversion helpers."""

    def test_task_to_video_dict(self, validator):
        """Test converting Task to video metadata dict."""
        task = Mock(spec=Task)
        task.id = uuid4()
        task.story_direction = "Pikachu hunts insects"
        task.metadata = {
            "thumbnail_path": "/tmp/thumb.png",
            "composite_path": "/tmp/comp.png",
            "title": "Pikachu Documentary",
            "description": "Nature film",
            "tags": ["pokemon"],
        }
        task.updated_at = datetime.now(timezone.utc)

        result = validator._task_to_video_dict(task)

        # Verify field mapping (especially story_direction -> story_script fix)
        assert result["story_script"] == "Pikachu hunts insects"
        assert result["title"] == "Pikachu Documentary"
        assert result["thumbnail_path"] == "/tmp/thumb.png"
        assert "uploaded_at" in result

    def test_task_to_upload_dict(self, validator):
        """Test converting Task to upload log dict."""
        task = Mock(spec=Task)
        task.id = uuid4()
        task.updated_at = datetime.now(timezone.utc)

        result = validator._task_to_upload_dict(task)

        assert "uploaded_at" in result
        assert result["uploaded_at"] == task.updated_at


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_channel_not_found(
        self, validator, mock_task, video_metadata, mock_db
    ):
        """Test handling when channel not found."""
        # Mock channel not found
        mock_db.get.return_value = None

        # Mock no recent uploads
        mock_db.execute.return_value.scalars.return_value.all.return_value = []

        with pytest.raises(ValueError, match="Channel .* not found"):
            await validator.validate_before_upload(mock_task, video_metadata, mock_db)

    @pytest.mark.asyncio
    async def test_missing_story_direction(
        self, validator, mock_task, mock_channel, video_metadata, mock_db
    ):
        """Test handling task with no story_direction."""
        mock_task.story_direction = None
        mock_task.metadata = {}

        mock_db.get.return_value = mock_channel
        mock_db.execute.return_value.scalars.return_value.all.return_value = []

        # Should handle gracefully with conservative defaults
        result = await validator.validate_before_upload(mock_task, video_metadata, mock_db)

        assert result["compliance_validated"] is True
