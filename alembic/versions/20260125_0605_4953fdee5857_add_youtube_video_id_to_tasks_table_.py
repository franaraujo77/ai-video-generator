"""Add youtube_video_id to tasks table (Story 7.4)

Revision ID: 4953fdee5857
Revises: 10b2c3d4e5f6
Create Date: 2026-01-25 06:05:57.341973
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4953fdee5857'
down_revision: Union[str, None] = '10b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add youtube_video_id column to tasks table.

    Story 7.4: Resumable Upload Implementation

    Adds youtube_video_id field to store the YouTube video ID (e.g., 'dQw4w9WgXcQ')
    after successful upload. This ID is used by Story 7.5 to construct the full YouTube URL.
    """
    op.add_column(
        'tasks',
        sa.Column(
            'youtube_video_id',
            sa.String(255),
            nullable=True,
            comment="YouTube video ID after successful upload (e.g., 'dQw4w9WgXcQ')"
        )
    )


def downgrade() -> None:
    """Remove youtube_video_id column from tasks table."""
    op.drop_column('tasks', 'youtube_video_id')
