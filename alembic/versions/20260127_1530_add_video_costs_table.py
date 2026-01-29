"""Add video_costs table for component-level cost tracking (Story 8.2)

Tracks API costs at granular component level (Gemini, Kling, ElevenLabs) for
financial analysis and budget forecasting across multi-channel video production.

Changes:
1. Create video_costs table with Decimal precision for financial amounts
2. Add foreign key to tasks table with CASCADE delete
3. Add composite index (task_id, timestamp) for efficient cost breakdown queries
4. Add timestamp index for trend analysis
5. Add correlation_id for distributed tracing (Story 8.1 integration)

Cost breakdown per video:
- gemini_assets: ~$1.50 (22 images @ $0.068/image)
- kling_video: ~$7.56 (18 clips @ $0.42/clip)
- elevenlabs_narration: ~$0.72 (18 clips @ $0.04/clip)
- elevenlabs_sfx: ~$0.72 (18 clips @ $0.04/clip)
Total per video: ~$10.50

Relationship to existing cost tracking:
- Complements task.total_cost_usd (running total for quick access)
- Provides component-level breakdown for financial reporting
- Enables channel-level cost aggregation via task.channel_id

Revision ID: 1f2a3b4c5d6e
Revises: abc123def456
Create Date: 2026-01-27 15:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f6e5d4c3b2a1'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create video_costs table for Story 8.2.

    Provides component-level cost tracking for video generation pipeline.
    Each API component (Gemini, Kling, ElevenLabs) creates a separate cost
    record, enabling detailed financial analysis and cost optimization.

    Decimal Precision:
        - cost_usd uses NUMERIC(10, 4) for 4 decimal places
        - Avoids floating-point precision errors in financial calculations
        - Python Decimal type maps to PostgreSQL NUMERIC

    Indexes:
        - Composite (task_id, timestamp): Fast cost breakdown queries per task
        - Single (timestamp): Trend analysis over time periods
    """
    # Create video_costs table
    op.create_table(
        'video_costs',
        sa.Column(
            'id',
            sa.Integer(),
            primary_key=True,
            autoincrement=True
        ),
        sa.Column(
            'task_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('tasks.id', ondelete='CASCADE'),
            nullable=False
        ),
        sa.Column(
            'component',
            sa.String(50),
            nullable=False,
            comment='API component: gemini_assets, kling_video, elevenlabs_narration, elevenlabs_sfx'
        ),
        sa.Column(
            'cost_usd',
            sa.Numeric(10, 4),
            nullable=False,
            comment='Cost in USD with 4 decimal places precision'
        ),
        sa.Column(
            'units_used',
            sa.Integer(),
            nullable=False,
            comment='API-specific units consumed (tokens, clips, characters, etc.)'
        ),
        sa.Column(
            'timestamp',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()'),
            comment='UTC timestamp when cost was recorded'
        ),
        sa.Column(
            'correlation_id',
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment='Correlation ID for distributed tracing (from Story 8.1 context)'
        ),
        comment='Per-component cost tracking for video generation. Enables financial analysis and budget forecasting.'
    )

    # Composite index for efficient cost breakdown queries by task
    op.create_index(
        'ix_video_costs_task_id_timestamp',
        'video_costs',
        ['task_id', 'timestamp']
    )

    # Single index for trend analysis over time
    op.create_index(
        'ix_video_costs_timestamp',
        'video_costs',
        ['timestamp']
    )


def downgrade() -> None:
    """Remove video_costs table.

    WARNING: Downgrading will lose all cost tracking history.
    Total cost remains in task.total_cost_usd but component breakdown is lost.
    """
    # Drop indexes
    op.drop_index('ix_video_costs_timestamp', table_name='video_costs')
    op.drop_index('ix_video_costs_task_id_timestamp', table_name='video_costs')

    # Drop table
    op.drop_table('video_costs')
