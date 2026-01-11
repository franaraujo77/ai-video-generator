# Story 1.6: Channel Capacity Tracking

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **system operator**,
I want **the system to track queue depth and processing capacity per channel**,
So that **I can monitor channel load and ensure fair scheduling** (FR13, FR16).

## Acceptance Criteria

1. **Given** multiple videos are queued for different channels
   **When** the queue status is queried
   **Then** queue depth is reported per channel (count of pending tasks)
   **And** channels are displayed with their current load

2. **Given** workers are processing tasks
   **When** channel capacity is calculated
   **Then** in-progress tasks are counted per channel
   **And** the system can determine which channel has capacity for new work (FR16)

3. **Given** a channel has reached its configured `max_concurrent` limit
   **When** a worker looks for tasks
   **Then** tasks from that channel are skipped temporarily
   **And** workers pick up tasks from other channels with capacity (FR13)

## Tasks / Subtasks

- [x] Task 1: Add max_concurrent column to Channel database model (AC: #3)
  - [x] 1.1: Add `max_concurrent` column (Integer, nullable=False, default=2) to Channel model in `app/models.py`
  - [x] 1.2: Update Channel docstring to document max_concurrent field
  - [x] 1.3: Update Channel `__repr__` to show max_concurrent value

- [x] Task 2: Create Alembic migration for max_concurrent column (AC: #3)
  - [x] 2.1: Generate new migration file: `alembic revision -m "add_max_concurrent_column"`
  - [x] 2.2: Add `max_concurrent` as Integer column with server_default="2"
  - [x] 2.3: Test migration forward and rollback locally
  - [x] 2.4: Review migration manually before committing

- [x] Task 3: Update ChannelConfigLoader to persist max_concurrent (AC: #3)
  - [x] 3.1: Update `ChannelConfigLoader.sync_to_database()` to persist max_concurrent to Channel model
  - [x] 3.2: Add validation: max_concurrent must be between 1 and 10 (already in schema)
  - [x] 3.3: Log max_concurrent value during sync with structlog

- [x] Task 4: Create ChannelCapacityService for capacity tracking (AC: #1, #2, #3)
  - [x] 4.1: Create `app/services/channel_capacity_service.py` with `ChannelCapacityService` class
  - [x] 4.2: Create `ChannelQueueStats` dataclass with: channel_id, channel_name, pending_count, in_progress_count, max_concurrent, has_capacity (bool)
  - [x] 4.3: Implement `get_queue_stats(db: AsyncSession) -> list[ChannelQueueStats]` method
  - [x] 4.4: Implement `get_channel_capacity(channel_id: str, db: AsyncSession) -> ChannelQueueStats` method
  - [x] 4.5: Implement `has_capacity(channel_id: str, db: AsyncSession) -> bool` method
  - [x] 4.6: Implement `get_channels_with_capacity(db: AsyncSession) -> list[str]` method for worker scheduling
  - [x] 4.7: Add logging for capacity calculations with structlog
  - [x] 4.8: Export from `app/services/__init__.py`

- [x] Task 5: Create Task model for queue tracking (AC: #1, #2)
  - [x] 5.1: Create `Task` model in `app/models.py` with fields: id, channel_id (FK to channels), status, created_at, updated_at
  - [x] 5.2: Add status column as String(20) with allowed values: "pending", "claimed", "processing", "awaiting_review", "approved", "rejected", "completed", "failed", "retry"
  - [x] 5.3: Add index on (channel_id, status) for efficient queue queries: `ix_tasks_channel_id_status`
  - [x] 5.4: Add partial index on status='pending' for fast pending task queries
  - [x] 5.5: Add relationship from Channel to Task (one-to-many)

- [x] Task 6: Create Alembic migration for Task model (AC: #1, #2)
  - [x] 6.1: Generate new migration file: `alembic revision -m "add_task_model"`
  - [x] 6.2: Create tasks table with id, channel_id, status, created_at, updated_at
  - [x] 6.3: Add foreign key constraint to channels table
  - [x] 6.4: Add composite index ix_tasks_channel_id_status
  - [x] 6.5: Add partial index idx_tasks_pending WHERE status='pending'
  - [x] 6.6: Test migration forward and rollback locally

- [x] Task 7: Write comprehensive tests (AC: #1, #2, #3)
  - [x] 7.1: Create `tests/test_channel_capacity_service.py`
  - [x] 7.2: Test get_queue_stats returns correct pending/in_progress counts per channel
  - [x] 7.3: Test get_channel_capacity returns correct stats for specific channel
  - [x] 7.4: Test has_capacity returns True when in_progress < max_concurrent
  - [x] 7.5: Test has_capacity returns False when in_progress >= max_concurrent
  - [x] 7.6: Test get_channels_with_capacity returns only channels with available capacity
  - [x] 7.7: Test capacity is channel-isolated (one channel at max doesn't affect others)
  - [x] 7.8: Test with zero pending tasks returns zero counts
  - [x] 7.9: Test with channel not found returns empty stats or raises error
  - [x] 7.10: Create `tests/test_task_model.py`
  - [x] 7.11: Test Task model creation with valid status values
  - [x] 7.12: Test Task-Channel relationship works correctly
  - [x] 7.13: Test max_concurrent sync from YAML to database (model-level tests)
  - [x] 7.14: Test sync_to_database persists default max_concurrent (integration test - Code Review)
  - [x] 7.15: Test sync_to_database persists custom max_concurrent (integration test - Code Review)
  - [x] 7.16: Test sync_to_database updates existing channel max_concurrent (integration test - Code Review)
  - [x] 7.17: Test max_concurrent schema validation range 1-10 (integration test - Code Review)

## Dev Notes

### Critical Technical Requirements

**Technology Stack (MANDATORY versions from project-context.md):**
- Python 3.10+ (use `str | None` syntax, NOT `Optional[str]`)
- SQLAlchemy >=2.0.0 (async engine, `Mapped[]` annotations)
- Pydantic >=2.8.0 (v2 syntax: `model_config = ConfigDict(...)`)
- structlog >=23.2.0 (JSON output, context binding)
- pytest >=7.4.0, pytest-asyncio >=0.21.0

**Task State Machine (from architecture.md):**
```python
# Task status values and transitions
TASK_STATUSES = {
    "pending",       # Task created, awaiting worker
    "claimed",       # Worker claimed task (transitional)
    "processing",    # Worker actively executing
    "awaiting_review", # Hit human review gate
    "approved",      # Human approved, continue
    "rejected",      # Human rejected, needs intervention
    "completed",     # Successfully finished
    "failed",        # Permanent failure
    "retry"          # Temporary failure, will retry
}

# Capacity calculation uses:
# - pending_count: status == "pending"
# - in_progress_count: status IN ("claimed", "processing", "awaiting_review")
```

**Capacity Calculation Pattern (AC #2, #3):**
```python
async def has_capacity(self, channel_id: str, db: AsyncSession) -> bool:
    """Check if channel has capacity for new work.

    Capacity is available when:
    in_progress_count < max_concurrent

    In-progress includes: claimed, processing, awaiting_review statuses.
    """
    stats = await self.get_channel_capacity(channel_id, db)
    return stats.in_progress_count < stats.max_concurrent
```

**Queue Stats Query Pattern (AC #1):**
```python
from sqlalchemy import select, func, case

async def get_queue_stats(self, db: AsyncSession) -> list[ChannelQueueStats]:
    """Get queue depth per channel.

    Returns count of pending and in-progress tasks per active channel.
    """
    # Use SQLAlchemy 2.0 select() style
    pending_statuses = ("pending",)
    in_progress_statuses = ("claimed", "processing", "awaiting_review")

    stmt = (
        select(
            Channel.channel_id,
            Channel.channel_name,
            Channel.max_concurrent,
            func.count(case((Task.status.in_(pending_statuses), 1))).label("pending_count"),
            func.count(case((Task.status.in_(in_progress_statuses), 1))).label("in_progress_count"),
        )
        .outerjoin(Task, Channel.channel_id == Task.channel_id)
        .where(Channel.is_active == True)
        .group_by(Channel.channel_id, Channel.channel_name, Channel.max_concurrent)
    )

    result = await db.execute(stmt)
    rows = result.all()

    return [
        ChannelQueueStats(
            channel_id=row.channel_id,
            channel_name=row.channel_name,
            pending_count=row.pending_count,
            in_progress_count=row.in_progress_count,
            max_concurrent=row.max_concurrent,
            has_capacity=row.in_progress_count < row.max_concurrent,
        )
        for row in rows
    ]
```

**Worker Scheduling Pattern (AC #3):**
```python
async def get_channels_with_capacity(self, db: AsyncSession) -> list[str]:
    """Get channel_ids that have capacity for new work.

    Used by workers to determine which channels to pull tasks from.
    Returns empty list if all channels are at capacity.
    """
    stats = await self.get_queue_stats(db)
    return [s.channel_id for s in stats if s.has_capacity]
```

### Anti-Patterns to AVOID

```python
# WRONG: Using legacy SQLAlchemy query() API
tasks = await session.query(Task).filter_by(status="pending").all()

# CORRECT: SQLAlchemy 2.0 select() style
result = await session.execute(select(Task).where(Task.status == "pending"))
tasks = result.scalars().all()

# WRONG: Holding transaction during capacity check
async with session.begin():
    capacity = await get_capacity(channel_id)
    # Long operation here...  # BLOCKS DB!

# CORRECT: Short transaction for capacity check
async with async_session_factory() as session:
    capacity = await get_capacity(channel_id, session)
# Session closed, no transaction held

# WRONG: N+1 queries for queue stats
for channel in channels:
    pending = await count_pending(channel.id)  # N queries!

# CORRECT: Single aggregation query with JOIN
stmt = select(...).outerjoin(Task).group_by(Channel.channel_id)  # 1 query

# WRONG: Missing index for queue queries (will be slow)
# (no index on tasks.channel_id, status)

# CORRECT: Composite index for efficient queue queries
Index("ix_tasks_channel_id_status", Task.channel_id, Task.status)
```

### Project Structure Notes

**File Locations (MANDATORY from project-context.md):**
```
app/
├── models.py                    # MODIFY: Add max_concurrent to Channel, create Task model
├── services/
│   ├── __init__.py              # MODIFY: Export ChannelCapacityService, ChannelQueueStats
│   ├── channel_config_loader.py # MODIFY: Sync max_concurrent to database
│   └── channel_capacity_service.py # NEW: ChannelCapacityService class

alembic/versions/
├── xxx_add_max_concurrent_column.py  # NEW: Migration for max_concurrent
└── xxx_add_task_model.py             # NEW: Migration for Task table

tests/
├── test_channel_capacity_service.py  # NEW: ChannelCapacityService tests
└── test_task_model.py                # NEW: Task model tests
```

**Naming Conventions:**
- Service classes: `{Domain}Service` (e.g., `ChannelCapacityService`)
- Dataclasses: `{Domain}Stats`, `{Domain}Info` (e.g., `ChannelQueueStats`)
- Database columns: snake_case (e.g., `max_concurrent`, `in_progress_count`)
- Indexes: `ix_{table}_{column}` (e.g., `ix_tasks_channel_id_status`)
- Partial indexes: `idx_{table}_{description}` (e.g., `idx_tasks_pending`)

### Previous Story (1.5) Learnings

**Patterns Established:**
- Use `datetime.now(UTC)` for timezone-aware timestamps
- Use `Mapped[type]` annotations for SQLAlchemy 2.0 models
- Keep `expire_on_commit=False` in session factory
- Use structlog for all logging
- All tests should be async with pytest-asyncio
- Use `asyncio.to_thread()` for blocking I/O in async context
- Service methods take `db: AsyncSession` as parameter for dependency injection

**Code Conventions Applied:**
- Docstrings on all public classes and functions
- Type hints on all parameters and return values
- `__repr__` method on models for debugging (but NOT exposing sensitive data)
- Dataclasses for structured return types (e.g., `ChannelQueueStats`)

**Testing Patterns:**
- Use `aiosqlite` for in-memory SQLite testing
- Create fixtures in `tests/conftest.py`
- Test both success and failure scenarios
- Test edge cases (zero tasks, channel not found, all at capacity)
- Use async fixtures with `pytest-asyncio`

### Git Intelligence from Stories 1.1-1.5

**Files Created in Previous Stories:**
- `app/__init__.py` - Package with `__all__` exports
- `app/database.py` - Async engine, session factory
- `app/models.py` - Channel model (193 lines - room to add Task model and max_concurrent)
- `app/config.py` - Global configuration with DEFAULT_VOICE_ID
- `app/schemas/__init__.py`, `app/schemas/channel_config.py` - Pydantic schemas (max_concurrent already exists)
- `app/services/__init__.py` - Service exports
- `app/services/channel_config_loader.py` - Config loader
- `app/services/credential_service.py` - Credential encryption/decryption
- `app/services/voice_branding_service.py` - Voice/branding resolution
- `app/services/storage_strategy_service.py` - Storage strategy resolution
- `app/exceptions.py` - Shared ConfigurationError exception
- `app/utils/encryption.py` - EncryptionService
- `alembic/` - Migration infrastructure established
- `tests/conftest.py` - Shared async fixtures

**Important Discovery: max_concurrent Already Exists in Schema!**
The `ChannelConfigSchema` in `app/schemas/channel_config.py` already has:
```python
max_concurrent: int = Field(default=2, ge=1, le=10)
```

This means:
- YAML parsing for max_concurrent is already working
- Schema validation (1-10 range) is already implemented
- Need to ADD: database column, migration, sync logic, ChannelCapacityService, Task model

**Dependencies Already in pyproject.toml:**
- SQLAlchemy, asyncpg, Alembic (database)
- pytest, pytest-asyncio, aiosqlite (testing)
- pydantic, pyyaml, structlog

### Architecture Requirements

**From architecture.md - Task Lifecycle State Machine:**
```
pending → claimed → processing → awaiting_review → approved → processing → completed
                                                  ↓
                                               rejected
processing → failed (non-retriable)
processing → retry → pending (retriable)
```

**From architecture.md - Worker Architecture:**
- 3 independent Python worker processes
- Each worker independently claims tasks
- Workers use `FOR UPDATE SKIP LOCKED` for atomic claims
- Workers should skip channels at capacity (FR13)

**From epics.md - FR13 & FR16:**
- FR13: Multi-channel parallel processing with round-robin scheduling
- FR16: System tracks queue depth per channel for capacity balancing

**Worker Integration Note:**
This story creates the **capacity tracking infrastructure**. The actual worker claim logic with capacity checks is part of Epic 4 (Worker Orchestration). This story provides:
- `ChannelCapacityService.get_channels_with_capacity()` - list of channel_ids with available capacity
- `ChannelCapacityService.has_capacity(channel_id)` - check if specific channel can accept work
- Task model with status tracking - enables pending/in-progress counts

### Database Schema Design

**Channel Model Addition:**
```python
# Add to existing Channel model in app/models.py
max_concurrent: Mapped[int] = mapped_column(
    Integer,
    nullable=False,
    default=2,
    server_default="2",
)
```

**Task Model (NEW):**
```python
class Task(Base):
    """Video generation task in the pipeline.

    Tasks represent a video generation job that moves through the 8-step
    pipeline. Status tracks progress and enables capacity calculations.
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

    # Index for efficient queue queries
    __table_args__ = (
        Index("ix_tasks_channel_id_status", "channel_id", "status"),
    )
```

### ChannelQueueStats Dataclass

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class ChannelQueueStats:
    """Queue statistics for a single channel.

    Attributes:
        channel_id: Business identifier for the channel.
        channel_name: Human-readable display name.
        pending_count: Number of tasks with status='pending'.
        in_progress_count: Number of tasks with status in (claimed, processing, awaiting_review).
        max_concurrent: Maximum allowed concurrent tasks for this channel.
        has_capacity: True if in_progress_count < max_concurrent.
    """
    channel_id: str
    channel_name: str
    pending_count: int
    in_progress_count: int
    max_concurrent: int
    has_capacity: bool
```

### Testing Requirements

**Required Test Coverage:**
- Queue stats aggregation across multiple channels
- Capacity calculation (pending vs in-progress counts)
- has_capacity True/False scenarios
- Channel isolation (one channel at max doesn't affect others)
- Empty queue returns zero counts
- max_concurrent sync from YAML to database
- Task model CRUD operations
- Task-Channel relationship

**Test File Structure:**
```python
# tests/test_channel_capacity_service.py
import pytest
from app.services.channel_capacity_service import ChannelCapacityService, ChannelQueueStats

class TestChannelCapacityService:
    @pytest.mark.asyncio
    async def test_get_queue_stats_empty(self, db_session): ...

    @pytest.mark.asyncio
    async def test_get_queue_stats_with_pending_tasks(self, db_session): ...

    @pytest.mark.asyncio
    async def test_get_queue_stats_with_in_progress_tasks(self, db_session): ...

    @pytest.mark.asyncio
    async def test_get_channel_capacity(self, db_session): ...

    @pytest.mark.asyncio
    async def test_has_capacity_returns_true_when_under_limit(self, db_session): ...

    @pytest.mark.asyncio
    async def test_has_capacity_returns_false_when_at_limit(self, db_session): ...

    @pytest.mark.asyncio
    async def test_get_channels_with_capacity_filters_correctly(self, db_session): ...

    @pytest.mark.asyncio
    async def test_capacity_isolation_between_channels(self, db_session): ...
```

### Channel YAML Format (After This Story)

```yaml
# channel_configs/pokechannel1.yaml
channel_id: pokechannel1
channel_name: "Pokemon Nature Docs"
notion_database_id: "abc123..."
priority: normal
is_active: true

# Voice configuration (FR10)
voice_id: "21m00Tcm4TlvDq8ikWAM"

# Storage configuration (FR12)
storage_strategy: notion

# Capacity configuration (FR13, FR16)
max_concurrent: 2  # Maximum parallel tasks for this channel (1-10)

# Branding configuration (FR11)
branding:
  intro_video: "channel_assets/intro_v2.mp4"
  outro_video: "channel_assets/outro_v2.mp4"
  watermark_image: "channel_assets/watermark.png"

# Budget (optional)
budget_daily_usd: 50.00
```

### References

- [Source: _bmad-output/planning-artifacts/epics.md - Story 1.6 Acceptance Criteria]
- [Source: _bmad-output/planning-artifacts/epics.md - FR13: Multi-channel parallel processing]
- [Source: _bmad-output/planning-artifacts/epics.md - FR16: Channel capacity balancing]
- [Source: _bmad-output/planning-artifacts/architecture.md - Task Lifecycle State Machine]
- [Source: _bmad-output/planning-artifacts/architecture.md - Worker Process Design]
- [Source: _bmad-output/project-context.md - Technology Stack: SQLAlchemy >=2.0.0, Pydantic >=2.8.0]
- [Source: _bmad-output/project-context.md - Database Naming Conventions]
- [Source: app/schemas/channel_config.py - Existing max_concurrent field with validation]
- [Source: app/models.py - Existing Channel model structure]
- [Source: PgQueuer docs - queue_size() method for queue statistics]
- [Source: _bmad-output/implementation-artifacts/1-5-channel-storage-strategy-configuration.md - Previous story patterns]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

- test_task_model.py: 15 tests (11 original + 4 integration tests from code review)
- test_channel_capacity_service.py: 20 tests
- Total Story 1.6 tests: 35
- Full suite: 346 tests pass

### Completion Notes List

- Implemented channel capacity tracking infrastructure (FR13, FR16)
- Added `max_concurrent` column to Channel model with default=2, server_default="2"
- Created Task model with full status lifecycle (pending, claimed, processing, awaiting_review, approved, rejected, completed, failed, retry)
- Created ChannelCapacityService with methods: get_queue_stats(), get_channel_capacity(), has_capacity(), get_channels_with_capacity()
- Used SQLAlchemy 2.0 async patterns with single aggregation query (no N+1)
- Created ChannelQueueStats frozen dataclass for type-safe queue statistics
- Added composite index on (channel_id, status) for efficient queue queries
- Added partial index on status='pending' for fast pending task lookups
- All 346 tests pass (35 new tests for this story + 311 existing)

### Code Review Findings Addressed

**Issue #1/#4 (HIGH/MEDIUM): Missing sync_to_database() integration tests**
- Added TestMaxConcurrentSyncToDatabase class with 4 integration tests
- Tests verify YAML → ChannelConfigSchema → sync_to_database() → Channel round-trip
- Tests cover: default value, custom value, update existing, schema validation range

**Issue #2 (MEDIUM): Test count discrepancy**
- Updated test counts from 335 to 346 (31→35 story tests, 304→311 existing)

**Issue #3 (MEDIUM): Duplicate index definition**
- Added documentation in model explaining migration is source of truth
- Model defines composite index for SQLAlchemy awareness
- Partial index only in migration (documented in model comment)

**Issue #5 (LOW): Missing status validation constraint**
- Added comment documenting valid status values
- Deferred CHECK constraint to Epic 4 (Worker Orchestration state machine)

**Issue #6 (LOW): Partial index not reflected in model**
- Added comment in model referencing idx_tasks_pending in migration

**Issue #7 (LOW): ChannelQueueStats export pattern**
- Documented: Consistent with other dataclasses (exported from services, not app)

### Future Improvements (Deferred)

- Epic 4: Add database-level CHECK constraint for Task.status valid values
- Epic 4: Implement full state machine with transition validation

### Change Log

- 2026-01-11: Implemented Story 1.6 Channel Capacity Tracking (all 7 tasks complete)
- 2026-01-11: Code review fixes - added 4 integration tests for sync_to_database() max_concurrent

### File List

**New Files:**
- app/services/channel_capacity_service.py - ChannelCapacityService and ChannelQueueStats
- alembic/versions/20260111_0001_005_add_max_concurrent_column.py - Migration for max_concurrent
- alembic/versions/20260111_0002_006_add_task_model.py - Migration for Task model
- tests/test_channel_capacity_service.py - 20 tests for ChannelCapacityService
- tests/test_task_model.py - 15 tests for Task model and max_concurrent (11 original + 4 integration tests)

**Modified Files:**
- app/models.py - Added max_concurrent column, Task model, PENDING_STATUSES, IN_PROGRESS_STATUSES constants, documentation comments
- app/services/__init__.py - Exported ChannelCapacityService, ChannelQueueStats
- app/services/channel_config_loader.py - Added max_concurrent sync in sync_to_database()
