"""add_gemini_quota_usage_table

Revision ID: 6c2d20acdb3f
Revises: 3a4fec4905a2
Create Date: 2026-01-23 13:30:54.403434
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '6c2d20acdb3f'
down_revision: Union[str, None] = '3a4fec4905a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add gemini_quota_usage table for API quota tracking.

    Story 6.8: API Quota Monitoring
    Tracks Gemini API requests per channel per day to prevent quota exhaustion.
    """
    op.create_table(
        'gemini_quota_usage',
        sa.Column('channel_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('requests_used', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('daily_limit', sa.Integer(), nullable=False, server_default='1500'),
        sa.CheckConstraint('requests_used >= 0', name='ck_gemini_quota_non_negative'),
        sa.CheckConstraint('daily_limit > 0', name='ck_gemini_quota_limit_positive'),
        sa.ForeignKeyConstraint(['channel_id'], ['channels.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('channel_id', 'date', name='pk_gemini_quota'),
        comment='Gemini API quota tracking per channel per day (Story 6.8 - FR34)'
    )

    # Index for cleanup queries (delete rows older than 7 days)
    op.create_index(
        'ix_gemini_quota_date',
        'gemini_quota_usage',
        ['date']
    )


def downgrade() -> None:
    """Remove gemini_quota_usage table."""
    op.drop_index('ix_gemini_quota_date', table_name='gemini_quota_usage')
    op.drop_table('gemini_quota_usage')
