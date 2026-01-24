# Story 7.0: Automated Daily Quota Reset

Status: ready-for-dev

## Story

As a **system operator**,
I want **YouTube and Gemini quotas to automatically reset at their API-defined midnight times**,
So that **the orchestration system can continue processing videos without manual quota intervention**.

## Acceptance Criteria

**Given** it is midnight Pacific Time (YouTube API reset time)
**When** the scheduled quota reset job runs
**Then** a new YouTubeQuotaUsage row is created for the new day with units_used=0
**And** the Channel.youtube_quota_exhausted flag is set to False
**And** old quota records from >90 days ago are retained (not deleted)

**Given** it is midnight Pacific Time (Gemini API reset time)
**When** the scheduled quota reset job runs
**Then** a new GeminiQuotaUsage row is created for the new day with requests_used=0
**And** the Channel.gemini_quota_exhausted flag is set to False
**And** old quota records from >90 days ago are retained (not deleted)

**Given** the scheduler (APScheduler or cron) is configured in Railway
**When** the worker service starts
**Then** the daily reset jobs are registered and scheduled
**And** jobs run reliably without manual triggering
**And** missed runs are not backfilled (only run if service was up at scheduled time)

**Given** a quota reset job fails to execute
**When** the error is caught
**Then** a CRITICAL alert is sent to Discord
**And** the error includes: service name, timezone, expected reset time, error message
**And** manual fallback instructions are provided in the alert

**Given** an operator needs to manually reset quota (emergency)
**When** a manual reset endpoint or CLI command is executed
**Then** quota usage is reset to 0 for the specified channel
**And** quota_exhausted flags are cleared
**And** an audit log entry records the manual reset action

**Given** quota reset jobs run
**When** tests verify reset logic
**Then** time-mocking is used to simulate midnight PST
**And** tests verify new quota records created
**And** tests verify quota_exhausted flags cleared
**And** tests verify old records are NOT deleted

## Tasks / Subtasks

- [ ] Task 1: Implement timezone-aware quota reset service (AC: Resets at correct API times)
  - [ ] Subtask 1.1: Create app/services/quota_reset_service.py
  - [ ] Subtask 1.2: Add QUOTA_TIMEZONE env var (default: "America/Los_Angeles" for YouTube/Gemini)
  - [ ] Subtask 1.3: Implement reset_youtube_quotas(date, db) - creates new rows, clears flags
  - [ ] Subtask 1.4: Implement reset_gemini_quotas(date, db) - creates new rows, clears flags
  - [ ] Subtask 1.5: Query all active channels (WHERE is_active=True)
  - [ ] Subtask 1.6: For each channel: INSERT new quota row with units_used/requests_used=0
  - [ ] Subtask 1.7: UPDATE Channel SET youtube_quota_exhausted=False, gemini_quota_exhausted=False
  - [ ] Subtask 1.8: Log reset completion with structlog (channels_reset_count, date, timezone)

- [ ] Task 2: Configure APScheduler for reliable scheduling (AC: Runs at midnight PST)
  - [ ] Subtask 2.1: Add apscheduler>=3.10.0 to pyproject.toml dependencies
  - [ ] Subtask 2.2: Create app/scheduler.py with AsyncIOScheduler setup
  - [ ] Subtask 2.3: Configure timezone-aware cron triggers (hour=0, minute=0, timezone=America/Los_Angeles)
  - [ ] Subtask 2.4: Register reset_youtube_quotas job (runs daily at midnight PST)
  - [ ] Subtask 2.5: Register reset_gemini_quotas job (runs daily at midnight PST)
  - [ ] Subtask 2.6: Add scheduler.start() to worker entrypoint (app/worker.py or app/entrypoints.py)
  - [ ] Subtask 2.7: Configure misfire_grace_time (60 seconds) - skip if worker down at midnight
  - [ ] Subtask 2.8: Add scheduler shutdown on worker termination (graceful cleanup)

- [ ] Task 3: Add reset failure alerting (AC: Alert if job fails)
  - [ ] Subtask 3.1: Wrap reset logic in try/except for error handling
  - [ ] Subtask 3.2: Catch database errors, timezone errors, and unexpected exceptions
  - [ ] Subtask 3.3: Send CRITICAL Discord alert on failure via alert_service
  - [ ] Subtask 3.4: Include error context: service (youtube/gemini), date, timezone, exception message
  - [ ] Subtask 3.5: Log reset failures with ERROR level (correlation_id, full traceback)
  - [ ] Subtask 3.6: Add alert with manual fallback instructions (SQL commands to reset quota)

- [ ] Task 4: Implement manual quota reset endpoint (AC: Ops team can manually trigger)
  - [ ] Subtask 4.1: Add POST /api/v1/admin/quota-reset endpoint (admin-only)
  - [ ] Subtask 4.2: Accept parameters: channel_id (UUID), service (youtube|gemini), date (optional, defaults to today)
  - [ ] Subtask 4.3: Call reset_youtube_quotas() or reset_gemini_quotas() based on service parameter
  - [ ] Subtask 4.4: Return 200 OK with reset confirmation (channels affected, new quota values)
  - [ ] Subtask 4.5: Log manual reset action to audit_logs table (admin_action, channel_id, service, timestamp)
  - [ ] Subtask 4.6: Return 400 if invalid service or channel_id not found
  - [ ] Subtask 4.7: Add authentication check (require admin API key or Railway internal auth)
  - [ ] Subtask 4.8: Document manual reset endpoint in docs/operations.md

- [ ] Task 5: Handle quota retention policy (AC: Old records retained for 90 days)
  - [ ] Subtask 5.1: Document quota retention: KEEP all records for 90 days (compliance/analytics)
  - [ ] Subtask 5.2: Add optional cleanup job (future enhancement): DELETE records >90 days old
  - [ ] Subtask 5.3: Note in dev comments: NOT implemented in Story 7.0 (deferred to Epic 8)
  - [ ] Subtask 5.4: Verify current schema allows historical queries (indexed by date)
  - [ ] Subtask 5.5: Add monitoring for quota table size growth (alert if >100k rows)

- [ ] Task 6: Railway deployment configuration (AC: Scheduler runs in Railway)
  - [ ] Subtask 6.1: Verify scheduler runs in worker process (NOT web service)
  - [ ] Subtask 6.2: Add QUOTA_TIMEZONE env var to Railway worker config (default: America/Los_Angeles)
  - [ ] Subtask 6.3: Document scheduler behavior: Only runs if worker up at midnight
  - [ ] Subtask 6.4: Test scheduler persistence across worker restarts (jobs re-register on startup)
  - [ ] Subtask 6.5: Add Railway logs filter: quota_reset_completed (for monitoring)
  - [ ] Subtask 6.6: Document what happens if worker crashes at midnight (missed run, no backfill)
  - [ ] Subtask 6.7: Add health check: scheduler.running status in /health endpoint

- [ ] Task 7: Write comprehensive tests with time-mocking (AC: Reset logic fully tested)
  - [ ] Subtask 7.1: Test reset_youtube_quotas() creates new quota rows with units_used=0
  - [ ] Subtask 7.2: Test reset_gemini_quotas() creates new quota rows with requests_used=0
  - [ ] Subtask 7.3: Test quota_exhausted flags cleared after reset (channel.youtube_quota_exhausted=False)
  - [ ] Subtask 7.4: Test timezone handling with freezegun or time mocking (simulate midnight PST)
  - [ ] Subtask 7.5: Test scheduler cron trigger configuration (midnight PST = 08:00 UTC in winter)
  - [ ] Subtask 7.6: Test reset failure handling (database connection error triggers alert)
  - [ ] Subtask 7.7: Test manual reset endpoint (POST /api/v1/admin/quota-reset)
  - [ ] Subtask 7.8: Integration test: Exhaust quota → reset → verify workers can claim tasks again

## Dev Notes

### Critical Context from Action Items and Epic 7 Blocker

**Story 7.0 is a PREPARATION STORY** for Epic 7 (YouTube Publishing & Compliance).

From action-items.yaml:119-138:
- **Owner:** Elena (primary) + Charlie (pairing)
- **Priority:** HIGH
- **Blocking:** Epic 7 cannot start until this story is complete
- **Rationale:** YouTube has strict daily quotas (10k units, resets midnight PT). Manual reset won't scale.
- **Effort Estimate:** 6-10 hours

**Key Integration Points:**
1. **Story 6.8 (API Quota Monitoring):** Existing quota tracking infrastructure in quota_service.py
2. **Epic 7 Stories:** YouTube upload automation requires reliable quota resets
3. **Architecture:** Async patterns, timezone handling, Railway deployment

### Architecture Compliance

**Timezone Handling (CRITICAL - Code Review Issue #8)**

From quota_service.py:15-21:
```python
# Timezone Considerations (Code Review Issue #8):
# - YouTube API: Quota resets at midnight PST (UTC-8/-7)
# - Gemini API: Quota resets at midnight PST (UTC-8/-7)
# - Current Implementation: Uses UTC for date boundaries (hardcoded)
# - Impact: Quota checks may be off by 7-8 hours from actual API reset
# - Future Enhancement: Add configurable QUOTA_TIMEZONE="America/Los_Angeles"
# - Recommendation: Document timezone assumption in deployment guide
```

**THIS STORY FIXES THE TIMEZONE ISSUE** identified in Story 6.8 code review.

**Database Schema References:**

**YouTubeQuotaUsage Model (app/models.py:925-1027):**
```python
class YouTubeQuotaUsage(Base):
    __tablename__ = "youtube_quota_usage"

    # Composite Primary Key: (channel_id, date)
    channel_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("channels.id"), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)

    # Quota tracking fields
    units_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    daily_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=10000, server_default="10000")

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
```

**GeminiQuotaUsage Model (app/models.py:1029-1116):**
```python
class GeminiQuotaUsage(Base):
    __tablename__ = "gemini_quota_usage"

    # Composite Primary Key: (channel_id, date)
    channel_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("channels.id"), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)

    # Quota tracking fields
    requests_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    daily_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=1500, server_default="1500")

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
```

**Channel Model Quota Flags (app/models.py:346-361):**
```python
# Quota exhaustion flags (Story 6.8 - FR34, NFR-I4)
# Set to True when daily quota hits 100%, automatically reset at midnight UTC
youtube_quota_exhausted: Mapped[bool] = mapped_column(
    Boolean,
    nullable=False,
    default=False,
    server_default="false",
    index=True,  # Index for worker quota checks (WHERE NOT youtube_quota_exhausted)
)
gemini_quota_exhausted: Mapped[bool] = mapped_column(
    Boolean,
    nullable=False,
    default=False,
    server_default="false",
    index=True,  # Index for worker quota checks (WHERE NOT gemini_quota_exhausted)
)
```

**CRITICAL IMPLEMENTATION NOTES:**

1. **Composite Primary Key Constraint:** YouTubeQuotaUsage and GeminiQuotaUsage use (channel_id, date) as composite PK. When creating new quota rows for the new day, the INSERT will naturally fail if the row already exists. Use INSERT ... ON CONFLICT DO NOTHING or check for existence first.

2. **Quota Reset Logic Pattern:**
```python
# For each active channel:
# 1. INSERT new quota row for new date (units_used=0)
# 2. UPDATE Channel SET youtube_quota_exhausted=False
# 3. Log reset completion

# Example:
async def reset_youtube_quotas(reset_date: date, db: AsyncSession) -> int:
    # Get all active channels
    channels = await db.execute(select(Channel).where(Channel.is_active == True))

    for channel in channels.scalars():
        # Create new quota row (ON CONFLICT DO NOTHING = idempotent)
        stmt = insert(YouTubeQuotaUsage).values(
            channel_id=channel.id,
            date=reset_date,
            units_used=0,
            daily_limit=10000
        ).on_conflict_do_nothing()
        await db.execute(stmt)

        # Clear exhausted flag
        channel.youtube_quota_exhausted = False

    await db.commit()
    return len(channels)
```

3. **Timezone Configuration:**
```python
# Use pytz for Pacific Time handling
from zoneinfo import ZoneInfo  # Python 3.9+
pacific_tz = ZoneInfo("America/Los_Angeles")
midnight_pacific = datetime.now(pacific_tz).replace(hour=0, minute=0, second=0, microsecond=0)
```

### Library & Framework Requirements

**APScheduler 3.10+ (REQUIRED)**
- Async scheduler for background jobs
- Timezone-aware cron triggers
- Graceful shutdown on worker termination
- Misfire handling (skip missed runs if worker was down)

```python
# Installation
uv add "apscheduler>=3.10.0"

# Usage Pattern (from Story 6.10 example):
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

scheduler = AsyncIOScheduler(timezone="America/Los_Angeles")

# Daily at midnight Pacific Time
scheduler.add_job(
    reset_youtube_quotas,
    trigger=CronTrigger(hour=0, minute=0, timezone="America/Los_Angeles"),
    args=[db_session],
    id="reset_youtube_quotas",
    replace_existing=True,
    misfire_grace_time=60  # Skip if more than 60s late
)

scheduler.start()
```

**Timezone Library (Python 3.9+ Built-in):**
```python
from zoneinfo import ZoneInfo

# Pacific Time (handles PDT/PST automatically)
pacific_tz = ZoneInfo("America/Los_Angeles")
now_pacific = datetime.now(pacific_tz)
```

### File Structure Requirements

**New Files to Create:**
```
app/
├── services/
│   └── quota_reset_service.py        # Quota reset logic
├── scheduler.py                       # APScheduler configuration
└── entrypoints.py                     # MODIFY - start scheduler in worker

docs/
└── operations.md                      # Manual reset instructions
```

**Files to Modify:**
```
app/
├── worker.py or entrypoints.py        # Add scheduler.start()
├── models.py                          # NO CHANGES (schema already supports reset)
└── services/
    └── quota_service.py               # NO CHANGES (tracking logic unchanged)

pyproject.toml                          # Add apscheduler dependency
```

### Testing Requirements

**Test Files to Create:**
```
tests/
└── services/
    └── test_quota_reset_service.py    # Comprehensive reset tests with time-mocking

tests/
└── integration/
    └── test_quota_reset_integration.py # End-to-end reset + worker claiming
```

**Time-Mocking Pattern:**
```python
import pytest
from freezegun import freeze_time
from datetime import datetime
from zoneinfo import ZoneInfo

@freeze_time("2026-01-25 00:00:00", tz_offset=0)  # Midnight PST
async def test_quota_reset_at_midnight_pst(db_session):
    # Simulate midnight Pacific Time
    pacific_midnight = datetime(2026, 1, 25, 0, 0, 0, tzinfo=ZoneInfo("America/Los_Angeles"))

    # Reset quotas
    reset_count = await reset_youtube_quotas(pacific_midnight.date(), db_session)

    # Verify new quota rows created
    quota = await db_session.get(YouTubeQuotaUsage, (channel_id, pacific_midnight.date()))
    assert quota.units_used == 0

    # Verify flag cleared
    channel = await db_session.get(Channel, channel_id)
    assert channel.youtube_quota_exhausted == False
```

### Previous Story Intelligence

**Story 6.8 (API Quota Monitoring) - DIRECT PREDECESSOR:**

From 6-8-api-quota-monitoring.md:
- Implemented quota tracking with atomic upsert pattern (INSERT ON CONFLICT UPDATE)
- Added youtube_quota_exhausted and gemini_quota_exhausted flags to Channel model
- Threshold alerting at 80% (WARNING) and 100% (CRITICAL)
- **Known Issue (Code Review #8):** Hardcoded UTC for date boundaries instead of PST
- **Resolution:** Story 7.0 must implement timezone-aware reset to fix this

**Key Learnings:**
1. Use datetime.now(timezone.utc) for UTC timestamps, datetime.now(ZoneInfo("America/Los_Angeles")) for Pacific
2. Quota flags prevent task claiming when exhausted (workers check flags in claim logic)
3. Alert deduplication via alert_service prevents spam (max 1 per channel per threshold per day)
4. Use structlog for all quota operations (correlation_id, channel_id, date, timezone)

**Story 6.10 (Auto-Recovery Success Rate) - SIMILAR PATTERN:**

From 6-10-auto-recovery-success-rate-tracking.md:
- Implemented weekly metrics calculation with APScheduler
- Used CronTrigger with timezone awareness (Monday 00:00 UTC)
- Followed atomic upsert pattern for metrics table (INSERT ON CONFLICT UPDATE)
- Added manual trigger endpoint for ops team
- **Subtask 5.1 NOT COMPLETED:** Cron job setup marked as MANUAL SETUP REQUIRED

**Key Learnings:**
1. APScheduler setup pattern: scheduler.add_job() with CronTrigger
2. Misfire handling: misfire_grace_time=60 (skip if service was down)
3. Manual trigger endpoints for emergency operations
4. Comprehensive tests with time-mocking (freezegun library)
5. Document what happens when scheduler misses a run (no backfill)

### Git Intelligence Summary

**Recent Patterns (Last 5 Commits):**

From git log:
```
7e10908 chore: Complete Epic 6 retrospective and establish action items tracking
94ea697 chore: Mark Story 6.10 and Epic 6 as complete after code review
7002dc2 chore: Update local Claude Code permissions with git operations
471c7a9 Merge pull request #10 from franaraujo77/feature/epic-6-error-handling-completion
03ae42a fix: Skip pagination performance test on Python 3.10
```

**Code Patterns Observed:**
1. **Commit Convention:** `chore:`, `fix:`, `feat:` prefixes for commit messages
2. **PR Workflow:** Feature branches merged via pull requests (feature/epic-6-error-handling-completion)
3. **Testing:** Test skipping for Python version compatibility (03ae42a)
4. **Documentation:** Action items tracking in YAML files (7e10908)

### Latest Technical Specifics

**APScheduler 3.10+ (Current Stable: 3.10.4):**
- **Major Change:** Async/await support with AsyncIOScheduler
- **Timezone Handling:** Built-in timezone support via CronTrigger(timezone=...)
- **Misfire Handling:** misfire_grace_time parameter (default: 1 second)
- **Persistence:** In-memory by default (Railway restart = jobs re-register)

**Key APScheduler APIs:**
```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# Create scheduler
scheduler = AsyncIOScheduler(timezone="America/Los_Angeles")

# Add job with cron trigger
scheduler.add_job(
    func=async_function,
    trigger=CronTrigger(hour=0, minute=0),  # Daily at midnight
    args=[arg1, arg2],
    id="unique_job_id",
    replace_existing=True,  # Prevent duplicates on restart
    misfire_grace_time=60  # Skip if >60s late
)

# Start scheduler
scheduler.start()

# Graceful shutdown
scheduler.shutdown(wait=False)
```

**Zoneinfo Library (Python 3.9+ Standard Library):**
- Replaces pytz for timezone handling
- Uses IANA timezone database
- More accurate DST handling than pytz

```python
from zoneinfo import ZoneInfo
from datetime import datetime

# Get current time in Pacific timezone
pacific_tz = ZoneInfo("America/Los_Angeles")
now_pacific = datetime.now(pacific_tz)

# Midnight Pacific (handles PDT/PST automatically)
midnight_pacific = now_pacific.replace(hour=0, minute=0, second=0, microsecond=0)

# Get date in Pacific timezone (for quota reset)
pacific_date = now_pacific.date()
```

**Railway Deployment Considerations:**
1. **Worker Process Only:** Scheduler MUST run in worker, NOT web service (avoid duplicate jobs)
2. **Environment Variables:** Add QUOTA_TIMEZONE to Railway config (default: America/Los_Angeles)
3. **Missed Runs:** If worker down at midnight, job missed (no backfill)
4. **Health Check:** Add scheduler.running to /health endpoint for monitoring
5. **Logs:** Railway captures stdout/stderr automatically (use structlog JSON format)

### Project Context Reference

From _bmad-output/project-context.md (comprehensive AI agent rules):

**Critical Rules for AI Agents:**
1. NEVER use placeholders or TODOs in implementation
2. Follow async patterns: AsyncSession, async/await throughout
3. Use structlog for all logging (JSON format, correlation IDs)
4. Short transactions: Never hold DB connections during I/O operations
5. Test everything: Unit tests + integration tests required
6. Railway deployment: Environment variables for configuration

**Database Patterns:**
1. Use INSERT ... ON CONFLICT for atomic upserts
2. Index boolean flags used in WHERE clauses (quota_exhausted flags already indexed)
3. Use server_default for default values (not just Python default)
4. Composite primary keys: (channel_id, date) for daily tracking

**Error Handling:**
1. Catch specific exceptions (not bare except:)
2. Log with ERROR level and full traceback
3. Send CRITICAL alerts for system failures
4. Include actionable context in alerts (what failed, how to fix)

### Story Completion Status

**Definition of Done:**
- [ ] All tasks and subtasks completed and checked off
- [ ] Quota reset service implemented with timezone handling
- [ ] APScheduler configured and running in worker process
- [ ] Manual reset endpoint created and documented
- [ ] Comprehensive tests written with time-mocking (100% coverage of reset logic)
- [ ] Railway deployment configured with QUOTA_TIMEZONE env var
- [ ] Reset failure alerting integrated with Discord
- [ ] All acceptance criteria verified
- [ ] Code review completed (all issues fixed)
- [ ] Documentation updated (operations.md, Railway deployment guide)

**Ready for dev-story workflow - comprehensive developer guide created!**

## Dev Agent Record

### Agent Model Used

_To be filled by dev agent during implementation_

### Debug Log References

_To be filled by dev agent during implementation_

### Completion Notes List

_To be filled by dev agent during implementation_

### File List

_To be filled by dev agent during implementation_
