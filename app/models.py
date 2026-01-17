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
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    PrimaryKeyConstraint,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, validates

from app.exceptions import InvalidStateTransitionError


def utcnow() -> datetime:
    """Get current UTC datetime (timezone-aware)."""
    return datetime.now(timezone.utc)


class TaskStatus(enum.Enum):
    """27-status workflow state machine for video generation pipeline.

    Status values follow the video generation pipeline order from draft to published.
    Each status represents a specific stage in the 8-step production pipeline.

    Pipeline Flow (Happy Path):
        draft → queued → claimed → generating_assets → assets_ready → assets_approved
        → generating_composites → composites_ready → generating_video → video_ready
        → video_approved → generating_audio → audio_ready → audio_approved
        → generating_sfx → sfx_ready → assembling → assembly_ready → final_review
        → approved → uploading → published

    Error Recovery Flow:
        asset_error/video_error/audio_error → queued (retry from beginning)
        upload_error → final_review (fix and re-upload)

    Cancellation Flow:
        queued → cancelled (user cancellation before processing starts)

    Terminal States:
        published (video live on YouTube), cancelled (user cancelled)

    See UX Design document for full state machine transitions.
    """

    # Initial states
    DRAFT = "draft"
    QUEUED = "queued"
    CLAIMED = "claimed"
    CANCELLED = "cancelled"

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
    """Video generation task with 27-status workflow state machine.

    Tasks represent video generation jobs that move through the 8-step production
    pipeline from draft to published. Each task belongs to a channel and tracks
    video metadata, Notion integration, and pipeline status.

    27-Status Workflow:
        The status field follows the TaskStatus enum (27 states) which maps to
        the 8-step pipeline: asset generation → composites → video → audio → sfx
        → assembly → review → upload. Includes CANCELLED status for user cancellation.
        See TaskStatus enum for full flow.

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
        status: Pipeline status (27-value enum, indexed).
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

    # State Machine Validation (Story 5.1 + Code Review Fixes)
    # Defines valid status transitions for the 27-status workflow
    # Only transitions listed here are allowed, enforced by @validates decorator
    VALID_TRANSITIONS = {
        # Initial states
        TaskStatus.DRAFT: [TaskStatus.QUEUED, TaskStatus.CANCELLED],
        TaskStatus.QUEUED: [TaskStatus.CLAIMED, TaskStatus.CANCELLED],
        TaskStatus.CLAIMED: [TaskStatus.GENERATING_ASSETS],
        # Asset generation phase (MANDATORY review gate)
        TaskStatus.GENERATING_ASSETS: [TaskStatus.ASSETS_READY, TaskStatus.ASSET_ERROR],
        TaskStatus.ASSETS_READY: [TaskStatus.ASSETS_APPROVED, TaskStatus.ASSET_ERROR],
        TaskStatus.ASSETS_APPROVED: [TaskStatus.QUEUED, TaskStatus.GENERATING_COMPOSITES],
        # Composite creation phase (OPTIONAL review - auto-proceeds)
        TaskStatus.GENERATING_COMPOSITES: [TaskStatus.COMPOSITES_READY],
        TaskStatus.COMPOSITES_READY: [TaskStatus.GENERATING_VIDEO],
        # Video generation phase (MANDATORY review gate - expensive step)
        TaskStatus.GENERATING_VIDEO: [TaskStatus.VIDEO_READY, TaskStatus.VIDEO_ERROR],
        TaskStatus.VIDEO_READY: [TaskStatus.VIDEO_APPROVED, TaskStatus.VIDEO_ERROR],
        TaskStatus.VIDEO_APPROVED: [TaskStatus.QUEUED, TaskStatus.GENERATING_AUDIO],
        # Audio generation phase (MANDATORY review gate)
        TaskStatus.GENERATING_AUDIO: [TaskStatus.AUDIO_READY, TaskStatus.AUDIO_ERROR],
        TaskStatus.AUDIO_READY: [TaskStatus.AUDIO_APPROVED, TaskStatus.AUDIO_ERROR],
        TaskStatus.AUDIO_APPROVED: [TaskStatus.QUEUED, TaskStatus.GENERATING_SFX],
        # Sound effects phase (OPTIONAL review - auto-proceeds)
        TaskStatus.GENERATING_SFX: [TaskStatus.SFX_READY],
        TaskStatus.SFX_READY: [TaskStatus.ASSEMBLING],
        # Assembly phase (OPTIONAL review - auto-proceeds)
        TaskStatus.ASSEMBLING: [TaskStatus.ASSEMBLY_READY],
        TaskStatus.ASSEMBLY_READY: [TaskStatus.FINAL_REVIEW],
        # Final review and upload phase (MANDATORY review gate - YouTube compliance)
        TaskStatus.FINAL_REVIEW: [TaskStatus.APPROVED, TaskStatus.CANCELLED],
        TaskStatus.APPROVED: [TaskStatus.QUEUED, TaskStatus.UPLOADING],
        TaskStatus.UPLOADING: [TaskStatus.PUBLISHED, TaskStatus.UPLOAD_ERROR],
        TaskStatus.PUBLISHED: [],  # Terminal state - no transitions allowed
        TaskStatus.CANCELLED: [],  # Terminal state - no transitions allowed
        # Error recovery paths (retry by returning to QUEUED)
        TaskStatus.ASSET_ERROR: [TaskStatus.QUEUED],
        TaskStatus.VIDEO_ERROR: [TaskStatus.QUEUED],
        TaskStatus.AUDIO_ERROR: [TaskStatus.QUEUED],
        TaskStatus.UPLOAD_ERROR: [TaskStatus.FINAL_REVIEW],  # Re-review before re-upload
    }

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

    # Narration scripts (Story 3.6)
    # List of 18 narration text strings, one per video clip
    # Stored as JSONB for structured querying in PostgreSQL
    # SQLite (for tests) will use JSON TEXT type
    narration_scripts: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    # Sound effects descriptions (Story 3.7)
    # List of 18 SFX description strings, one per video clip
    # Describes environmental ambience: forest sounds, wind, water, etc.
    # NOT narration - this is ambient environmental audio
    # Stored as JSONB for structured querying in PostgreSQL
    # SQLite (for tests) will use JSON TEXT type
    sfx_descriptions: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
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

    # Final video output (Story 3.8 - Video Assembly)
    # Path to final assembled 90-second documentary MP4 file
    # Populated after successful FFmpeg assembly step
    final_video_path: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # Final video duration in seconds (Story 3.8 - Video Assembly)
    # Measured duration of assembled final video (~90 seconds typical)
    # Populated after successful FFmpeg assembly step
    final_video_duration: Mapped[float | None] = mapped_column(
        nullable=True,
    )

    # Pipeline orchestration metadata (Story 3.9)
    # Tracks step completion for partial resume and performance monitoring
    step_completion_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    # Pipeline timing and performance tracking (Story 3.9)
    # Used for NFR-P1 compliance (≤2 hours target) and cost analysis
    pipeline_start_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    pipeline_end_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    pipeline_duration_seconds: Mapped[float | None] = mapped_column(
        nullable=True,
    )
    pipeline_cost_usd: Mapped[float | None] = mapped_column(
        nullable=True,
    )

    # Review gate timing (Story 5.2)
    # Tracks time spent waiting at mandatory review gates for quality control
    # Used for observability: "How long do tasks wait at review gates?"
    review_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    review_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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

    @validates("status")
    def validate_status_change(self, key: str, value: TaskStatus) -> TaskStatus:
        """Validate status transition before committing to database.

        This method enforces the 27-status workflow state machine defined in
        VALID_TRANSITIONS. Only valid transitions are allowed.

        Args:
            key: The attribute name being validated (always "status").
            value: The new TaskStatus value being assigned.

        Returns:
            The validated TaskStatus value if transition is valid.

        Raises:
            InvalidStateTransitionError: If the transition is not valid according
                to VALID_TRANSITIONS mapping.

        Note:
            - Validation is skipped on initial task creation (status is None)
            - Validation is enforced on all subsequent status changes
            - Terminal states (PUBLISHED) have no valid transitions

        Example:
            >>> task.status = TaskStatus.DRAFT
            >>> task.status = TaskStatus.QUEUED  # Valid - allowed
            >>> task.status = TaskStatus.PUBLISHED  # Invalid - raises exception

        Related:
            - Story 5.1: 26-Status Workflow State Machine
            - FR51: 26 workflow status progression
            - Task.VALID_TRANSITIONS: Allowed transition mapping
        """
        # Skip validation on initial task creation (status is None)
        if self.status is None:
            return value

        # Check if transition is valid
        allowed_transitions = self.VALID_TRANSITIONS.get(self.status, [])
        if value not in allowed_transitions:
            raise InvalidStateTransitionError(
                f"Invalid transition: {self.status.value} → {value.value}",
                from_status=self.status,
                to_status=value,
            )

        return value

    @property
    def review_duration_seconds(self) -> int | None:
        """Calculate time spent at review gate in seconds.

        Used for observability and SLA tracking: "How long do tasks wait for review?"

        Returns:
            Integer seconds spent at review gate, or None if review not complete.

        Example:
            >>> task.review_started_at = datetime(2024, 1, 1, 12, 0, 0)
            >>> task.review_completed_at = datetime(2024, 1, 1, 12, 5, 30)
            >>> task.review_duration_seconds
            330  # 5 minutes 30 seconds

        Related:
            - Story 5.2: Review Gate Enforcement
            - Subtask 3.3: Calculate review duration for observability
        """
        if self.review_started_at and self.review_completed_at:
            delta = self.review_completed_at - self.review_started_at
            return int(delta.total_seconds())
        return None

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


class YouTubeQuotaUsage(Base):
    """YouTube Data API v3 quota tracking per channel per day.

    Tracks YouTube API quota consumption to prevent exceeding the 10,000 units/day
    limit. Used for rate-aware task selection (Story 4.5) - workers check quota
    availability before claiming upload tasks.

    Composite Primary Key:
        (channel_id, date) - One row per channel per day for quota isolation.

    Quota Costs (YouTube Data API v3):
        - Upload video: 1,600 units
        - Update video: 50 units
        - List videos: 1 unit
        - Search: 100 units

    Quota Reset:
        YouTube quotas reset at midnight Pacific Time (PST/PDT) daily.

    Alert Thresholds:
        - 80% usage: WARNING alert to Discord webhook
        - 100% usage: CRITICAL alert to Discord webhook

    Attributes:
        channel_id: Foreign key to channels.id (part of composite PK).
        date: Date of quota tracking (part of composite PK).
        units_used: Accumulated quota units used today (default: 0).
        daily_limit: Daily quota limit in units (default: 10,000).

    Indexes:
        - Composite PK on (channel_id, date) for fast lookups
        - Index on date for cleanup queries (delete rows older than 7 days)

    Constraints:
        - units_used >= 0 (no negative usage)
        - daily_limit > 0 (positive limit required)

    Usage:
        # Check quota before upload
        quota = await db.get(YouTubeQuotaUsage, (channel_id, date.today()))
        if quota and (quota.units_used + 1600) > quota.daily_limit:
            # Quota exhausted - skip upload task
            ...

    Related:
        - Story 4.5: Rate Limit Aware Task Selection
        - FR42: Pre-claim quota verification
        - FR34: API quota monitoring
    """

    __tablename__ = "youtube_quota_usage"

    # Composite primary key: (channel_id, date)
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("channels.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )

    date: Mapped[date] = mapped_column(
        Date,
        primary_key=True,
        nullable=False,
    )

    # Quota tracking
    units_used: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    daily_limit: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=10000,
        server_default="10000",
    )

    # Relationship to channel
    channel: Mapped["Channel"] = relationship("Channel")

    __table_args__ = (
        # Composite primary key constraint (explicit name)
        PrimaryKeyConstraint("channel_id", "date", name="pk_youtube_quota"),
        # Index for cleanup queries (delete WHERE date < CURRENT_DATE - 7)
        Index("ix_youtube_quota_date", "date"),
        # Check constraints for data integrity
        CheckConstraint("units_used >= 0", name="ck_youtube_quota_non_negative"),
        CheckConstraint("daily_limit > 0", name="ck_youtube_quota_limit_positive"),
    )

    def __repr__(self) -> str:
        """Return string representation for debugging."""
        percentage = (self.units_used / self.daily_limit * 100) if self.daily_limit > 0 else 0
        return (
            f"<YouTubeQuotaUsage(channel_id={self.channel_id!s:.8}, "
            f"date={self.date!s}, usage={self.units_used}/{self.daily_limit} "
            f"({percentage:.1f}%))>"
        )
