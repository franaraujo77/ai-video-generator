"""add_upload_error_retrying_status

Revision ID: 805444bceaf0
Revises: 5a6b7c8d9e0f
Create Date: 2026-01-25 13:29:22.675896
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '805444bceaf0'
down_revision: Union[str, None] = '5a6b7c8d9e0f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add UPLOAD_ERROR_RETRYING status to TaskStatus enum (Story 7.6).

    Adds new status value for transient YouTube upload errors that will be
    retried with exponential backoff or paused until quota reset.
    """
    # Add new enum value to taskstatus using raw SQL (PostgreSQL specific)
    op.execute("ALTER TYPE taskstatus ADD VALUE IF NOT EXISTS 'upload_error_retrying'")


def downgrade() -> None:
    """Remove UPLOAD_ERROR_RETRYING status from TaskStatus enum.

    WARNING: This downgrade is difficult to implement safely in PostgreSQL
    because removing enum values can break existing data. This is a no-op
    downgrade that leaves the enum value in place.

    To fully downgrade, you would need to:
    1. Update all tasks with status='upload_error_retrying' to another status
    2. Recreate the enum type without the value (requires table locks)
    """
    # No-op downgrade - removing enum values is complex and risky
    pass
