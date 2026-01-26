"""Add privacy configuration: default_privacy and privacy_override

Story 7.8 - Channel Privacy Configuration (AC2, AC3, AC4)

Changes:
1. Update channels.default_privacy server_default from 'unlisted' to 'private' (AC3: safest default)
2. Add tasks.privacy_override column for per-video privacy override from Notion (AC4)

Note: This migration modifies an existing column's default and adds a new column.
Existing channel rows will retain their current default_privacy values.
New channels will default to 'private' for maximum safety.

Revision ID: 10d87c432e2e
Revises: 1d6d7240f181
Create Date: 2026-01-25 20:51:02.471208
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '10d87c432e2e'
down_revision: Union[str, None] = '1d6d7240f181'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Update default_privacy default to 'private' and add privacy_override.

    Story 7.8 - Channel Privacy Configuration

    Changes:
    1. Alter channels.default_privacy default from 'unlisted' to 'private' (AC3)
       - Existing rows keep their current values
       - New rows default to 'private' (safest option)
    2. Add tasks.privacy_override column for per-video privacy override (AC4)
    """
    # 1. Update channels.default_privacy server_default to 'private'
    # Note: This only affects NEW rows. Existing rows retain their current values.
    op.alter_column(
        'channels',
        'default_privacy',
        server_default='private',
        existing_type=sa.String(20),
        existing_nullable=False,
        existing_comment="Default privacy for uploads: 'private', 'unlisted', or 'public' (Story 7.8)"
    )

    # 2. Add tasks.privacy_override column for per-video privacy override
    op.add_column(
        'tasks',
        sa.Column(
            'privacy_override',
            sa.String(20),
            nullable=True,
            comment="Per-video privacy override from Notion: 'public', 'unlisted', or 'private'"
        )
    )


def downgrade() -> None:
    """Revert default_privacy default to 'unlisted' and remove privacy_override.

    WARNING: Downgrading will:
    1. Change default_privacy default back to 'unlisted' (existing rows unchanged)
    2. Drop privacy_override column (all per-video privacy data lost)
    """
    # 1. Revert channels.default_privacy server_default to 'unlisted'
    op.alter_column(
        'channels',
        'default_privacy',
        server_default='unlisted',
        existing_type=sa.String(20),
        existing_nullable=False,
        existing_comment="Default privacy for uploads: 'private', 'unlisted', or 'public' (Story 7.8)"
    )

    # 2. Drop tasks.privacy_override column
    op.drop_column('tasks', 'privacy_override')
