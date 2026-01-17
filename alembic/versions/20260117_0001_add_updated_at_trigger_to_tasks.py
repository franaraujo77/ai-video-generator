"""Add PostgreSQL trigger for Task.updated_at auto-update.

This migration adds a PostgreSQL trigger to automatically update the
tasks.updated_at timestamp on every UPDATE operation. This complements
the SQLAlchemy onupdate=utcnow parameter which handles Python-level updates.

The trigger ensures updated_at is always current, even for direct SQL updates
outside SQLAlchemy ORM (e.g., pgqueuer task claims, manual DB operations).

This is required for Story 5.6 (Real-Time Status Updates to Notion) to ensure
accurate last-modified timestamps are synced to Notion (AC2, FR55).

Revision ID: 20260117_0001
Revises: 20260116_0004_add_round_robin_index
Create Date: 2026-01-17

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260117_0001"
down_revision: str | None = "20260116_0004_add_round_robin_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add PostgreSQL trigger to auto-update tasks.updated_at on every UPDATE."""
    # Create reusable trigger function for updating updated_at timestamps
    op.execute(
        """
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    # Apply trigger to tasks table
    op.execute(
        """
        CREATE TRIGGER update_tasks_updated_at
            BEFORE UPDATE ON tasks
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
        """
    )


def downgrade() -> None:
    """Remove PostgreSQL trigger for tasks.updated_at auto-update."""
    # Drop trigger from tasks table
    op.execute("DROP TRIGGER IF EXISTS update_tasks_updated_at ON tasks;")

    # Drop trigger function (only if no other tables use it)
    # Note: If we add this trigger to other tables in future, we should not drop
    # the function in downgrade. For now, it's safe to drop.
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column();")
