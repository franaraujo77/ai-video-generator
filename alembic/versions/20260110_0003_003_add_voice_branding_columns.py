"""003 add voice branding columns

Revision ID: 003_add_voice_branding
Revises: 002_add_encrypted_credentials
Create Date: 2026-01-10

Adds voice configuration and branding columns to channels table for
per-channel voice selection (FR10) and branding assets (FR11).

Voice columns:
    - voice_id: ElevenLabs voice ID for channel narration (NOT encrypted - public ID)
    - default_voice_id: Fallback voice ID when channel voice is None

Branding columns:
    - branding_intro_path: Relative path to intro video
    - branding_outro_path: Relative path to outro video
    - branding_watermark_path: Relative path to watermark image

All columns are nullable since channels may not have voice/branding configured.
Use VoiceBrandingService for resolution logic with fallback to global default.
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003_add_voice_branding"
down_revision: str | None = "002_add_encrypted_credentials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add voice and branding columns to channels table."""
    # Voice configuration columns (FR10)
    op.add_column(
        "channels",
        sa.Column("voice_id", sa.String(100), nullable=True),
    )
    op.add_column(
        "channels",
        sa.Column("default_voice_id", sa.String(100), nullable=True),
    )

    # Branding configuration columns (FR11)
    op.add_column(
        "channels",
        sa.Column("branding_intro_path", sa.String(255), nullable=True),
    )
    op.add_column(
        "channels",
        sa.Column("branding_outro_path", sa.String(255), nullable=True),
    )
    op.add_column(
        "channels",
        sa.Column("branding_watermark_path", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    """Remove voice and branding columns from channels table."""
    # Remove branding columns
    op.drop_column("channels", "branding_watermark_path")
    op.drop_column("channels", "branding_outro_path")
    op.drop_column("channels", "branding_intro_path")

    # Remove voice columns
    op.drop_column("channels", "default_voice_id")
    op.drop_column("channels", "voice_id")
