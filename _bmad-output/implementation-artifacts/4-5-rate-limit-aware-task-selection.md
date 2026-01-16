# Story 4.5: Rate Limit Aware Task Selection

**Epic:** 4 - Worker Orchestration & Parallel Processing
**Priority:** High (Critical for API Stability & Cost Control)
**Story Points:** 8 (Complex - Multi-API Rate Tracking + Task Claiming Integration)
**Status:** implemented
**Implementation Date:** 2026-01-16

## Story Description

**As a** system developer,
**I want** workers to check API rate limits before claiming tasks,
**So that** tasks aren't claimed only to fail immediately on rate limits (FR42).

## Context & Background

Story 4.5 is the **FIFTH STORY in Epic 4**, building on the round-robin channel scheduling from Story 4.4. It implements intelligent task selection that checks API quota availability BEFORE claiming tasks, preventing workers from claiming tasks that will immediately fail due to rate limit exhaustion.

**Critical Requirements:**

1. **Pre-Claim Quota Checks**: Workers must verify API quota availability before claiming tasks
2. **API-Specific Rate Tracking**: Different rate limits for Gemini, Kling, YouTube, ElevenLabs
3. **Graceful Degradation**: Skip rate-limited tasks, continue processing other work
4. **Multi-Channel Quota Isolation**: YouTube quota tracked per channel
5. **No Task Starvation**: Temporary rate limits don't permanently block tasks
6. **Alert Thresholds**: Warning at 80%, critical at 100% quota

**Why Rate Limit Aware Task Selection is Critical:**

- **API Stability**: Prevents quota exhaustion failures during task execution
- **Cost Control**: Avoids claiming tasks that will burn API quota unnecessarily
- **Operational Efficiency**: Workers skip blocked tasks, process available work instead
- **Multi-Channel Fairness**: Per-channel YouTube quotas prevent one channel from starving others
- **User Experience**: Graceful queue pauses better than cascading failures

**Referenced Architecture:**

- Architecture: Rate Limit Aware Task Selection - Pre-claim quota verification
- Architecture: API Quota Management - YouTube 10K units/day, Notion 3 req/sec
- Architecture: Worker Independence - No inter-worker quota coordination needed
- PRD: FR42 (Rate Limit Aware Task Selection) - Check limits before claiming
- PRD: FR34 (API Quota Monitoring) - Track usage against daily quotas
- Story 4.4: Round-Robin Channel Scheduling - Channel rotation infrastructure
- Story 4.3: Priority Queue Management - Priority ordering foundation
- Story 4.2: Task Claiming with PgQueuer - Atomic claiming pattern

**Key Architectural Pattern:**

```python
# Rate-aware task claiming via query filtering + post-claim validation
async def claim_next_available_task() -> Task | None:
    """
    Claim next task with rate limit awareness.

    Strategy:
    1. Identify task's required API (Gemini/Kling/YouTube/ElevenLabs)
    2. Check if API has available quota
    3. If quota exhausted → skip task (don't claim)
    4. If quota available → claim task atomically
    5. Double-check quota after claim (race condition safety)
    """

    # Step 1: Check which APIs have available quota
    available_apis = await get_available_apis()

    # Step 2: Attempt to claim task (respecting priority → channel → FIFO)
    task = await pgq.claim_next_task()
    if not task:
        return None  # Queue empty

    # Step 3: Determine which API this task needs
    required_api = get_required_api_for_task(task.status)

    # Step 4: Verify API quota available (double-check after claim)
    if required_api not in available_apis:
        # Quota exhausted for this API - release task back to queue
        await release_task(task)
        log.warning("task_released_quota_exhausted", api=required_api)
        return None

    # Step 5: Task claimed and quota available - proceed
    return task
```

**API Rate Limits (From Architecture Analysis):**

| API | Rate Limit | Tracking Method | Check Timing | Reset Behavior |
|-----|-----------|-----------------|--------------|----------------|
| **YouTube** | 10,000 units/day | Database table per channel | Before claiming upload tasks | Midnight PST daily |
| **Gemini** | Unknown (quota-based) | API response detection | On first failure | Midnight reset |
| **Kling** | 2-5 min per clip (concurrency) | In-memory tracking | Before claiming video tasks | N/A (throughput limit) |
| **ElevenLabs** | Character-based pricing | No hard limit | N/A | N/A |
| **Notion** | 3 requests/sec | AsyncLimiter client-side | During sync operations | Rolling window |

**Rate Limit Decision Tree:**

```
Task Ready to Claim?
    |
    ├─> Determine required API (based on task.status)
    |   ├─> "pending" → Gemini (asset generation)
    |   ├─> "composites_ready" → Kling (video generation)
    |   ├─> "video_approved" → ElevenLabs (audio generation)
    |   └─> "final_review" → YouTube (upload)
    |
    ├─> Check API quota availability
    |   ├─> YouTube: Query YouTubeQuotaUsage table for channel
    |   ├─> Gemini: Check if previous task failed with quota error
    |   ├─> Kling: Check concurrent task count < max_concurrent
    |   └─> ElevenLabs: Always available (no quota limit)
    |
    ├─> Quota Available?
    |   ├─> YES → Claim task (FOR UPDATE SKIP LOCKED)
    |   └─> NO → Skip task, log warning, try next task
    |
    └─> After claiming: Double-check quota (race condition safety)
        ├─> Still available? → Process task
        └─> Exhausted? → Release task, try next task
```

**Existing Implementation Analysis:**

- **Story 4.4**: Round-robin query handles channel fairness
- **Story 4.3**: Priority query handles high/normal/low ordering
- **Story 4.2**: PgQueuer atomic claiming via FOR UPDATE SKIP LOCKED
- **Story 1.1**: Database foundation with channel isolation
- **Story 4.5 extends**: Add pre-claim quota checks to task selection logic

**Database Schema Requirements:**

```python
# NEW: YouTube quota tracking (per channel per day)
class YouTubeQuotaUsage(Base):
    __tablename__ = "youtube_quota_usage"

    channel_id = Column(UUID, ForeignKey("channels.id"), primary_key=True)
    date = Column(Date, primary_key=True)
    units_used = Column(Integer, default=0, nullable=False)
    daily_limit = Column(Integer, default=10000, nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint('channel_id', 'date'),
        Index('idx_youtube_quota_date', 'date'),
    )

# EXISTING: Task status indicates which API needed
class Task(Base):
    __tablename__ = "tasks"

    id = Column(UUID, primary_key=True)
    channel_id = Column(UUID, ForeignKey("channels.id"), nullable=False)
    status = Column(task_status_enum, default=TaskStatus.pending, nullable=False)
    # Status → API mapping:
    #   - "pending" → Gemini (asset generation)
    #   - "composites_ready" → Kling (video generation)
    #   - "video_approved" → ElevenLabs (audio generation)
    #   - "final_review" → YouTube (upload)
```

**Deployment Configuration (Railway):**

```yaml
# Existing from Story 4.1-4.4
services:
  web:
    build: {dockerfile: "Dockerfile"}
    start: "uvicorn app.main:app --host 0.0.0.0 --port $PORT"

  worker-1:
    build: {dockerfile: "Dockerfile"}
    start: "python -m app.worker"  # Now with rate-aware claiming

  worker-2:
    build: {dockerfile: "Dockerfile"}
    start: "python -m app.worker"

  worker-3:
    build: {dockerfile: "Dockerfile"}
    start: "python -m app.worker"

  postgres:
    image: "postgres:16"
```

**Derived from Previous Stories:**

- ✅ Story 4.4: Round-robin channel scheduling with channel_id ASC ordering
- ✅ Story 4.3: Priority queue management with CASE priority ordering
- ✅ Story 4.2: PgQueuer atomic claiming with FOR UPDATE SKIP LOCKED
- ✅ Story 4.1: Worker foundation with async patterns
- ✅ Story 1.3: Encrypted credentials storage (YouTube OAuth tokens)
- ✅ Story 1.1: Database foundation with channels table

**Key Technical Decisions:**

1. **Pre-Claim Quota Checks**: Verify quota BEFORE claiming task (not after)
2. **API Detection**: Map task.status → required API (deterministic, no API field needed)
3. **YouTube Per-Channel Tracking**: One quota row per channel per day (composite PK)
4. **Gemini Quota Detection**: Flag in worker state (not database) - resets on restart
5. **Kling Concurrency Limiting**: In-memory counter per worker (stateless)
6. **Alert Thresholds**: 80% warning, 100% critical (Discord webhook)
7. **No Task Modification**: Rate-limited tasks remain in queue unchanged (retry later)

## Acceptance Criteria

### Scenario 1: YouTube Quota Pre-Check Prevents Upload Claim

**Given** Channel poke1 has used 9,500 units of 10,000 daily YouTube quota
**And** An upload task for poke1 exists (costs 1,600 units)
**And** The total would exceed quota: 9,500 + 1,600 = 11,100 > 10,000

**When** Worker attempts to claim next task
**Then** Worker queries YouTubeQuotaUsage table for poke1 + today's date
**And** Worker calculates: current_usage (9,500) + upload_cost (1,600) > limit (10,000)
**And** Worker skips the upload task (does not claim)
**And** Worker logs: "youtube_quota_insufficient" with channel_id, current_usage, operation_cost

**And** Worker continues to next task (non-upload task for different channel)
**And** Upload task remains in "final_review" status (not claimed, not failed)

### Scenario 2: Gemini Quota Exhaustion Flag Prevents Asset Tasks

**Given** Gemini API returned quota exhaustion error on previous asset generation
**And** Worker set in-memory flag: `gemini_quota_exhausted = True`
**And** Multiple asset generation tasks exist in "pending" status

**When** Worker attempts to claim next task
**Then** Worker checks task status → "pending" → requires Gemini API
**And** Worker checks in-memory flag: `gemini_quota_exhausted == True`
**And** Worker skips all "pending" tasks (does not claim)
**And** Worker logs: "gemini_quota_exhausted_skipping_asset_tasks"

**And** Worker continues to next task (video/audio/upload task not requiring Gemini)
**And** Asset tasks remain in "pending" status (retry after midnight reset)

### Scenario 3: Multi-Channel YouTube Quota Isolation

**Given** Channel poke1 has exhausted YouTube quota (10,000/10,000 used)
**And** Channel poke2 has available YouTube quota (3,000/10,000 used)
**And** Upload tasks exist for both channels

**When** Worker attempts to claim upload task
**Then** Worker queries YouTubeQuotaUsage for each channel separately
**And** poke1 quota check fails: 10,000 + 1,600 > 10,000 (skip)
**And** poke2 quota check succeeds: 3,000 + 1,600 < 10,000 (claim)

**And** Worker claims poke2 upload task successfully
**And** poke1 upload task remains in queue (not claimed, not failed)
**And** No cross-channel quota bleeding or interference

### Scenario 4: Quota Warning Alert at 80% Threshold

**Given** Channel poke1 has used 8,000 units of 10,000 YouTube quota
**And** An upload task completes, recording 1,600 units
**And** Total usage becomes: 8,000 + 1,600 = 9,600 (96% of quota)

**When** Quota usage is recorded in database
**Then** System calculates percentage: 9,600 / 10,000 = 96%
**And** Threshold check: 96% > 80% (warning threshold)
**And** Discord webhook triggered with WARNING level alert
**And** Alert message includes:
  - Channel: poke1
  - Current usage: 9,600 units
  - Daily limit: 10,000 units
  - Percentage: 96%
  - Remaining capacity: 400 units (~0 uploads remaining)

### Scenario 5: Quota Critical Alert at 100% Threshold

**Given** Channel poke1 has used 9,800 units of 10,000 YouTube quota
**And** An upload task completes, recording 1,600 units
**And** Total usage becomes: 9,800 + 1,600 = 11,400 (114% of quota - overage)

**When** Quota usage is recorded
**Then** System calculates percentage: 11,400 / 10,000 = 114%
**And** Threshold check: 114% >= 100% (critical threshold)
**And** Discord webhook triggered with CRITICAL level alert
**And** Alert message includes:
  - Channel: poke1
  - Current usage: 11,400 units
  - Daily limit: 10,000 units
  - Percentage: 114%
  - Overage: 1,400 units
  - Action: All upload tasks for poke1 paused until midnight PST reset

**And** All future upload tasks for poke1 skipped until quota resets
**And** Other channels continue processing normally

### Scenario 6: Kling Concurrency Limiting (In-Memory Tracking)

**Given** Worker configuration: `max_concurrent_video_generation = 3`
**And** Worker has 3 video generation tasks currently processing
**And** In-memory counter: `active_video_tasks = 3`
**And** Additional video generation tasks exist in queue

**When** Worker attempts to claim next task
**Then** Worker checks task status → "composites_ready" → requires Kling API
**And** Worker checks in-memory counter: `active_video_tasks (3) >= max_concurrent (3)`
**And** Worker skips video generation tasks (does not claim)
**And** Worker logs: "kling_concurrency_limit_reached" with count: 3

**And** Worker continues to next task (asset/audio/upload task not requiring Kling)
**And** Video tasks remain in queue (retry when slot available)

**When** One video generation task completes
**Then** In-memory counter decrements: `active_video_tasks = 2`
**And** Next video generation task can be claimed

### Scenario 7: API Detection from Task Status (Deterministic Mapping)

**Given** Tasks exist with various statuses:
  - Task A: status = "pending" (requires Gemini for assets)
  - Task B: status = "composites_ready" (requires Kling for video)
  - Task C: status = "video_approved" (requires ElevenLabs for audio)
  - Task D: status = "final_review" (requires YouTube for upload)

**When** Worker inspects each task to determine required API
**Then** API detection logic maps:
  - "pending" → Gemini
  - "composites_ready" → Kling
  - "video_approved" → ElevenLabs
  - "final_review" → YouTube

**And** No additional "required_api" column needed (derived from status)
**And** Mapping is deterministic and documented in code

### Scenario 8: Double-Check Quota After Claim (Race Condition Safety)

**Given** Two workers (worker-1 and worker-2) attempt to claim tasks simultaneously
**And** Channel poke1 has 200 units remaining in YouTube quota
**And** Upload task exists for poke1 (costs 1,600 units)

**When** Worker-1 checks quota: 200 units available → passes pre-check
**And** Worker-2 checks quota: 200 units available → passes pre-check
**And** Worker-1 claims task atomically (FOR UPDATE SKIP LOCKED)
**And** Worker-2 fails to claim (task already locked)

**Then** Worker-1 performs post-claim double-check:
  - Quota still available? NO (would exceed)
  - Action: Release task back to queue
  - Log: "task_released_quota_race_condition"

**And** Task remains in queue (not failed, not marked error)
**And** No quota units consumed (task never processed)
**And** Task retries after quota resets (midnight PST)

### Scenario 9: Graceful Degradation - Skip Blocked Work, Process Available

**Given** Gemini quota exhausted (in-memory flag set)
**And** Channel poke1 YouTube quota exhausted
**And** Tasks exist:
  - 5 asset generation tasks (require Gemini - BLOCKED)
  - 2 upload tasks for poke1 (require YouTube for poke1 - BLOCKED)
  - 3 audio generation tasks (require ElevenLabs - AVAILABLE)
  - 2 upload tasks for poke2 (require YouTube for poke2 - AVAILABLE)

**When** Worker polls for next task
**Then** Worker skips:
  - 5 Gemini tasks (quota exhausted)
  - 2 poke1 upload tasks (quota exhausted)

**And** Worker claims and processes:
  - 3 audio generation tasks (ElevenLabs available)
  - 2 poke2 upload tasks (poke2 quota available)

**And** Worker continues productive work despite partial API outages
**And** No tasks fail or transition to error state
**And** Blocked tasks automatically retry when quotas reset

### Scenario 10: Structured Logging with Quota Context

**Given** Worker checks YouTube quota for channel poke1
**And** Quota check fails: 9,500 + 1,600 > 10,000

**When** Worker logs the quota check failure
**Then** Structured log entry includes:
  - `event`: "youtube_quota_check_failed"
  - `worker_id`: "worker-1"
  - `channel_id`: "poke1"
  - `current_usage`: 9500
  - `operation_cost`: 1600
  - `daily_limit`: 10000
  - `required_total`: 11100
  - `overage`: 1100
  - `action`: "skipping_upload_task"

**And** Logs enable filtering by channel for quota debugging
**And** Logs enable alerting on quota exhaustion patterns

## Dev Agent Guardrails - CRITICAL REQUIREMENTS

### 🔥 Rate Limit Implementation (MANDATORY)

**1. YouTube Quota Tracking Database Schema:**

```python
# ✅ CORRECT: Composite primary key (channel_id, date)
class YouTubeQuotaUsage(Base):
    __tablename__ = "youtube_quota_usage"

    channel_id = Column(UUID(as_uuid=True), ForeignKey("channels.id"), primary_key=True)
    date = Column(Date, primary_key=True, nullable=False)
    units_used = Column(Integer, default=0, nullable=False)
    daily_limit = Column(Integer, default=10000, nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint('channel_id', 'date', name='pk_youtube_quota'),
        Index('idx_youtube_quota_date', 'date'),  # Cleanup queries
        CheckConstraint('units_used >= 0', name='ck_youtube_quota_non_negative'),
        CheckConstraint('daily_limit > 0', name='ck_youtube_quota_limit_positive'),
    )

# ❌ WRONG: Single primary key (can't track per channel)
channel_id = Column(UUID, nullable=False)  # Not part of PK
date = Column(Date, primary_key=True)  # Only date as PK - WRONG!

# ❌ WRONG: Separate id column (composite PK is natural)
id = Column(UUID, primary_key=True)  # Unnecessary surrogate key
```

**2. Quota Check Function (Pre-Claim Verification):**

```python
# ✅ CORRECT: Pre-claim quota check with operation cost calculation
async def check_youtube_quota(
    channel_id: UUID,
    operation: str,
    db: AsyncSession
) -> bool:
    """
    Check if YouTube quota available for operation.

    Args:
        channel_id: Channel UUID
        operation: Operation type ("upload", "update", "list", "search")
        db: Database session

    Returns:
        True if quota available, False if exhausted
    """
    from datetime import date

    # Operation costs (YouTube Data API v3 pricing)
    OPERATION_COSTS = {
        "upload": 1600,
        "update": 50,
        "list": 1,
        "search": 100,
    }

    cost = OPERATION_COSTS.get(operation, 0)
    today = date.today()

    # Get or create quota record for today
    stmt = select(YouTubeQuotaUsage).where(
        YouTubeQuotaUsage.channel_id == channel_id,
        YouTubeQuotaUsage.date == today
    )
    result = await db.execute(stmt)
    quota = result.scalar_one_or_none()

    if not quota:
        # First operation today - quota available
        return True

    # Check if operation would exceed quota
    return (quota.units_used + cost) <= quota.daily_limit

# ❌ WRONG: Check quota AFTER claiming task
# ❌ WRONG: Don't include operation cost in calculation
# ❌ WRONG: Check global quota instead of per-channel quota
```

**3. Rate-Aware Task Claiming Logic:**

```python
# ✅ CORRECT: Pre-check quota before claiming task
@pgq.entrypoint("process_video")
async def process_video(job: Job) -> None:
    """Process video with rate limit awareness"""
    task_id = job.payload.decode()

    # Step 1: Get task details (short query)
    async with AsyncSessionLocal() as db:
        task = await db.get(Task, task_id)

        # Determine required API from task status
        required_api = get_required_api(task.status)

        # Check quota for required API
        if required_api == "youtube":
            quota_available = await check_youtube_quota(
                channel_id=task.channel_id,
                operation="upload",
                db=db
            )

            if not quota_available:
                # Quota exhausted - release task, don't process
                log.warning(
                    "task_skipped_youtube_quota_exhausted",
                    task_id=task_id,
                    channel_id=str(task.channel_id),
                )
                # Task remains in queue - retry after midnight reset
                raise SkipTaskError("YouTube quota exhausted")

        # Similar checks for Gemini, Kling, ElevenLabs...

        # Quota available - mark as processing
        task.status = "processing"
        await db.commit()

    # Step 2: Execute work (OUTSIDE transaction)
    # ... process task ...

# ❌ WRONG: Check quota AFTER marking task as processing
# ❌ WRONG: Fail task permanently on quota exhaustion
# ❌ WRONG: Don't differentiate between APIs
```

**4. API Detection from Task Status:**

```python
# ✅ CORRECT: Deterministic mapping from status to required API
def get_required_api(status: str) -> str | None:
    """
    Determine which API is required for task at given status.

    Args:
        status: Task status from TaskStatus enum

    Returns:
        API name: "gemini", "kling", "elevenlabs", "youtube", or None
    """
    API_MAPPING = {
        "pending": "gemini",              # Asset generation
        "assets_approved": "none",        # Internal (composite creation)
        "composites_ready": "kling",      # Video generation
        "video_approved": "elevenlabs",   # Audio generation
        "audio_approved": "none",         # Internal (FFmpeg assembly)
        "final_review": "youtube",        # Upload
    }

    return API_MAPPING.get(status, None)

# ❌ WRONG: Add "required_api" column to Task model (redundant)
# ❌ WRONG: Use string matching on status (fragile)
# ❌ WRONG: Hardcode API checks in business logic (not reusable)
```

### 🧠 Architecture Compliance (MANDATORY)

**1. YouTube Quota Recording After Success:**

```python
# ✅ CORRECT: Record quota usage AFTER successful operation
async def record_youtube_quota(
    channel_id: UUID,
    operation: str,
    db: AsyncSession
) -> None:
    """Record YouTube quota usage after successful operation"""
    from datetime import date

    OPERATION_COSTS = {
        "upload": 1600,
        "update": 50,
        "list": 1,
        "search": 100,
    }

    cost = OPERATION_COSTS.get(operation, 0)
    today = date.today()

    # Get or create quota record
    stmt = select(YouTubeQuotaUsage).where(
        YouTubeQuotaUsage.channel_id == channel_id,
        YouTubeQuotaUsage.date == today
    )
    result = await db.execute(stmt)
    quota = result.scalar_one_or_none()

    if not quota:
        quota = YouTubeQuotaUsage(
            channel_id=channel_id,
            date=today,
            units_used=cost,
            daily_limit=10000
        )
        db.add(quota)
    else:
        quota.units_used += cost

    await db.commit()

    # Check alert thresholds
    percentage = (quota.units_used / quota.daily_limit) * 100

    if percentage >= 100:
        await send_alert(
            level="CRITICAL",
            message=f"YouTube quota exhausted for channel {channel_id}",
            details={"usage": quota.units_used, "limit": quota.daily_limit}
        )
    elif percentage >= 80:
        await send_alert(
            level="WARNING",
            message=f"YouTube quota at {percentage:.0f}% for channel {channel_id}",
            details={"usage": quota.units_used, "limit": quota.daily_limit}
        )

# ❌ WRONG: Record quota BEFORE operation (operation might fail)
# ❌ WRONG: Don't check alert thresholds
# ❌ WRONG: Use single global quota counter (not per-channel)
```

**2. Gemini Quota State Management (In-Memory):**

```python
# ✅ CORRECT: Worker-local in-memory flag (resets on restart)
class WorkerState:
    """Worker-local state (not shared between workers)"""

    def __init__(self):
        self.gemini_quota_exhausted: bool = False
        self.gemini_quota_reset_time: datetime | None = None

    def mark_gemini_quota_exhausted(self):
        """Mark Gemini quota as exhausted (resets at midnight)"""
        from datetime import datetime, timedelta

        self.gemini_quota_exhausted = True
        # Assume midnight PST reset (adjust for timezone)
        tomorrow = datetime.now().date() + timedelta(days=1)
        self.gemini_quota_reset_time = datetime.combine(tomorrow, datetime.min.time())

    def check_gemini_quota_available(self) -> bool:
        """Check if Gemini quota has reset"""
        from datetime import datetime

        if not self.gemini_quota_exhausted:
            return True

        # Check if past reset time
        if datetime.now() >= self.gemini_quota_reset_time:
            self.gemini_quota_exhausted = False
            return True

        return False

# ❌ WRONG: Store Gemini quota flag in database (shared state)
# ❌ WRONG: Never reset flag automatically (manual intervention required)
# ❌ WRONG: Share flag between workers (creates coordination complexity)
```

**3. Kling Concurrency Limiting (In-Memory Counter):**

```python
# ✅ CORRECT: Worker-local concurrency counter
class WorkerState:
    """Worker-local state"""

    def __init__(self):
        self.active_video_tasks: int = 0
        self.max_concurrent_video: int = 3  # Configurable

    def can_claim_video_task(self) -> bool:
        """Check if worker can claim another video generation task"""
        return self.active_video_tasks < self.max_concurrent_video

    def increment_video_tasks(self):
        """Increment active video task counter"""
        self.active_video_tasks += 1

    def decrement_video_tasks(self):
        """Decrement active video task counter"""
        self.active_video_tasks = max(0, self.active_video_tasks - 1)

# Usage in worker:
worker_state = WorkerState()

@pgq.entrypoint("process_video")
async def process_video(job: Job) -> None:
    task_id = job.payload.decode()

    async with AsyncSessionLocal() as db:
        task = await db.get(Task, task_id)

        # Check if task requires Kling API
        if get_required_api(task.status) == "kling":
            if not worker_state.can_claim_video_task():
                log.warning("kling_concurrency_limit_reached", count=worker_state.active_video_tasks)
                raise SkipTaskError("Kling concurrency limit reached")

            worker_state.increment_video_tasks()

        task.status = "processing"
        await db.commit()

    try:
        # Process video...
        pass
    finally:
        # Always decrement counter
        if get_required_api(task.status) == "kling":
            worker_state.decrement_video_tasks()

# ❌ WRONG: Track concurrency in database (adds contention)
# ❌ WRONG: Global concurrency limit across all workers (too restrictive)
# ❌ WRONG: Don't decrement counter on failure (leak)
```

### 📚 Library & Framework Requirements

**Required Libraries (all existing):**

- **PgQueuer ≥0.10.0**: Already installed, extends custom query with quota checks
- **asyncpg ≥0.29.0**: Already installed for async database operations
- **SQLAlchemy ≥2.0.0**: Already installed for ORM
- **httpx ≥0.25.0**: Already installed for Discord webhook alerts
- **structlog ≥23.2.0**: Already installed for structured logging

**DO NOT Install:**
- ❌ No new libraries needed (rate limiting uses existing stack)

**Database Changes:**

- **NEW**: YouTubeQuotaUsage table with composite PK (channel_id, date)
- **NEW**: Alert threshold constants (80% warning, 100% critical)
- **EXISTING**: Task model with status enum (maps to required API)
- **EXISTING**: Channels table with channel_id for quota isolation

### 🗂️ File Structure Requirements

**MUST Create:**
- `app/models.py` - Add YouTubeQuotaUsage model (~30 lines)
- `app/services/quota_manager.py` - NEW file for quota operations (~200 lines)
- `app/utils/alerts.py` - NEW file for Discord webhook alerts (~80 lines)
- `alembic/versions/XXXXXX_add_youtube_quota_table.py` - NEW migration (~120 lines)
- `tests/test_services/test_quota_manager.py` - NEW tests (~250 lines)
- `tests/test_utils/test_alerts.py` - NEW tests (~100 lines)

**MUST Modify:**
- `app/worker.py` - Add WorkerState class, integrate quota checks (~50 lines added)
- `app/entrypoints.py` - Add quota checks before task processing (~40 lines added)
- `tests/test_worker.py` - Add quota check test cases (~150 lines added)
- `tests/test_entrypoints.py` - Add quota awareness tests (~120 lines added)
- `README.md` - Add Rate Limit Aware Task Selection section (~150 lines)

**MUST NOT Modify:**
- Any files in `scripts/` directory (CLI scripts remain unchanged)
- `app/queue.py` (round-robin query stays same, quota checks in worker)
- `app/models.py` Task model (status enum unchanged, no new columns)

**Expected Changes Summary:**
- 4 new files created (~630 lines)
- 5 files modified (~510 lines added)
- Total: ~1,140 lines added (implementation + tests + migration + docs)

### 🧪 Testing Requirements

**Minimum Test Coverage:**
- ✅ YouTube quota checks: 5+ test cases (available, exhausted, per-channel, alert thresholds)
- ✅ Gemini quota detection: 3+ test cases (exhausted flag, reset behavior, task skipping)
- ✅ Kling concurrency limiting: 3+ test cases (limit reached, counter decrement, multiple workers)
- ✅ API detection: 4+ test cases (status → API mapping for all pipeline stages)
- ✅ Alert triggering: 3+ test cases (80% warning, 100% critical, Discord webhook)
- ✅ Race condition safety: 2+ test cases (double-check after claim, task release)
- ✅ Graceful degradation: 2+ test cases (skip blocked work, process available)

**Test Pattern Example:**

```python
import pytest
from datetime import date
from app.models import YouTubeQuotaUsage
from app.services.quota_manager import check_youtube_quota, record_youtube_quota
from uuid import UUID

@pytest.mark.asyncio
async def test_youtube_quota_check_available():
    """Test YouTube quota check when quota is available"""
    channel_id = UUID("00000000-0000-4000-8000-000000000001")

    # Arrange: Channel has 5,000 units used
    async with AsyncSessionLocal() as db:
        quota = YouTubeQuotaUsage(
            channel_id=channel_id,
            date=date.today(),
            units_used=5000,
            daily_limit=10000
        )
        db.add(quota)
        await db.commit()

    # Act: Check if upload (1,600 units) is possible
    async with AsyncSessionLocal() as db:
        available = await check_youtube_quota(channel_id, "upload", db)

    # Assert: Quota available (5,000 + 1,600 = 6,600 < 10,000)
    assert available is True

@pytest.mark.asyncio
async def test_youtube_quota_check_exhausted():
    """Test YouTube quota check when quota is exhausted"""
    channel_id = UUID("00000000-0000-4000-8000-000000000001")

    # Arrange: Channel has 9,500 units used
    async with AsyncSessionLocal() as db:
        quota = YouTubeQuotaUsage(
            channel_id=channel_id,
            date=date.today(),
            units_used=9500,
            daily_limit=10000
        )
        db.add(quota)
        await db.commit()

    # Act: Check if upload (1,600 units) is possible
    async with AsyncSessionLocal() as db:
        available = await check_youtube_quota(channel_id, "upload", db)

    # Assert: Quota exhausted (9,500 + 1,600 = 11,100 > 10,000)
    assert available is False

@pytest.mark.asyncio
async def test_youtube_quota_per_channel_isolation():
    """Test YouTube quota isolation between channels"""
    channel_a = UUID("00000000-0000-4000-8000-000000000001")
    channel_b = UUID("00000000-0000-4000-8000-000000000002")

    # Arrange: Channel A exhausted, Channel B available
    async with AsyncSessionLocal() as db:
        db.add(YouTubeQuotaUsage(
            channel_id=channel_a,
            date=date.today(),
            units_used=10000,
            daily_limit=10000
        ))
        db.add(YouTubeQuotaUsage(
            channel_id=channel_b,
            date=date.today(),
            units_used=3000,
            daily_limit=10000
        ))
        await db.commit()

    # Act: Check quota for both channels
    async with AsyncSessionLocal() as db:
        available_a = await check_youtube_quota(channel_a, "upload", db)
        available_b = await check_youtube_quota(channel_b, "upload", db)

    # Assert: A exhausted, B available
    assert available_a is False
    assert available_b is True

@pytest.mark.asyncio
async def test_youtube_quota_alert_at_80_percent(mock_send_alert):
    """Test WARNING alert triggered at 80% quota"""
    channel_id = UUID("00000000-0000-4000-8000-000000000001")

    # Arrange: Channel at 70% usage
    async with AsyncSessionLocal() as db:
        quota = YouTubeQuotaUsage(
            channel_id=channel_id,
            date=date.today(),
            units_used=7000,
            daily_limit=10000
        )
        db.add(quota)
        await db.commit()

    # Act: Record upload (1,600 units) → 8,600 / 10,000 = 86%
    async with AsyncSessionLocal() as db:
        await record_youtube_quota(channel_id, "upload", db)

    # Assert: WARNING alert triggered
    mock_send_alert.assert_called_once()
    call_args = mock_send_alert.call_args
    assert call_args[1]["level"] == "WARNING"
    assert "86%" in call_args[1]["message"]

@pytest.mark.asyncio
async def test_gemini_quota_exhausted_flag():
    """Test Gemini quota exhausted flag behavior"""
    from app.worker import WorkerState

    # Arrange: Worker state
    state = WorkerState()
    assert state.check_gemini_quota_available() is True

    # Act: Mark Gemini quota as exhausted
    state.mark_gemini_quota_exhausted()

    # Assert: Quota now unavailable
    assert state.check_gemini_quota_available() is False
    assert state.gemini_quota_exhausted is True

@pytest.mark.asyncio
async def test_kling_concurrency_limit():
    """Test Kling concurrency limiting"""
    from app.worker import WorkerState

    # Arrange: Worker with max 3 concurrent video tasks
    state = WorkerState()
    state.max_concurrent_video = 3

    # Act: Claim 3 tasks
    assert state.can_claim_video_task() is True
    state.increment_video_tasks()  # 1

    assert state.can_claim_video_task() is True
    state.increment_video_tasks()  # 2

    assert state.can_claim_video_task() is True
    state.increment_video_tasks()  # 3

    # Assert: 4th task blocked
    assert state.can_claim_video_task() is False

    # Act: Complete 1 task
    state.decrement_video_tasks()  # 2

    # Assert: Can claim again
    assert state.can_claim_video_task() is True
```

### 🔒 Security Requirements

**1. Discord Webhook Security:**

```python
# ✅ CORRECT: Validate webhook URL, sanitize message content
async def send_alert(
    level: str,
    message: str,
    details: dict | None = None
) -> None:
    """Send alert to Discord webhook (sanitized input)"""
    import httpx
    import os

    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        log.warning("discord_webhook_not_configured")
        return

    # Sanitize message (prevent injection)
    sanitized_message = message[:2000]  # Discord 2000 char limit

    payload = {
        "content": f"**{level}**: {sanitized_message}",
        "embeds": [
            {
                "title": f"{level} Alert",
                "description": sanitized_message,
                "fields": [
                    {"name": key, "value": str(value), "inline": True}
                    for key, value in (details or {}).items()
                ],
                "color": {
                    "CRITICAL": 0xFF0000,  # Red
                    "WARNING": 0xFFA500,   # Orange
                    "INFO": 0x0000FF       # Blue
                }.get(level, 0x808080)  # Default gray
            }
        ]
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(webhook_url, json=payload, timeout=5.0)
            response.raise_for_status()
        except Exception as e:
            log.error("discord_webhook_failed", error=str(e))

# ❌ WRONG: Include sensitive data in alert messages (API keys, tokens)
# ❌ WRONG: Don't sanitize user input (XSS vulnerability)
# ❌ WRONG: Expose webhook URL in logs
```

**2. Quota Table Integrity Constraints:**

```python
# ✅ CORRECT: Check constraints prevent invalid data
__table_args__ = (
    CheckConstraint('units_used >= 0', name='ck_youtube_quota_non_negative'),
    CheckConstraint('daily_limit > 0', name='ck_youtube_quota_limit_positive'),
    CheckConstraint('units_used <= daily_limit * 1.5', name='ck_youtube_quota_reasonable_overage'),
)

# Rationale: Prevent negative usage, zero limits, unreasonable overage (>150%)
```

## Previous Story Intelligence

**From Story 4.4 (Round-Robin Channel Scheduling):**

Story 4.4 established fair channel distribution that Story 4.5 preserves:

**Key Implementations:**
- ✅ `app/queue.py` - PgQueuer with ROUND_ROBIN_QUERY (priority → channel → FIFO)
- ✅ Extended composite index: `idx_tasks_status_priority_channel_created`
- ✅ Dynamic query pattern extraction for logging
- ✅ Channel rotation via `channel_id ASC` ordering
- ✅ Structured logging with channel_id context

**Patterns Established:**
- ✅ **SQL Query Extension**: Extend PgQueuer query without breaking existing logic
- ✅ **Composite Index Coverage**: Match ORDER BY columns for performance
- ✅ **Dynamic Pattern Detection**: Extract ordering pattern from SQL for logging
- ✅ **Worker Independence**: No inter-worker coordination or shared state
- ✅ **Migration Safety**: `postgresql_concurrently=True` for zero-downtime

**Files Modified:**
- `app/queue.py` (~195 lines) - Round-robin query with channel ordering
- `app/entrypoints.py` (~181 lines) - Channel_id logging (inherited from 4.3)
- `tests/test_queue.py` (~377 lines) - 11 round-robin tests added
- `alembic/versions/20260116_0004_add_round_robin_index.py` (~106 lines)

**Implementation Learnings:**
1. **Query Extension Pattern**: Add columns to ORDER BY without breaking priority/FIFO
2. **Index Composition**: Extend existing index by appending new columns
3. **Logging Consistency**: Include channel_id in all task-related logs
4. **Race-Free Claiming**: FOR UPDATE SKIP LOCKED prevents duplicate claims
5. **Zero-Downtime Migrations**: Always use `postgresql_concurrently=True`

**Code Review Insights (from Story 4.4):**
- ✅ Unit tests validate SQL structure, behavioral tests deferred to integration
- ✅ Index verification required post-deployment (SQL commands in README)
- ✅ Comprehensive failure modes documentation
- ⏳ Integration tests deferred to E2E/QA phase (requires PostgreSQL runtime)

**Critical Constraints from Story 4.4:**
- **Query Preservation**: Story 4.5 MUST NOT modify ROUND_ROBIN_QUERY (quota checks in worker, not query)
- **Channel Isolation**: Quota tracking respects channel_id for multi-channel fairness
- **Logging Consistency**: Maintain structured logging patterns with channel context
- **Worker Independence**: Quota state remains worker-local (no cross-worker coordination)

## Latest Technical Specifications

### YouTube Quota Management (Research 2026-01)

**YouTube Data API v3 Quota Costs:**

| Operation | Quota Cost | Frequency | Impact |
|-----------|-----------|-----------|--------|
| **Upload Video** | 1,600 units | Per video | 6 uploads max/day (default quota) |
| **Update Video** | 50 units | Per update | 200 updates max/day |
| **List Videos** | 1 unit | Per query | 10,000 queries max/day |
| **Search** | 100 units | Per search | 100 searches max/day |

**Default Quota:** 10,000 units/day per project (can be increased via Google Cloud Console)

**Quota Reset:** Midnight Pacific Time (PST/PDT) daily

**Rate Limit Aware Query Strategy:**

```python
# Strategy: Don't modify PgQueuer query, filter in worker after claim attempt

# EXISTING (Story 4.4): Round-robin query unchanged
ROUND_ROBIN_QUERY = """
    SELECT * FROM tasks
    WHERE status = 'pending'
    ORDER BY
        CASE priority
            WHEN 'high' THEN 1
            WHEN 'normal' THEN 2
            WHEN 'low' THEN 3
        END ASC,
        channel_id ASC,
        created_at ASC
    FOR UPDATE SKIP LOCKED
    LIMIT 1
"""

# NEW (Story 4.5): Rate limit checks in worker BEFORE processing
async def claim_next_available_task(pgq: PgQueuer) -> Task | None:
    """
    Claim next task with rate limit awareness.

    Strategy:
    1. Claim task atomically (preserves round-robin + priority)
    2. Check if required API has available quota
    3. If quota exhausted → skip task (don't process)
    4. If quota available → process task

    This approach keeps query simple while adding rate awareness.
    """
    # Claim task (preserves priority → channel → FIFO)
    job = await pgq.claim_next_job()
    if not job:
        return None  # Queue empty

    # Get task details
    task_id = job.payload.decode()
    async with AsyncSessionLocal() as db:
        task = await db.get(Task, task_id)

        # Check quota for required API
        required_api = get_required_api(task.status)

        if required_api == "youtube":
            quota_available = await check_youtube_quota(
                task.channel_id, "upload", db
            )
            if not quota_available:
                # Skip task, continue to next
                raise SkipTaskError("YouTube quota exhausted")

        # Similar checks for other APIs...

        return task
```

**Alert Threshold Configuration:**

```python
# Quota alert thresholds
YOUTUBE_QUOTA_WARNING_THRESHOLD = 0.80  # 80% usage
YOUTUBE_QUOTA_CRITICAL_THRESHOLD = 1.00  # 100% usage

# Alert throttling (prevent spam)
MIN_ALERT_INTERVAL_SECONDS = 300  # 5 minutes between alerts per channel
```

### File Structure

```
app/
├── models.py                      # MODIFY - Add YouTubeQuotaUsage model
├── worker.py                      # MODIFY - Add WorkerState, quota checks
├── entrypoints.py                 # MODIFY - Add rate-aware task claiming
├── services/
│   └── quota_manager.py           # NEW - Quota check/record functions
└── utils/
    └── alerts.py                  # NEW - Discord webhook alerts

alembic/versions/
└── XXXXXX_add_youtube_quota_table.py   # NEW - YouTubeQuotaUsage migration

tests/
├── test_services/
│   └── test_quota_manager.py      # NEW - Quota management tests
├── test_utils/
│   └── test_alerts.py             # NEW - Alert system tests
├── test_worker.py                 # MODIFY - Add quota check tests
└── test_entrypoints.py            # MODIFY - Add rate awareness tests

README.md                          # MODIFY - Add rate limiting section
```

## Technical Specifications

### Core Implementation: `app/services/quota_manager.py` (NEW)

**Purpose:** Centralized quota checking and recording for all external APIs.

```python
"""
YouTube API quota management with per-channel tracking.

Implements pre-claim quota verification to prevent tasks from being claimed
when API quota is exhausted. Supports 80% warning and 100% critical alerting.

Architecture Pattern:
    - Pre-claim verification: Check quota BEFORE claiming task
    - Per-channel isolation: One quota row per channel per day
    - Alert thresholds: 80% warning, 100% critical
    - Daily reset: Midnight PST (YouTube API behavior)

References:
    - Architecture: API Quota Management
    - Story 4.5: Rate Limit Aware Task Selection
    - PRD: FR42 (Rate limit aware task selection)
    - PRD: FR34 (API quota monitoring)
"""

from datetime import date
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import YouTubeQuotaUsage
from app.utils.logging import get_logger
from app.utils.alerts import send_alert

log = get_logger(__name__)

# YouTube Data API v3 operation costs
YOUTUBE_OPERATION_COSTS = {
    "upload": 1600,
    "update": 50,
    "list": 1,
    "search": 100,
}

# Alert thresholds
YOUTUBE_QUOTA_WARNING_THRESHOLD = 0.80  # 80%
YOUTUBE_QUOTA_CRITICAL_THRESHOLD = 1.00  # 100%


async def check_youtube_quota(
    channel_id: UUID,
    operation: str,
    db: AsyncSession
) -> bool:
    """
    Check if YouTube quota available for operation.

    Queries YouTubeQuotaUsage table to verify if performing the given
    operation would exceed the channel's daily quota limit.

    Args:
        channel_id: Channel UUID
        operation: Operation type ("upload", "update", "list", "search")
        db: Database session

    Returns:
        True if quota available, False if exhausted

    Example:
        >>> available = await check_youtube_quota(channel_id, "upload", db)
        >>> if available:
        ...     # Safe to proceed with upload
        >>> else:
        ...     # Skip task, quota exhausted
    """
    cost = YOUTUBE_OPERATION_COSTS.get(operation, 0)
    today = date.today()

    # Get quota record for today
    stmt = select(YouTubeQuotaUsage).where(
        YouTubeQuotaUsage.channel_id == channel_id,
        YouTubeQuotaUsage.date == today
    )
    result = await db.execute(stmt)
    quota = result.scalar_one_or_none()

    if not quota:
        # First operation today - quota available
        log.debug(
            "youtube_quota_check_first_today",
            channel_id=str(channel_id),
            operation=operation,
            cost=cost
        )
        return True

    # Check if operation would exceed quota
    available = (quota.units_used + cost) <= quota.daily_limit

    log.info(
        "youtube_quota_check",
        channel_id=str(channel_id),
        operation=operation,
        cost=cost,
        current_usage=quota.units_used,
        daily_limit=quota.daily_limit,
        available=available,
        would_total=quota.units_used + cost
    )

    return available


async def record_youtube_quota(
    channel_id: UUID,
    operation: str,
    db: AsyncSession
) -> None:
    """
    Record YouTube quota usage after successful operation.

    CRITICAL: Only call this AFTER operation succeeds. If operation fails,
    do NOT record quota usage.

    Triggers alerts at 80% (warning) and 100% (critical) thresholds.

    Args:
        channel_id: Channel UUID
        operation: Operation type ("upload", "update", "list", "search")
        db: Database session

    Raises:
        ValueError: If operation type invalid

    Example:
        >>> # After successful YouTube upload
        >>> await record_youtube_quota(channel_id, "upload", db)
    """
    cost = YOUTUBE_OPERATION_COSTS.get(operation)
    if cost is None:
        raise ValueError(f"Invalid YouTube operation: {operation}")

    today = date.today()

    # Get or create quota record
    stmt = select(YouTubeQuotaUsage).where(
        YouTubeQuotaUsage.channel_id == channel_id,
        YouTubeQuotaUsage.date == today
    ).with_for_update()  # Lock for atomic update

    result = await db.execute(stmt)
    quota = result.scalar_one_or_none()

    if not quota:
        quota = YouTubeQuotaUsage(
            channel_id=channel_id,
            date=today,
            units_used=cost,
            daily_limit=10000
        )
        db.add(quota)
    else:
        quota.units_used += cost

    await db.commit()

    # Check alert thresholds
    percentage = (quota.units_used / quota.daily_limit)

    log.info(
        "youtube_quota_recorded",
        channel_id=str(channel_id),
        operation=operation,
        cost=cost,
        total_usage=quota.units_used,
        daily_limit=quota.daily_limit,
        percentage=f"{percentage * 100:.1f}%"
    )

    # Trigger alerts
    if percentage >= YOUTUBE_QUOTA_CRITICAL_THRESHOLD:
        await send_alert(
            level="CRITICAL",
            message=f"YouTube quota exhausted for channel {channel_id}",
            details={
                "channel_id": str(channel_id),
                "usage": quota.units_used,
                "limit": quota.daily_limit,
                "percentage": f"{percentage * 100:.0f}%",
                "action": "Upload tasks paused until midnight PST reset"
            }
        )
    elif percentage >= YOUTUBE_QUOTA_WARNING_THRESHOLD:
        await send_alert(
            level="WARNING",
            message=f"YouTube quota at {percentage * 100:.0f}% for channel {channel_id}",
            details={
                "channel_id": str(channel_id),
                "usage": quota.units_used,
                "limit": quota.daily_limit,
                "percentage": f"{percentage * 100:.0f}%",
                "remaining": quota.daily_limit - quota.units_used
            }
        )


def get_required_api(status: str) -> str | None:
    """
    Determine which external API is required for task at given status.

    Maps task status to external API dependency. Used for quota checking
    before task claiming.

    Args:
        status: Task status from TaskStatus enum

    Returns:
        API name ("gemini", "kling", "elevenlabs", "youtube") or None if
        no external API required (internal processing step)

    Example:
        >>> get_required_api("pending")
        "gemini"
        >>> get_required_api("final_review")
        "youtube"
        >>> get_required_api("assets_approved")
        None  # Internal step (composite creation)
    """
    API_MAPPING = {
        "pending": "gemini",              # Asset generation
        "assets_approved": None,          # Internal (composite creation)
        "composites_ready": "kling",      # Video generation
        "video_approved": "elevenlabs",   # Audio generation
        "audio_approved": None,           # Internal (FFmpeg assembly)
        "final_review": "youtube",        # Upload
    }

    return API_MAPPING.get(status)
```

### Core Implementation: `app/utils/alerts.py` (NEW)

**Purpose:** Discord webhook integration for quota alerts.

```python
"""
Discord webhook alert system for quota exhaustion and system issues.

Sends structured alerts to Discord channel via webhook URL configured in
DISCORD_WEBHOOK_URL environment variable.

Architecture Pattern:
    - Async HTTP client (httpx)
    - Message sanitization (prevent injection)
    - Timeout handling (5s max)
    - Graceful degradation (log on failure, don't crash)

References:
    - Story 4.5: Rate Limit Aware Task Selection
    - PRD: FR32 (Alert system for terminal failures)
"""

import httpx
import os
from app.utils.logging import get_logger

log = get_logger(__name__)


async def send_alert(
    level: str,
    message: str,
    details: dict | None = None
) -> None:
    """
    Send alert to Discord webhook.

    Args:
        level: Alert level ("CRITICAL", "WARNING", "INFO")
        message: Alert message (max 2000 chars, will be truncated)
        details: Optional structured details (dict)

    Environment Variables:
        DISCORD_WEBHOOK_URL: Discord webhook URL (required)

    Example:
        >>> await send_alert(
        ...     level="WARNING",
        ...     message="YouTube quota at 85%",
        ...     details={"channel": "poke1", "usage": 8500, "limit": 10000}
        ... )
    """
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        log.warning("discord_webhook_not_configured")
        return

    # Sanitize message (Discord 2000 char limit)
    sanitized_message = message[:2000]

    # Color mapping
    colors = {
        "CRITICAL": 0xFF0000,  # Red
        "WARNING": 0xFFA500,   # Orange
        "INFO": 0x0000FF,      # Blue
        "SUCCESS": 0x00FF00    # Green
    }

    payload = {
        "content": f"**{level}**: {sanitized_message}",
        "embeds": [
            {
                "title": f"{level} Alert",
                "description": sanitized_message,
                "fields": [
                    {"name": key, "value": str(value)[:1024], "inline": True}
                    for key, value in (details or {}).items()
                ],
                "color": colors.get(level, 0x808080)  # Default gray
            }
        ]
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                webhook_url,
                json=payload,
                timeout=5.0
            )
            response.raise_for_status()

            log.info(
                "discord_alert_sent",
                level=level,
                message=message[:100]  # Truncate for log
            )
    except httpx.TimeoutException:
        log.error("discord_webhook_timeout", webhook_url=webhook_url[:50])
    except httpx.HTTPStatusError as e:
        log.error(
            "discord_webhook_http_error",
            status_code=e.response.status_code,
            response=e.response.text[:500]
        )
    except Exception as e:
        log.error("discord_webhook_failed", error=str(e))
```

### Database Migration: YouTube Quota Table

**Purpose:** Create YouTubeQuotaUsage table for per-channel daily quota tracking.

```python
"""Add YouTube quota tracking table

Revision ID: add_youtube_quota_20260116
Revises: add_round_robin_index_20260116  # Story 4.4 migration
Create Date: 2026-01-16

This migration adds the YouTubeQuotaUsage table for tracking YouTube Data API v3
quota usage per channel per day. Enables rate-aware task selection before claiming
upload tasks.

Table Structure:
    - Composite PK: (channel_id, date)
    - One row per channel per day
    - units_used: Accumulated daily usage
    - daily_limit: Quota limit (default 10,000 units)

Quota Reset:
    - Daily at midnight PST (YouTube API behavior)
    - Old rows cleaned up automatically (7-day retention)

Performance Impact:
    - Zero downtime (no locks on existing tables)
    - Small table size (~100 channels × 7 days = 700 rows max)
    - Query performance: O(1) via composite PK lookup

Deployment Notes:
    - Safe to apply on production
    - No data migration needed (starts fresh)
    - Cleanup cron job recommended (delete rows older than 7 days)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid

# revision identifiers
revision = 'add_youtube_quota_20260116'
down_revision = 'add_round_robin_index_20260116'  # Story 4.4
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Add YouTubeQuotaUsage table for per-channel quota tracking.

    Schema:
        - channel_id (UUID, FK to channels.id, part of composite PK)
        - date (Date, part of composite PK)
        - units_used (Integer, default 0, NOT NULL)
        - daily_limit (Integer, default 10000, NOT NULL)

    Constraints:
        - Composite PK: (channel_id, date)
        - Foreign key: channel_id → channels.id (ON DELETE CASCADE)
        - Check: units_used >= 0
        - Check: daily_limit > 0

    Indexes:
        - idx_youtube_quota_date: For cleanup queries (delete old rows)

    Usage:
        SELECT * FROM youtube_quota_usage
        WHERE channel_id = $1 AND date = CURRENT_DATE
    """
    op.create_table(
        'youtube_quota_usage',
        sa.Column('channel_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('units_used', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('daily_limit', sa.Integer(), nullable=False, server_default='10000'),

        # Composite primary key
        sa.PrimaryKeyConstraint('channel_id', 'date', name='pk_youtube_quota'),

        # Foreign key to channels table
        sa.ForeignKeyConstraint(
            ['channel_id'],
            ['channels.id'],
            name='fk_youtube_quota_channel',
            ondelete='CASCADE'  # Delete quota records when channel deleted
        ),

        # Check constraints
        sa.CheckConstraint('units_used >= 0', name='ck_youtube_quota_non_negative'),
        sa.CheckConstraint('daily_limit > 0', name='ck_youtube_quota_limit_positive'),
    )

    # Index for cleanup queries (delete WHERE date < CURRENT_DATE - 7)
    op.create_index(
        'idx_youtube_quota_date',
        'youtube_quota_usage',
        ['date'],
        unique=False
    )


def downgrade() -> None:
    """Remove YouTubeQuotaUsage table"""
    op.drop_index('idx_youtube_quota_date', table_name='youtube_quota_usage')
    op.drop_table('youtube_quota_usage')
```

## Dependencies

**Required Before Starting:**
- ✅ Story 4.4 complete: Round-robin channel scheduling with channel_id ordering
- ✅ Story 4.3 complete: Priority queue management with CASE priority ordering
- ✅ Story 4.2 complete: PgQueuer task claiming with FOR UPDATE SKIP LOCKED
- ✅ Story 4.1 complete: Worker process foundation
- ✅ Story 1.3 complete: Encrypted credentials storage (YouTube OAuth tokens)
- ✅ Story 1.1 complete: Database foundation with channels table
- ✅ PostgreSQL 16: Railway managed database

**Blocks These Stories:**
- Story 4.6: Parallel Task Execution (parallelism respects rate limits)
- Epic 6: Error Handling & Auto-Recovery (quota errors trigger retry logic)
- Epic 7: YouTube Publishing & Compliance (upload uses quota checks)

## Definition of Done

### Core Implementation
- [ ] `app/models.py` modified: YouTubeQuotaUsage model added
- [ ] `app/services/quota_manager.py` created: check/record functions
- [ ] `app/utils/alerts.py` created: Discord webhook integration
- [ ] `app/worker.py` modified: WorkerState class with quota flags
- [ ] `app/entrypoints.py` modified: Rate-aware task claiming logic
- [ ] `alembic/versions/20260116_0005_add_youtube_quota_table.py` created
- [ ] Composite PK migration: (channel_id, date) with check constraints
- [ ] Migration docstring includes cleanup recommendations

### Test Coverage
- [ ] All quota manager tests passing (15+ tests)
- [ ] All alert tests passing (5+ tests)
- [ ] All worker tests passing (8+ new quota tests)
- [ ] All entrypoint tests passing (10+ new rate-aware tests)
- [ ] YouTube quota checks: available, exhausted, per-channel isolation
- [ ] Gemini quota flag: exhausted, reset, task skipping
- [ ] Kling concurrency: limit reached, counter management
- [ ] Alert triggering: 80% warning, 100% critical, Discord webhook
- [ ] Race condition safety: double-check after claim, task release
- [ ] Graceful degradation: skip blocked work, process available

### Code Quality
- [ ] Type hints complete (all parameters and return types annotated)
- [ ] Docstrings complete (module and function-level with examples)
- [ ] Structured logging with quota context in all operations
- [ ] Alert messages sanitized (prevent injection, respect Discord limits)

### Documentation & Deployment
- [ ] README.md updated with Rate Limit Aware Task Selection section
- [ ] README.md updated with Quota Monitoring & Alerts section
- [ ] Alembic migration ready for production deployment
- [ ] Cleanup cron job documented for old quota records

### Code Review & Merge
- [ ] Code review completed
- [ ] All code review issues addressed
- [ ] Merged to `main` branch

## Related Stories

**Depends On:**
- 4-4 (Round-Robin Channel Scheduling) - provides channel rotation infrastructure
- 4-3 (Priority Queue Management) - provides priority ordering foundation
- 4-2 (Task Claiming with PgQueuer) - provides atomic claiming pattern
- 4-1 (Worker Process Foundation) - provides worker loop structure
- 1-3 (Encrypted Credentials Storage) - provides YouTube OAuth tokens
- 1-1 (Database Foundation) - provides channels table

**Blocks:**
- 4-6 (Parallel Task Execution) - parallelism strategy respects rate limits
- Epic 6 (Error Handling & Auto-Recovery) - quota errors trigger retry logic
- Epic 7 (YouTube Publishing & Compliance) - upload operations use quota checks

**Related:**
- Epic 1 (Channel Management) - per-channel quota isolation
- Epic 8 (Monitoring & Observability) - quota alerts and tracking

## Source References

**PRD Requirements:**
- FR42: Rate Limit Aware Task Selection (Check limits before claiming)
- FR34: API Quota Monitoring (Track usage against daily quotas)
- FR41: Round-Robin Channel Scheduling (Fair distribution preserved)

**Architecture Decisions:**
- Rate Limit Aware Task Selection: Pre-claim quota verification
- API Quota Management: YouTube 10K units/day, per-channel tracking
- Worker Independence: No inter-worker quota coordination
- Database Schema: YouTubeQuotaUsage with composite PK (channel_id, date)

**Context:**
- project-context.md: Integration Utilities, External Service Patterns
- epics.md: Epic 4 Story 5 - Rate Limit Aware Task Selection
- Story 4.4: Round-Robin Channel Scheduling completion notes
- Story 4.3: Priority Queue Management completion notes
- Story 4.2: Task Claiming with PgQueuer completion notes

**YouTube Documentation:**
- [YouTube Data API v3 Quota](https://developers.google.com/youtube/v3/getting-started#quota)
- [Quota Calculator](https://developers.google.com/youtube/v3/determine_quota_cost)

---

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.5 (claude-sonnet-4-5-20250929)

### Debug Log References

- Story Creation Date: 2026-01-16
- Context Analysis Complete: Architecture document, epics file, Story 4.4 learnings, project-context.md, recent commits
- Ultimate Context Engine: Comprehensive developer guide created with complete rate limit aware task selection details

### Completion Notes List

**Implementation Completed:** 2026-01-16

1. **YouTubeQuotaUsage Model** - Added to `app/models.py`:
   - Composite primary key (channel_id, date) for per-channel daily quota isolation
   - Check constraints for data integrity (units_used >= 0, daily_limit > 0)
   - Index on date for cleanup queries
   - Foreign key with CASCADE delete to channels table

2. **Quota Manager Service** - Created `app/services/quota_manager.py`:
   - `check_youtube_quota()`: Pre-claim quota verification
   - `record_youtube_quota()`: Post-operation quota recording with alert triggering
   - `get_required_api()`: Status → API mapping function
   - Alert thresholds: 80% WARNING, 100% CRITICAL

3. **Discord Alerts Utility** - Created `app/utils/alerts.py`:
   - Async Discord webhook integration with httpx
   - Message sanitization (2000 char limit)
   - Alert levels: CRITICAL (red), WARNING (orange), INFO (blue), SUCCESS (green)
   - Graceful degradation (log on failure, don't crash)
   - 5-second timeout handling

4. **WorkerState Class** - Added to `app/worker.py`:
   - `gemini_quota_exhausted`: Worker-local Gemini 429 flag
   - `active_video_tasks`: Kling concurrency counter
   - `max_concurrent_video`: Configurable limit (default: 3)

5. **Rate-Aware Entrypoints** - Modified `app/entrypoints.py`:
   - Double-check quota after PgQueuer claims task
   - YouTube quota: Database check before upload tasks
   - Gemini quota: Worker-local flag check before asset tasks
   - Kling concurrency: Worker-local counter check before video tasks
   - Release task back to queue if rate limit hit (return early, don't update status)

6. **Database Migration** - Created `alembic/versions/20260116_0005_add_youtube_quota_usage_table.py`:
   - CREATE TABLE youtube_quota_usage with composite PK
   - Foreign key constraint with CASCADE delete
   - Check constraints for data integrity
   - Index on date column for cleanup queries

7. **Comprehensive Tests** - Created test suites:
   - `tests/test_services/test_quota_manager.py`: 18 test scenarios covering quota checks, recording, alerts, API mapping
   - `tests/test_utils/test_alerts.py`: 10 test scenarios covering Discord webhook integration, error handling, message truncation

### File List

**Created:**
- `app/services/quota_manager.py` (~220 lines)
- `app/utils/alerts.py` (~95 lines)
- `alembic/versions/20260116_0005_add_youtube_quota_usage_table.py` (~125 lines)
- `tests/test_services/test_quota_manager.py` (~330 lines)
- `tests/test_utils/test_alerts.py` (~250 lines)

**Modified:**
- `app/models.py` (+110 lines) - Added YouTubeQuotaUsage model
- `app/worker.py` (+35 lines) - Added WorkerState class
- `app/entrypoints.py` (+80 lines) - Added rate-aware task claiming logic

**Total Lines:** ~1,245 lines (implementation + tests)

---

## Status

**Status:** implemented
**Created:** 2026-01-16 via BMad Method workflow (create-story)
**Implemented:** 2026-01-16 via BMad Method workflow (dev-story)
**Ultimate Context Engine:** Comprehensive developer guide created with complete rate limit aware task selection implementation details, multi-API quota tracking, alert thresholds, graceful degradation patterns, and per-channel isolation
