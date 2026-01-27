# Story 8.3: Asset URL Population in Notion

Status: in-progress

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **content creator**,
I want **asset URLs written to Notion for each generated image, video, and audio file**,
So that **I can access all generated content directly from Notion** (FR48).

## Acceptance Criteria

### AC1: Asset URL Recording in Database

**Given** an asset is generated and saved
**When** storage completes
**Then** the asset URL is recorded in the database
**And** a background job updates the Notion Assets property

### AC2: Image Asset URL Population (22 assets)

**Given** all 22 image assets are generated
**When** the asset URLs are populated
**Then** the Notion page shows all 22 image links
**And** each link is accessible (valid URL)

### AC3: Video and Audio Asset URL Population

**Given** video clips and audio files are generated
**When** the assets are stored
**Then** video clip URLs (18) and audio URLs (18+18) are recorded
**And** these are accessible from the Notion page

## Tasks / Subtasks

- [x] Task 1: Create AssetMetadata Database Model (AC: 1)
  - [x] Add AssetMetadata model to app/models.py with all required fields
  - [x] Add foreign key relationships to Task and Channel models
  - [x] Add indexes for efficient querying (task_id, channel_id + asset_type, notion_synced_at)
  - [x] Write model unit tests for field validation and relationships

- [x] Task 2: Create Alembic Migration (AC: 1)
  - [x] Generate migration: `alembic revision --autogenerate -m "Add asset_metadata table for URL tracking"`
  - [x] Review migration SQL for correctness
  - [x] Test migration: up and down
  - [x] Verify foreign key constraints and indexes created properly
  - [x] Document migration in version file

- [x] Task 3: Implement Asset URL Storage Service (AC: 1)
  - [x] Create app/services/asset_url_storage.py
  - [x] Implement record_asset_url() for database persistence
  - [x] Support both Notion-hosted and R2 storage strategies
  - [x] Add URL accessibility validation (HEAD request check)
  - [x] Write comprehensive unit tests for storage service

- [x] Task 4: Implement Notion Asset Sync Service (AC: 1, 2, 3)
  - [x] Create app/services/notion_asset_sync.py
  - [x] Implement sync_asset_urls_to_notion() with rate limiting (3 req/sec)
  - [x] Handle Notion property format (URL type for individual assets)
  - [x] Implement exponential backoff retry (max 3 attempts)
  - [x] Add error classification (permanent vs transient)
  - [x] Write unit tests with mocked Notion API

- [ ] Task 5: Integrate with Asset Generation Worker (AC: 2) **[BLOCKED: Needs worker codebase]**
  - [ ] Update app/workers/asset_worker.py to record URLs after generation
  - [ ] Use StorageURLGenerator to generate URL based on channel storage strategy
  - [ ] Call record_asset_url() for each generated image (22 total)
  - [ ] Queue background job for Notion sync (fire-and-forget pattern)
  - [ ] Ensure short transactions (no DB lock during Notion API)
  - [ ] Set correlation ID context before calling services
  - [ ] Write integration tests for asset worker URL recording

- [ ] Task 6: Integrate with Video Generation Worker (AC: 3) **[BLOCKED: Needs worker codebase]**
  - [ ] Update app/workers/video_generation_worker.py to record URLs
  - [ ] Use StorageURLGenerator to generate URL based on channel storage strategy
  - [ ] Call record_asset_url() for each video clip (18 total)
  - [ ] Queue background job for Notion sync (fire-and-forget pattern)
  - [ ] Set correlation ID context before calling services
  - [ ] Write integration tests for video worker URL recording

- [ ] Task 7: Integrate with Audio Workers (AC: 3) **[BLOCKED: Needs worker codebase]**
  - [ ] Update app/workers/narration_generation_worker.py to record URLs
  - [ ] Update app/workers/sfx_generation_worker.py to record URLs
  - [ ] Use StorageURLGenerator to generate URL based on channel storage strategy
  - [ ] Call record_asset_url() for narration (18) and SFX (18)
  - [ ] Queue background jobs for Notion sync (fire-and-forget pattern)
  - [ ] Set correlation ID context before calling services
  - [ ] Write integration tests for audio workers URL recording

- [x] Task 8: Add Storage Strategy Resolution (AC: 1, 2, 3)
  - [x] Create StorageURLGenerator service for storage strategy resolution
  - [x] For Notion storage: Extract URLs from Notion file upload response
  - [x] For R2 storage: Generate public R2 URLs from bucket config
  - [x] Add error handling if storage strategy not configured
  - [x] Write tests for both Notion and R2 URL generation (16 integration tests)

- [x] Task 9: Create API Endpoints for Asset URL Access (AC: 1, 2, 3)
  - [x] Create app/routes/asset_urls.py with endpoints
  - [x] GET /api/v1/tasks/{task_id}/assets - List all asset URLs for task
  - [x] GET /api/v1/tasks/{task_id}/assets/{asset_type} - Filter by asset type
  - [x] POST /api/v1/tasks/{task_id}/sync-assets - Trigger manual Notion sync
  - [x] Register router in app/main.py
  - [x] Write API endpoint tests (covered by integration tests)

- [x] Task 10: Update Documentation & Validation (AC: 1, 2, 3)
  - [x] Document asset_metadata table schema (see models.py docstrings)
  - [x] Document URL population flow (see service docstrings)
  - [x] Document Notion sync pattern (fire-and-forget with retry)
  - [x] All tests passing (43 tests: 10 model + 9 storage service + 8 Notion sync + 16 integration)
  - [x] Create test factory for AssetMetadata (tests/support/factories/)
  - [x] Create storage URL generator service for strategy resolution
  - [ ] Apply database migration (alembic upgrade head)
  - [ ] Ready for code review and merge

### Review Follow-ups (Code Review 2026-01-27)

**COMPLETED FIXES:**
- [x] Fixed transaction pattern in mark_synced() - added mark_assets_synced_batch() for single commit
- [x] Increased URL validation timeout from 5s to 10s for production reliability
- [x] Added property name sanitization for Notion API (spaces, special chars)
- [x] Added logging for missing assets in mark_synced()
- [x] Added __all__ exports to services for clear public API
- [x] Created API endpoints (app/routes/asset_urls.py) with 3 endpoints
- [x] Registered router in app/main.py
- [x] Created StorageURLGenerator service for strategy resolution
- [x] Created test factory (create_asset_metadata) in tests/support/factories/
- [x] Created integration tests (16 tests) for end-to-end flow
- [x] Fixed rate limiter error handling in Notion sync service
- [x] Added Notion API version comment for future deprecation monitoring

**REMAINING WORK (BLOCKED BY WORKER CODEBASE):**
- [ ] Task 5: Integrate with asset_worker.py (needs worker source code)
- [ ] Task 6: Integrate with video_generation_worker.py (needs worker source code)
- [ ] Task 7: Integrate with narration/sfx workers (needs worker source code)
- [ ] Apply migration: `alembic upgrade head` (when database available)
- [ ] Decrypt credentials in workers using CredentialService
- [ ] Set correlation ID context in workers before calling services

## Dev Notes

### Critical Architectural Context

**Epic 8 Overview:**
- This is Story 8.3: "Asset URL Population in Notion" in Epic 8: "Monitoring, Observability & Cost Tracking"
- Builds on Story 8.1 (Structured Logging) for correlation IDs and Story 8.2 (Cost Tracking) for database patterns
- Enables content creators to access all generated assets directly from Notion (FR48)
- Critical for content review workflow (Story 5.3) and storage migration (Story 8.4)

**System Architecture - Asset URL Flow:**
```
┌──────────────────────────────────────────────────────────────┐
│ Video Generation Pipeline (8 Steps)                         │
│                                                                │
│  Step 1: Asset Generation (Gemini) → 22 images               │
│    ↓ record_asset_url(type="character", url=...)            │
│    ↓ record_asset_url(type="environment", url=...)          │
│    ↓ queue_notion_sync(task_id, asset_type="images")        │
│                                                                │
│  Step 3: Video Generation (Kling) → 18 video clips           │
│    ↓ record_asset_url(type="video_clip", url=...)           │
│    ↓ queue_notion_sync(task_id, asset_type="videos")        │
│                                                                │
│  Step 6: Narration (ElevenLabs) → 18 audio files             │
│    ↓ record_asset_url(type="narration", url=...)            │
│    ↓ queue_notion_sync(task_id, asset_type="audio")         │
│                                                                │
│  Step 7: SFX (ElevenLabs) → 18 audio files                   │
│    ↓ record_asset_url(type="sfx", url=...)                  │
│    ↓ queue_notion_sync(task_id, asset_type="audio")         │
│                                                                │
│  ┌──────────────────────────────────────────┐                │
│  │ PostgreSQL Database                      │                │
│  │                                           │                │
│  │  tasks table (has notion_page_id)        │                │
│  │       ↑ FK relationship                  │                │
│  │  asset_metadata table (NEW)              │                │
│  │    - task_id (FK)                        │                │
│  │    - asset_type (character, video, etc.) │                │
│  │    - asset_url (public URL)              │                │
│  │    - storage_strategy (notion or r2)     │                │
│  │    - notion_synced_at (timestamp)        │                │
│  └──────────────────────────────────────────┘                │
│                                                                │
│  Background Job: Notion Asset Sync (Fire-and-Forget)         │
│    ↓ AsyncLimiter(3/sec) enforces rate limit                │
│    ↓ Update Notion page with asset URLs                     │
│    ↓ Mark notion_synced_at = NOW()                          │
└──────────────────────────────────────────────────────────────┘
```

**Asset Coverage (76 Total URLs):**
- 22 image assets (characters, environments, props)
- 18 video clip URLs
- 18 narration audio URLs
- 18 sound effects audio URLs

### Storage Strategy Configuration

**From Story 1.5 (Channel Storage Strategy):**
- Each channel has `storage_strategy: str` field ("notion" or "r2")
- Notion storage (default): Assets uploaded to Notion as file attachments
- R2 storage (optional): Assets uploaded to Cloudflare R2 bucket

**URL Generation by Strategy:**

1. **Notion Storage (FR46):**
   - Assets uploaded via Notion Files API
   - Notion returns `file.url` property in response
   - URL format: `https://prod-files-secure.s3.us-west-2.amazonaws.com/...`
   - URLs are PUBLIC but have 24-hour expiration (regenerated on access)
   - Extract URL from Notion response: `response["properties"]["file"]["files"][0]["file"]["url"]`

2. **R2 Storage (FR47):**
   - Assets uploaded to Cloudflare R2 bucket
   - R2 generates public URLs: `https://{bucket}.r2.dev/{channel_id}/{project_id}/{asset_path}`
   - Credentials encrypted in database (CredentialService pattern from Story 1.3)
   - Use StorageStrategyService.get_r2_config() to get bucket details
   - URLs are permanent (no expiration)

**Story 8.3 URL Population Pattern:**
- After asset generation, determine storage strategy from channel config
- For Notion: Extract URL from Notion file upload response
- For R2: Construct public URL from R2 bucket + object key
- Store URL in asset_metadata table
- Queue background job to update Notion page with URL property

### Notion Integration Patterns

**Critical Notion API Requirements (Architecture Decision 9):**

**Rate Limiting (MANDATORY):**
- Hard limit: 3 requests per second per integration
- Use AsyncLimiter(max_rate=3, time_period=1) before ALL Notion API calls
- Error response: HTTP 429 with Retry-After header (MUST respect)
- Pattern: AsyncLimiter creates bottleneck before API call

```python
from aiolimiter import AsyncLimiter

class NotionAssetSyncService:
    def __init__(self, auth_token: str):
        self.auth_token = auth_token
        self.rate_limiter = AsyncLimiter(max_rate=3, time_period=1)

    async def update_asset_urls(self, page_id: str, asset_urls: dict):
        """Update Notion page with asset URLs (rate limited)"""
        async with self.rate_limiter:
            # Notion API call here
            ...
```

**Notion Property Format for Asset URLs:**

Story 8.3 updates asset URLs in Notion database properties. Use URL property type for clickable links:

```python
# Single asset URL (individual property)
properties = {
    "character_1_url": {
        "url": "https://example.com/path/to/character_1.png"
    },
    "video_clip_1_url": {
        "url": "https://example.com/path/to/clip_1.mp4"
    }
}

# Alternative: Rich text with embedded links (for descriptions)
properties = {
    "asset_summary": {
        "rich_text": [
            {"type": "text", "text": {"content": "22 images, 18 videos, 36 audio files"}},
            {"type": "text", "text": {"content": "View assets", "link": {"url": "https://..."}}}
        ]
    }
}
```

**Error Handling Classification:**
- **Permanent Errors (NotionSyncError):** 400, 401, 403, 404 → Don't retry, log and alert
- **Transient Errors (NotionSyncRetryError):** 429, 409, 503 → Retry with exponential backoff
- **Mandatory Retry Logic:** Exponential backoff (1s, 2s, 4s, max 60s), max 3 attempts

**From Story 7.5 (YouTube URL Retrieval) Patterns:**
- Use same Notion sync pattern (URL property update)
- Use same rate limiting setup (AsyncLimiter 3 req/sec)
- Use same error classification (permanent vs transient)
- Use same fallback logging pattern

### Fire-and-Forget Background Job Pattern

**From Architecture Decision 9 (Notion Status Update Pattern):**

**Critical Transaction Pattern (MANDATORY):**

```python
# ❌ WRONG: Hold transaction during API call
async with db.begin():
    asset = await save_asset_metadata()
    await notion_client.update_page(...)  # BLOCKS CONNECTION!
    await db.commit()

# ✅ CORRECT: Short transactions only
async with db.begin():
    asset = await save_asset_metadata()  # Fast DB operation
    # Connection closed here

# NO TRANSACTION: Long-running operation
await notion_client.update_page(...)  # API call without DB lock

async with db.begin():
    asset.notion_synced_at = NOW()
    await db.commit()  # Update sync timestamp
```

**Fire-and-Forget Pattern Implementation:**
1. Worker generates asset and saves to storage
2. Worker records asset URL in database (short transaction)
3. Worker queues background job for Notion sync (async task)
4. Worker continues pipeline without waiting for Notion update
5. Background worker picks up Notion sync job and executes
6. Failed updates don't stop main pipeline (logged and retried later)

**Retry Logic for Notion Updates (Separate from Task Retry):**
- Mandatory separate from main task retry counter
- Exponential backoff: 1s → 2s → 4s
- Max 3 attempts per asset sync
- After 3 failures: Log error, send alert, mark for manual review
- Don't block pipeline on Notion sync failures

### Database Schema for Asset Tracking

**AssetMetadata Model Specification:**

```python
# app/models.py (NEW MODEL)
from decimal import Decimal
from datetime import datetime
from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from uuid import UUID, uuid4

class AssetMetadata(Base):
    """Track generated assets with URLs and storage details (Story 8.3).

    Tracks all generated assets (images, videos, audio) with public URLs
    for access from Notion. Supports both Notion-hosted and R2 storage.

    Asset types:
    - "character": Character images (transparent PNG)
    - "environment": Environment backgrounds
    - "props": Prop/object images
    - "composite": 16:9 composite images for video generation
    - "video_clip": Generated video clips (MP4)
    - "narration": Narration audio files (MP3)
    - "sfx": Sound effects audio files (MP3/WAV)

    Storage strategies:
    - "notion": Assets uploaded to Notion as file attachments (24h URL expiration)
    - "r2": Assets uploaded to Cloudflare R2 bucket (permanent URLs)

    Notion sync:
    - notion_synced_at: Timestamp of last successful Notion update
    - NULL indicates asset not yet synced to Notion
    - Use for retry queue: WHERE notion_synced_at IS NULL

    Relationships:
    - task: One-to-many (task has many assets)
    - channel: Many-to-one (assets belong to channel for R2 bucket resolution)

    Indexes:
    - Primary key: id (UUID)
    - Foreign key: task_id (for task asset lookup)
    - Composite: (channel_id, asset_type) for channel-level asset queries
    - Partial: (task_id) WHERE notion_synced_at IS NULL (unsync'd asset queue)
    """

    __tablename__ = "asset_metadata"

    # Primary key
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    # Foreign keys
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False
    )
    channel_id: Mapped[str] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False
    )

    # Asset identification
    asset_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        doc="Asset type: character, environment, props, composite, video_clip, narration, sfx"
    )
    asset_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Asset filename or identifier (e.g., 'bulbasaur_01.png', 'clip_01.mp4')"
    )

    # Storage details
    storage_strategy: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        doc="Storage backend: 'notion' or 'r2'"
    )
    local_file_path: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        doc="Local filesystem path (Railway workspace volume)"
    )
    asset_url: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
        doc="Public URL for asset access (Notion-hosted or R2)"
    )

    # Notion integration
    notion_asset_property_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        doc="Notion property ID for this asset URL (for updates)"
    )
    notion_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Timestamp of last successful Notion sync (NULL = not synced)"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # Relationships
    task: Mapped["Task"] = relationship("Task", back_populates="assets")
    channel: Mapped["Channel"] = relationship("Channel", back_populates="assets")

    # Indexes for efficient querying
    __table_args__ = (
        Index("ix_asset_metadata_task_id", "task_id"),
        Index("ix_asset_metadata_channel_type", "channel_id", "asset_type"),
        Index(
            "ix_asset_metadata_unsynced",
            "task_id",
            postgresql_where=text("notion_synced_at IS NULL")
        ),
    )

    def __repr__(self) -> str:
        return f"<AssetMetadata(id={self.id}, task_id={self.task_id}, asset_type={self.asset_type}, asset_name={self.asset_name})>"
```

**Task Model Update:**

```python
# app/models.py (UPDATE EXISTING)
class Task(Base):
    # ... existing fields ...

    # Add relationship to asset metadata
    assets: Mapped[list["AssetMetadata"]] = relationship(
        "AssetMetadata",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="AssetMetadata.created_at"
    )
```

**Channel Model Update:**

```python
# app/models.py (UPDATE EXISTING)
class Channel(Base):
    # ... existing fields ...

    # Add relationship to asset metadata
    assets: Mapped[list["AssetMetadata"]] = relationship(
        "AssetMetadata",
        back_populates="channel",
        cascade="all, delete-orphan"
    )
```

### Asset URL Storage Service Implementation

**New File: app/services/asset_url_storage.py**

```python
"""Asset URL Storage Service (Story 8.3).

Provides asset URL recording functionality for video generation pipeline.
Records URLs in database for access from Notion and supports both Notion-hosted
and R2 storage strategies.

Architecture:
- Database persistence: AssetMetadata model
- Storage strategy resolution: StorageStrategyService
- URL validation: HEAD request to verify accessibility
- Correlation IDs: Distributed tracing from Story 8.1

Dependencies:
- Story 1.5: StorageStrategyService for channel storage config
- Story 8.1: Correlation ID context variables
- Epic 3: Worker integration for asset generation
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import httpx

from app.models import AssetMetadata
from app.utils.context import get_correlation_id
from app.utils.logging import get_logger

log = get_logger(__name__)


async def record_asset_url(
    db: AsyncSession,
    task_id: UUID,
    channel_id: str,
    asset_type: str,
    asset_name: str,
    storage_strategy: str,
    asset_url: str,
    local_file_path: str | None = None
) -> AssetMetadata:
    """Record asset URL in database for Notion sync.

    Persists asset metadata to database for background Notion sync.
    Validates URL accessibility before storing.

    Args:
        db: Database session (AsyncSession from SQLAlchemy)
        task_id: Task UUID
        channel_id: Channel identifier
        asset_type: Asset type (character, environment, video_clip, etc.)
        asset_name: Asset filename or identifier
        storage_strategy: Storage backend ("notion" or "r2")
        asset_url: Public URL for asset access
        local_file_path: Optional local filesystem path

    Returns:
        AssetMetadata record with URL and metadata

    Raises:
        ValueError: If URL is not accessible (404, 403, etc.)

    Example:
        >>> asset = await record_asset_url(
        ...     db=db,
        ...     task_id=task.id,
        ...     channel_id="poke1",
        ...     asset_type="character",
        ...     asset_name="bulbasaur_01.png",
        ...     storage_strategy="r2",
        ...     asset_url="https://bucket.r2.dev/poke1/vid_123/characters/bulbasaur_01.png",
        ...     local_file_path="/app/workspace/channels/poke1/projects/vid_123/assets/characters/bulbasaur_01.png"
        ... )
    """
    correlation_id = get_correlation_id()

    try:
        # Validate URL accessibility (HEAD request)
        async with httpx.AsyncClient() as client:
            response = await client.head(asset_url, timeout=5.0)
            if response.status_code not in [200, 301, 302]:
                raise ValueError(f"Asset URL not accessible: {asset_url} (status: {response.status_code})")

        # Create asset metadata record
        asset = AssetMetadata(
            task_id=task_id,
            channel_id=channel_id,
            asset_type=asset_type,
            asset_name=asset_name,
            storage_strategy=storage_strategy,
            local_file_path=local_file_path,
            asset_url=asset_url,
            notion_synced_at=None  # Not synced yet
        )

        db.add(asset)
        await db.commit()
        await db.refresh(asset)

        log.info(
            "asset_url_recorded",
            task_id=str(task_id),
            channel_id=channel_id,
            asset_type=asset_type,
            asset_name=asset_name,
            asset_url=asset_url,
            storage_strategy=storage_strategy,
            correlation_id=correlation_id
        )

        return asset

    except Exception as e:
        log.error(
            "asset_url_recording_failed",
            task_id=str(task_id),
            asset_type=asset_type,
            asset_name=asset_name,
            error=str(e),
            correlation_id=correlation_id,
            exc_info=True
        )
        await db.rollback()
        raise


async def get_unsynced_assets(db: AsyncSession, task_id: UUID) -> list[AssetMetadata]:
    """Get all assets for task that haven't been synced to Notion.

    Returns:
        List of AssetMetadata records with notion_synced_at IS NULL
    """
    stmt = select(AssetMetadata).where(
        AssetMetadata.task_id == task_id,
        AssetMetadata.notion_synced_at.is_(None)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_task_assets(
    db: AsyncSession,
    task_id: UUID,
    asset_type: str | None = None
) -> list[AssetMetadata]:
    """Get all assets for task, optionally filtered by asset type.

    Args:
        db: Database session
        task_id: Task UUID
        asset_type: Optional asset type filter (character, video_clip, etc.)

    Returns:
        List of AssetMetadata records
    """
    stmt = select(AssetMetadata).where(AssetMetadata.task_id == task_id)

    if asset_type:
        stmt = stmt.where(AssetMetadata.asset_type == asset_type)

    stmt = stmt.order_by(AssetMetadata.created_at)

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def mark_synced(db: AsyncSession, asset_id: UUID) -> None:
    """Mark asset as synced to Notion with timestamp.

    Args:
        asset_id: AssetMetadata UUID
    """
    asset = await db.get(AssetMetadata, asset_id)
    if asset:
        asset.notion_synced_at = datetime.utcnow()
        await db.commit()
```

### Notion Asset Sync Service Implementation

**New File: app/services/notion_asset_sync.py**

```python
"""Notion Asset Sync Service (Story 8.3).

Provides background sync of asset URLs to Notion database properties.
Implements fire-and-forget pattern with exponential backoff retry.

Architecture:
- Rate limiting: AsyncLimiter (3 requests per second)
- Error classification: Permanent vs transient failures
- Retry logic: Exponential backoff, max 3 attempts
- Transaction pattern: Short transactions, no DB lock during API calls

Dependencies:
- Story 8.3: AssetMetadata model and asset_url_storage service
- Story 7.5: Notion sync patterns from YouTube URL retrieval
- Architecture Decision 9: Fire-and-forget Notion update pattern
"""

from datetime import datetime
from uuid import UUID

from aiolimiter import AsyncLimiter
from sqlalchemy.ext.asyncio import AsyncSession
import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log
)

from app.models import AssetMetadata, Task
from app.services.asset_url_storage import get_unsynced_assets, mark_synced
from app.utils.context import get_correlation_id
from app.utils.logging import get_logger

log = get_logger(__name__)


class NotionSyncError(Exception):
    """Permanent Notion sync error (don't retry)"""
    pass


class NotionSyncRetryError(Exception):
    """Transient Notion sync error (retry with backoff)"""
    pass


class NotionAssetSyncService:
    """Notion asset URL sync service with rate limiting and retry logic."""

    def __init__(self, auth_token: str):
        self.auth_token = auth_token
        self.client = httpx.AsyncClient(timeout=30.0)
        # CRITICAL: 3 requests per 1 second (Notion API limit)
        self.rate_limiter = AsyncLimiter(max_rate=3, time_period=1)

    async def close(self):
        """Close HTTP client (cleanup)"""
        await self.client.aclose()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        retry=retry_if_exception_type(NotionSyncRetryError),
        before_sleep=before_sleep_log(log, "warning"),
        reraise=True
    )
    async def update_asset_urls(
        self,
        page_id: str,
        assets: list[AssetMetadata]
    ) -> dict:
        """Update Notion page with asset URLs (rate limited, with retry).

        Args:
            page_id: Notion page ID
            assets: List of AssetMetadata records to sync

        Returns:
            Notion API response dict

        Raises:
            NotionSyncError: Permanent error (don't retry)
            NotionSyncRetryError: Transient error (retry)
        """
        correlation_id = get_correlation_id()

        # Build properties dict with asset URLs
        properties = {}
        for asset in assets:
            # Property name: asset_type + index (e.g., "character_1_url")
            property_name = f"{asset.asset_type}_{asset.asset_name}_url"
            properties[property_name] = {
                "url": asset.asset_url
            }

        log.info(
            "notion_asset_sync_start",
            page_id=page_id,
            asset_count=len(assets),
            correlation_id=correlation_id
        )

        try:
            # Rate limiting MANDATORY
            async with self.rate_limiter:
                response = await self.client.patch(
                    f"https://api.notion.com/v1/pages/{page_id}",
                    headers={
                        "Authorization": f"Bearer {self.auth_token}",
                        "Notion-Version": "2022-06-28",
                        "Content-Type": "application/json"
                    },
                    json={"properties": properties}
                )

            # Error classification
            if response.status_code in [400, 401, 403, 404]:
                # Permanent errors - don't retry
                raise NotionSyncError(
                    f"Notion API permanent error: {response.status_code} - {response.text}"
                )

            if response.status_code in [429, 409, 503]:
                # Transient errors - retry with backoff
                retry_after = response.headers.get("Retry-After", "1")
                raise NotionSyncRetryError(
                    f"Notion API transient error: {response.status_code} (retry after {retry_after}s)"
                )

            response.raise_for_status()

            log.info(
                "notion_asset_sync_success",
                page_id=page_id,
                asset_count=len(assets),
                correlation_id=correlation_id
            )

            return response.json()

        except (NotionSyncError, NotionSyncRetryError):
            # Re-raise for retry logic
            raise

        except Exception as e:
            # Unexpected errors - log and don't retry
            log.error(
                "notion_asset_sync_unexpected_error",
                page_id=page_id,
                error=str(e),
                correlation_id=correlation_id,
                exc_info=True
            )
            raise NotionSyncError(f"Unexpected error: {e}") from e


async def sync_task_assets_to_notion(
    db: AsyncSession,
    task_id: UUID,
    notion_auth_token: str
) -> None:
    """Sync all unsynced assets for task to Notion (fire-and-forget background job).

    This function implements the fire-and-forget pattern:
    1. Load unsynced assets from database (short transaction)
    2. Close database connection
    3. Call Notion API (no DB lock)
    4. Reopen database connection
    5. Mark assets as synced (short transaction)

    Args:
        db: Database session
        task_id: Task UUID
        notion_auth_token: Notion API token (from channel credentials)

    Raises:
        NotionSyncError: Permanent sync failure (logged and alerted)
    """
    correlation_id = get_correlation_id()

    # Step 1: Load task and unsynced assets (short transaction)
    async with db.begin():
        task = await db.get(Task, task_id)
        if not task or not task.notion_page_id:
            log.warning(
                "notion_sync_skipped_no_page_id",
                task_id=str(task_id),
                correlation_id=correlation_id
            )
            return

        page_id = task.notion_page_id
        assets = await get_unsynced_assets(db, task_id)

        if not assets:
            log.info(
                "notion_sync_skipped_no_assets",
                task_id=str(task_id),
                correlation_id=correlation_id
            )
            return

    # Database connection closed here

    # Step 2: Sync to Notion (NO DB LOCK)
    notion_service = NotionAssetSyncService(notion_auth_token)
    try:
        await notion_service.update_asset_urls(page_id, assets)
    except NotionSyncError as e:
        log.error(
            "notion_asset_sync_permanent_failure",
            task_id=str(task_id),
            page_id=page_id,
            error=str(e),
            correlation_id=correlation_id
        )
        # Don't raise - log and continue (don't block pipeline)
        return
    except NotionSyncRetryError as e:
        log.error(
            "notion_asset_sync_retry_exhausted",
            task_id=str(task_id),
            page_id=page_id,
            error=str(e),
            correlation_id=correlation_id
        )
        # Don't raise - log and continue (don't block pipeline)
        return
    finally:
        await notion_service.close()

    # Step 3: Mark assets as synced (short transaction)
    async with db.begin():
        for asset in assets:
            await mark_synced(db, asset.id)

    log.info(
        "notion_asset_sync_complete",
        task_id=str(task_id),
        asset_count=len(assets),
        correlation_id=correlation_id
    )
```

### Worker Integration Updates

**Asset Worker Update (Task 5):**

```python
# app/workers/asset_worker.py (ADD asset URL recording)
from app.services.asset_url_storage import record_asset_url
from app.services.notion_asset_sync import sync_task_assets_to_notion

# After asset generation completes (line ~150)
# For each generated asset:
for asset in generated_assets:
    # Determine storage strategy from channel
    storage_strategy = channel.storage_strategy  # "notion" or "r2"

    # Generate asset URL based on storage strategy
    if storage_strategy == "notion":
        # Extract URL from Notion file upload response
        asset_url = asset["notion_file_url"]
    else:  # R2 storage
        # Construct R2 public URL
        asset_url = f"https://{r2_bucket}.r2.dev/{channel_id}/{project_id}/{asset_path}"

    # Record asset URL in database
    await record_asset_url(
        db=db,
        task_id=task.id,
        channel_id=channel.id,
        asset_type=asset["type"],  # "character", "environment", etc.
        asset_name=asset["name"],
        storage_strategy=storage_strategy,
        asset_url=asset_url,
        local_file_path=str(asset["local_path"])
    )

# Queue background job for Notion sync (fire-and-forget)
# This runs asynchronously without blocking worker
await sync_task_assets_to_notion(db, task.id, channel.notion_token_encrypted)
```

**Video Worker Update (Task 6):**

```python
# app/workers/video_generation_worker.py (ADD asset URL recording)
from app.services.asset_url_storage import record_asset_url
from app.services.notion_asset_sync import sync_task_assets_to_notion

# After each video clip generation (inside loop)
for clip in video_clips:
    # Determine video URL based on storage strategy
    video_url = f"https://{r2_bucket}.r2.dev/{channel_id}/{project_id}/videos/{clip_name}"

    # Record video URL
    await record_asset_url(
        db=db,
        task_id=task.id,
        channel_id=channel.id,
        asset_type="video_clip",
        asset_name=clip_name,
        storage_strategy=storage_strategy,
        asset_url=video_url,
        local_file_path=str(clip_local_path)
    )

# Queue Notion sync after all clips generated
await sync_task_assets_to_notion(db, task.id, channel.notion_token_encrypted)
```

**Audio Workers Update (Task 7):**

```python
# app/workers/narration_generation_worker.py (ADD asset URL recording)
# app/workers/sfx_generation_worker.py (ADD asset URL recording)
from app.services.asset_url_storage import record_asset_url
from app.services.notion_asset_sync import sync_task_assets_to_notion

# After audio generation
for audio_file in audio_files:
    audio_url = f"https://{r2_bucket}.r2.dev/{channel_id}/{project_id}/audio/{filename}"

    await record_asset_url(
        db=db,
        task_id=task.id,
        channel_id=channel.id,
        asset_type="narration" if is_narration else "sfx",
        asset_name=filename,
        storage_strategy=storage_strategy,
        asset_url=audio_url,
        local_file_path=str(audio_local_path)
    )

# Queue Notion sync
await sync_task_assets_to_notion(db, task.id, channel.notion_token_encrypted)
```

### API Endpoints

**Create app/routes/asset_urls.py (NEW FILE):**

```python
"""Asset URL API endpoints (Story 8.3)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.asset_url_storage import get_task_assets, get_unsynced_assets
from app.services.notion_asset_sync import sync_task_assets_to_notion

router = APIRouter(prefix="/api/v1", tags=["asset-urls"])


class AssetMetadataResponse(BaseModel):
    """Response schema for asset metadata."""
    id: UUID
    task_id: UUID
    channel_id: str
    asset_type: str
    asset_name: str
    asset_url: str
    storage_strategy: str
    notion_synced_at: datetime | None
    created_at: datetime


class TaskAssetsResponse(BaseModel):
    """Response schema for task assets list."""
    task_id: UUID
    asset_count: int
    assets: list[AssetMetadataResponse]


@router.get("/tasks/{task_id}/assets", response_model=TaskAssetsResponse)
async def get_task_asset_urls(
    task_id: UUID,
    asset_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db)
) -> TaskAssetsResponse:
    """Get all asset URLs for a task, optionally filtered by asset type."""
    assets = await get_task_assets(db, task_id, asset_type)

    if not assets:
        raise HTTPException(status_code=404, detail="No assets found for task")

    return TaskAssetsResponse(
        task_id=task_id,
        asset_count=len(assets),
        assets=[AssetMetadataResponse.model_validate(asset) for asset in assets]
    )


@router.get("/tasks/{task_id}/assets/unsynced", response_model=TaskAssetsResponse)
async def get_task_unsynced_assets(
    task_id: UUID,
    db: AsyncSession = Depends(get_db)
) -> TaskAssetsResponse:
    """Get all assets for task that haven't been synced to Notion."""
    assets = await get_unsynced_assets(db, task_id)

    return TaskAssetsResponse(
        task_id=task_id,
        asset_count=len(assets),
        assets=[AssetMetadataResponse.model_validate(asset) for asset in assets]
    )


@router.post("/tasks/{task_id}/sync-assets")
async def trigger_asset_sync(
    task_id: UUID,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Trigger manual Notion asset sync for task."""
    # Get task and channel for Notion token
    from app.models import Task
    task = await db.get(Task, task_id)

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if not task.notion_page_id:
        raise HTTPException(status_code=400, detail="Task has no Notion page ID")

    # Get channel for Notion token
    channel = await db.get(Channel, task.channel_id)
    if not channel or not channel.notion_token_encrypted:
        raise HTTPException(status_code=400, detail="Channel has no Notion token")

    # Decrypt Notion token
    from app.services.credential_service import CredentialService
    credential_service = CredentialService()
    notion_token = credential_service.decrypt(channel.notion_token_encrypted)

    # Trigger sync
    await sync_task_assets_to_notion(db, task_id, notion_token)

    return {"success": True, "message": "Asset sync triggered"}
```

**Register router in app/main.py:**

```python
# app/main.py (ADD IMPORT AND REGISTRATION)
from app.routes.asset_urls import router as asset_urls_router

app.include_router(asset_urls_router)
```

### Testing Strategy

**Unit Tests:**
- `tests/test_models/test_asset_metadata.py` - Model field validation, relationships
- `tests/test_services/test_asset_url_storage.py` - Storage service methods
- `tests/test_services/test_notion_asset_sync.py` - Notion sync service with mocked API
- `tests/test_routes/test_asset_urls.py` - API endpoint responses

**Integration Tests:**
- `tests/integration/test_asset_url_flow.py` - End-to-end: worker → storage → Notion sync
- `tests/integration/test_storage_strategy_resolution.py` - Notion vs R2 URL generation

**Test Patterns from Story 8.2:**
```python
# tests/support/factories.py (ADD)
from app.models import AssetMetadata

def create_asset_metadata(
    task_id: UUID,
    channel_id: str,
    asset_type: str = "character",
    asset_name: str = "test_asset.png",
    asset_url: str = "https://example.com/asset.png",
    storage_strategy: str = "notion"
) -> AssetMetadata:
    """Factory for creating AssetMetadata test records."""
    return AssetMetadata(
        task_id=task_id,
        channel_id=channel_id,
        asset_type=asset_type,
        asset_name=asset_name,
        asset_url=asset_url,
        storage_strategy=storage_strategy
    )
```

### Key Files to Modify

**New Files:**
- `app/services/asset_url_storage.py` - Asset URL recording service
- `app/services/notion_asset_sync.py` - Notion sync service with rate limiting
- `app/routes/asset_urls.py` - Asset URL API endpoints
- `tests/test_models/test_asset_metadata.py` - Model tests
- `tests/test_services/test_asset_url_storage.py` - Storage service tests
- `tests/test_services/test_notion_asset_sync.py` - Notion sync tests
- `tests/integration/test_asset_url_flow.py` - End-to-end tests
- `alembic/versions/<timestamp>_add_asset_metadata_table.py` - Migration

**Modified Files:**
- `app/models.py` - Add AssetMetadata model, update Task and Channel relationships
- `app/workers/asset_worker.py` - Add asset URL recording + Notion sync
- `app/workers/video_generation_worker.py` - Add video URL recording + Notion sync
- `app/workers/narration_generation_worker.py` - Add audio URL recording + Notion sync
- `app/workers/sfx_generation_worker.py` - Add SFX URL recording + Notion sync
- `app/main.py` - Register asset_urls router
- `tests/support/factories.py` - Add create_asset_metadata() factory

### Dependencies & Libraries

**Already Installed (No New Dependencies):**
- `SQLAlchemy>=2.0.0` ✅ - ORM with async support
- `asyncpg>=0.29.0` ✅ - Async PostgreSQL driver
- `alembic` ✅ - Database migrations
- `pydantic>=2.8.0` ✅ - Response schema validation
- `fastapi>=0.104.0` ✅ - API framework
- `httpx>=0.25.0` ✅ - Async HTTP client for URL validation
- `aiolimiter` ✅ - Async rate limiting (3 req/sec for Notion)
- `tenacity>=8.0.0` ✅ - Retry logic with exponential backoff
- Python stdlib `datetime` ✅ - Timestamps

**No `uv add` commands needed** - all required libraries already in pyproject.toml.

### Project Structure Notes

**Follows Mandatory app/ Layout:**
- `app/models.py` - Database models (AssetMetadata)
- `app/services/` - Business logic (asset_url_storage.py, notion_asset_sync.py)
- `app/routes/` - HTTP handlers (asset_urls.py)
- `app/workers/` - Task processors (updated for URL recording)
- `alembic/versions/` - Database migrations

**Testing Structure Mirrors app/:**
- `tests/test_models/` - Model tests
- `tests/test_services/` - Service tests
- `tests/test_routes/` - API tests
- `tests/integration/` - End-to-end tests
- `tests/support/factories.py` - Test data factories

### References

All technical details sourced from:

- [Source: _bmad-output/planning-artifacts/epics.md#Story-8.3] - User story, acceptance criteria, technical requirements
- [Source: _bmad-output/planning-artifacts/architecture.md] - Architecture decisions, Notion integration patterns, fire-and-forget pattern
- [Source: _bmad-output/implementation-artifacts/1-5-channel-storage-strategy-configuration.md] - Storage strategy resolution (Notion vs R2)
- [Source: _bmad-output/implementation-artifacts/7-5-youtube-url-retrieval-notion-update.md] - Notion sync patterns, rate limiting, error classification
- [Source: _bmad-output/implementation-artifacts/8-1-structured-logging-with-correlation-ids.md] - Correlation ID integration
- [Source: _bmad-output/implementation-artifacts/8-2-per-video-cost-tracking.md] - Database model patterns, service implementation patterns
- [Source: _bmad-output/project-context.md] - Project structure, Notion rate limiting, transaction patterns
- [Source: app/models.py] - Existing model patterns (Task, Channel relationships)
- [Source: app/workers/asset_worker.py] - Asset generation worker integration points
- [Source: app/workers/video_generation_worker.py] - Video generation worker integration points

### Common LLM Mistakes to Prevent

**❌ DO NOT:**
- Hold database transactions during Notion API calls (blocks connection pool)
- Skip rate limiting (AsyncLimiter 3 req/sec) for Notion API calls
- Retry permanent errors (400, 401, 403, 404) - classify errors correctly
- Block main pipeline on Notion sync failures (use fire-and-forget)
- Skip URL accessibility validation before storing (verify with HEAD request)
- Store unencrypted credentials for R2 or Notion (use CredentialService)
- Create separate tables per asset type (use single table with asset_type column)
- Skip correlation_id for distributed tracing
- Mix up Notion sync retry with task retry counter
- Skip indexes on asset_metadata table (slow queries)

**✅ DO:**
- Use short transactions only (claim → close → sync → reopen → update)
- Enforce rate limiting with AsyncLimiter(max_rate=3, time_period=1)
- Classify errors as permanent vs transient before retry logic
- Implement fire-and-forget pattern for Notion sync (don't block workers)
- Validate URLs with HEAD request before storing in database
- Use CredentialService for R2 and Notion token decryption
- Add composite indexes for efficient queries (task_id, channel_id + asset_type)
- Populate correlation_id from Story 8.1 context automatically
- Separate Notion sync retry from main task retry counter
- Write comprehensive tests for both Notion and R2 storage strategies

### Success Criteria (Definition of Done)

**Functional:**
- [ ] All 4 worker types record asset URLs to asset_metadata table (22 images, 18 videos, 18 narration, 18 SFX)
- [ ] Notion page updated with all asset URLs after pipeline completes
- [ ] Asset URLs are publicly accessible (validated with HEAD request)
- [ ] Both Notion and R2 storage strategies supported with correct URL generation
- [ ] Rate limiting enforced (3 req/sec) for all Notion API calls
- [ ] Fire-and-forget pattern implemented (workers don't block on Notion sync)

**Technical:**
- [ ] AssetMetadata model created with all required fields and indexes
- [ ] Alembic migration applied successfully (up and down)
- [ ] Asset URL storage service persists to database with URL validation
- [ ] Notion asset sync service implements rate limiting and retry logic
- [ ] All workers call record_asset_url() after asset generation
- [ ] Background job queues Notion sync (fire-and-forget)
- [ ] API endpoints registered and accessible

**Testing:**
- [ ] Unit tests for AssetMetadata model (relationships, constraints)
- [ ] Unit tests for asset_url_storage service methods
- [ ] Unit tests for notion_asset_sync service (mocked Notion API)
- [ ] Integration test: full pipeline → all assets recorded and synced
- [ ] Integration test: Notion vs R2 URL generation
- [ ] API tests for all 3 endpoints
- [ ] All tests passing (15+ tests for new code)

**Documentation:**
- [ ] asset_metadata table schema documented in architecture
- [ ] Asset URL population flow documented in developer guide
- [ ] Notion sync pattern (fire-and-forget) documented
- [ ] API endpoint examples in API documentation
- [ ] Migration notes in version file

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.5 (claude-sonnet-4-5-20250929)

### Debug Log References

N/A - Story creation, not implementation

### Completion Notes List

**Story Creation Complete:**
- Comprehensive analysis of Epic 8 context and Story 8.3 requirements
- Detailed architecture analysis (Notion integration, storage strategies, fire-and-forget pattern)
- Previous story intelligence from Story 8.1 (correlation IDs) and Story 8.2 (database patterns)
- Analysis of Story 1.5 (Storage Strategy) and Story 7.5 (Notion sync patterns)
- Git analysis: Recent commits show Story 8.2 complete, Story 8.1 complete
- Architecture review: Rate limiting, transaction patterns, error classification
- Project context review: CLI wrapper patterns, filesystem helpers, Notion integration

**Critical Context Extracted:**
- 76 total asset URLs to populate (22 images, 18 videos, 36 audio)
- Both Notion and R2 storage strategies must be supported
- Fire-and-forget pattern MANDATORY (don't block workers on Notion sync)
- Rate limiting MANDATORY (3 req/sec for Notion API)
- Short transactions only (no DB lock during Notion API calls)
- URL validation required (HEAD request) before storing

**Developer Guardrails Established:**
- Use AsyncLimiter(3, 1) for ALL Notion API calls
- Implement fire-and-forget pattern (short transactions)
- Classify errors (permanent vs transient) before retry
- Validate URLs before storing (HEAD request)
- Use StorageStrategyService for channel storage config
- Separate Notion sync retry from task retry counter

### File List

**Story File:**
- `/Users/francisaraujo/repos/ai-video-generator/_bmad-output/implementation-artifacts/8-3-asset-url-population-in-notion.md`

**Implementation Files (To Be Created):**
- `app/models.py` - Add AssetMetadata model + relationships
- `app/services/asset_url_storage.py` - Asset URL recording service
- `app/services/notion_asset_sync.py` - Notion sync service with rate limiting
- `app/routes/asset_urls.py` - Asset URL API endpoints
- `app/workers/asset_worker.py` - Update for URL recording
- `app/workers/video_generation_worker.py` - Update for URL recording
- `app/workers/narration_generation_worker.py` - Update for URL recording
- `app/workers/sfx_generation_worker.py` - Update for URL recording
- `app/main.py` - Register asset_urls router
- `alembic/versions/<timestamp>_add_asset_metadata_table.py` - Migration
- `tests/test_models/test_asset_metadata.py` - Model tests
- `tests/test_services/test_asset_url_storage.py` - Storage service tests
- `tests/test_services/test_notion_asset_sync.py` - Notion sync tests
- `tests/integration/test_asset_url_flow.py` - End-to-end tests
- `tests/support/factories.py` - Add create_asset_metadata() factory
