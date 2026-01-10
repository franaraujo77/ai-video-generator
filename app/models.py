"""SQLAlchemy 2.0 ORM models.

This module contains all SQLAlchemy models for the orchestration layer.
All models use the Mapped[type] annotation pattern required by SQLAlchemy 2.0.

Models are kept in a single file until ~500 lines, then split by domain.

Encrypted Fields Pattern:
    Sensitive credentials (OAuth tokens, API keys) are stored encrypted using
    Fernet symmetric encryption. Encrypted columns follow the naming convention
    `{field}_encrypted` and use LargeBinary type since Fernet outputs bytes.

    Example:
        youtube_token_encrypted: Mapped[bytes | None]  # OAuth refresh token
        notion_token_encrypted: Mapped[bytes | None]   # Integration token

    NEVER expose encrypted fields in __repr__ or log statements.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, LargeBinary, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    """Get current UTC datetime (timezone-aware)."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


class Channel(Base):
    """YouTube channel configuration and tracking.

    Each channel represents a distinct YouTube channel with its own
    credentials, voice settings, branding, and content configuration.

    Attributes:
        id: Internal UUID primary key.
        channel_id: Business identifier for the channel (e.g., "poke1", "nature1").
        channel_name: Human-readable display name.
        created_at: Timestamp when channel was registered.
        updated_at: Timestamp of last configuration change.
        is_active: Whether channel is enabled for video generation.
        youtube_token_encrypted: Fernet-encrypted YouTube OAuth refresh token.
        notion_token_encrypted: Fernet-encrypted Notion integration token.
        gemini_key_encrypted: Fernet-encrypted Gemini API key.
        elevenlabs_key_encrypted: Fernet-encrypted ElevenLabs API key.
        voice_id: ElevenLabs voice ID for narration (FR10). Not sensitive, stored plaintext.
        default_voice_id: Fallback voice ID when channel voice is None.
        branding_intro_path: Relative path to intro video for video assembly (FR11).
        branding_outro_path: Relative path to outro video for video assembly (FR11).
        branding_watermark_path: Relative path to watermark image for video assembly (FR11).

    Note:
        Encrypted fields store credentials as bytes. Use CredentialService
        to encrypt/decrypt credentials - NEVER access encrypted fields directly.
        Voice IDs are NOT encrypted - they are not sensitive (public ElevenLabs IDs).
    """

    __tablename__ = "channels"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    channel_id: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )
    channel_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        index=True,  # Index for filtering active/inactive channels
    )

    # Encrypted credentials (Fernet symmetric encryption)
    # Use CredentialService for encrypt/decrypt operations
    youtube_token_encrypted: Mapped[bytes | None] = mapped_column(
        LargeBinary,
        nullable=True,
    )
    notion_token_encrypted: Mapped[bytes | None] = mapped_column(
        LargeBinary,
        nullable=True,
    )
    gemini_key_encrypted: Mapped[bytes | None] = mapped_column(
        LargeBinary,
        nullable=True,
    )
    elevenlabs_key_encrypted: Mapped[bytes | None] = mapped_column(
        LargeBinary,
        nullable=True,
    )

    # Voice configuration (FR10)
    # Voice IDs are NOT encrypted - they are public ElevenLabs identifiers
    voice_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    default_voice_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    # Branding configuration (FR11)
    # Paths are relative to channel workspace, validated in schema
    branding_intro_path: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    branding_outro_path: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    branding_watermark_path: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    def __repr__(self) -> str:
        """Return string representation for debugging.

        Note:
            NEVER expose encrypted fields in repr - security risk.
            Shows voice_id presence (not value) for debugging.
        """
        voice_info = "set" if self.voice_id else "not_set"
        return f"<Channel(channel_id={self.channel_id!r}, name={self.channel_name!r}, voice_id={voice_info})>"
