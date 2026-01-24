"""add_retry_tracking_to_tasks

Revision ID: 6ff98a5dad9c
Revises: 3d36aa5f1eac
Create Date: 2026-01-18 09:03:27.053041
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6ff98a5dad9c'
down_revision: Union[str, None] = '3d36aa5f1eac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add retry tracking fields to tasks table (Story 6.2).

    Adds:
        - retry_count: Number of retry attempts (default 0)
        - next_retry_at: Timestamp for next retry (nullable, indexed)
        - Index on next_retry_at for efficient retry polling
    """
    # Add retry_count column (Integer, NOT NULL, default 0)
    op.add_column(
        'tasks',
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0')
    )

    # Add next_retry_at column (DateTime with timezone, nullable)
    op.add_column(
        'tasks',
        sa.Column('next_retry_at', sa.DateTime(timezone=True), nullable=True)
    )

    # Create index on next_retry_at for efficient retry polling
    # Partial index: only index rows where next_retry_at IS NOT NULL
    # This makes the index smaller and faster for retry queries
    op.create_index(
        'ix_tasks_next_retry_at',
        'tasks',
        ['next_retry_at'],
        unique=False,
        postgresql_where=sa.text('next_retry_at IS NOT NULL')
    )


def downgrade() -> None:
    """Remove retry tracking fields from tasks table.

    Drops:
        - Index ix_tasks_next_retry_at
        - Column next_retry_at
        - Column retry_count
    """
    # Drop index first (must drop before column)
    op.drop_index('ix_tasks_next_retry_at', table_name='tasks')

    # Drop columns
    op.drop_column('tasks', 'next_retry_at')
    op.drop_column('tasks', 'retry_count')
