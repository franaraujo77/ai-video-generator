"""Add max_concurrent column to channels table.

This migration adds the max_concurrent column to the channels table for
capacity tracking (FR13, FR16). This enables tracking how many parallel
tasks each channel can handle.

Revision ID: 005_add_max_concurrent
Revises: 004_add_storage_strategy
Create Date: 2026-01-11

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "005_add_max_concurrent"
down_revision: str | None = "004_add_storage_strategy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add max_concurrent column to channels table.

    Adds:
        - max_concurrent: Integer column with default=2, not nullable
          Used for capacity tracking and fair scheduling (FR13, FR16).
    """
    op.add_column(
        "channels",
        sa.Column(
            "max_concurrent",
            sa.Integer(),
            nullable=False,
            server_default="2",
        ),
    )


def downgrade() -> None:
    """Remove max_concurrent column from channels table."""
    op.drop_column("channels", "max_concurrent")
