"""Add task model for queue tracking.

This migration creates the tasks table for tracking video generation jobs
and calculating channel capacity (FR13, FR16).

The tasks table includes:
    - id: UUID primary key
    - channel_id: Foreign key to channels table
    - status: Task status (pending, claimed, processing, etc.)
    - created_at, updated_at: Timestamps
    - Composite index on (channel_id, status) for efficient queue queries
    - Partial index on status='pending' for fast pending task lookups

Revision ID: 006_add_task_model
Revises: 005_add_max_concurrent
Create Date: 2026-01-11

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "006_add_task_model"
down_revision: str | None = "005_add_max_concurrent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create tasks table with indexes."""
    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel_id", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["channel_id"],
            ["channels.channel_id"],
            name="fk_tasks_channel_id",
        ),
    )

    # Individual indexes on channel_id and status
    op.create_index(
        "ix_tasks_channel_id",
        "tasks",
        ["channel_id"],
    )
    op.create_index(
        "ix_tasks_status",
        "tasks",
        ["status"],
    )

    # Composite index for efficient queue queries
    op.create_index(
        "ix_tasks_channel_id_status",
        "tasks",
        ["channel_id", "status"],
    )

    # Partial index on status='pending' for fast pending task lookups
    op.create_index(
        "idx_tasks_pending",
        "tasks",
        ["channel_id"],
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    """Remove tasks table and indexes."""
    op.drop_index("idx_tasks_pending", table_name="tasks")
    op.drop_index("ix_tasks_channel_id_status", table_name="tasks")
    op.drop_index("ix_tasks_status", table_name="tasks")
    op.drop_index("ix_tasks_channel_id", table_name="tasks")
    op.drop_table("tasks")
