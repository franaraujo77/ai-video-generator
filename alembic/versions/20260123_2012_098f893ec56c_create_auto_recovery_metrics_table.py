"""create_auto_recovery_metrics_table

Revision ID: 098f893ec56c
Revises: 479d7df4f527
Create Date: 2026-01-23 20:12:12.764702
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '098f893ec56c'
down_revision: Union[str, None] = '479d7df4f527'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema - create auto_recovery_metrics table.

    Story 6.10: Auto-Recovery Success Rate Tracking
    Creates weekly metrics table for FR35 (80% auto-recovery target) tracking.
    Uses composite PK (channel_id, week_starting_date) for per-channel per-week metrics.
    """
    op.create_table(
        'auto_recovery_metrics',
        # Composite primary key columns
        sa.Column('channel_id', sa.UUID(), nullable=False),
        sa.Column('week_starting_date', sa.Date(), nullable=False),

        # Success rate metrics
        sa.Column('total_retry_attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_auto_recovered', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('success_rate', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('average_retries_before_success', sa.Float(), nullable=True),

        # Error category breakdown
        sa.Column('transient_error_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('transient_recovered', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('permanent_error_count', sa.Integer(), nullable=False, server_default='0'),

        # Metadata timestamps
        sa.Column('calculated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),

        # Composite primary key constraint
        sa.PrimaryKeyConstraint('channel_id', 'week_starting_date', name='pk_auto_recovery_metrics'),

        # Foreign key to channels table (CASCADE delete)
        sa.ForeignKeyConstraint(['channel_id'], ['channels.id'], ondelete='CASCADE'),

        # Check constraints for data integrity
        sa.CheckConstraint('total_retry_attempts >= 0', name='ck_auto_recovery_attempts_non_negative'),
        sa.CheckConstraint('total_auto_recovered >= 0', name='ck_auto_recovery_recovered_non_negative'),
        sa.CheckConstraint(
            'total_auto_recovered <= total_retry_attempts',
            name='ck_auto_recovery_recovered_le_attempts'
        ),
        sa.CheckConstraint(
            'success_rate >= 0.0 AND success_rate <= 100.0',
            name='ck_auto_recovery_rate_range'
        ),
    )

    # Indexes for metrics queries
    # Historical queries by week
    op.create_index('ix_auto_recovery_metrics_week', 'auto_recovery_metrics', ['week_starting_date'], unique=False)

    # Threshold alert queries (WHERE success_rate < 80)
    op.create_index('ix_auto_recovery_metrics_success_rate', 'auto_recovery_metrics', ['success_rate'], unique=False)

    # Per-channel queries
    op.create_index('ix_auto_recovery_metrics_channel', 'auto_recovery_metrics', ['channel_id'], unique=False)


def downgrade() -> None:
    """Downgrade database schema - drop auto_recovery_metrics table."""
    # Drop indexes
    op.drop_index('ix_auto_recovery_metrics_channel', table_name='auto_recovery_metrics')
    op.drop_index('ix_auto_recovery_metrics_success_rate', table_name='auto_recovery_metrics')
    op.drop_index('ix_auto_recovery_metrics_week', table_name='auto_recovery_metrics')

    # Drop table (CASCADE removes foreign key constraints)
    op.drop_table('auto_recovery_metrics')
