"""add_missing_task_columns_for_notion_sync

Revision ID: 20260114_1923_3893cea04e01
Revises: 006_add_task_model
Create Date: 2026-01-14 19:23

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260114_1923_3893cea04e01"
down_revision: str | None = "006_add_task_model"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add missing columns to tasks table for Notion integration.

    This migration adds the columns that were supposed to be added by
    migration 007 but couldn't run due to enum conflicts. It handles
    the case where the table exists but is missing required columns.
    """
    # Add notion_page_id column (36 chars to support UUID format with dashes)
    op.add_column(
        "tasks",
        sa.Column("notion_page_id", sa.String(36), nullable=True, unique=True),
    )

    # Add video metadata columns
    op.add_column(
        "tasks",
        sa.Column("title", sa.String(255), nullable=True),
    )
    op.add_column(
        "tasks",
        sa.Column("topic", sa.Text(), nullable=True),
    )
    op.add_column(
        "tasks",
        sa.Column("story_direction", sa.Text(), nullable=True),
    )

    # Add priority as string (not enum to avoid conflicts)
    op.add_column(
        "tasks",
        sa.Column("priority", sa.String(20), nullable=True, server_default="normal"),
    )

    # Add error tracking
    op.add_column(
        "tasks",
        sa.Column("error_log", sa.Text(), nullable=True),
    )

    # Add YouTube URL
    op.add_column(
        "tasks",
        sa.Column("youtube_url", sa.String(255), nullable=True),
    )

    # Create index on notion_page_id for fast lookups
    op.create_index(
        "ix_tasks_notion_page_id",
        "tasks",
        ["notion_page_id"],
        unique=True,
    )


def downgrade() -> None:
    """Remove added columns."""
    op.drop_index("ix_tasks_notion_page_id", table_name="tasks")
    op.drop_column("tasks", "youtube_url")
    op.drop_column("tasks", "error_log")
    op.drop_column("tasks", "priority")
    op.drop_column("tasks", "story_direction")
    op.drop_column("tasks", "topic")
    op.drop_column("tasks", "title")
    op.drop_column("tasks", "notion_page_id")
