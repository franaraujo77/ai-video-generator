"""add narration_scripts to tasks

Revision ID: 20260115_2122
Revises: 20260115_0001_add_total_cost_usd_to_tasks
Create Date: 2026-01-15 21:22:00

Story: 3.6 - Narration Generation Step (ElevenLabs)

Adds narration_scripts JSONB column to tasks table to store the 18 narration
text strings (one per video clip) that will be passed to ElevenLabs API for
audio generation.

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260115_2122"
down_revision: str | None = "20260115_0001_add_total_cost_usd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add narration_scripts JSONB column to tasks table.

    This column stores a list of 18 narration text strings (one per video clip)
    that will be processed by the narration generation service (Story 3.6).

    PostgreSQL uses JSONB for efficient structured querying.
    SQLite uses JSON (TEXT) for testing compatibility.
    """
    # Add narration_scripts column (nullable, no default value)
    op.add_column(
        "tasks",
        sa.Column("narration_scripts", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    """Remove narration_scripts column from tasks table."""
    op.drop_column("tasks", "narration_scripts")
