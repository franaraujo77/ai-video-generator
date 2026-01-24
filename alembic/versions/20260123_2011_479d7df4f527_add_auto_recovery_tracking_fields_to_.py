"""add_auto_recovery_tracking_fields_to_task

Revision ID: 479d7df4f527
Revises: 4f75c9412fd1
Create Date: 2026-01-23 20:11:06.681118
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '479d7df4f527'
down_revision: Union[str, None] = '4f75c9412fd1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema - add auto-recovery tracking fields to tasks.

    Story 6.10: Auto-Recovery Success Rate Tracking
    Adds three fields to track auto-recovery for FR35 metrics (80% target):
    - auto_recovered: Did task recover from error via retry?
    - recovery_attempt_number: Which retry succeeded (1-5)?
    - error_category: Error classification (TRANSIENT/PERMANENT/UNKNOWN)

    Also adds indexes for efficient metrics queries.
    """
    # Add auto_recovered boolean field (default False, not nullable)
    op.add_column('tasks', sa.Column('auto_recovered', sa.Boolean(),
                                      nullable=False, server_default='false'))

    # Add recovery_attempt_number integer field (nullable - NULL if never recovered)
    op.add_column('tasks', sa.Column('recovery_attempt_number', sa.Integer(),
                                      nullable=True))

    # Add error_category string field (nullable - NULL if no error)
    # Values: TRANSIENT, PERMANENT, UNKNOWN
    op.add_column('tasks', sa.Column('error_category', sa.String(20),
                                      nullable=True))

    # Indexes for metrics queries (Story 6.10 performance requirements)
    # Partial index on auto_recovered=true for fast recovered task queries
    op.create_index(
        'ix_tasks_auto_recovered',
        'tasks',
        ['auto_recovered'],
        unique=False,
        postgresql_where=sa.text("auto_recovered = true")
    )

    # Index on error_category for metrics breakdown (transient vs permanent)
    op.create_index('ix_tasks_error_category', 'tasks', ['error_category'], unique=False)

    # Composite index on (updated_at, retry_count) for weekly metrics queries
    # Used by calculate_weekly_metrics() to filter tasks in date range with retries
    op.create_index('ix_tasks_updated_at_retry', 'tasks', ['updated_at', 'retry_count'], unique=False)


def downgrade() -> None:
    """Downgrade database schema - remove auto-recovery tracking fields."""
    # Drop indexes
    op.drop_index('ix_tasks_updated_at_retry', table_name='tasks')
    op.drop_index('ix_tasks_error_category', table_name='tasks')
    op.drop_index('ix_tasks_auto_recovered', table_name='tasks')

    # Drop columns
    op.drop_column('tasks', 'error_category')
    op.drop_column('tasks', 'recovery_attempt_number')
    op.drop_column('tasks', 'auto_recovered')
