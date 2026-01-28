"""add_cost_thresholds_table

Story 8.8: Cost Dashboard & Reporting - Cost Threshold Alerting Infrastructure

This migration creates the cost_thresholds table for per-channel budget limits
and threshold alerting configuration. Enables cost alerts via Discord webhooks.

Revision ID: f8e9b7a6c5d4
Revises: c078ac509e9e
Create Date: 2026-01-28 20:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f8e9b7a6c5d4'
down_revision: Union[str, None] = 'c078ac509e9e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema - add cost_thresholds table."""
    op.create_table(
        'cost_thresholds',
        # Primary key
        sa.Column(
            'id',
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Unique threshold ID"
        ),
        # Foreign key to channels
        sa.Column(
            'channel_id',
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Channel this threshold applies to"
        ),
        # Threshold configuration
        sa.Column(
            'threshold_usd',
            sa.Numeric(precision=10, scale=2),
            nullable=False,
            comment="Cost limit in USD (e.g., 500.00 for $500 weekly limit)"
        ),
        sa.Column(
            'period',
            sa.String(length=20),
            nullable=False,
            comment="Threshold period: 'weekly' (Mon-Sun) or 'monthly' (1st-last day)"
        ),
        # Alert configuration
        sa.Column(
            'enabled',
            sa.Boolean(),
            nullable=False,
            server_default='true',
            comment="Whether threshold alerting is active"
        ),
        sa.Column(
            'alert_on_approach',
            sa.Boolean(),
            nullable=False,
            server_default='true',
            comment="Alert at 80% threshold (early warning before overspending)"
        ),
        # Discord webhook (optional per-threshold override)
        sa.Column(
            'discord_webhook_url',
            sa.String(length=500),
            nullable=True,
            comment="Optional per-threshold Discord webhook override (uses global webhook if None)"
        ),
        # Audit timestamps
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()'),
            comment="Threshold creation timestamp"
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()'),
            comment="Threshold last update timestamp"
        ),
        # Primary key constraint
        sa.PrimaryKeyConstraint('id'),
        # Foreign key constraint
        sa.ForeignKeyConstraint(
            ['channel_id'],
            ['channels.id'],
            ondelete='CASCADE'
        ),
        # Check constraints
        sa.CheckConstraint(
            'threshold_usd > 0',
            name='ck_cost_thresholds_positive_threshold'
        ),
        sa.CheckConstraint(
            "period IN ('weekly', 'monthly')",
            name='ck_cost_thresholds_valid_period'
        )
    )

    # Create indexes for efficient queries
    op.create_index(
        'ix_cost_thresholds_channel_id',
        'cost_thresholds',
        ['channel_id']
    )
    op.create_index(
        'ix_cost_thresholds_enabled',
        'cost_thresholds',
        ['enabled']
    )


def downgrade() -> None:
    """Downgrade database schema - remove cost_thresholds table."""
    op.drop_index('ix_cost_thresholds_enabled', table_name='cost_thresholds')
    op.drop_index('ix_cost_thresholds_channel_id', table_name='cost_thresholds')
    op.drop_table('cost_thresholds')
