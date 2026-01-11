"""004 add storage strategy columns

Revision ID: 004_add_storage_strategy
Revises: 003_add_voice_branding
Create Date: 2026-01-10

Adds storage strategy configuration columns to channels table for
per-channel asset storage strategy (FR12).

Storage strategy columns:
    - storage_strategy: "notion" (default) or "r2" for Cloudflare R2 storage
    - r2_account_id_encrypted: Fernet-encrypted Cloudflare account ID
    - r2_access_key_id_encrypted: Fernet-encrypted R2 access key ID
    - r2_secret_access_key_encrypted: Fernet-encrypted R2 secret access key
    - r2_bucket_name: R2 bucket name (not encrypted, not sensitive)

R2 credential columns are nullable since channels default to Notion storage.
Use StorageStrategyService for resolution logic with fallback to "notion".
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004_add_storage_strategy"
down_revision: str | None = "003_add_voice_branding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add storage strategy columns to channels table."""
    # Storage strategy column (FR12) - non-nullable with default "notion"
    op.add_column(
        "channels",
        sa.Column(
            "storage_strategy",
            sa.String(20),
            nullable=False,
            server_default="notion",
        ),
    )

    # R2 credential columns (encrypted) - nullable
    op.add_column(
        "channels",
        sa.Column("r2_account_id_encrypted", sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        "channels",
        sa.Column("r2_access_key_id_encrypted", sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        "channels",
        sa.Column("r2_secret_access_key_encrypted", sa.LargeBinary(), nullable=True),
    )

    # R2 bucket name - not encrypted, just a string
    op.add_column(
        "channels",
        sa.Column("r2_bucket_name", sa.String(100), nullable=True),
    )


def downgrade() -> None:
    """Remove storage strategy columns from channels table."""
    # Remove R2 columns
    op.drop_column("channels", "r2_bucket_name")
    op.drop_column("channels", "r2_secret_access_key_encrypted")
    op.drop_column("channels", "r2_access_key_id_encrypted")
    op.drop_column("channels", "r2_account_id_encrypted")

    # Remove storage strategy column
    op.drop_column("channels", "storage_strategy")
