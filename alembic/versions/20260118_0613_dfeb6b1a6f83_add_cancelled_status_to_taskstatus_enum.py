"""Add cancelled status to taskstatus enum.

This migration adds the 'cancelled' status to the PostgreSQL taskstatus enum
to support user cancellation of video generation tasks (Story 5.1 code review fix).

The cancelled status allows users to:
- Cancel tasks from DRAFT, QUEUED, or FINAL_REVIEW states
- Re-queue cancelled tasks if they change their mind (CANCELLED → QUEUED)

This completes the 27-status workflow state machine implementation.

Revision ID: dfeb6b1a6f83
Revises: 20260117_0001
Create Date: 2026-01-18 06:13:24.258755
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dfeb6b1a6f83'
down_revision: Union[str, None] = '20260117_0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add 'cancelled' status to taskstatus PostgreSQL enum.

    PostgreSQL enum modification pattern:
    - ADD VALUE adds a new enum value to existing type
    - AFTER 'claimed' positions it logically with other initial states
    - Operation is NOT transactional - cannot be rolled back
    """
    # Add 'cancelled' status after 'claimed' (groups initial states together)
    op.execute("ALTER TYPE taskstatus ADD VALUE 'cancelled' AFTER 'claimed'")


def downgrade() -> None:
    """Downgrade not supported for PostgreSQL enum value removal.

    PostgreSQL does not support removing enum values once added.
    To remove, would need to:
    1. Create new enum without 'cancelled'
    2. Migrate all data
    3. Drop old enum
    4. Rename new enum

    This is complex and risky, so downgrade is not implemented.
    If rollback is needed, restore from database backup.
    """
    raise NotImplementedError(
        "Downgrade not supported: PostgreSQL cannot remove enum values. "
        "Restore from backup if rollback is required."
    )
