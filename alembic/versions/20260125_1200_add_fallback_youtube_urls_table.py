"""Add fallback_youtube_urls table and youtube_url to tasks (Story 7.5)

Revision ID: 5a6b7c8d9e0f
Revises: 4953fdee5857
Create Date: 2026-01-25 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = '5a6b7c8d9e0f'
down_revision: Union[str, None] = '4953fdee5857'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add fallback_youtube_urls table and youtube_url column to tasks table.

    Story 7.5: YouTube URL Retrieval & Notion Update

    Changes:
        1. Add youtube_url column to tasks table for storing full YouTube URL
        2. Create fallback_youtube_urls table for manual recovery when Notion sync fails
        3. Add index on task_id for fast fallback URL lookups

    The fallback_youtube_urls table provides a safety net when YouTube upload succeeds
    but Notion database update fails (rate limit, permissions, service outage). This
    ensures the YouTube URL is never lost and can be manually recovered via Story 6.7.
    """
    # Add youtube_url column to tasks table
    op.add_column(
        'tasks',
        sa.Column(
            'youtube_url',
            sa.String(512),
            nullable=True,
            comment="Full YouTube URL (https://www.youtube.com/watch?v={video_id})"
        )
    )

    # Create fallback_youtube_urls table
    op.create_table(
        'fallback_youtube_urls',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            'task_id',
            UUID(as_uuid=True),
            sa.ForeignKey('tasks.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'channel_id',
            UUID(as_uuid=True),
            sa.ForeignKey('channels.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'video_id',
            sa.String(255),
            nullable=False,
            comment="YouTube video ID (11 chars, e.g., 'dQw4w9WgXcQ')",
        ),
        sa.Column(
            'youtube_url',
            sa.String(512),
            nullable=False,
            comment="Full YouTube URL (https://www.youtube.com/watch?v={video_id})",
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('CURRENT_TIMESTAMP'),
        ),
    )

    # Add index on task_id for fast lookups during manual recovery
    op.create_index(
        'ix_fallback_youtube_urls_task_id',
        'fallback_youtube_urls',
        ['task_id'],
    )


def downgrade() -> None:
    """Remove fallback_youtube_urls table and youtube_url column from tasks table."""
    # Drop index first
    op.drop_index('ix_fallback_youtube_urls_task_id', table_name='fallback_youtube_urls')

    # Drop fallback table
    op.drop_table('fallback_youtube_urls')

    # Drop youtube_url column from tasks
    op.drop_column('tasks', 'youtube_url')
