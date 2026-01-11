"""002 add encrypted credential columns

Revision ID: 002_add_encrypted_credentials
Revises: 001_initial_channels
Create Date: 2026-01-10

Adds encrypted credential columns to channels table for storing
per-channel OAuth tokens and API keys using Fernet encryption.

Columns added:
    - youtube_token_encrypted: YouTube OAuth refresh token (bytes)
    - notion_token_encrypted: Notion integration token (bytes)
    - gemini_key_encrypted: Gemini API key (bytes)
    - elevenlabs_key_encrypted: ElevenLabs API key (bytes)

All columns are nullable since channels may not have credentials initially.
Use CredentialService for encrypt/decrypt operations.
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002_add_encrypted_credentials"
down_revision: str | None = "001_initial_channels"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add encrypted credential columns to channels table."""
    op.add_column(
        "channels",
        sa.Column("youtube_token_encrypted", sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        "channels",
        sa.Column("notion_token_encrypted", sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        "channels",
        sa.Column("gemini_key_encrypted", sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        "channels",
        sa.Column("elevenlabs_key_encrypted", sa.LargeBinary(), nullable=True),
    )


def downgrade() -> None:
    """Remove encrypted credential columns from channels table."""
    op.drop_column("channels", "elevenlabs_key_encrypted")
    op.drop_column("channels", "gemini_key_encrypted")
    op.drop_column("channels", "notion_token_encrypted")
    op.drop_column("channels", "youtube_token_encrypted")
