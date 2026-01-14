"""add_notion_webhook_events_table

Revision ID: f1f1300884be
Revises: 007_migrate_task_26_status
Create Date: 2026-01-13 17:03:28.278787
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1f1300884be'
down_revision: Union[str, None] = '007_migrate_task_26_status'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    # Create notion_webhook_events table for webhook idempotency tracking
    op.create_table(
        'notion_webhook_events',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('event_id', sa.String(100), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('page_id', sa.String(100), nullable=False),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('event_id', name='uq_webhook_events_event_id')
    )

    # Create index for page_id lookups (event_id already has unique constraint)
    op.create_index('ix_notion_webhook_events_page_id', 'notion_webhook_events', ['page_id'], unique=False)


def downgrade() -> None:
    """Downgrade database schema."""
    # Drop index
    op.drop_index('ix_notion_webhook_events_page_id', table_name='notion_webhook_events')

    # Drop table
    op.drop_table('notion_webhook_events')
