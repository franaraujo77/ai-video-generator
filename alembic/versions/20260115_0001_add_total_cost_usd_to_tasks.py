"""add_total_cost_usd_to_tasks

Revision ID: 20260115_0001_add_total_cost_usd
Revises: 20260114_1923_3893cea04e01
Create Date: 2026-01-15

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260115_0001_add_total_cost_usd"
down_revision: str | None = "20260114_1923_3893cea04e01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add total_cost_usd column to tasks table.

    This column tracks the running total of all API costs for a task
    (Gemini, Kling, ElevenLabs) and is updated incrementally as each
    pipeline step completes.

    Story 3.3 (Asset Generation) requires cost tracking for budget monitoring.
    """
    op.add_column(
        "tasks",
        sa.Column(
            "total_cost_usd",
            sa.Float(),
            nullable=False,
            server_default="0.0",
        ),
    )


def downgrade() -> None:
    """Remove total_cost_usd column."""
    op.drop_column("tasks", "total_cost_usd")
