"""add pipeline orchestration metadata

Revision ID: 20260116_0002
Revises: 20260116_0001
Create Date: 2026-01-16 00:00:00

Story: 3.9 - End-to-End Pipeline Orchestration

Adds pipeline orchestration metadata columns to tasks table to support:
- Step completion tracking (for partial resume after failures)
- Pipeline duration monitoring (performance target: ≤2 hours)
- Cost tracking ($6-13 per video expected)
- Performance analysis and optimization

New Columns:
- step_completion_metadata: JSONB column storing completion status for each step
- pipeline_start_time: When pipeline execution began
- pipeline_end_time: When pipeline execution completed
- pipeline_duration_seconds: Total pipeline duration for performance tracking
- pipeline_cost_usd: Total cost of API calls (Gemini + Kling + ElevenLabs)

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260116_0002"
down_revision: str | None = "20260116_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add pipeline orchestration metadata columns to tasks table.

    Adds 5 new columns to support the pipeline orchestrator (Story 3.9):

    1. step_completion_metadata (JSONB): Stores completion status for each pipeline step
       - Enables partial resume after failures (skip completed steps)
       - Format: {"asset_generation": {"completed": true, "duration": 456.7}, ...}

    2. pipeline_start_time (TIMESTAMPTZ): Records when pipeline execution began
       - Used to calculate total pipeline duration
       - Timezone-aware for accurate global tracking

    3. pipeline_end_time (TIMESTAMPTZ): Records when pipeline execution completed
       - Used to calculate total pipeline duration
       - Timezone-aware for accurate global tracking

    4. pipeline_duration_seconds (FLOAT): Total duration of pipeline execution
       - Performance monitoring (target: ≤2 hours = 7200 seconds)
       - NFR-P1 compliance tracking

    5. pipeline_cost_usd (FLOAT): Total cost of API calls
       - Budget monitoring and cost analysis
       - Expected range: $6-13 per video

    PostgreSQL uses JSONB for efficient structured querying.
    SQLite uses JSON (TEXT) for testing compatibility.
    """
    # Add step_completion_metadata column (stores partial progress for resume)
    op.add_column(
        "tasks",
        sa.Column("step_completion_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    # Add pipeline timing columns (performance monitoring)
    op.add_column(
        "tasks",
        sa.Column("pipeline_start_time", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tasks",
        sa.Column("pipeline_end_time", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tasks",
        sa.Column("pipeline_duration_seconds", sa.Float(), nullable=True),
    )

    # Add pipeline cost tracking column (budget monitoring)
    op.add_column(
        "tasks",
        sa.Column("pipeline_cost_usd", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    """Remove pipeline orchestration metadata columns from tasks table."""
    op.drop_column("tasks", "pipeline_cost_usd")
    op.drop_column("tasks", "pipeline_duration_seconds")
    op.drop_column("tasks", "pipeline_end_time")
    op.drop_column("tasks", "pipeline_start_time")
    op.drop_column("tasks", "step_completion_metadata")
