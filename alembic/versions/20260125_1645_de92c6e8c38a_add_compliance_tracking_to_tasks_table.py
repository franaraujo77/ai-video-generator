"""Add compliance tracking to tasks table

Revision ID: de92c6e8c38a
Revises: 805444bceaf0
Create Date: 2026-01-25 16:45:16.376157
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'de92c6e8c38a'
down_revision: Union[str, None] = '805444bceaf0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add YouTube Partner Program compliance tracking fields to tasks table.

    Story 7.7 - YouTube Compliance Enforcement

    Adds:
    - compliance_evidence: JSONB field for human review evidence package
    - compliance_validated_at: Timestamp when compliance checks passed
    - COMPLIANCE_VIOLATION enum value: Terminal status for compliance failures
    """
    # Add COMPLIANCE_VIOLATION to TaskStatus enum
    op.execute("ALTER TYPE taskstatus ADD VALUE IF NOT EXISTS 'compliance_violation'")

    # Add compliance tracking columns to tasks table
    op.add_column(
        'tasks',
        sa.Column(
            'compliance_evidence',
            sa.dialects.postgresql.JSON,
            nullable=True,
            comment='Human review evidence package (creative_decisions, review_artifacts, production_timeline)'
        )
    )

    op.add_column(
        'tasks',
        sa.Column(
            'compliance_validated_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Timestamp when compliance checks passed (uniqueness, duplicate detection, frequency throttling)'
        )
    )


def downgrade() -> None:
    """Remove compliance tracking fields from tasks table.

    WARNING: Downgrading will lose all compliance evidence data.
    Cannot remove enum values in PostgreSQL (limitation of ALTER TYPE).
    """
    # Drop compliance tracking columns
    op.drop_column('tasks', 'compliance_validated_at')
    op.drop_column('tasks', 'compliance_evidence')

    # NOTE: Cannot remove 'compliance_violation' from taskstatus enum
    # PostgreSQL does not support removing enum values via ALTER TYPE
    # The enum value will remain but become unused after downgrade
