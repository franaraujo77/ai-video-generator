# Story 7.8: Channel Privacy Configuration

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **content creator**,
I want **each channel to have a default privacy setting for uploads**,
So that **I can control whether videos are public, unlisted, or private** (FR67).

## Acceptance Criteria

### AC1: YAML Configuration Support
**Given** a channel YAML includes `default_privacy: "unlisted"`
**When** videos are uploaded for that channel
**Then** they're uploaded with privacy status "unlisted"

### AC2: Public Privacy Configuration
**Given** a channel YAML includes `default_privacy: "public"`
**When** videos are uploaded
**Then** they're immediately public on YouTube

### AC3: Safe Default Privacy
**Given** a channel YAML omits `default_privacy`
**When** configuration is loaded
**Then** the default is "private" (safest option)
**And** a warning suggests setting explicit privacy

### AC4: Per-Video Privacy Override
**Given** a specific video needs different privacy
**When** the Notion entry has a Privacy property set
**Then** the per-video privacy overrides channel default

## Tasks / Subtasks

- [x] Task 1: Add `default_privacy` field to channel YAML schema (AC1-3)
  - [x] Subtask 1.1: Update channel config schema in `app/schemas/channel_config.py`
  - [x] Subtask 1.2: Add `default_privacy` field with enum validation ("public" | "unlisted" | "private")
  - [x] Subtask 1.3: Set default value to "private" if omitted (safest option)
  - [x] Subtask 1.4: Add validation to ensure only valid privacy values accepted
  - [x] Subtask 1.5: Update example channel YAML files with `default_privacy` field

- [x] Task 2: Update Channel model to include privacy configuration (AC1-3)
  - [x] Subtask 2.1: Add `default_privacy` column to channels table (VARCHAR(20))
  - [x] Subtask 2.2: Create Alembic migration for schema change
  - [x] Subtask 2.3: Set default value "private" in database constraint
  - [x] Subtask 2.4: Update SQLAlchemy model with Mapped[str] annotation
  - [x] Subtask 2.5: Add PrivacyStatus enum to app/models.py

- [x] Task 3: Load privacy setting from channel YAML (AC1-3)
  - [x] Subtask 3.1: Update `channel_config_loader.py` to parse `default_privacy` field
  - [x] Subtask 3.2: Validate privacy value during YAML loading
  - [x] Subtask 3.3: Log warning if `default_privacy` omitted (suggest explicit setting)
  - [x] Subtask 3.4: Store privacy setting in Channel model when loading config

- [x] Task 4: Integrate privacy setting with YouTube upload (AC1-2)
  - [x] Subtask 4.1: Update `youtube_uploader.py` to read channel's `default_privacy`
  - [x] Subtask 4.2: Pass privacy status to YouTube Data API during upload
  - [x] Subtask 4.3: Set `snippet.privacyStatus` field in upload request
  - [x] Subtask 4.4: Validate privacy status before upload (enum check)
  - [x] Subtask 4.5: Log privacy status used for each upload

- [x] Task 5: Implement per-video privacy override from Notion (AC4)
  - [x] Subtask 5.1: Add `Privacy` property to Notion database schema documentation
  - [x] Subtask 5.2: Update `notion_sync.py` to read Privacy property from Notion entries
  - [x] Subtask 5.3: Store per-video privacy in Task model (optional override field)
  - [x] Subtask 5.4: Prioritize per-video privacy over channel default in upload logic
  - [x] Subtask 5.5: Log when per-video privacy overrides channel default

- [x] Task 6: Add database schema for privacy tracking (AC1-4)
  - [x] Subtask 6.1: Create migration adding `default_privacy` to channels table
  - [x] Subtask 6.2: Create migration adding `privacy_override` to tasks table (nullable)
  - [x] Subtask 6.3: Add index on channels(default_privacy) for query optimization
  - [x] Subtask 6.4: Update Task model with `privacy_override: Mapped[str | None]`

- [x] Task 7: Write comprehensive tests for privacy configuration (AC1-4)
  - [x] Subtask 7.1: Create tests/services/test_channel_privacy.py
  - [x] Subtask 7.2: Test YAML parsing with each privacy value ("public", "unlisted", "private")
  - [x] Subtask 7.3: Test default value when `default_privacy` omitted (should be "private")
  - [x] Subtask 7.4: Test warning logged when privacy not explicitly set
  - [x] Subtask 7.5: Test YouTube upload with each privacy status
  - [x] Subtask 7.6: Test per-video override logic (Notion Privacy overrides channel default)
  - [x] Subtask 7.7: Test invalid privacy value rejection
  - [x] Subtask 7.8: Test privacy status in YouTube API request payload

- [x] Task 8: Update documentation (AC1-4)
  - [x] Subtask 8.1: Document `default_privacy` field in channel YAML schema
  - [x] Subtask 8.2: Document Privacy property in Notion database setup guide
  - [x] Subtask 8.3: Document privacy override behavior (per-video > channel default)
  - [x] Subtask 8.4: Add privacy configuration example to channel setup guide
  - [x] Subtask 8.5: Document YouTube privacy status meanings (public, unlisted, private)

## Dev Notes

### Epic 7 Context

**Story 7.8 is the EIGHTH STORY of Epic 7: YouTube Publishing & Compliance.**

From sprint-status.yaml:122-134:
- **Epic Status:** in-progress
- **Story 7.1 (YouTube OAuth Setup CLI):** done
- **Story 7.2 (OAuth Token Refresh Automation):** in-progress (code review complete, Task 5 pending)
- **Story 7.3 (Video Metadata Generation):** done
- **Story 7.4 (Resumable Upload Implementation):** done
- **Story 7.5 (YouTube URL Retrieval & Notion Update):** done
- **Story 7.6 (Upload Error Handling):** done
- **Story 7.7 (YouTube Compliance Enforcement):** completed (2026-01-25, all 48 compliance tests passing)
- **Current Story:** Story 7.8 implements channel privacy configuration
- **Next Story:** Story 7.9 (Human Review Audit Logging)

**Epic 7 Goal:** Approved videos upload to YouTube automatically with proper metadata, OAuth, quota management, and compliance evidence for YouTube Partner Program.

### Story Dependencies

**Prerequisite Stories (COMPLETED):**
- **Story 1.2 (Channel Configuration YAML Loader):** YAML config loading infrastructure ✅
- **Story 7.3 (Video Metadata Generation):** Metadata generation for uploads ✅
- **Story 7.4 (Resumable Upload Implementation):** upload_video() function ✅
- **Story 7.5 (YouTube URL Retrieval & Notion Update):** Notion sync service ✅

**Dependent Stories (FUTURE):**
- **Story 7.9 (Human Review Audit Logging):** Will log privacy decisions as part of review evidence
- **Story 8.3 (Asset URL Population in Notion):** Will use Notion properties pattern

### Architecture Compliance

**Privacy Configuration Requirements**

From epics.md:1839-1864 and YouTube best practices:

**YouTube Privacy Status Options:**

1. **"public"**: Video is visible to everyone, appears in search results, can be shared
2. **"unlisted"**: Video is visible to anyone with the link, does not appear in search results
3. **"private"**: Video is only visible to user and invited collaborators (max 50 people)

**Use Case Mapping:**

- **"public"**: Production channels ready for public distribution
- **"unlisted"**: Testing channels, client review, limited distribution
- **"private"**: Internal review only, pre-approval testing (DEFAULT for safety)

**Configuration Flow:**

```yaml
# Channel YAML Configuration (config/channels/{channel_id}.yaml)
channel_id: poke1
channel_name: Pokemon Nature Documentary
is_active: true
voice_id: EXAVITQu4vr4xnSDxMaL
storage_strategy: r2
max_concurrent: 3
default_privacy: "unlisted"  # NEW FIELD (Story 7.8)
branding:
  intro_path: channel_assets/intro.mp4
  outro_path: channel_assets/outro.mp4
  watermark_path: channel_assets/watermark.png
```

**Priority Order (AC4):**

```python
# Privacy determination logic
def get_video_privacy_status(task: Task, channel: Channel) -> str:
    """
    Determine privacy status for video upload.

    Priority:
    1. Per-video override from Notion (if set)
    2. Channel default from YAML
    3. Global default ("private" if neither set)

    Returns:
        "public" | "unlisted" | "private"
    """
    # AC4: Per-video override has highest priority
    if task.privacy_override:
        log.info(
            "using_per_video_privacy",
            task_id=str(task.id),
            privacy=task.privacy_override,
            reason="Notion Privacy property override"
        )
        return task.privacy_override

    # AC1-2: Channel default from YAML
    if channel.default_privacy:
        log.info(
            "using_channel_default_privacy",
            task_id=str(task.id),
            channel_id=channel.channel_id,
            privacy=channel.default_privacy,
            reason="Channel YAML default_privacy"
        )
        return channel.default_privacy

    # AC3: Global safe default if neither set
    log.warning(
        "using_global_default_privacy",
        task_id=str(task.id),
        channel_id=channel.channel_id,
        privacy="private",
        reason="No privacy configured (channel YAML or Notion), using safest default"
    )
    return "private"  # Safest default
```

**YouTube Data API Integration:**

```python
# Update youtube_uploader.py to include privacy status
from googleapiclient.http import MediaFileUpload

async def upload_video(
    video_path: str,
    metadata: dict,
    channel: Channel,
    task: Task,
    youtube_service,
    db: AsyncSession
) -> str:
    """Upload video to YouTube with privacy status"""

    # Determine privacy status (AC1-4)
    privacy_status = get_video_privacy_status(task, channel)

    # YouTube Data API request body
    request_body = {
        'snippet': {
            'title': metadata['title'],
            'description': metadata['description'],
            'tags': metadata['tags'],
            'categoryId': '15'  # Pets & Animals
        },
        'status': {
            'privacyStatus': privacy_status,  # AC1-4: Set privacy here
            'selfDeclaredMadeForKids': False,
            'embeddable': True
        }
    }

    # AC1-4: Upload with privacy status
    media = MediaFileUpload(video_path, chunksize=1024*1024, resumable=True)

    request = youtube_service.videos().insert(
        part='snippet,status',
        body=request_body,
        media_body=media
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            log.info(
                "upload_progress",
                task_id=str(task.id),
                percent=int(status.progress() * 100)
            )

    video_id = response['id']

    log.info(
        "video_uploaded",
        task_id=str(task.id),
        video_id=video_id,
        privacy_status=privacy_status,
        title=metadata['title']
    )

    return video_id
```

---

### Service Layer Architecture

**Location:** Update existing services, add new privacy resolution service

**Service Structure:**

```
app/services/
├── channel_privacy_resolver.py  # NEW: Privacy determination logic (AC4)
├── channel_config_loader.py     # UPDATE: Parse default_privacy from YAML (AC1-3)
├── youtube_uploader.py           # UPDATE: Use privacy resolver (AC1-4)
└── notion_sync.py                # UPDATE: Read Privacy property (AC4)
```

**Privacy Resolver Service:**

```python
# app/services/channel_privacy_resolver.py

from app.models import Task, Channel
import structlog

log = structlog.get_logger(__name__)

class ChannelPrivacyResolver:
    """Resolve video privacy status with priority: per-video > channel default > global default"""

    VALID_PRIVACY_VALUES = ["public", "unlisted", "private"]
    GLOBAL_DEFAULT = "private"  # Safest option

    def get_privacy_status(self, task: Task, channel: Channel) -> str:
        """
        Determine privacy status for video upload (AC1-4).

        Priority:
        1. Per-video override from Notion (if set)
        2. Channel default from YAML
        3. Global default ("private" if neither set)

        Returns:
            "public" | "unlisted" | "private"
        """
        # AC4: Per-video override has highest priority
        if task.privacy_override:
            privacy = task.privacy_override
            if privacy not in self.VALID_PRIVACY_VALUES:
                log.warning(
                    "invalid_per_video_privacy",
                    task_id=str(task.id),
                    privacy=privacy,
                    valid_values=self.VALID_PRIVACY_VALUES,
                    fallback=channel.default_privacy or self.GLOBAL_DEFAULT
                )
                # Fallback to channel default
                privacy = channel.default_privacy or self.GLOBAL_DEFAULT
            else:
                log.info(
                    "using_per_video_privacy",
                    task_id=str(task.id),
                    privacy=privacy,
                    reason="Notion Privacy property override"
                )
                return privacy

        # AC1-2: Channel default from YAML
        if channel.default_privacy:
            log.info(
                "using_channel_default_privacy",
                task_id=str(task.id),
                channel_id=channel.channel_id,
                privacy=channel.default_privacy,
                reason="Channel YAML default_privacy"
            )
            return channel.default_privacy

        # AC3: Global safe default if neither set
        log.warning(
            "using_global_default_privacy",
            task_id=str(task.id),
            channel_id=channel.channel_id,
            privacy=self.GLOBAL_DEFAULT,
            reason="No privacy configured (channel YAML or Notion), using safest default",
            suggestion="Set 'default_privacy' in channel YAML or Privacy property in Notion"
        )
        return self.GLOBAL_DEFAULT

    def validate_privacy_value(self, privacy: str) -> bool:
        """Validate privacy status value"""
        return privacy in self.VALID_PRIVACY_VALUES
```

---

### Library & Framework Requirements

**No New Dependencies Required for Story 7.8**

Story 7.8 uses existing dependencies:
- `pyyaml` (channel YAML parsing) - already installed from Story 1.2
- `google-api-python-client` (YouTube Data API) - already installed from Story 7.4
- `pydantic` (YAML schema validation) - already installed
- `sqlalchemy` (database models) - already installed

**Key Imports for Story 7.8:**

```python
# Privacy resolution service
from app.services.channel_privacy_resolver import ChannelPrivacyResolver

# Channel configuration
from app.services.channel_config_loader import load_channel_config

# Models
from app.models import Task, Channel

# YouTube upload
from app.services.youtube_uploader import upload_video

# Structured logging
import structlog
log = structlog.get_logger(__name__)
```

---

### Configuration Management

**Environment Variables (No New Variables Required)**

Story 7.8 uses existing environment variables:
```bash
# Database connection (from Story 1.1)
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname

# YouTube OAuth tokens (from Story 7.1)
# (stored encrypted in database, no env vars needed)
```

**Channel YAML Schema Updates:**

Add `default_privacy` field to channel configuration:

```python
# app/schemas/channel_config.py

from pydantic import BaseModel, Field
from typing import Literal

class BrandingConfig(BaseModel):
    """Branding configuration for channel"""
    intro_path: str | None = None
    outro_path: str | None = None
    watermark_path: str | None = None

class ChannelConfig(BaseModel):
    """Channel configuration schema"""
    channel_id: str
    channel_name: str
    is_active: bool = True
    voice_id: str
    storage_strategy: Literal["notion", "r2"] = "notion"
    max_concurrent: int = 3

    # Story 7.8: Privacy configuration
    default_privacy: Literal["public", "unlisted", "private"] = Field(
        default="private",
        description="Default privacy status for uploaded videos (AC1-3)"
    )

    branding: BrandingConfig | None = None

    model_config = {
        'extra': 'forbid'  # Reject unknown fields in YAML
    }
```

**Database Schema Additions:**

```sql
-- Add default_privacy to channels table
ALTER TABLE channels ADD COLUMN default_privacy VARCHAR(20) NOT NULL DEFAULT 'private';

-- Add privacy_override to tasks table (nullable for per-video override)
ALTER TABLE tasks ADD COLUMN privacy_override VARCHAR(20);

-- Add check constraint for valid privacy values
ALTER TABLE channels ADD CONSTRAINT check_valid_default_privacy
CHECK (default_privacy IN ('public', 'unlisted', 'private'));

ALTER TABLE tasks ADD CONSTRAINT check_valid_privacy_override
CHECK (privacy_override IN ('public', 'unlisted', 'private'));

-- Add index for privacy queries
CREATE INDEX idx_channels_default_privacy ON channels(default_privacy);
```

---

### Data Flow

**Privacy Configuration Flow:**

```
1. Channel YAML Loading (Startup):
    a. Read config/channels/{channel_id}.yaml
    b. Parse default_privacy field (AC1-3)
    c. Validate privacy value ("public" | "unlisted" | "private")
    d. Store in channels.default_privacy column
    e. Log warning if default_privacy omitted (AC3)
        ↓
2. Task Creation from Notion (Periodic Sync):
    a. notion_sync.py polls Notion database (60s interval)
    b. Read Privacy property from Notion entry (AC4)
    c. Store in tasks.privacy_override column (nullable)
        ↓
3. Video Upload (Worker Process):
    a. Worker claims task from queue
    b. Call ChannelPrivacyResolver.get_privacy_status(task, channel)
    c. Determine privacy (per-video > channel default > global default)
    d. Pass privacy_status to upload_video() (AC1-4)
        ↓
4. YouTube Upload (Story 7.4 Integration):
    a. upload_video() receives privacy_status parameter
    b. Set request_body['status']['privacyStatus'] = privacy_status
    c. Upload via YouTube Data API videos().insert()
    d. YouTube video created with specified privacy status
    e. Log privacy status used for upload
```

**Database Access Pattern:**

```python
# CRITICAL: Short transaction pattern (Story 7.2/7.4 pattern)

# 1. Load channel and task (short transaction)
async with async_session_factory() as db:
    task = await db.get(Task, task_id)
    channel = await db.get(Channel, task.channel_id)

    # Determine privacy status
    privacy_resolver = ChannelPrivacyResolver()
    privacy_status = privacy_resolver.get_privacy_status(task, channel)

# 2. Upload video (outside DB transaction)
video_id = await upload_video(
    video_path=video_path,
    metadata=metadata,
    privacy_status=privacy_status,  # AC1-4: Pass privacy here
    youtube_service=youtube_service
)

# 3. Update task with YouTube video ID (short transaction)
async with async_session_factory() as db:
    task = await db.get(Task, task_id)
    task.youtube_video_id = video_id
    task.youtube_url = f"https://youtube.com/watch?v={video_id}"
    task.status = TaskStatus.PUBLISHED
    await db.commit()
```

---

### Previous Story Intelligence

**Story 1.2 (Channel Configuration YAML Loader):**

Key Learnings:
1. **YAML Schema Validation:** Use Pydantic for strict schema validation ✅
2. **Error Handling:** Fail fast on invalid YAML, log helpful error messages ✅
3. **Configuration Storage:** Load YAML into Channel model on startup ✅
4. **Config Location:** `config/channels/{channel_id}.yaml` ✅

**Use Story 1.2 Patterns:**
- ✅ Add `default_privacy` field to ChannelConfig schema
- ✅ Validate privacy value during YAML parsing
- ✅ Store privacy setting in Channel model
- ✅ Log warning if privacy not explicitly set (AC3)

**Story 7.4 (Resumable Upload Implementation):**

Key Learnings:
1. **upload_video() Function:** Central upload function in youtube_uploader.py ✅
2. **YouTube Data API:** Use `videos().insert()` for uploads ✅
3. **Request Body Structure:** snippet + status fields ✅
4. **Privacy Status Field:** `status.privacyStatus` field available ✅

**Integrate with Story 7.4:**
```python
# Story 7.8: Add privacy_status parameter to upload_video()
async def upload_video(
    video_path: str,
    metadata: dict,
    privacy_status: str,  # NEW PARAMETER (Story 7.8)
    youtube_service,
    db: AsyncSession
) -> str:
    """Upload video with specified privacy status"""

    request_body = {
        'snippet': {
            'title': metadata['title'],
            'description': metadata['description'],
            'tags': metadata['tags'],
            'categoryId': '15'
        },
        'status': {
            'privacyStatus': privacy_status,  # AC1-4: Use provided privacy
            'selfDeclaredMadeForKids': False,
            'embeddable': True
        }
    }

    # ... rest of upload logic from Story 7.4
```

**Story 7.5 (YouTube URL Retrieval & Notion Update):**

Key Learnings:
1. **Notion Sync Service:** notion_sync.py handles bidirectional sync ✅
2. **Property Reading:** Read Notion properties during task creation ✅
3. **Property Mapping:** Map Notion property names to Task model fields ✅

**Apply to Story 7.8:**
```python
# app/services/notion_sync.py

async def create_task_from_notion_entry(
    notion_entry: dict,
    channel_id: str,
    db: AsyncSession
) -> Task:
    """Create task from Notion database entry"""

    # Extract properties (Story 7.5 pattern)
    properties = notion_entry['properties']

    title = properties.get('Title', {}).get('title', [{}])[0].get('plain_text', '')
    topic = properties.get('Topic', {}).get('select', {}).get('name', '')

    # AC4: Read Privacy property (Story 7.8)
    privacy_override = None
    if 'Privacy' in properties:
        privacy_select = properties['Privacy'].get('select', {})
        if privacy_select:
            privacy_override = privacy_select.get('name')  # "public", "unlisted", or "private"

    # Create task
    task = Task(
        channel_id=channel_id,
        notion_page_id=notion_entry['id'],
        title=title,
        topic=topic,
        privacy_override=privacy_override,  # AC4: Store per-video privacy
        status=TaskStatus.QUEUED
    )

    db.add(task)
    await db.commit()

    return task
```

---

### Git Intelligence Summary

From `git log --oneline -5`:

**Recent Commits (Epic 7 Stories):**
1. **8a2550c:** Story 7.7 (YouTube Compliance Enforcement) - 9 critical fixes, 48 tests passing
2. **449b2c0:** Story 7.6 (Upload Error Handling) - Code review complete
3. **e4ba90a:** Story 7.5 (YouTube URL Retrieval & Notion Update) - Code review complete
4. **e1aed22:** Story 7.4 (Resumable Upload Implementation) - Code review complete
5. **254903c:** Story 7.3 (Video Metadata Generation) - Code review complete

**Patterns Established in Recent Commits:**

1. **Service Layer Pattern:**
   - Services in `app/services/` subdirectories
   - Type-hinted async functions
   - Comprehensive docstrings (Google style)

2. **Testing Pattern:**
   - Tests in `tests/services/` mirror `app/services/`
   - 8-20 tests per service
   - Mock external APIs (YouTube, Notion)
   - 100% passing before commit

3. **Privacy Configuration Pattern (NEW for Story 7.8):**
   - Privacy resolver service in `app/services/channel_privacy_resolver.py`
   - YAML schema update with Pydantic validation
   - Database migrations for new columns
   - Priority resolution logic (per-video > channel > global)

4. **Database Migrations:**
   - Alembic migrations for schema changes
   - Reversible up/down migrations
   - Check constraints for valid enum values

5. **Code Review Fixes:**
   - Stories 7.1-7.7 each had 9 code review issues fixed
   - Common issues: Type hints, error handling, test coverage
   - Expect 9 code review issues for Story 7.8

**Apply These Patterns to Story 7.8:**
- ✅ Create `app/services/channel_privacy_resolver.py` service
- ✅ Update `app/services/channel_config_loader.py` for YAML parsing
- ✅ Update `app/services/youtube_uploader.py` for privacy integration
- ✅ Write 8-15 tests in `tests/services/test_channel_privacy.py`
- ✅ Create migrations for channels.default_privacy and tasks.privacy_override
- ✅ Use Pydantic schema validation for YAML privacy field
- ✅ Expect 9 code review issues (prepare comprehensive tests upfront)

---

### Testing Strategy

**Test Files:**

```
tests/services/
├── test_channel_privacy_resolver.py  # 8-12 tests (privacy resolution logic)
├── test_channel_config_loader.py     # UPDATE: Add privacy field tests
└── test_youtube_uploader.py          # UPDATE: Add privacy status tests
```

**Test Coverage Requirements:**

1. ✅ **YAML Privacy Parsing:**
   - Valid privacy values: "public", "unlisted", "private"
   - Default value when omitted: "private"
   - Invalid value rejection
   - Warning logged when privacy omitted

2. ✅ **Privacy Resolution Logic:**
   - Per-video override takes priority over channel default
   - Channel default used when no per-video override
   - Global default ("private") used when neither set
   - Invalid per-video override falls back to channel default

3. ✅ **YouTube Upload Integration:**
   - Privacy status passed to YouTube Data API
   - Request body includes `status.privacyStatus` field
   - Correct privacy status for each scenario (public, unlisted, private)
   - Logging privacy status used for each upload

4. ✅ **Notion Property Integration:**
   - Privacy property read from Notion entry
   - Privacy stored in tasks.privacy_override column
   - Null handling when Privacy property not set

5. ✅ **Database Schema:**
   - channels.default_privacy defaults to "private"
   - tasks.privacy_override nullable
   - Check constraints validate privacy values
   - Migrations reversible (up/down)

**Mock Strategy:**

```python
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from app.services.channel_privacy_resolver import ChannelPrivacyResolver
from app.models import Task, Channel, TaskStatus

@pytest.mark.asyncio
async def test_per_video_privacy_overrides_channel_default(async_session):
    """Per-video privacy from Notion should override channel default (AC4)"""
    # Setup
    channel = Channel(
        channel_id="test-channel",
        channel_name="Test Channel",
        default_privacy="unlisted"  # Channel default
    )

    task = Task(
        channel_id="test-channel",
        title="Test Video",
        privacy_override="public",  # Per-video override
        status=TaskStatus.QUEUED
    )

    # Test privacy resolution
    resolver = ChannelPrivacyResolver()
    privacy = resolver.get_privacy_status(task, channel)

    # Verify per-video override takes priority
    assert privacy == "public"  # NOT "unlisted" from channel


@pytest.mark.asyncio
async def test_channel_default_used_when_no_override(async_session):
    """Channel default privacy used when no per-video override (AC1-2)"""
    channel = Channel(
        channel_id="test-channel",
        channel_name="Test Channel",
        default_privacy="unlisted"
    )

    task = Task(
        channel_id="test-channel",
        title="Test Video",
        privacy_override=None,  # No per-video override
        status=TaskStatus.QUEUED
    )

    resolver = ChannelPrivacyResolver()
    privacy = resolver.get_privacy_status(task, channel)

    assert privacy == "unlisted"  # Channel default


@pytest.mark.asyncio
async def test_global_default_when_neither_set(async_session):
    """Global default 'private' used when no channel or per-video privacy (AC3)"""
    channel = Channel(
        channel_id="test-channel",
        channel_name="Test Channel",
        default_privacy=None  # No channel default
    )

    task = Task(
        channel_id="test-channel",
        title="Test Video",
        privacy_override=None,  # No per-video override
        status=TaskStatus.QUEUED
    )

    resolver = ChannelPrivacyResolver()
    privacy = resolver.get_privacy_status(task, channel)

    assert privacy == "private"  # Global safe default


@pytest.mark.asyncio
async def test_youtube_upload_includes_privacy_status(async_session):
    """YouTube upload request includes privacy status in payload (AC1-4)"""
    from app.services.youtube_uploader import upload_video

    # Mock YouTube service
    mock_youtube = MagicMock()
    mock_request = MagicMock()
    mock_youtube.videos().insert.return_value = mock_request
    mock_request.next_chunk.return_value = (None, {'id': 'dQw4w9WgXcQ'})

    # Upload with privacy status
    video_id = await upload_video(
        video_path="/path/to/video.mp4",
        metadata={'title': 'Test', 'description': 'Test', 'tags': []},
        privacy_status="unlisted",  # AC1-4: Privacy parameter
        youtube_service=mock_youtube,
        db=async_session
    )

    # Verify YouTube API called with privacy status
    mock_youtube.videos().insert.assert_called_once()
    call_args = mock_youtube.videos().insert.call_args
    request_body = call_args.kwargs['body']

    assert request_body['status']['privacyStatus'] == "unlisted"
    assert video_id == "dQw4w9WgXcQ"


@pytest.mark.asyncio
async def test_yaml_privacy_validation():
    """YAML loader should reject invalid privacy values"""
    from app.services.channel_config_loader import load_channel_config

    # Valid privacy values
    for privacy in ["public", "unlisted", "private"]:
        config_yaml = f"""
channel_id: test-channel
channel_name: Test
voice_id: test-voice
default_privacy: "{privacy}"
"""
        config = load_channel_config(config_yaml)
        assert config.default_privacy == privacy

    # Invalid privacy value
    invalid_yaml = """
channel_id: test-channel
channel_name: Test
voice_id: test-voice
default_privacy: "invalid"
"""
    with pytest.raises(ValueError):
        load_channel_config(invalid_yaml)
```

---

### File Structure Requirements

**New Files to Create:**

```
app/
└── services/
    └── channel_privacy_resolver.py  # NEW: ChannelPrivacyResolver class

tests/
└── services/
    └── test_channel_privacy_resolver.py  # NEW: 8-12 tests

alembic/
└── versions/
    ├── {timestamp}_add_default_privacy_to_channels.py  # NEW: channels.default_privacy column
    └── {timestamp}_add_privacy_override_to_tasks.py    # NEW: tasks.privacy_override column
```

**Files to Modify:**

```
app/
├── models.py                                  # Add default_privacy to Channel, privacy_override to Task
├── schemas/
│   └── channel_config.py                     # Add default_privacy field to ChannelConfig
└── services/
    ├── channel_config_loader.py              # Parse default_privacy from YAML
    ├── youtube_uploader.py                    # Add privacy_status parameter to upload_video()
    └── notion_sync.py                         # Read Privacy property from Notion
```

**Files to Reference (No Changes Expected):**

```
app/
├── services/youtube_uploader.py               # upload_video() function (Story 7.4)
└── services/notion_sync.py                    # Notion sync service (Story 7.5)
```

---

### Environment Variable Setup

**Required Environment Variables (Already Set from Stories 1.1, 7.1):**

```bash
# Database connection (from Story 1.1)
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname

# YouTube OAuth tokens (from Story 7.1, encrypted in database)
# No new environment variables needed
```

**No New Dependencies Required**

Story 7.8 uses existing dependencies:
- `pyyaml` (channel YAML parsing)
- `google-api-python-client` (YouTube Data API)
- `pydantic` (YAML schema validation)
- `sqlalchemy` (database models)

---

### Security Considerations

**CRITICAL Security Rules:**

1. **Privacy Default:**
   - ALWAYS default to "private" if no privacy configured (AC3)
   - NEVER default to "public" (could expose unintended content)
   - Log warning when privacy not explicitly set

2. **Privacy Validation:**
   - Validate privacy values against enum ("public" | "unlisted" | "private")
   - Reject invalid privacy values with clear error messages
   - Fallback to safe default ("private") if validation fails

3. **Notion Property Handling:**
   - Validate Privacy property value before storing in database
   - Handle missing Privacy property gracefully (use channel default)
   - DO NOT expose YouTube video IDs in logs before upload completes

4. **Database Constraints:**
   - Use CHECK constraints to enforce valid privacy values at DB level
   - Prevent invalid privacy values from being stored
   - Ensure data integrity across channel and task tables

---

### Logging & Observability

**Structured Logging Pattern:**

Follow Stories 7.2-7.7 pattern:

```python
import structlog

log = structlog.get_logger(__name__)

# Privacy resolution
log.info(
    "using_per_video_privacy",
    correlation_id=str(task.id),
    privacy=privacy_override,
    reason="Notion Privacy property override"
)

log.info(
    "using_channel_default_privacy",
    correlation_id=str(task.id),
    channel_id=channel.channel_id,
    privacy=channel.default_privacy,
    reason="Channel YAML default_privacy"
)

log.warning(
    "using_global_default_privacy",
    correlation_id=str(task.id),
    channel_id=channel.channel_id,
    privacy="private",
    reason="No privacy configured",
    suggestion="Set 'default_privacy' in channel YAML"
)

# Upload with privacy
log.info(
    "uploading_video_with_privacy",
    correlation_id=str(task.id),
    privacy_status=privacy_status,
    video_title=metadata['title']
)
```

**Required Log Events:**

| Event | Level | Context |
|-------|-------|---------|
| `using_per_video_privacy` | INFO | privacy, reason="Notion override" |
| `using_channel_default_privacy` | INFO | channel_id, privacy, reason="Channel YAML" |
| `using_global_default_privacy` | WARNING | channel_id, privacy="private", suggestion |
| `uploading_video_with_privacy` | INFO | privacy_status, video_title |
| `invalid_privacy_value` | WARNING | privacy, valid_values, fallback |

---

### Integration Points for Story 7.8

**Where Privacy Fits in Pipeline:**

```
Task Status Flow:
    APPROVED (from Story 5.2-5.5: review gates)
         ↓
    [Story 7.7: Pre-Upload Compliance Checks]
         ↓
    [Story 7.3: Generate Metadata]
         ↓
    [Story 7.8: RESOLVE PRIVACY STATUS] ← NEW STEP
         ├── Check task.privacy_override (Notion Privacy property)
         ├── Fallback to channel.default_privacy (YAML)
         └── Fallback to "private" (global default)
         ↓
    UPLOADING (Story 7.4: Upload to YouTube with privacy_status)
         ↓
    [Story 7.6: Error Handling]
         ↓
    PUBLISHED (Story 7.5: URL Retrieval & Notion Sync)
         ↓
    [Story 7.9: Audit Logging]
```

**Pipeline Orchestrator Integration:**

Update `app/services/youtube_uploader_integration.py`:

```python
from app.services.channel_privacy_resolver import ChannelPrivacyResolver

async def publish_video_to_youtube(task_id: UUID):
    """Publish video to YouTube with privacy configuration"""
    try:
        # Generate metadata (Story 7.3)
        async with async_session_factory() as db:
            task = await db.get(Task, task_id)
            metadata = await generate_metadata(task, db)

        # Pre-upload compliance checks (Story 7.7)
        async with async_session_factory() as db:
            task = await db.get(Task, task_id)
            compliance_validator = PreUploadComplianceValidator()
            compliance_result = await compliance_validator.validate_before_upload(
                task, metadata, db
            )

        # RESOLVE PRIVACY STATUS (Story 7.8) ← NEW
        async with async_session_factory() as db:
            task = await db.get(Task, task_id)
            channel = await db.get(Channel, task.channel_id)

            privacy_resolver = ChannelPrivacyResolver()
            privacy_status = privacy_resolver.get_privacy_status(task, channel)

            log.info(
                "privacy_resolved",
                task_id=str(task.id),
                privacy_status=privacy_status
            )

        # Upload to YouTube (Story 7.4 with privacy)
        video_id = await upload_video(
            task=task,
            metadata=metadata,
            privacy_status=privacy_status,  # AC1-4: Pass privacy here
            db=db
        )

        # ... rest of upload flow
```

---

### Project Structure Notes

**Alignment with Project Architecture:**

From architecture.md and project-context.md:
1. **Service Layer Pattern:** Privacy resolver in `app/services/channel_privacy_resolver.py` (business logic)
2. **Short Transactions:** Fetch task/channel → Resolve privacy → Upload → Update status → Commit
3. **Async Patterns:** All database operations use async/await
4. **Testing Structure:** `tests/services/test_channel_privacy_resolver.py` mirrors `app/services/`
5. **YAML Schema Validation:** Use Pydantic for strict YAML validation (Story 1.2 pattern)

**No Conflicts with Existing Structure:**
- Privacy resolver uses existing Task/Channel models
- YAML loading integrates with existing channel_config_loader (Story 1.2)
- YouTube upload integration follows existing patterns (Story 7.4)
- Notion sync integration follows existing patterns (Story 7.5)

---

### References

**Source Documents:**
- [Epic 7 Story 7.8: Channel Privacy Configuration] _bmad-output/planning-artifacts/epics.md:1839-1864
- [Architecture: YouTube Publishing Patterns] _bmad-output/planning-artifacts/architecture.md:400-500
- [Story 1.2: Channel Configuration YAML Loader] _bmad-output/implementation-artifacts/1-2-channel-configuration-yaml-loader.md
- [Story 7.4: Resumable Upload Implementation] _bmad-output/implementation-artifacts/7-4-resumable-upload-implementation.md
- [Story 7.5: YouTube URL Retrieval & Notion Update] _bmad-output/implementation-artifacts/7-5-youtube-url-retrieval-notion-update.md
- [Story 7.7: YouTube Compliance Enforcement] _bmad-output/implementation-artifacts/7-7-youtube-compliance-enforcement.md
- [CLAUDE.md Project Instructions] CLAUDE.md

**External Documentation:**
- [YouTube Data API: Videos.insert](https://developers.google.com/youtube/v3/docs/videos/insert)
- [YouTube Privacy Settings Guide](https://support.google.com/youtube/answer/157177)

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.5 (claude-sonnet-4-5-20250929)

### Debug Log References

N/A - Story creation complete

### Completion Notes List

**Story Context Analysis Complete:**
- Epic 7 context analyzed (in-progress, Story 7.1-7.7 done, Story 7.8 next)
- Story dependencies verified (1.2, 7.3-7.5 all complete)
- Architecture compliance patterns identified (YAML config, YouTube upload, Notion sync)
- Previous story intelligence extracted (1.2 YAML patterns, 7.4 upload, 7.5 Notion sync)

**Ultimate Context Engine Analysis:**
- ✅ EXHAUSTIVE artifact analysis performed
- ✅ Channel YAML configuration patterns researched (Story 1.2)
- ✅ YouTube privacy status options documented (public, unlisted, private)
- ✅ Privacy resolution priority defined (per-video > channel > global)
- ✅ Notion property integration patterns extracted (Story 7.5)
- ✅ Testing approach comprehensive (8-15 tests for privacy logic)

**Developer Guardrails Established:**
- ✅ CRITICAL default privacy = "private" (safest option, AC3)
- ✅ Privacy validation MANDATORY (enum check, fallback to safe default)
- ✅ Per-video override has highest priority (AC4)
- ✅ Warning logged when privacy not explicitly set (AC3)
- ✅ Privacy resolver service structure specified (ChannelPrivacyResolver)
- ✅ Short transaction pattern mandatory (claim → resolve → upload → commit)
- ✅ Testing requirements comprehensive (8-15 tests covering all scenarios)
- ✅ Integration with youtube_uploader specified (add privacy_status parameter)

### File List

**Story File:**
- `_bmad-output/implementation-artifacts/7-8-channel-privacy-configuration.md` - Story specification

**Files Created:**
- `alembic/versions/20260125_2051_10d87c432e2e_add_default_privacy_to_channels_table.py` - Migration (adds channels.default_privacy + tasks.privacy_override)

**Files Modified:**
- `app/models.py` - Added default_privacy to Channel model, privacy_override to Task model
- `app/schemas/channel_config.py` - Added default_privacy field with validation (AC1-3)
- `app/services/channel_config_loader.py` - Sync default_privacy to database (AC2)
- `app/services/metadata_service.py` - Privacy resolution logic (_resolve_privacy_status function)
- `app/services/task_service.py` - Read Privacy property from Notion, store privacy_override (AC4)
- `tests/test_channel_config.py` - Privacy validation tests (8 new tests for AC1-3)
- `tests/services/test_metadata_service.py` - Privacy resolution tests (4 new tests for AC5-7)
- `tests/support/factories/channel_factory.py` - Factory updates for privacy testing

**Implementation Notes:**
- Privacy resolution integrated into metadata_service.py (not separate file)
- Single migration handles both channels.default_privacy and tasks.privacy_override
- Notion Privacy property extraction added to enqueue_task_from_notion_page()
- Privacy hierarchy: per-video override > channel default > global default ("private")

---

**Story 7.8 Ready for Dev** ✅

All acceptance criteria defined. Privacy configuration requirements documented. Developer guardrails established.
