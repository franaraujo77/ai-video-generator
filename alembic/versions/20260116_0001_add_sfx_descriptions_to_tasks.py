"""add sfx_descriptions to tasks

Revision ID: 20260116_0001
Revises: 20260115_2122
Create Date: 2026-01-16 00:00:00

Story: 3.7 - Sound Effects Generation Step (ElevenLabs)

Adds sfx_descriptions JSONB column to tasks table to store the 18 SFX
description strings (one per video clip) that will be passed to ElevenLabs
Sound Effects Generation API for ambient audio generation.

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260116_0001"
down_revision: str | None = "20260115_2122"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add sfx_descriptions JSONB column to tasks table.

    This column stores a list of 18 SFX description strings (one per video clip)
    that will be processed by the SFX generation service (Story 3.7).

    PostgreSQL uses JSONB for efficient structured querying.
    SQLite uses JSON (TEXT) for testing compatibility.
    """
    # Add sfx_descriptions column (nullable, no default value)
    op.add_column(
        "tasks",
        sa.Column("sfx_descriptions", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    """Remove sfx_descriptions column from tasks table."""
    op.drop_column("tasks", "sfx_descriptions")
