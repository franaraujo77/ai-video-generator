"""add_worker_heartbeats_table

Story 8.7: Health Check Endpoint - Worker Heartbeat Infrastructure

This migration creates the worker_heartbeats table for tracking worker process
liveness and activity. Used by health check endpoint to determine system status.

Revision ID: c078ac509e9e
Revises: 53568460d196
Create Date: 2026-01-28 18:03:58.897518
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c078ac509e9e'
down_revision: Union[str, None] = '53568460d196'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema - add worker_heartbeats table."""
    op.create_table(
        'worker_heartbeats',
        # Primary key
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, comment='Unique heartbeat record ID'),

        # Worker identification
        sa.Column('worker_id', sa.String(length=50), nullable=False, comment='Worker identifier (e.g., worker-1, worker-2, worker-3)'),

        # Heartbeat timestamp
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False, comment='Last heartbeat timestamp (UTC)'),

        # Worker status
        sa.Column('status', sa.String(length=20), nullable=False, server_default='online', comment='Worker status: online, idle, processing'),

        # Active task count
        sa.Column('active_task_count', sa.Integer(), nullable=False, server_default='0', comment='Number of tasks currently processing'),

        # Audit timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()'), comment='Record creation timestamp'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()'), comment='Record last update timestamp'),

        # Primary key constraint
        sa.PrimaryKeyConstraint('id', name='pk_worker_heartbeats'),
    )

    # Create indexes
    # Unique index on worker_id for atomic upserts (INSERT ON CONFLICT UPDATE)
    op.create_index('ix_worker_heartbeats_worker_id', 'worker_heartbeats', ['worker_id'], unique=True)

    # Index on last_seen_at for efficient active worker queries (< 100ms)
    op.create_index('ix_worker_heartbeats_last_seen_at', 'worker_heartbeats', ['last_seen_at'], unique=False)


def downgrade() -> None:
    """Downgrade database schema - drop worker_heartbeats table."""
    # Drop indexes first
    op.drop_index('ix_worker_heartbeats_last_seen_at', table_name='worker_heartbeats')
    op.drop_index('ix_worker_heartbeats_worker_id', table_name='worker_heartbeats')

    # Drop table
    op.drop_table('worker_heartbeats')
