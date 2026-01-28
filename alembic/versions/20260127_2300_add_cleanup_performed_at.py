"""Add cleanup_performed_at to tasks table

Revision ID: 20260127_2300
Revises: g7f6e5d4c3b2
Create Date: 2026-01-27

Story 8.5 Task 4: AssetMetadata Cleanup Tracking

Adds cleanup_performed_at timestamp column to tasks table for tracking
when workspace cleanup has been performed. Used to prevent duplicate
cleanup attempts and enable cleanup metrics.

Key Features:
- Nullable timestamp (NULL = not yet cleaned)
- Indexed for efficient queries (cleanup eligibility checks)
- Timezone-aware (UTC)
- Supports idempotent cleanup operations
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers
revision = '20260127_2300'
down_revision = 'g7f6e5d4c3b2'
branch_labels = None
depends_on = None


def upgrade():
    """Add cleanup_performed_at column to tasks table."""
    # Add column
    op.add_column(
        'tasks',
        sa.Column(
            'cleanup_performed_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Timestamp when workspace cleanup was performed (Story 8.5)'
        )
    )

    # Add partial index for cleanup queries
    # Partial index only on NULL values for efficient cleanup eligibility queries
    # Query: WHERE cleanup_performed_at IS NULL (tasks needing cleanup)
    op.create_index(
        'ix_tasks_cleanup_performed_at',
        'tasks',
        ['cleanup_performed_at'],
        unique=False,
        postgresql_where=text('cleanup_performed_at IS NULL')
    )


def downgrade():
    """Remove cleanup_performed_at column from tasks table."""
    # Drop index first
    op.drop_index('ix_tasks_cleanup_performed_at', table_name='tasks')

    # Drop column
    op.drop_column('tasks', 'cleanup_performed_at')
