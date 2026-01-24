"""add_retry_state_visibility_fields

Revision ID: 4f75c9412fd1
Revises: 29593497c7a3
Create Date: 2026-01-23 18:42:01.153675
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4f75c9412fd1'
down_revision: Union[str, None] = '29593497c7a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add retry state visibility fields to tasks table (Story 6.9).

    Adds:
        - max_retry_attempts: Maximum retry attempts before terminal failure (default 5)
        - last_error_timestamp: Timestamp of most recent error (nullable, timezone-aware)
    """
    # Add max_retry_attempts column (Integer, NOT NULL, default 5)
    op.add_column(
        'tasks',
        sa.Column('max_retry_attempts', sa.Integer(), nullable=False, server_default='5')
    )

    # Add last_error_timestamp column (DateTime with timezone, nullable)
    op.add_column(
        'tasks',
        sa.Column('last_error_timestamp', sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    """Remove retry state visibility fields from tasks table.

    Drops:
        - Column last_error_timestamp
        - Column max_retry_attempts
    """
    # Drop columns (no indexes to drop - last_error_timestamp not indexed)
    op.drop_column('tasks', 'last_error_timestamp')
    op.drop_column('tasks', 'max_retry_attempts')
