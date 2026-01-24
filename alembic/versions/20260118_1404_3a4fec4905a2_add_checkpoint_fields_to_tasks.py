"""add_checkpoint_fields_to_tasks

Adds completed_steps and step_metadata JSONB fields to tasks table for
checkpoint/resume functionality (Story 6.3).

Checkpoint Fields:
    - completed_steps: JSONB list of step-level checkpoints
    - step_metadata: JSONB dict for fine-grained sub-step progress

Indexes:
    - GIN index on completed_steps for efficient JSONB queries

Revision ID: 3a4fec4905a2
Revises: 6ff98a5dad9c
Create Date: 2026-01-18 14:04:20.181959
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '3a4fec4905a2'
down_revision: Union[str, None] = '6ff98a5dad9c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    # Add completed_steps JSONB column with default empty list
    op.add_column(
        'tasks',
        sa.Column(
            'completed_steps',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default='[]'
        )
    )

    # Add step_metadata JSONB column with default empty dict
    op.add_column(
        'tasks',
        sa.Column(
            'step_metadata',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default='{}'
        )
    )

    # Create GIN index on completed_steps for efficient JSONB queries
    # GIN indexes are optimal for JSONB containment queries (@>, ?, ?&, ?|)
    op.create_index(
        'ix_tasks_completed_steps_gin',
        'tasks',
        ['completed_steps'],
        postgresql_using='gin'
    )


def downgrade() -> None:
    """Downgrade database schema."""
    # Drop GIN index first
    op.drop_index('ix_tasks_completed_steps_gin', table_name='tasks')

    # Drop columns
    op.drop_column('tasks', 'step_metadata')
    op.drop_column('tasks', 'completed_steps')
