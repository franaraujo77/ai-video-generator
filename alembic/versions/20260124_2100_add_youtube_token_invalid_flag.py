"""add youtube_token_invalid flag to channels

Revision ID: 09a1b2c3d4e5
Revises: 098f893ec56c, dfeb6b1a6f83
Create Date: 2026-01-24 21:00:00.000000

This migration adds the youtube_token_invalid flag to the channels table.
The flag is set to True when YouTube refresh token is invalid/revoked
(RefreshError from google-auth) and reset to False when new OAuth setup
completes via Story 7.1 CLI.

This is a merge migration that combines two branches:
- dfeb6b1a6f83: add cancelled status to TaskStatus enum (Story 6.x)
- 098f893ec56c: create auto_recovery_metrics table (Story 6.10)

Story: 7.2 - OAuth Token Refresh Automation
FR: FR61 (Auto-refresh), NFR-I5 (No upload failures)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '09a1b2c3d4e5'
down_revision = ('098f893ec56c', 'dfeb6b1a6f83')
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add youtube_token_invalid flag to channels table.

    This flag tracks whether the YouTube refresh token is invalid/revoked.
    When True, YouTube operations are paused for the channel until
    re-authorization via Story 7.1 OAuth setup CLI.

    Default: False (tokens valid by default)
    Not indexed (not queried frequently)
    """
    op.add_column(
        'channels',
        sa.Column(
            'youtube_token_invalid',
            sa.Boolean(),
            nullable=False,
            server_default='false',
            comment='True if YouTube refresh token is invalid/revoked (requires re-auth)'
        )
    )


def downgrade() -> None:
    """Remove youtube_token_invalid flag from channels table."""
    op.drop_column('channels', 'youtube_token_invalid')
