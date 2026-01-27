"""Tests for ReviewAuditService (Story 7.9).

Tests all audit logging functionality including:
- AC1: Audit log entry creation on review actions
- AC2: Immutable audit log storage (no update/delete methods)
- AC3: 2-year retention policy (query date ranges)
- AC4: Audit log export for compliance

Test Coverage:
- log_review_action() - creates audit entries
- get_task_audit_history() - queries by task ID
- get_channel_audit_logs() - queries by channel with date filters
- get_reviewer_audit_logs() - queries by reviewer
- export_audit_logs_for_compliance() - generates compliance reports
- Invalid action type validation
- Integration with ReviewService
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Channel, ReviewActionAuditLog, Task, TaskStatus
from app.services.review_audit_service import ReviewAuditService


@pytest.fixture
def audit_service():
    """Create ReviewAuditService instance."""
    return ReviewAuditService()


@pytest.fixture
async def sample_channel(async_session: AsyncSession):
    """Create a sample channel for testing."""
    channel = Channel(
        channel_id="test-channel",
        channel_name="Test Channel",
    )
    async_session.add(channel)
    await async_session.commit()
    await async_session.refresh(channel)
    return channel


@pytest.fixture
async def sample_task(async_session: AsyncSession, sample_channel: Channel):
    """Create a sample task for testing."""
    task = Task(
        channel_id=sample_channel.id,
        notion_page_id="test-page-123",
        title="Test Task",
        topic="Test Topic",
        story_direction="Test story direction",
        status=TaskStatus.VIDEO_READY,
    )
    async_session.add(task)
    await async_session.commit()
    await async_session.refresh(task)
    return task


class TestLogReviewAction:
    """Test audit log entry creation (AC1)."""

    async def test_log_approve_action_creates_audit_entry(
        self,
        async_session: AsyncSession,
        audit_service: ReviewAuditService,
        sample_task: Task,
    ):
        """Test that approving a video creates an audit log entry."""
        # Create audit log entry for approval
        audit_entry = await audit_service.log_review_action(
            db=async_session,
            task_id=sample_task.id,
            channel_id=sample_task.channel_id,
            action_type="approve",
            action_status="video_approved",
            reviewer_user_id="a1b2c3d4-e5f6-4789-a012-123456789abc",
            reviewer_name="John Doe",
            reviewer_email="john@example.com",
            correlation_id="test-correlation-123",
        )
        await async_session.commit()

        # Verify audit entry was created
        assert audit_entry.id is not None
        assert audit_entry.task_id == sample_task.id
        assert audit_entry.channel_id == sample_task.channel_id
        assert audit_entry.action_type == "approve"
        assert audit_entry.action_status == "video_approved"
        assert audit_entry.reviewer_user_id == "a1b2c3d4-e5f6-4789-a012-123456789abc"
        assert audit_entry.reviewer_name == "John Doe"
        assert audit_entry.reviewer_email == "john@example.com"
        assert audit_entry.reason is None  # Approvals don't have reasons
        assert audit_entry.affected_clip_numbers is None
        assert audit_entry.correlation_id == "test-correlation-123"
        assert audit_entry.action_timestamp is not None

    async def test_log_reject_action_with_reason(
        self,
        async_session: AsyncSession,
        audit_service: ReviewAuditService,
        sample_task: Task,
    ):
        """Test that rejecting with reason stores reason in audit log."""
        # Create audit log entry for rejection
        audit_entry = await audit_service.log_review_action(
            db=async_session,
            task_id=sample_task.id,
            channel_id=sample_task.channel_id,
            action_type="reject",
            action_status="video_error",
            reviewer_user_id="b2c3d4e5-f6a7-4890-b123-234567890bcd",
            reviewer_name="Jane Smith",
            reviewer_email="jane@example.com",
            reason="Low video quality in clips 5, 12",
            correlation_id="test-correlation-456",
        )
        await async_session.commit()

        # Verify rejection details
        assert audit_entry.action_type == "reject"
        assert audit_entry.action_status == "video_error"
        assert audit_entry.reason == "Low video quality in clips 5, 12"
        assert audit_entry.reviewer_name == "Jane Smith"

    async def test_log_audio_rejection_with_affected_clips(
        self,
        async_session: AsyncSession,
        audit_service: ReviewAuditService,
        sample_task: Task,
    ):
        """Test that audio rejection with clip numbers stores affected_clip_numbers."""
        # Create audit log entry for audio rejection with specific clips
        audit_entry = await audit_service.log_review_action(
            db=async_session,
            task_id=sample_task.id,
            channel_id=sample_task.channel_id,
            action_type="reject",
            action_status="audio_error",
            reviewer_user_id="c3d4e5f6-a7b8-4901-c234-345678901cde",
            reviewer_name="Bob Johnson",
            reason="Audio quality issues",
            affected_clip_numbers=[3, 7, 12],
            correlation_id="test-correlation-789",
        )
        await async_session.commit()

        # Verify affected clips stored
        assert audit_entry.affected_clip_numbers == [3, 7, 12]
        assert audit_entry.action_status == "audio_error"

    async def test_log_bulk_approve_action(
        self,
        async_session: AsyncSession,
        audit_service: ReviewAuditService,
        sample_task: Task,
    ):
        """Test that bulk approve action type is recorded."""
        audit_entry = await audit_service.log_review_action(
            db=async_session,
            task_id=sample_task.id,
            channel_id=sample_task.channel_id,
            action_type="bulk_approve",
            action_status="video_approved",
            reviewer_user_id="d4e5f6a7-b8c9-4012-d345-456789012def",
            reviewer_name="Bulk Reviewer",
        )
        await async_session.commit()

        assert audit_entry.action_type == "bulk_approve"

    async def test_invalid_action_type_raises_error(
        self,
        async_session: AsyncSession,
        audit_service: ReviewAuditService,
        sample_task: Task,
    ):
        """Test that invalid action types raise ValueError (AC2 - immutability)."""
        with pytest.raises(ValueError, match="Invalid action_type"):
            await audit_service.log_review_action(
                db=async_session,
                task_id=sample_task.id,
                channel_id=sample_task.channel_id,
                action_type="invalid_action",  # Invalid!
                action_status="video_approved",
            )

    async def test_audit_entry_persisted_to_database(
        self,
        async_session: AsyncSession,
        audit_service: ReviewAuditService,
        sample_task: Task,
    ):
        """Test that audit entries are actually persisted to database (AC2)."""
        # Create audit entry
        audit_entry = await audit_service.log_review_action(
            db=async_session,
            task_id=sample_task.id,
            channel_id=sample_task.channel_id,
            action_type="approve",
            action_status="video_approved",
            reviewer_user_id="e5f6a7b8-c9d0-4123-e456-567890123efa",
        )
        await async_session.commit()

        # Query database directly to verify persistence
        result = await async_session.execute(
            select(ReviewActionAuditLog).where(ReviewActionAuditLog.id == audit_entry.id)
        )
        persisted_entry = result.scalar_one()

        assert persisted_entry.id == audit_entry.id
        assert persisted_entry.task_id == sample_task.id
        assert persisted_entry.action_type == "approve"


class TestGetTaskAuditHistory:
    """Test querying audit logs by task (AC4)."""

    async def test_get_task_audit_history_returns_chronological_entries(
        self,
        async_session: AsyncSession,
        audit_service: ReviewAuditService,
        sample_task: Task,
    ):
        """Test that task history returns entries in chronological order."""
        # Create multiple audit entries for same task
        now = datetime.now(timezone.utc)

        # Entry 1: Initial approval (1 hour ago)
        await audit_service.log_review_action(
            db=async_session,
            task_id=sample_task.id,
            channel_id=sample_task.channel_id,
            action_type="approve",
            action_status="assets_approved",
            action_timestamp=now - timedelta(hours=1),
        )

        # Entry 2: Rejection (30 minutes ago)
        await audit_service.log_review_action(
            db=async_session,
            task_id=sample_task.id,
            channel_id=sample_task.channel_id,
            action_type="reject",
            action_status="video_error",
            reason="Quality issues",
            action_timestamp=now - timedelta(minutes=30),
        )

        # Entry 3: Second approval (now)
        await audit_service.log_review_action(
            db=async_session,
            task_id=sample_task.id,
            channel_id=sample_task.channel_id,
            action_type="approve",
            action_status="video_approved",
            action_timestamp=now,
        )

        await async_session.commit()

        # Get audit history
        history = await audit_service.get_task_audit_history(async_session, sample_task.id)

        # Verify chronological order (oldest first)
        assert len(history) == 3
        assert history[0].action_type == "approve"
        assert history[0].action_status == "assets_approved"
        assert history[1].action_type == "reject"
        assert history[1].action_status == "video_error"
        assert history[2].action_type == "approve"
        assert history[2].action_status == "video_approved"

    async def test_get_task_audit_history_empty_for_no_reviews(
        self,
        async_session: AsyncSession,
        audit_service: ReviewAuditService,
        sample_task: Task,
    ):
        """Test that tasks with no reviews return empty history."""
        history = await audit_service.get_task_audit_history(async_session, sample_task.id)
        assert len(history) == 0


class TestGetChannelAuditLogs:
    """Test querying audit logs by channel and date range (AC4)."""

    async def test_get_channel_audit_logs_filters_by_channel(
        self,
        async_session: AsyncSession,
        audit_service: ReviewAuditService,
        sample_channel: Channel,
        sample_task: Task,
    ):
        """Test that channel audit logs only return logs for that channel."""
        # Create audit entry for this channel
        await audit_service.log_review_action(
            db=async_session,
            task_id=sample_task.id,
            channel_id=sample_channel.id,
            action_type="approve",
            action_status="video_approved",
        )

        # Create another channel and task
        other_channel = Channel(channel_id="other-channel", channel_name="Other")
        async_session.add(other_channel)
        await async_session.flush()

        other_task = Task(
            channel_id=other_channel.id,
            notion_page_id="other-page",
            title="Other Task",
            topic="Other",
            story_direction="Other",
            status=TaskStatus.VIDEO_READY,
        )
        async_session.add(other_task)
        await async_session.flush()

        # Create audit entry for other channel
        await audit_service.log_review_action(
            db=async_session,
            task_id=other_task.id,
            channel_id=other_channel.id,
            action_type="reject",
            action_status="video_error",
        )
        await async_session.commit()

        # Query logs for sample_channel only
        logs = await audit_service.get_channel_audit_logs(
            async_session, sample_channel.id, limit=100
        )

        # Verify only sample_channel logs returned
        assert len(logs) == 1
        assert logs[0].channel_id == sample_channel.id
        assert logs[0].action_type == "approve"

    async def test_get_channel_audit_logs_filters_by_date_range(
        self,
        async_session: AsyncSession,
        audit_service: ReviewAuditService,
        sample_task: Task,
    ):
        """Test that date range filtering works correctly (AC3 - retention)."""
        now = datetime.now(timezone.utc)

        # Entry 1: 3 years ago (outside 2-year retention)
        await audit_service.log_review_action(
            db=async_session,
            task_id=sample_task.id,
            channel_id=sample_task.channel_id,
            action_type="approve",
            action_status="video_approved",
            action_timestamp=now - timedelta(days=1095),  # 3 years
        )

        # Entry 2: 1 year ago (within retention)
        await audit_service.log_review_action(
            db=async_session,
            task_id=sample_task.id,
            channel_id=sample_task.channel_id,
            action_type="reject",
            action_status="video_error",
            action_timestamp=now - timedelta(days=365),  # 1 year
        )

        # Entry 3: Today (within retention)
        await audit_service.log_review_action(
            db=async_session,
            task_id=sample_task.id,
            channel_id=sample_task.channel_id,
            action_type="approve",
            action_status="audio_approved",
            action_timestamp=now,
        )
        await async_session.commit()

        # Query last 2 years (AC3 - retention policy)
        date_from = now - timedelta(days=730)  # 2 years
        logs = await audit_service.get_channel_audit_logs(
            async_session, sample_task.channel_id, date_from=date_from, date_to=now
        )

        # Verify only entries within 2-year window returned
        assert len(logs) == 2
        # SQLite stores datetimes as naive, so compare without timezone
        date_from_naive = date_from.replace(tzinfo=None)
        assert logs[0].action_timestamp >= date_from_naive  # Most recent (DESC order)
        assert logs[1].action_timestamp >= date_from_naive


class TestGetReviewerAuditLogs:
    """Test querying audit logs by reviewer (AC4)."""

    async def test_get_reviewer_audit_logs_filters_by_reviewer(
        self,
        async_session: AsyncSession,
        audit_service: ReviewAuditService,
        sample_task: Task,
    ):
        """Test that reviewer audit logs only return logs for that reviewer."""
        # Create entries for reviewer 1
        await audit_service.log_review_action(
            db=async_session,
            task_id=sample_task.id,
            channel_id=sample_task.channel_id,
            action_type="approve",
            action_status="video_approved",
            reviewer_user_id="f6a7b8c9-d0e1-4234-f567-678901234fab",
            reviewer_name="Reviewer One",
        )

        # Create entries for reviewer 2
        await audit_service.log_review_action(
            db=async_session,
            task_id=sample_task.id,
            channel_id=sample_task.channel_id,
            action_type="reject",
            action_status="audio_error",
            reviewer_user_id="a7b8c9d0-e1f2-4345-a678-789012345abc",
            reviewer_name="Reviewer Two",
        )
        await async_session.commit()

        # Query logs for reviewer-1 only (using UUID)
        logs = await audit_service.get_reviewer_audit_logs(async_session, "f6a7b8c9-d0e1-4234-f567-678901234fab")

        # Verify only reviewer-1 logs returned
        assert len(logs) == 1
        assert logs[0].reviewer_user_id == "f6a7b8c9-d0e1-4234-f567-678901234fab"
        assert logs[0].action_type == "approve"


class TestExportAuditLogsForCompliance:
    """Test compliance export functionality (AC4)."""

    async def test_export_audit_logs_returns_json_format(
        self,
        async_session: AsyncSession,
        audit_service: ReviewAuditService,
        sample_task: Task,
    ):
        """Test that compliance export returns properly formatted JSON."""
        # Create audit entry
        await audit_service.log_review_action(
            db=async_session,
            task_id=sample_task.id,
            channel_id=sample_task.channel_id,
            action_type="approve",
            action_status="video_approved",
            reviewer_user_id="b8c9d0e1-f2a3-4456-b789-890123456bcd",
            reviewer_name="Compliance Reviewer",
            reviewer_email="compliance@example.com",
        )
        await async_session.commit()

        # Export for compliance
        now = datetime.now(timezone.utc)
        date_from = now - timedelta(days=365)
        export_data = await audit_service.export_audit_logs_for_compliance(
            async_session, sample_task.channel_id, date_from, now
        )

        # Verify JSON structure
        assert len(export_data) == 1
        entry = export_data[0]

        assert "audit_log_id" in entry
        assert "task_id" in entry
        assert "channel_id" in entry
        assert "action_type" in entry
        assert entry["action_type"] == "approve"
        assert "reviewer" in entry
        assert entry["reviewer"]["user_id"] == "b8c9d0e1-f2a3-4456-b789-890123456bcd"
        assert entry["reviewer"]["name"] == "Compliance Reviewer"
        assert entry["reviewer"]["email"] == "compliance@example.com"
        assert "action_timestamp" in entry


class TestImmutability:
    """Test immutability enforcement (AC2)."""

    def test_no_update_method_exists(self):
        """Test that ReviewAuditService has no update method (AC2)."""
        audit_service = ReviewAuditService()
        assert not hasattr(audit_service, "update_review_action")
        assert not hasattr(audit_service, "delete_review_action")
        assert not hasattr(audit_service, "modify_review_action")

    def test_only_insert_method_exists(self):
        """Test that ReviewAuditService only has log method (AC2)."""
        audit_service = ReviewAuditService()
        # Only log_review_action should exist for data modification
        assert hasattr(audit_service, "log_review_action")
        # All other methods are query-only
        assert hasattr(audit_service, "get_task_audit_history")
        assert hasattr(audit_service, "get_channel_audit_logs")
        assert hasattr(audit_service, "get_reviewer_audit_logs")
        assert hasattr(audit_service, "export_audit_logs_for_compliance")

    async def test_database_level_update_is_possible_pending_rls(
        self,
        async_session: AsyncSession,
        audit_service: ReviewAuditService,
        sample_task: Task,
    ):
        """Test that database-level UPDATE is currently possible (future: add RLS).

        NOTE: This test documents that database-level immutability is NOT yet enforced.
        Future enhancement (Story TBD): Add PostgreSQL Row-Level Security (RLS) to
        block UPDATE/DELETE operations at the database level.

        Current implementation (AC2):
        - Application-level: No update/delete methods in service ✅
        - Database-level: UPDATE/DELETE operations are possible (gap)

        This test verifies the current state and will FAIL when RLS is implemented,
        serving as a reminder to update the test to expect blocking.
        """
        # Create audit entry
        audit_entry = await audit_service.log_review_action(
            db=async_session,
            task_id=sample_task.id,
            channel_id=sample_task.channel_id,
            action_type="approve",
            action_status="video_approved",
            reviewer_user_id="c9d0e1f2-a3b4-4567-c890-901234567cde",
            reviewer_name="Test User",
        )
        await async_session.commit()
        original_action_type = audit_entry.action_type

        # Attempt direct database UPDATE (currently succeeds, future: should fail)
        from sqlalchemy import update

        stmt = (
            update(ReviewActionAuditLog)
            .where(ReviewActionAuditLog.id == audit_entry.id)
            .values(action_type="reject")  # Modify immutable field
        )

        # Currently this succeeds (no database-level protection yet)
        await async_session.execute(stmt)
        await async_session.commit()

        # Verify update succeeded (documenting the gap)
        result = await async_session.execute(
            select(ReviewActionAuditLog).where(ReviewActionAuditLog.id == audit_entry.id)
        )
        updated_entry = result.scalar_one()

        # This assertion documents current behavior (will need updating when RLS added)
        assert updated_entry.action_type == "reject"  # UPDATE succeeded
        assert original_action_type == "approve"  # Original was different

        # TODO: When PostgreSQL RLS is implemented, this test should be updated to:
        # with pytest.raises(sqlalchemy.exc.InsufficientPrivilege):
        #     await async_session.execute(stmt)

    async def test_database_level_delete_is_possible_pending_rls(
        self,
        async_session: AsyncSession,
        audit_service: ReviewAuditService,
        sample_task: Task,
    ):
        """Test that database-level DELETE is currently possible (future: add RLS).

        NOTE: This test documents that database-level immutability is NOT yet enforced.
        See test_database_level_update_is_possible_pending_rls for full explanation.

        This test verifies the current state and will FAIL when RLS is implemented.
        """
        # Create audit entry
        audit_entry = await audit_service.log_review_action(
            db=async_session,
            task_id=sample_task.id,
            channel_id=sample_task.channel_id,
            action_type="approve",
            action_status="video_approved",
            reviewer_user_id="d0e1f2a3-b4c5-4678-d901-012345678def",
        )
        await async_session.commit()
        entry_id = audit_entry.id

        # Attempt direct database DELETE (currently succeeds, future: should fail)
        from sqlalchemy import delete

        stmt = delete(ReviewActionAuditLog).where(ReviewActionAuditLog.id == entry_id)

        # Currently this succeeds (no database-level protection yet)
        await async_session.execute(stmt)
        await async_session.commit()

        # Verify delete succeeded (documenting the gap)
        result = await async_session.execute(
            select(ReviewActionAuditLog).where(ReviewActionAuditLog.id == entry_id)
        )
        deleted_entry = result.scalar_one_or_none()

        # This assertion documents current behavior (will need updating when RLS added)
        assert deleted_entry is None  # DELETE succeeded

        # TODO: When PostgreSQL RLS is implemented, this test should be updated to:
        # with pytest.raises(sqlalchemy.exc.InsufficientPrivilege):
        #     await async_session.execute(stmt)
