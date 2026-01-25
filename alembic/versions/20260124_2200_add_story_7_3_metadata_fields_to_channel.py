"""add story 7.3 metadata fields to channel

Revision ID: 10b2c3d4e5f6
Revises: 09a1b2c3d4e5
Create Date: 2026-01-24 22:00:00.000000

This migration adds three metadata configuration fields to the channels table
for YouTube video metadata generation (Story 7.3 - FR62):

1. default_tags: JSON array of default tags for all channel videos
2. description_template: Text template with {placeholders} for video descriptions
3. default_privacy: Default privacy setting ("private", "unlisted", "public")

These fields enable channels to configure metadata generation behavior for
YouTube uploads without hardcoding values in the application.

Story: 7.3 - Video Metadata Generation
FR: FR62 (Generate metadata from Notion)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON


# revision identifiers, used by Alembic.
revision = '10b2c3d4e5f6'
down_revision = '09a1b2c3d4e5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add metadata configuration fields to channels table.

    Fields added:
    - default_tags: JSON array of default tags (nullable, e.g., ['nature', 'documentary'])
    - description_template: Text template with placeholders (nullable)
    - default_privacy: String for privacy setting (NOT NULL, default 'unlisted')

    These fields support Story 7.3 metadata generation service.
    """
    # Add default_tags JSON field
    op.add_column(
        'channels',
        sa.Column(
            'default_tags',
            JSON,
            nullable=True,
            comment="Default tags for all channel videos (e.g., ['nature', 'documentary'])"
        )
    )

    # Add description_template text field
    op.add_column(
        'channels',
        sa.Column(
            'description_template',
            sa.Text(),
            nullable=True,
            comment='Description template with {placeholders} for title, topic, channel_name, etc.'
        )
    )

    # Add default_privacy field
    op.add_column(
        'channels',
        sa.Column(
            'default_privacy',
            sa.String(20),
            nullable=False,
            server_default='unlisted',
            comment="Default privacy for uploads: 'private', 'unlisted', or 'public' (Story 7.8)"
        )
    )


def downgrade() -> None:
    """Remove metadata configuration fields from channels table."""
    op.drop_column('channels', 'default_privacy')
    op.drop_column('channels', 'description_template')
    op.drop_column('channels', 'default_tags')
