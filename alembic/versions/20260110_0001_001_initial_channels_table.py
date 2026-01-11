"""001 initial channels table

Revision ID: 001_initial_channels
Revises:
Create Date: 2026-01-10

Creates the channels table for storing YouTube channel configurations.
This is the foundation for multi-channel isolation.
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_initial_channels"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create channels table."""
    op.create_table(
        "channels",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel_id", sa.String(50), nullable=False, index=True),
        sa.Column("channel_name", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, index=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("channel_id", name="uq_channels_channel_id"),
    )
    # Note: index on channel_id created via Column(index=True) above


def downgrade() -> None:
    """Drop channels table."""
    op.drop_table("channels")
