"""Review Audit Service for logging all human review actions.

Story 7.9 - Human Review Audit Logging (AC1, AC2, AC3, AC4)

This service provides YouTube Partner Program compliance by creating an immutable
audit trail of all human review actions (approve/reject decisions).

Key Responsibilities:
- Create audit log entries for every review action (AC1)
- Capture reviewer attribution (user_id, name, email from Notion) (AC1)
- Enforce immutability (append-only, no updates/deletes) (AC2)
- Implement 2-year retention policy (AC3)
- Support compliance queries by channel, reviewer, date range (AC4)

Architecture Pattern:
    Service (Smart): Validates inputs, creates audit entries, enforces immutability
    Database: Stores append-only audit log with composite indexes
    Integration: Called from ReviewService after every approve/reject action

Immutability (AC2):
    - Only INSERT operations allowed
    - No UPDATE or DELETE operations
    - Application-level enforcement (no update/delete methods provided)
    - Database-level protection via check constraints and indexes

Retention Policy (AC3):
    - 2-year minimum retention (YouTube Partner Program requirement)
    - Archive (don't delete) logs older than 2 years for audits
    - Automated archival script (future enhancement)

Dependencies:
    - Story 5.2: Review Gate Enforcement (review actions)
    - Story 5.4: Video Review Interface (approve_videos, reject_videos)
    - Story 5.5: Audio Review Interface (approve_audio, reject_audio)
    - Story 5.8: Bulk Review Operations (bulk_approve_tasks, bulk_reject_tasks)
    - Story 7.7: YouTube Compliance Enforcement (compliance evidence)

Usage:
    from app.services.review_audit_service import ReviewAuditService

    audit_service = ReviewAuditService()
    await audit_service.log_review_action(
        db=db,
        task_id=task.id,
        channel_id=task.channel_id,
        action_type="approve",
        action_status="VIDEO_APPROVED",
        reviewer_user_id="notion-user-123",
        reviewer_name="John Doe",
        reviewer_email="john@example.com",
        correlation_id="corr-456"
    )
"""

import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Channel, ReviewActionAuditLog, TaskStatus
from app.utils.logging import get_logger

log = get_logger(__name__)


class ReviewAuditService:
    """Service for creating and querying immutable audit logs of review actions.

    This service enforces YouTube Partner Program compliance by providing an
    append-only audit trail showing who reviewed what content, when, and
    what decision was made.

    Immutability Enforcement (AC2):
        - Only log_review_action() method for INSERT operations
        - No update/delete methods provided
        - Audit logs cannot be modified after creation
        - Critical for compliance: audit trail must be trustworthy

    Retention Policy (AC3):
        - 2-year minimum retention required by YouTube Partner Program
        - Logs older than 2 years should be archived (not deleted)
        - Archive function (future enhancement) will export to cold storage
    """

    async def log_review_action(
        self,
        db: AsyncSession,
        task_id: UUID,
        channel_id: UUID,
        action_type: str,
        action_status: str,
        reviewer_user_id: str | None = None,
        reviewer_name: str | None = None,
        reviewer_email: str | None = None,
        reason: str | None = None,
        affected_clip_numbers: list[int] | None = None,
        action_timestamp: datetime | None = None,
        correlation_id: str | None = None,
    ) -> ReviewActionAuditLog:
        """Create immutable audit log entry for human review action (AC1).

        This method creates an append-only audit log record capturing all
        relevant details of a human review decision. Critical for YouTube
        Partner Program compliance to prove human oversight.

        Immutability (AC2):
            - This is the ONLY method that writes to the audit log
            - No update/delete methods exist - audit logs are permanent
            - Once written, audit entries cannot be modified

        Args:
            db: Active database session (managed by caller)
            task_id: Internal task UUID being reviewed
            channel_id: Channel UUID for compliance filtering
            action_type: Review action ("approve", "reject", "bulk_approve", "bulk_reject")
            action_status: TaskStatus value at time of action (e.g., "VIDEO_APPROVED")
            reviewer_user_id: Notion user ID (UUID format from last_edited_by)
            reviewer_name: Human name from Notion user object
            reviewer_email: Email from Notion user object (optional)
            reason: Rejection reason text (nullable for approvals)
            affected_clip_numbers: Failed clip indices for partial audio rejection
            action_timestamp: When action occurred (defaults to now if None)
            correlation_id: UUID for tracing action across pipeline

        Returns:
            ReviewActionAuditLog: Created audit entry (with generated ID)

        Raises:
            ValueError: If action_type is invalid or required fields missing

        Example:
            >>> audit_entry = await audit_service.log_review_action(
            ...     db=db,
            ...     task_id=task.id,
            ...     channel_id=task.channel_id,
            ...     action_type="approve",
            ...     action_status="VIDEO_APPROVED",
            ...     reviewer_user_id="notion-user-123",
            ...     reviewer_name="John Doe",
            ...     reviewer_email="john@example.com",
            ...     correlation_id="corr-456",
            ... )
            >>> print(f"Audit log created: {audit_entry.id}")

        Related:
            - AC1: Audit log entry creation on review actions
            - AC2: Immutable audit log storage
            - Story 5.2: Review Gate Enforcement
            - Story 5.4: Video Review Interface
            - Story 5.5: Audio Review Interface
        """
        # Validate action_type (AC2: enforce valid values)
        valid_action_types = {"approve", "reject", "bulk_approve", "bulk_reject"}
        if action_type not in valid_action_types:
            raise ValueError(
                f"Invalid action_type: {action_type}. "
                f"Must be one of: {', '.join(valid_action_types)}"
            )

        # Validate channel_id exists in database
        channel_result = await db.get(Channel, channel_id)
        if channel_result is None:
            raise ValueError(f"Channel not found: {channel_id}")

        # Validate action_status is a valid TaskStatus value
        valid_statuses = {status.value for status in TaskStatus}
        if action_status not in valid_statuses:
            raise ValueError(
                f"Invalid action_status: {action_status}. Must be a valid TaskStatus value."
            )

        # Validate reviewer_user_id format (should be UUID-like string if provided)
        if reviewer_user_id is not None:
            # UUID pattern: 8-4-4-4-12 hex digits, with or without dashes
            uuid_pattern = re.compile(
                r"^[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}$", re.IGNORECASE
            )
            if not uuid_pattern.match(reviewer_user_id):
                raise ValueError(
                    f"Invalid reviewer_user_id format: {reviewer_user_id}. "
                    f"Must be UUID format (with or without dashes)."
                )

        # Default timestamp to now if not provided
        if action_timestamp is None:
            action_timestamp = datetime.now(timezone.utc)

        # Create audit log entry
        audit_entry = ReviewActionAuditLog(
            task_id=task_id,
            channel_id=channel_id,
            action_type=action_type,
            action_status=action_status,
            reviewer_user_id=reviewer_user_id,
            reviewer_name=reviewer_name,
            reviewer_email=reviewer_email,
            reason=reason,
            affected_clip_numbers=affected_clip_numbers,
            action_timestamp=action_timestamp,
            correlation_id=correlation_id,
        )

        db.add(audit_entry)
        await db.flush()  # Generate ID but don't commit (caller handles commit)

        log.info(
            "review_action_logged",
            correlation_id=correlation_id,
            audit_log_id=str(audit_entry.id),
            task_id=str(task_id),
            channel_id=str(channel_id),
            action_type=action_type,
            action_status=action_status,
            reviewer_user_id=reviewer_user_id,
            reviewer_name=reviewer_name,
        )

        return audit_entry

    async def get_task_audit_history(
        self,
        db: AsyncSession,
        task_id: UUID,
    ) -> list[ReviewActionAuditLog]:
        """Get complete review history for a task (AC4).

        Returns chronological list of all review actions taken on this task.
        Useful for debugging and understanding task review lifecycle.

        Args:
            db: Active database session
            task_id: Task UUID to query

        Returns:
            List of audit log entries, ordered by action_timestamp ASC

        Example:
            >>> history = await audit_service.get_task_audit_history(db, task_id)
            >>> for entry in history:
            ...     print(f"{entry.action_timestamp}: {entry.action_type} by {entry.reviewer_name}")
        """
        stmt = (
            select(ReviewActionAuditLog)
            .where(ReviewActionAuditLog.task_id == task_id)
            .order_by(ReviewActionAuditLog.action_timestamp.asc())
        )

        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_channel_audit_logs(
        self,
        db: AsyncSession,
        channel_id: UUID,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 1000,
    ) -> list[ReviewActionAuditLog]:
        """Get audit logs for channel within date range (AC4).

        Compliance query for YouTube Partner Program: Show all human review
        actions for a channel within specified date range. Used for audits
        and compliance reporting.

        Args:
            db: Active database session
            channel_id: Channel UUID to query
            date_from: Start date (inclusive, defaults to 2 years ago)
            date_to: End date (inclusive, defaults to now)
            limit: Maximum entries to return (default 1000, max 10000)

        Returns:
            List of audit log entries, ordered by action_timestamp DESC

        Example:
            >>> # Get last 30 days of review actions for channel
            >>> from datetime import datetime, timedelta, timezone
            >>> date_from = datetime.now(timezone.utc) - timedelta(days=30)
            >>> logs = await audit_service.get_channel_audit_logs(
            ...     db, channel_id, date_from=date_from
            ... )
            >>> print(f"Found {len(logs)} review actions in last 30 days")

        Related:
            - AC4: Audit log export for compliance
            - AC3: 2-year retention policy
        """
        # Apply limit bounds (max 10000 for safety)
        limit = min(max(1, limit), 10000)

        # Default date range: last 2 years
        if date_to is None:
            date_to = datetime.now(timezone.utc)
        if date_from is None:
            # YouTube Partner Program requires 2-year retention
            from datetime import timedelta

            date_from = date_to - timedelta(days=730)  # 2 years

        stmt = (
            select(ReviewActionAuditLog)
            .where(
                and_(
                    ReviewActionAuditLog.channel_id == channel_id,
                    ReviewActionAuditLog.action_timestamp >= date_from,
                    ReviewActionAuditLog.action_timestamp <= date_to,
                )
            )
            .order_by(desc(ReviewActionAuditLog.action_timestamp))
            .limit(limit)
        )

        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_reviewer_audit_logs(
        self,
        db: AsyncSession,
        reviewer_user_id: str,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 1000,
    ) -> list[ReviewActionAuditLog]:
        """Get audit logs for specific reviewer within date range (AC4).

        Query all review actions taken by a specific Notion user. Useful for
        reviewer performance analysis and compliance reporting.

        Args:
            db: Active database session
            reviewer_user_id: Notion user ID to query
            date_from: Start date (inclusive, defaults to 30 days ago)
            date_to: End date (inclusive, defaults to now)
            limit: Maximum entries to return (default 1000, max 10000)

        Returns:
            List of audit log entries, ordered by action_timestamp DESC

        Example:
            >>> logs = await audit_service.get_reviewer_audit_logs(
            ...     db, reviewer_user_id="notion-user-123"
            ... )
            >>> approvals = [log for log in logs if log.action_type == "approve"]
            >>> rejections = [log for log in logs if log.action_type == "reject"]
            >>> print(f"Reviewer approved {len(approvals)}, rejected {len(rejections)}")
        """
        # Apply limit bounds (max 10000 for safety)
        limit = min(max(1, limit), 10000)

        # Default date range: last 30 days
        if date_to is None:
            date_to = datetime.now(timezone.utc)
        if date_from is None:
            from datetime import timedelta

            date_from = date_to - timedelta(days=30)

        stmt = (
            select(ReviewActionAuditLog)
            .where(
                and_(
                    ReviewActionAuditLog.reviewer_user_id == reviewer_user_id,
                    ReviewActionAuditLog.action_timestamp >= date_from,
                    ReviewActionAuditLog.action_timestamp <= date_to,
                )
            )
            .order_by(desc(ReviewActionAuditLog.action_timestamp))
            .limit(limit)
        )

        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def export_audit_logs_for_compliance(
        self,
        db: AsyncSession,
        channel_id: UUID,
        date_from: datetime,
        date_to: datetime,
    ) -> list[dict[str, Any]]:
        """Export audit logs as JSON for compliance reporting (AC4).

        Exports audit logs for YouTube Partner Program compliance audits.
        Returns structured JSON with all audit trail details.

        Args:
            db: Active database session
            channel_id: Channel UUID to export
            date_from: Start date (inclusive)
            date_to: End date (inclusive)

        Returns:
            List of dicts with audit log details formatted for compliance

        Example:
            >>> from datetime import datetime, timedelta, timezone
            >>> date_to = datetime.now(timezone.utc)
            >>> date_from = date_to - timedelta(days=365)  # 1 year
            >>> export = await audit_service.export_audit_logs_for_compliance(
            ...     db, channel_id, date_from, date_to
            ... )
            >>> print(f"Exported {len(export)} audit entries")
            >>> # Save to JSON file for YouTube Partner Program audit
            >>> import json
            >>> with open("audit_export.json", "w") as f:
            ...     json.dump(export, f, indent=2, default=str)

        Related:
            - AC4: Audit log export for compliance
            - Story 7.7: YouTube Compliance Enforcement
        """
        logs = await self.get_channel_audit_logs(
            db=db,
            channel_id=channel_id,
            date_from=date_from,
            date_to=date_to,
            limit=10000,  # Max export size
        )

        # Format for compliance export
        export_data = []
        for log in logs:
            export_data.append(
                {
                    "audit_log_id": str(log.id),
                    "task_id": str(log.task_id),
                    "channel_id": str(log.channel_id),
                    "action_type": log.action_type,
                    "action_status": log.action_status,
                    "reviewer": {
                        "user_id": log.reviewer_user_id,
                        "name": log.reviewer_name,
                        "email": log.reviewer_email,
                    },
                    "action_timestamp": log.action_timestamp.isoformat(),
                    "reason": log.reason,
                    "affected_clip_numbers": log.affected_clip_numbers,
                    "correlation_id": log.correlation_id,
                }
            )

        log.info(
            "compliance_export_generated",
            channel_id=str(channel_id),
            date_from=date_from.isoformat(),
            date_to=date_to.isoformat(),
            total_entries=len(export_data),
        )

        return export_data
