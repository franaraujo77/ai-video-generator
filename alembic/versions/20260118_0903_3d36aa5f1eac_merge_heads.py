"""merge_heads

Revision ID: 3d36aa5f1eac
Revises: 20260117_0001, 169b38ee7c88
Create Date: 2026-01-18 09:03:22.698455
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3d36aa5f1eac'
down_revision: Union[str, None] = ('20260117_0001', '169b38ee7c88')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    pass


def downgrade() -> None:
    """Downgrade database schema."""
    pass
