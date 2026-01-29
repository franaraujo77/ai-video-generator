"""Add review_action_audit_logs table for YouTube Partner Program compliance

Story 7.9 - Human Review Audit Logging (AC1, AC2, AC3)

Creates review_action_audit_logs table to track all human review actions for
YouTube Partner Program compliance requirements. Provides immutable audit trail
showing who reviewed what content, when, and what decision was made.

Changes:
1. Create review_action_audit_logs table with immutable append-only pattern
2. Add indexes for fast compliance queries by channel, reviewer, timestamp
3. Add check constraint to enforce valid action types
4. 2-year retention policy enforced at application level

Immutability (AC2):
- Append-only table: INSERT operations only
- No UPDATE/DELETE operations permitted (application-level enforcement)
- Database-level protection via trigger/policy (future enhancement)

Revision ID: abc123def456
Revises: 10d87c432e2e
Create Date: 2026-01-26 01:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '10d87c432e2e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create review_action_audit_logs table for Story 7.9.

    YouTube Partner Program compliance requirement: Evidence of human oversight
    for all uploaded content. This table provides queryable audit trail showing
    who reviewed what content, when, and what decision was made.

    Immutability (AC2):
        - Append-only table: INSERT operations only
        - No UPDATE/DELETE operations permitted (application-level enforcement)
        - Critical for compliance: audit logs must never be modified after creation

    Retention Policy (AC3):
        - 2-year retention minimum (YouTube Partner Program requirement)
        - Archive (not delete) logs older than 2 years for compliance
    """
    # Create review_action_audit_logs table
    op.create_table(
        'review_action_audit_logs',
        sa.Column(
            'id',
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text('gen_random_uuid()')
        ),
        sa.Column(
            'task_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('tasks.id', ondelete='CASCADE'),
            nullable=False,
            index=True
        ),
        sa.Column(
            'channel_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('channels.id', ondelete='CASCADE'),
            nullable=False,
            index=True
        ),
        sa.Column(
            'action_type',
            sa.String(50),
            nullable=False,
            comment='approve, reject, bulk_approve, bulk_reject'
        ),
        sa.Column(
            'action_status',
            sa.String(50),
            nullable=False,
            comment='TaskStatus value at time of action (e.g., VIDEO_APPROVED, AUDIO_ERROR)'
        ),
        sa.Column(
            'reviewer_user_id',
            sa.String(100),
            nullable=True,
            index=True,
            comment='Notion user ID (UUID format from last_edited_by)'
        ),
        sa.Column(
            'reviewer_name',
            sa.String(200),
            nullable=True,
            comment='Human name from Notion user object'
        ),
        sa.Column(
            'reviewer_email',
            sa.String(200),
            nullable=True,
            comment='Email from Notion user object (optional)'
        ),
        sa.Column(
            'reason',
            sa.Text,
            nullable=True,
            comment='Rejection reason (nullable for approvals)'
        ),
        sa.Column(
            'affected_clip_numbers',
            postgresql.ARRAY(sa.Integer),
            nullable=True,
            comment='Failed clip indices for partial audio rejection (Story 5.5)'
        ),
        sa.Column(
            'action_timestamp',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()'),
            index=True
        ),
        sa.Column(
            'correlation_id',
            sa.String(36),
            nullable=True,
            comment='UUID for tracing review action across pipeline'
        ),
        comment='Immutable audit log for all human review actions. YouTube Partner Program compliance requirement: 2-year minimum retention, append-only (no UPDATE/DELETE), queryable evidence of who reviewed what content.'
    )

    # Composite index for fast compliance queries by channel and date range (AC4)
    op.create_index(
        'ix_audit_logs_channel_timestamp',
        'review_action_audit_logs',
        ['channel_id', 'action_timestamp']
    )

    # Composite index for fast queries by reviewer and date range
    op.create_index(
        'ix_audit_logs_reviewer_timestamp',
        'review_action_audit_logs',
        ['reviewer_user_id', 'action_timestamp']
    )

    # Check constraint to enforce valid action types (AC2)
    op.create_check_constraint(
        'ck_audit_log_valid_action_type',
        'review_action_audit_logs',
        "action_type IN ('approve', 'reject', 'bulk_approve', 'bulk_reject')"
    )


def downgrade() -> None:
    """Remove review_action_audit_logs table.

    WARNING: Downgrading will lose all review audit history.
    This may impact YouTube Partner Program compliance evidence.
    """
    # Drop check constraint first (must drop constraints before indexes)
    op.drop_constraint(
        'ck_audit_log_valid_action_type',
        'review_action_audit_logs',
        type_='check'
    )

    # Drop indexes
    op.drop_index('ix_audit_logs_reviewer_timestamp', table_name='review_action_audit_logs')
    op.drop_index('ix_audit_logs_channel_timestamp', table_name='review_action_audit_logs')

    # Drop table
    op.drop_table('review_action_audit_logs')
