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

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, LargeBinary, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    """Get current UTC datetime (timezone-aware)."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


class Channel(Base):
    """YouTube channel configuration and tracking.

    Each channel represents a distinct YouTube channel with its own
    credentials, voice settings, branding, storage, and content configuration.

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
        storage_strategy: Asset storage strategy - "notion" (default) or "r2" (FR12).
        r2_account_id_encrypted: Fernet-encrypted Cloudflare account ID for R2 storage.
        r2_access_key_id_encrypted: Fernet-encrypted R2 access key ID.
        r2_secret_access_key_encrypted: Fernet-encrypted R2 secret access key.
        r2_bucket_name: R2 bucket name for asset storage (not encrypted, not sensitive).
        max_concurrent: Maximum parallel tasks allowed for this channel (FR13, FR16).
            Used for capacity tracking and fair scheduling. Default is 2, range 1-10.

    Note:
        Encrypted fields store credentials as bytes. Use CredentialService
        to encrypt/decrypt credentials - NEVER access encrypted fields directly.
        Voice IDs are NOT encrypted - they are not sensitive (public ElevenLabs IDs).
        R2 bucket names are NOT encrypted - they are not sensitive.
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

    # Storage strategy configuration (FR12)
    # "notion" (default) or "r2" for Cloudflare R2 storage
    storage_strategy: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="notion",
        server_default="notion",
    )

    # R2 credentials (Fernet encrypted) - only used when storage_strategy="r2"
    # Use CredentialService for encrypt/decrypt operations
    r2_account_id_encrypted: Mapped[bytes | None] = mapped_column(
        LargeBinary,
        nullable=True,
    )
    r2_access_key_id_encrypted: Mapped[bytes | None] = mapped_column(
        LargeBinary,
        nullable=True,
    )
    r2_secret_access_key_encrypted: Mapped[bytes | None] = mapped_column(
        LargeBinary,
        nullable=True,
    )
    # R2 bucket name is NOT encrypted - not sensitive
    r2_bucket_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    # Capacity configuration (FR13, FR16)
    # Maximum parallel tasks allowed for this channel (range 1-10)
    max_concurrent: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=2,
        server_default="2",
    )

    # Relationship to tasks (one-to-many)
    tasks: Mapped[list["Task"]] = relationship("Task", back_populates="channel")

    def __repr__(self) -> str:
        """Return string representation for debugging.

        Note:
            NEVER expose encrypted fields in repr - security risk.
            Shows voice_id presence (not value) for debugging.
            Shows storage_strategy and max_concurrent values for clarity.
        """
        voice_info = "set" if self.voice_id else "not_set"
        return (
            f"<Channel(channel_id={self.channel_id!r}, name={self.channel_name!r}, "
            f"voice_id={voice_info}, storage_strategy={self.storage_strategy!r}, "
            f"max_concurrent={self.max_concurrent})>"
        )


# Task status constants for capacity calculations
PENDING_STATUSES = ("pending",)
IN_PROGRESS_STATUSES = ("claimed", "processing", "awaiting_review")


class Task(Base):
    """Video generation task in the pipeline.

    Tasks represent a video generation job that moves through the 8-step
    pipeline. Status tracks progress and enables capacity calculations.

    Status values and their meanings:
        - pending: Task created, awaiting worker pickup
        - claimed: Worker claimed task (transitional state)
        - processing: Worker actively executing task
        - awaiting_review: Hit human review gate
        - approved: Human approved, continue processing
        - rejected: Human rejected, needs intervention
        - completed: Successfully finished
        - failed: Permanent failure (non-retriable)
        - retry: Temporary failure, will retry

    Capacity calculation uses:
        - pending_count: status == "pending"
        - in_progress_count: status IN ("claimed", "processing", "awaiting_review")

    Attributes:
        id: Internal UUID primary key.
        channel_id: Foreign key to channel this task belongs to.
        status: Current task status (see status values above).
        created_at: Timestamp when task was created.
        updated_at: Timestamp of last status change.
        channel: Relationship to the Channel model.

    Note:
        Composite index on (channel_id, status) optimizes queue queries.
        Partial index on status='pending' speeds up pending task lookups.
    """

    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    channel_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("channels.channel_id"),
        nullable=False,
        index=True,
    )
    # Status column stores task lifecycle state.
    # Valid values: pending, claimed, processing, awaiting_review, approved,
    # rejected, completed, failed, retry (see TASK_STATUSES in architecture.md)
    # Note: Database-level CHECK constraint deferred to Epic 4 (Worker Orchestration)
    # which implements the full state machine with transitions.
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        index=True,
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

    # Relationship to channel
    channel: Mapped["Channel"] = relationship("Channel", back_populates="tasks")

    # Indexes for efficient queue queries
    # Note: Migration is source of truth for indexes. Model defines composite
    # index for SQLAlchemy awareness. Additional indexes in migration:
    # - idx_tasks_pending: Partial index WHERE status='pending' for fast lookups
    __table_args__ = (
        # Composite index for channel + status filtering (capacity queries)
        Index("ix_tasks_channel_id_status", "channel_id", "status"),
    )

    def __repr__(self) -> str:
        """Return string representation for debugging."""
        return (
            f"<Task(id={self.id!s:.8}, channel_id={self.channel_id!r}, "
            f"status={self.status!r})>"
        )
