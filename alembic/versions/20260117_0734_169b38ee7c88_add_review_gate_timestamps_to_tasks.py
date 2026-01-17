"""add review gate timestamps to tasks

Revision ID: 169b38ee7c88
Revises: 00c0dbdd097a
Create Date: 2026-01-17 07:34:35.809350

Story: 5.2 - Review Gate Enforcement
Subtasks: 3.1, 3.2

Adds review_started_at and review_completed_at timestamp columns to tasks table
to track time spent waiting at mandatory review gates (ASSETS_READY, VIDEO_READY,
AUDIO_READY, FINAL_REVIEW).

Used for observability and SLA tracking: "How long do tasks wait for review?"
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '169b38ee7c88'
down_revision: Union[str, None] = '00c0dbdd097a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add review gate timestamp columns to tasks table.

    These columns track when tasks enter and exit review gates for quality control:
    - review_started_at: Set when task reaches *_READY status (review gate)
    - review_completed_at: Set when task moves to *_APPROVED status (approval)

    Both columns are nullable and timezone-aware (UTC).
    """
    # Add review_started_at column (nullable, no default)
    op.add_column(
        "tasks",
        sa.Column(
            "review_started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # Add review_completed_at column (nullable, no default)
    op.add_column(
        "tasks",
        sa.Column(
            "review_completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Remove review gate timestamp columns from tasks table."""
    op.drop_column("tasks", "review_completed_at")
    op.drop_column("tasks", "review_started_at")
