"""add_youtube_quota_usage_table

Revision ID: 20260116_0005_add_youtube_quota_usage_table
Revises: 20260116_0004
Create Date: 2026-01-16

This migration adds the youtube_quota_usage table for tracking YouTube Data API v3
quota consumption per channel per day (Story 4.5: Rate Limit Aware Task Selection).

Table Structure:
    - Composite Primary Key: (channel_id, date)
    - One row per channel per day for quota isolation
    - Check constraints for data integrity
    - Index on date for cleanup queries

Quota Costs (YouTube Data API v3):
    - Upload video: 1,600 units
    - Update video: 50 units
    - List videos: 1 unit
    - Search: 100 units

Daily Limit:
    10,000 units per channel per day (resets at midnight PST)

Alert Thresholds:
    - 80% usage: WARNING alert to Discord webhook
    - 100% usage: CRITICAL alert to Discord webhook

Cleanup Recommendations:
    Implement a daily cron job to remove old quota records (7-day retention):

    ```sql
    -- Cleanup cron job (run daily at 1 AM):
    DELETE FROM youtube_quota_usage
    WHERE date < CURRENT_DATE - INTERVAL '7 days';
    ```

    Alternative: PostgreSQL pg_cron extension (if available on Railway):

    ```sql
    -- One-time setup:
    SELECT cron.schedule(
        'cleanup-youtube-quota',
        '0 1 * * *',  -- Daily at 1 AM
        $$DELETE FROM youtube_quota_usage WHERE date < CURRENT_DATE - INTERVAL '7 days'$$
    );
    ```

References:
    - Story 4.5: Rate Limit Aware Task Selection
    - FR42: Pre-claim quota verification
    - FR34: API quota monitoring
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260116_0005_add_youtube_quota_usage_table"
down_revision: str | None = "20260116_0004_add_round_robin_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add youtube_quota_usage table with composite primary key.

    Table: youtube_quota_usage
    Primary Key: (channel_id, date) - composite

    Columns:
        - channel_id: UUID (FK to channels.id)
        - date: DATE (quota tracking day)
        - units_used: INTEGER (accumulated units used today, default 0)
        - daily_limit: INTEGER (quota limit, default 10000)

    Constraints:
        - pk_youtube_quota: Composite primary key on (channel_id, date)
        - ck_youtube_quota_non_negative: units_used >= 0
        - ck_youtube_quota_limit_positive: daily_limit > 0
        - fk_youtube_quota_channel_id: Foreign key to channels.id with CASCADE delete

    Indexes:
        - ix_youtube_quota_date: Index on date for cleanup queries

    Usage Pattern:
        # Check quota before upload
        SELECT * FROM youtube_quota_usage
        WHERE channel_id = $1 AND date = CURRENT_DATE
        FOR UPDATE;  -- Lock for atomic increment

        # Record quota usage
        INSERT INTO youtube_quota_usage (channel_id, date, units_used, daily_limit)
        VALUES ($1, CURRENT_DATE, 1600, 10000)
        ON CONFLICT (channel_id, date)
        DO UPDATE SET units_used = youtube_quota_usage.units_used + 1600;
    """
    op.create_table(
        "youtube_quota_usage",
        sa.Column("channel_id", sa.UUID(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("units_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("daily_limit", sa.Integer(), nullable=False, server_default="10000"),
        sa.ForeignKeyConstraint(
            ["channel_id"],
            ["channels.id"],
            name="fk_youtube_quota_channel_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("channel_id", "date", name="pk_youtube_quota"),
        sa.CheckConstraint(
            "units_used >= 0",
            name="ck_youtube_quota_non_negative",
        ),
        sa.CheckConstraint(
            "daily_limit > 0",
            name="ck_youtube_quota_limit_positive",
        ),
    )

    # Create index on date for cleanup queries (delete WHERE date < CURRENT_DATE - 7)
    op.create_index(
        "ix_youtube_quota_date",
        "youtube_quota_usage",
        ["date"],
        unique=False,
    )


def downgrade() -> None:
    """Remove youtube_quota_usage table and associated index."""
    op.drop_index("ix_youtube_quota_date", table_name="youtube_quota_usage")
    op.drop_table("youtube_quota_usage")
