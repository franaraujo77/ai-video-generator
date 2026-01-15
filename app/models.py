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

import enum
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    """Get current UTC datetime (timezone-aware)."""
    return datetime.now(timezone.utc)


class TaskStatus(enum.Enum):
    """26-status workflow state machine for video generation pipeline.

    Status values follow the video generation pipeline order from draft to published.
    Each status represents a specific stage in the 8-step production pipeline.

    Pipeline Flow:
        draft → queued → claimed → generating_assets → assets_ready → assets_approved
        → generating_composites → composites_ready → generating_video → video_ready
        → video_approved → generating_audio → audio_ready → audio_approved
        → generating_sfx → sfx_ready → assembling → assembly_ready → final_review
        → approved → uploading → published

    Error States (recoverable via retry):
        asset_error, video_error, audio_error, upload_error

    See UX Design document for full state machine transitions.
    """

    # Initial states
    DRAFT = "draft"
    QUEUED = "queued"
    CLAIMED = "claimed"

    # Asset generation phase (Step 1)
    GENERATING_ASSETS = "generating_assets"
    ASSETS_READY = "assets_ready"
    ASSETS_APPROVED = "assets_approved"

    # Composite creation phase (Step 2)
    GENERATING_COMPOSITES = "generating_composites"
    COMPOSITES_READY = "composites_ready"

    # Video generation phase (Step 3)
    GENERATING_VIDEO = "generating_video"
    VIDEO_READY = "video_ready"
    VIDEO_APPROVED = "video_approved"

    # Audio generation phase (Step 4)
    GENERATING_AUDIO = "generating_audio"
    AUDIO_READY = "audio_ready"
    AUDIO_APPROVED = "audio_approved"

    # Sound effects phase (Step 5)
    GENERATING_SFX = "generating_sfx"
    SFX_READY = "sfx_ready"

    # Assembly phase (Step 6)
    ASSEMBLING = "assembling"
    ASSEMBLY_READY = "assembly_ready"

    # Review and approval phase (Step 7)
    FINAL_REVIEW = "final_review"
    APPROVED = "approved"

    # YouTube upload phase (Step 8)
    UPLOADING = "uploading"
    PUBLISHED = "published"

    # Error states
    ASSET_ERROR = "asset_error"
    VIDEO_ERROR = "video_error"
    AUDIO_ERROR = "audio_error"
    UPLOAD_ERROR = "upload_error"


# Status groupings for capacity tracking (FR13, FR16)
PENDING_STATUSES = [TaskStatus.QUEUED]

IN_PROGRESS_STATUSES = [
    TaskStatus.CLAIMED,
    TaskStatus.GENERATING_ASSETS,
    TaskStatus.ASSETS_READY,
    TaskStatus.GENERATING_COMPOSITES,
    TaskStatus.COMPOSITES_READY,
    TaskStatus.GENERATING_VIDEO,
    TaskStatus.VIDEO_READY,
    TaskStatus.GENERATING_AUDIO,
    TaskStatus.AUDIO_READY,
    TaskStatus.GENERATING_SFX,
    TaskStatus.SFX_READY,
    TaskStatus.ASSEMBLING,
    TaskStatus.ASSEMBLY_READY,
    TaskStatus.FINAL_REVIEW,
]


class PriorityLevel(enum.Enum):
    """Task priority levels for queue management.

    Priority determines task execution order within the queue.
    Workers select tasks using: Priority (high > normal > low) → FIFO (created_at).

    Levels:
        high: Urgent content, processed first (e.g., trending topics, time-sensitive)
        normal: Standard priority (default for most videos)
        low: Background tasks, processed when no high/normal tasks available
    """

    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


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


class Task(Base):
    """Video generation task with 26-status workflow state machine.

    Tasks represent video generation jobs that move through the 8-step production
    pipeline from draft to published. Each task belongs to a channel and tracks
    video metadata, Notion integration, and pipeline status.

    26-Status Workflow:
        The status field follows the TaskStatus enum (26 states) which maps to
        the 8-step pipeline: asset generation → composites → video → audio → sfx
        → assembly → review → upload. See TaskStatus enum for full flow.

    Notion Integration:
        Tasks are bidirectionally synced with Notion database entries via the
        notion_page_id field (unique constraint). Workers poll Notion for new
        entries and push status updates back to Notion.

    Capacity Calculation:
        Channel.max_concurrent enforces parallel task limits per channel. Workers
        query tasks WHERE status IN (claimed, generating_*, assembling, uploading)
        to calculate in-progress count before claiming new tasks.

    Attributes:
        id: Internal UUID primary key.
        channel_id: Foreign key to channels.id (NOT channel_id string).
        notion_page_id: Notion page UUID (32 chars, no dashes). Unique constraint.
        title: Video title (255 chars max, from Notion).
        topic: Video topic/category (500 chars max, from Notion).
        story_direction: Rich text story direction from Notion (unlimited).
        status: Pipeline status (26-value enum, indexed).
        priority: Queue priority (high/normal/low, default: normal).
        error_log: Append-only error history (nullable, text field).
        youtube_url: Published YouTube URL (nullable, populated after upload).
        created_at: Task creation timestamp (UTC).
        updated_at: Last status change timestamp (UTC, auto-updated).
        channel: Relationship to Channel model.

    Indexes:
        - ix_tasks_status: Status filtering (queue queries)
        - ix_tasks_channel_id: Per-channel queries
        - ix_tasks_created_at: FIFO ordering within priority
        - ix_tasks_channel_id_status: Composite for capacity calculations
        - Partial index on status='queued' for fast worker claims

    Foreign Key:
        channel_id references channels.id with ondelete='RESTRICT' (preserve
        task history even if channel is deactivated).
    """

    __tablename__ = "tasks"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Foreign key to channels table
    # CRITICAL: References channels.id (UUID), NOT channels.channel_id (string)
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("channels.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # Notion integration (unique constraint for bidirectional sync)
    notion_page_id: Mapped[str] = mapped_column(
        String(36),  # Supports UUID with or without dashes (32-36 chars)
        unique=True,
        nullable=False,
        index=True,
    )

    # Content metadata (from Notion database)
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    topic: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    story_direction: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # Workflow state (26-status enum)
    # Uses PostgreSQL native enum type with lowercase values matching Python enum .value
    # values_callable tells SQLAlchemy to use enum.value (lowercase) not enum.name (UPPERCASE)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(
            TaskStatus,
            native_enum=True,
            name="taskstatus",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=TaskStatus.DRAFT,
        index=True,
    )

    # Priority queue management
    priority: Mapped[PriorityLevel] = mapped_column(
        Enum(
            PriorityLevel,
            native_enum=True,
            name="prioritylevel",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=PriorityLevel.NORMAL,
    )

    # Error tracking (append-only log)
    error_log: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # YouTube output
    youtube_url: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Cost tracking (Epic 8 - Story 3.3 requirement)
    # Running total of all API costs for this task (Gemini, Kling, ElevenLabs)
    # Updated incrementally as each pipeline step completes
    total_cost_usd: Mapped[float] = mapped_column(
        nullable=False,
        default=0.0,
        server_default="0.0",
    )

    # Timestamps (UTC timezone-aware)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )

    # Relationship to channel
    channel: Mapped["Channel"] = relationship("Channel", back_populates="tasks")

    # Indexes for efficient queue queries
    # Note: Migration is source of truth for indexes. Model defines indexes
    # for SQLAlchemy awareness. Additional indexes in migration:
    # - ix_tasks_status: Status filtering
    # - ix_tasks_channel_id: Per-channel queries
    # - ix_tasks_created_at: FIFO ordering
    # - Partial index WHERE status='queued' for fast worker claims
    __table_args__ = (
        # Composite index for channel + status filtering (capacity queries)
        Index("ix_tasks_channel_id_status", "channel_id", "status"),
    )

    def __repr__(self) -> str:
        """Return string representation for debugging.

        Shows task ID (truncated), title, status, and priority for quick identification.
        """
        return (
            f"<Task(id={self.id!s:.8}, title={self.title!r}, "
            f"status={self.status.value!r}, priority={self.priority.value!r})>"
        )


class NotionWebhookEvent(Base):
    """Notion webhook event tracking for idempotency.

    Notion may send duplicate webhooks for the same event (network retries, etc.).
    This table tracks processed webhook events to prevent duplicate processing.

    Each webhook event has a unique event_id that serves as the deduplication key.
    The payload is stored for debugging and audit purposes.

    Attributes:
        id: Internal UUID primary key.
        event_id: Notion webhook event ID (unique constraint for idempotency).
        event_type: Type of webhook event (page.created, page.updated, page.archived).
        page_id: Notion page UUID that the event is about (32 chars, no dashes).
        processed_at: Timestamp when event was first processed (UTC).
        payload: Full webhook payload as JSON (for debugging and audit).

    Indexes:
        - Unique constraint on event_id for idempotency checks
        - Index on page_id for looking up events by page

    Note:
        This table grows monotonically. Consider implementing cleanup for
        events older than 30 days in production.
    """

    __tablename__ = "notion_webhook_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    event_id: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )

    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    page_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )

    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )

    payload: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
    )

    def __repr__(self) -> str:
        """Return string representation for debugging."""
        return (
            f"<NotionWebhookEvent(event_id={self.event_id!r}, "
            f"event_type={self.event_type!r}, page_id={self.page_id!r})>"
        )
