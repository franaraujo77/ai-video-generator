"""Add weekly_metrics table (Story 8.6)

Revision ID: 53568460d196
Revises: 20260127_2300
Create Date: 2026-01-28 08:48:00

Story 8.6: Weekly Success Rate Calculation

Creates weekly_metrics table for tracking overall pipeline health, success rate,
and failure patterns. Uses composite PK (channel_id, week_starting_date) for
per-channel per-week metrics.

Key Features:
- Composite primary key (channel_id, week_starting_date)
- Decimal precision for percentages (success_rate, auto_recovery_rate)
- Failure breakdown by category (TRANSIENT, PERMANENT, UNKNOWN)
- Failure breakdown by stage (assets, video, audio, upload)
- DESC index on week_starting_date for trend queries
- Check constraints for data integrity
- CASCADE delete when channel is deleted
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '53568460d196'
down_revision: Union[str, None] = '20260127_2300'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema - create weekly_metrics table.

    Story 8.6: Weekly Success Rate Calculation
    Creates weekly metrics table for overall pipeline health monitoring.
    Uses composite PK (channel_id, week_starting_date) for per-channel per-week metrics.
    """
    op.create_table(
        'weekly_metrics',
        # Composite primary key columns
        sa.Column('channel_id', sa.UUID(), nullable=False),
        sa.Column('week_starting_date', sa.Date(), nullable=False),

        # Volume metrics
        sa.Column('total_videos_processed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('successful_videos', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('success_rate', sa.Numeric(5, 2), nullable=False, server_default='0.00'),

        # Performance metrics
        sa.Column('avg_processing_time_seconds', sa.Integer(), nullable=True),

        # Recovery metrics
        sa.Column('auto_recovery_rate', sa.Numeric(5, 2), nullable=True),

        # Failure breakdown by category
        sa.Column('transient_failures', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('permanent_failures', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('unknown_failures', sa.Integer(), nullable=False, server_default='0'),

        # Failure breakdown by stage
        sa.Column('failed_at_assets', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_at_video', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_at_audio', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_at_upload', sa.Integer(), nullable=False, server_default='0'),

        # Metadata timestamps
        sa.Column('calculated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),

        # Composite primary key constraint
        sa.PrimaryKeyConstraint('channel_id', 'week_starting_date', name='pk_weekly_metrics'),

        # Foreign key to channels table (CASCADE delete)
        sa.ForeignKeyConstraint(['channel_id'], ['channels.id'], ondelete='CASCADE'),

        # Check constraints for data integrity
        sa.CheckConstraint('total_videos_processed >= 0', name='ck_weekly_metrics_total_non_negative'),
        sa.CheckConstraint('successful_videos >= 0', name='ck_weekly_metrics_successful_non_negative'),
        sa.CheckConstraint(
            'successful_videos <= total_videos_processed',
            name='ck_weekly_metrics_successful_le_total'
        ),
        sa.CheckConstraint(
            'success_rate >= 0.0 AND success_rate <= 100.0',
            name='ck_weekly_metrics_rate_range'
        ),
        sa.CheckConstraint('transient_failures >= 0', name='ck_weekly_metrics_transient_non_negative'),
        sa.CheckConstraint('permanent_failures >= 0', name='ck_weekly_metrics_permanent_non_negative'),
        sa.CheckConstraint('unknown_failures >= 0', name='ck_weekly_metrics_unknown_non_negative'),
        sa.CheckConstraint('failed_at_assets >= 0', name='ck_weekly_metrics_assets_non_negative'),
        sa.CheckConstraint('failed_at_video >= 0', name='ck_weekly_metrics_video_non_negative'),
        sa.CheckConstraint('failed_at_audio >= 0', name='ck_weekly_metrics_audio_non_negative'),
        sa.CheckConstraint('failed_at_upload >= 0', name='ck_weekly_metrics_upload_non_negative'),
    )

    # Indexes for metrics queries
    # Trend queries (most recent first) - PostgreSQL DESC operator on week_starting_date
    op.create_index(
        'ix_weekly_metrics_channel_week_desc',
        'weekly_metrics',
        ['channel_id', 'week_starting_date'],
        unique=False,
        postgresql_ops={'week_starting_date': 'DESC'}
    )

    # Audit trail queries
    op.create_index(
        'ix_weekly_metrics_calculated_at',
        'weekly_metrics',
        ['calculated_at'],
        unique=False
    )


def downgrade() -> None:
    """Downgrade database schema - drop weekly_metrics table."""
    # Drop indexes
    op.drop_index('ix_weekly_metrics_calculated_at', table_name='weekly_metrics')
    op.drop_index('ix_weekly_metrics_channel_week_desc', table_name='weekly_metrics')

    # Drop table (CASCADE removes foreign key constraints)
    op.drop_table('weekly_metrics')
