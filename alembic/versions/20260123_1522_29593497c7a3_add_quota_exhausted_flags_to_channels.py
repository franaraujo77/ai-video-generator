"""add_quota_exhausted_flags_to_channels

Revision ID: 29593497c7a3
Revises: 6c2d20acdb3f
Create Date: 2026-01-23 15:22:31.580724
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '29593497c7a3'
down_revision: Union[str, None] = '6c2d20acdb3f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add quota_exhausted flags to channels table.

    Story 6.8: API Quota Monitoring (Task 6, Subtasks 6.3-6.4)
    These flags pause task claiming when quotas are exhausted at 100%.
    Automatically reset at midnight UTC (YouTube) / PST (Gemini).
    """
    # Add YouTube quota exhausted flag
    op.add_column(
        'channels',
        sa.Column(
            'youtube_quota_exhausted',
            sa.Boolean(),
            nullable=False,
            server_default='false',
        )
    )
    # Add index for worker quota checks
    op.create_index(
        'ix_channels_youtube_quota_exhausted',
        'channels',
        ['youtube_quota_exhausted']
    )

    # Add Gemini quota exhausted flag
    op.add_column(
        'channels',
        sa.Column(
            'gemini_quota_exhausted',
            sa.Boolean(),
            nullable=False,
            server_default='false',
        )
    )
    # Add index for worker quota checks
    op.create_index(
        'ix_channels_gemini_quota_exhausted',
        'channels',
        ['gemini_quota_exhausted']
    )


def downgrade() -> None:
    """Remove quota_exhausted flags from channels table."""
    op.drop_index('ix_channels_gemini_quota_exhausted', table_name='channels')
    op.drop_column('channels', 'gemini_quota_exhausted')
    op.drop_index('ix_channels_youtube_quota_exhausted', table_name='channels')
    op.drop_column('channels', 'youtube_quota_exhausted')
