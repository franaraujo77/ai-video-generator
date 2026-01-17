"""merge divergent migration heads

Revision ID: 00c0dbdd097a
Revises: 81f5f41a5e64, 20260116_0005_add_youtube_quota_usage_table
Create Date: 2026-01-17 07:34:30.854277
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '00c0dbdd097a'
down_revision: Union[str, None] = ('81f5f41a5e64', '20260116_0005_add_youtube_quota_usage_table')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    pass


def downgrade() -> None:
    """Downgrade database schema."""
    pass
