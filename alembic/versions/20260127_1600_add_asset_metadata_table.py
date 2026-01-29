"""Add asset_metadata table for URL tracking (Story 8.3)

Tracks all generated assets (images, videos, audio) with public URLs for access
from Notion. Supports both Notion-hosted and R2 storage strategies.

Changes:
1. Create asset_metadata table with UUID primary key
2. Add foreign keys to tasks and channels tables with CASCADE delete
3. Add indexes for efficient querying:
   - ix_asset_metadata_task_id (task asset lookup)
   - ix_asset_metadata_channel_type (channel-level asset queries)
   - ix_asset_metadata_unsynced (partial index for unsync'd queue)
4. Track storage strategy, URLs, and Notion sync status
5. Support correlation IDs for distributed tracing (Story 8.1 integration)

Asset types supported:
- character: Character images (transparent PNG)
- environment: Environment backgrounds
- props: Prop/object images
- composite: 16:9 composite images for video generation
- video_clip: Generated video clips (MP4)
- narration: Narration audio files (MP3)
- sfx: Sound effects audio files (MP3/WAV)

Storage strategies:
- notion: Assets uploaded to Notion as file attachments (24h URL expiration)
- r2: Assets uploaded to Cloudflare R2 bucket (permanent URLs)

Asset coverage per video:
- 22 image assets (characters, environments, props)
- 18 video clip URLs
- 18 narration audio URLs
- 18 sound effects audio URLs
Total: 76 asset URLs per video

Notion sync:
- notion_synced_at tracks last successful Notion update
- NULL indicates asset not yet synced to Notion
- Partial index on (task_id) WHERE notion_synced_at IS NULL for retry queue

Revision ID: g7f6e5d4c3b2
Revises: f6e5d4c3b2a1
Create Date: 2026-01-27 16:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'g7f6e5d4c3b2'
down_revision: Union[str, None] = 'f6e5d4c3b2a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create asset_metadata table for Story 8.3.

    Provides URL tracking for all generated assets across the video generation
    pipeline. Enables content creators to access all assets directly from Notion
    (FR48). Supports both Notion-hosted and R2 storage strategies.

    Indexes:
        - ix_asset_metadata_task_id: Fast lookup of all assets for a task
        - ix_asset_metadata_channel_type: Channel-level asset queries by type
        - ix_asset_metadata_unsynced: Partial index for unsync'd asset queue
          (WHERE notion_synced_at IS NULL)
    """
    # Create asset_metadata table
    op.create_table(
        'asset_metadata',
        sa.Column(
            'id',
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text('gen_random_uuid()'),
        ),
        sa.Column(
            'task_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('tasks.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'channel_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('channels.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'asset_type',
            sa.String(50),
            nullable=False,
            comment='Asset type: character, environment, props, composite, video_clip, narration, sfx',
        ),
        sa.Column(
            'asset_name',
            sa.String(255),
            nullable=False,
            comment='Asset filename or identifier (e.g., bulbasaur_01.png, clip_01.mp4)',
        ),
        sa.Column(
            'storage_strategy',
            sa.String(20),
            nullable=False,
            comment='Storage backend: notion or r2',
        ),
        sa.Column(
            'local_file_path',
            sa.String(512),
            nullable=True,
            comment='Local filesystem path (Railway workspace volume)',
        ),
        sa.Column(
            'asset_url',
            sa.String(1024),
            nullable=False,
            comment='Public URL for asset access (Notion-hosted or R2)',
        ),
        sa.Column(
            'notion_asset_property_id',
            sa.String(255),
            nullable=True,
            comment='Notion property ID for this asset URL (for updates)',
        ),
        sa.Column(
            'notion_synced_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Timestamp of last successful Notion sync (NULL = not synced)',
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()'),
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()'),
        ),
        comment='Track generated assets with URLs for Notion sync. Supports both Notion and R2 storage.',
    )

    # Index for fast task asset lookup
    op.create_index(
        'ix_asset_metadata_task_id',
        'asset_metadata',
        ['task_id'],
    )

    # Composite index for channel-level asset queries by type
    op.create_index(
        'ix_asset_metadata_channel_type',
        'asset_metadata',
        ['channel_id', 'asset_type'],
    )

    # Partial index for unsync'd asset queue (PostgreSQL-specific)
    # This creates an efficient index for: WHERE notion_synced_at IS NULL
    op.execute("""
        CREATE INDEX ix_asset_metadata_unsynced
        ON asset_metadata(task_id)
        WHERE notion_synced_at IS NULL
    """)


def downgrade() -> None:
    """Remove asset_metadata table.

    WARNING: Downgrading will lose all asset URL tracking history.
    Content creators will no longer be able to access asset URLs from Notion.
    """
    # Drop indexes
    op.drop_index('ix_asset_metadata_unsynced', table_name='asset_metadata')
    op.drop_index('ix_asset_metadata_channel_type', table_name='asset_metadata')
    op.drop_index('ix_asset_metadata_task_id', table_name='asset_metadata')

    # Drop table
    op.drop_table('asset_metadata')
