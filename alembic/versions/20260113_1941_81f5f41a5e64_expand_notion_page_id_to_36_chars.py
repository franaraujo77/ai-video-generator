"""expand notion_page_id to 36 chars

Revision ID: 81f5f41a5e64
Revises: f1f1300884be
Create Date: 2026-01-13 19:41:23.509861
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '81f5f41a5e64'
down_revision: Union[str, None] = 'f1f1300884be'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Expand notion_page_id column from 32 to 36 chars.

    Supports Notion UUIDs with dashes (36 chars) in addition to
    compact format without dashes (32 chars).
    """
    op.alter_column(
        'tasks',
        'notion_page_id',
        type_=sa.String(36),
        existing_type=sa.String(32),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Revert notion_page_id column from 36 back to 32 chars.

    WARNING: This will truncate any 36-char UUIDs (with dashes) to 32 chars.
    Only safe if all stored values are 32 chars or less.
    """
    op.alter_column(
        'tasks',
        'notion_page_id',
        type_=sa.String(32),
        existing_type=sa.String(36),
        existing_nullable=False,
    )
