# Story 6.10: Auto-Recovery Success Rate Tracking

Status: in-progress

## Story

As a **system operator**,
I want **weekly metrics on auto-recovery success rate**,
So that **I can verify the system meets the 80% target** (FR35).

## Acceptance Criteria

**Given** transient failures occur throughout the week
**When** the weekly report is generated
**Then** metrics include:
- Total transient failures
- Successfully auto-recovered count
- Auto-recovery rate (target: 80%+)
- Average retries before success

**Given** auto-recovery rate falls below 80%
**When** the weekly report runs
**Then** an alert is triggered
**And** the alert includes failure patterns for investigation

**Given** a task successfully recovers after retry
**When** the recovery is logged
**Then** `auto_recovered: true` is recorded
**And** retry_count is preserved for metrics

## Tasks / Subtasks

- [x] Task 1: Add auto-recovery tracking fields to Task model (AC: auto_recovered field tracked)
  - [x] Subtask 1.1: Add `auto_recovered` boolean field (default False, nullable=False)
  - [x] Subtask 1.2: Add `recovery_attempt_number` integer field (which retry succeeded, nullable)
  - [x] Subtask 1.3: Add `error_category` text field (TRANSIENT/PERMANENT/UNKNOWN, nullable)
  - [x] Subtask 1.4: Create Alembic migration for auto-recovery tracking
  - [x] Subtask 1.5: Add database indexes for metrics queries (updated_at, retry_count, auto_recovered)

- [x] Task 2: Create AutoRecoveryMetrics database model (AC: Weekly metrics stored)
  - [x] Subtask 2.1: Define AutoRecoveryMetrics model with composite PK (channel_id, week_starting_date)
  - [x] Subtask 2.2: Add metrics fields (total_retry_attempts, total_auto_recovered, success_rate)
  - [x] Subtask 2.3: Add breakdown fields (transient_error_count, transient_recovered, permanent_error_count)
  - [x] Subtask 2.4: Create Alembic migration for auto_recovery_metrics table
  - [x] Subtask 2.5: Add calculated_at timestamp field for audit trail

- [x] Task 3: Update retry orchestrator to mark auto-recovery (AC: Success tracked)
  - [x] Subtask 3.1: Modify schedule_retry() to set error_category on initial failure
  - [x] Subtask 3.2: Add mark_task_recovered() function called on successful retry completion
  - [x] Subtask 3.3: Set auto_recovered=True when retry succeeds (retry_count > 0 AND status=PUBLISHED)
  - [x] Subtask 3.4: Set recovery_attempt_number to current retry_count on success
  - [x] Subtask 3.5: Log auto_recovery event with structlog (correlation_id, recovery_time)

- [x] Task 4: Implement auto_recovery_metrics_service (AC: Calculate weekly success rate)
  - [x] Subtask 4.1: Create app/services/auto_recovery_metrics_service.py
  - [x] Subtask 4.2: Implement calculate_weekly_metrics(channel_id, week_starting_date, db)
  - [x] Subtask 4.3: Query tasks in target week using updated_at date range (Monday-Sunday UTC)
  - [x] Subtask 4.4: Count total_retry_attempts (WHERE retry_count > 0 AND error_category=TRANSIENT)
  - [x] Subtask 4.5: Count total_auto_recovered (WHERE auto_recovered=True AND retry_count > 0)
  - [x] Subtask 4.6: Calculate success_rate = (total_auto_recovered / total_retry_attempts) * 100
  - [x] Subtask 4.7: Calculate average_retries_before_success (AVG(recovery_attempt_number))
  - [x] Subtask 4.8: Atomic upsert into AutoRecoveryMetrics (INSERT ON CONFLICT UPDATE pattern)

- [x] Task 5: Add weekly metrics calculation trigger (AC: Metrics calculated automatically)
  - [ ] Subtask 5.1: Create scheduled task/cron job to run weekly (Monday 00:00 UTC) **[MANUAL SETUP REQUIRED - See Dev Notes]**
  - [x] Subtask 5.2: Calculate metrics for previous week (week ending Sunday)
  - [x] Subtask 5.3: Calculate for all active channels with retry activity
  - [x] Subtask 5.4: Handle edge cases (no retry attempts in week, zero division)
  - [x] Subtask 5.5: Log metrics calculation completion with structlog

- [x] Task 6: Implement success rate threshold alerting (AC: Alert when below 80%)
  - [x] Subtask 6.1: Add check_success_rate_thresholds(metrics, db) function
  - [x] Subtask 6.2: Trigger Discord alert when success_rate < 80%
  - [x] Subtask 6.3: Include metrics details: channel, week, rate, total_recovered/total_attempts
  - [x] Subtask 6.4: Rate-limit alerts (max 1 per channel per week)
  - [x] Subtask 6.5: Add failure pattern summary to alert (most common error types)

- [ ] Task 7: Add Notion sync for auto-recovery metrics (AC: Metrics visible in Notion) **[OPTIONAL - Deferred]**
  - [ ] Subtask 7.1: Add weekly summary section to Notion channel pages (optional)
  - [ ] Subtask 7.2: Display success rate, total recovered, total attempts
  - [ ] Subtask 7.3: Show trend compared to previous weeks
  - [ ] Subtask 7.4: Add link to detailed metrics (if implemented)
  - [ ] Subtask 7.5: Update Notion sync documentation (docs/notion-setup.md)

- [x] Task 8: Write comprehensive tests (AC: All metrics logic tested)
  - [x] Subtask 8.1: Test auto_recovered field set on successful retry
  - [x] Subtask 8.2: Test calculate_weekly_metrics() with various scenarios
  - [x] Subtask 8.3: Test success rate calculation (0%, 50%, 80%, 100%)
  - [x] Subtask 8.4: Test zero division handling (no retry attempts in week)
  - [x] Subtask 8.5: Test threshold alerting (>=80% no alert, <80% triggers alert)
  - [x] Subtask 8.6: Test atomic upsert for concurrent worker updates
  - [x] Subtask 8.7: Test weekly aggregation across multiple channels
  - [x] Subtask 8.8: Integration test: Fail task → retry → recover → metrics calculated

## Dev Notes

### Critical Context from Story 6.10 Requirements

**FR35: Auto-Recovery Success Rate**
From epics.md:1595-1621, Story 6.10 tracks auto-recovery success rate:
- Target: 80%+ transient failures auto-recover without human intervention
- Weekly metrics aggregation
- Alert when falling below target
- Detailed breakdown: total attempts, successful recoveries, failure patterns

**Key Integration Points:**
1. **Story 6.2 (Exponential Backoff):** Retry orchestrator tracks retry_count
2. **Story 6.3 (Resume from Failure Point):** Checkpoint service tracks partial completion
3. **Story 6.4 (Granular Error Status):** Error category classification (TRANSIENT/PERMANENT)
4. **Story 6.8 (Quota Monitoring):** Similar metrics pattern (atomic upsert, threshold alerts)
5. **Story 6.9 (Retry State Visibility):** Retry tracking fields (retry_count, next_retry_at)

### Architecture Compliance

**Auto-Recovery Metrics Pattern (CRITICAL)**

From architecture.md and Story 6.8 (quota monitoring) implementation patterns:

**Database Schema: Task Model Extension (REQUIRED):**
```python
# app/models.py (MODIFY - add auto-recovery fields to Task model)

from sqlalchemy import Column, Boolean, Integer, String
from datetime import datetime, timezone

class Task(Base):
    """
    Task model - ADD auto-recovery tracking fields for Story 6.10.

    New Fields:
    - auto_recovered: Did task recover from error state via retry?
    - recovery_attempt_number: Which retry succeeded (1-5)?
    - error_category: Error classification (TRANSIENT/PERMANENT/UNKNOWN)

    Integration:
    - Story 6.2: Uses retry_count from exponential backoff
    - Story 6.4: Uses error classification for breakdown metrics
    - Story 6.8: Follows similar atomic upsert pattern for metrics
    """
    __tablename__ = "tasks"

    # ... existing fields ...

    # Auto-recovery tracking (Story 6.10)
    auto_recovered = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Task recovered from error via automatic retry (not manual)"
    )
    recovery_attempt_number = Column(
        Integer,
        nullable=True,
        comment="Which retry succeeded (1-5), NULL if not recovered"
    )
    error_category = Column(
        String(20),
        nullable=True,
        comment="Error classification: TRANSIENT, PERMANENT, UNKNOWN"
    )
```

**Database Schema: AutoRecoveryMetrics Model (CREATE NEW):**
```python
# app/models.py (ADD - new model for weekly metrics)

from sqlalchemy import Column, UUID, Date, Integer, Float, DateTime, ForeignKey
from sqlalchemy.schema import PrimaryKeyConstraint, Index

class AutoRecoveryMetrics(Base):
    """
    Weekly auto-recovery success rate tracking (Story 6.10).

    Composite Primary Key:
        (channel_id, week_starting_date) - one row per channel per week

    Purpose:
        Calculate weekly success rate to verify 80% target (FR35)

    Atomic Upsert Pattern:
        Uses INSERT ON CONFLICT UPDATE for concurrent safety
        Similar to YouTubeQuotaUsage/GeminiQuotaUsage (Story 6.8)
    """
    __tablename__ = "auto_recovery_metrics"

    # Composite primary key
    channel_id = Column(
        UUID(as_uuid=True),
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
        comment="Channel these metrics apply to"
    )
    week_starting_date = Column(
        Date,
        nullable=False,
        comment="Monday of week (ISO week, YYYY-MM-DD)"
    )

    # Success rate metrics
    total_retry_attempts = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Tasks with retry_count > 0 in week (attempted recovery)"
    )
    total_auto_recovered = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Tasks that recovered via retry (auto_recovered=True)"
    )
    success_rate = Column(
        Float,
        nullable=False,
        default=0.0,
        comment="Percentage: total_auto_recovered / total_retry_attempts * 100"
    )
    average_retries_before_success = Column(
        Float,
        nullable=True,
        comment="Average recovery_attempt_number for recovered tasks"
    )

    # Detailed breakdown by error category
    transient_error_count = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Tasks with error_category=TRANSIENT in week"
    )
    transient_recovered = Column(
        Integer,
        nullable=False,
        default=0,
        comment="TRANSIENT errors that successfully recovered"
    )
    permanent_error_count = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Tasks with error_category=PERMANENT (never recover)"
    )

    # Metadata
    calculated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="When metrics were calculated (audit trail)"
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    # Composite primary key constraint
    __table_args__ = (
        PrimaryKeyConstraint('channel_id', 'week_starting_date', name='pk_auto_recovery_metrics'),
        Index('ix_auto_recovery_metrics_week', 'week_starting_date'),
        Index('ix_auto_recovery_metrics_success_rate', 'success_rate'),
        Index('ix_auto_recovery_metrics_channel', 'channel_id'),
    )
```

**Retry Orchestrator Integration (REQUIRED):**
```python
# app/services/retry_orchestrator.py (MODIFY - track auto-recovery)

async def schedule_retry(
    task_id: UUID,
    exception: Exception,
    db: AsyncSession,
    context: ErrorContext
) -> ErrorPayload:
    """
    Schedule retry for transient failure.

    NEW for Story 6.10: Set error_category for metrics breakdown.
    """
    task = await db.get(Task, task_id)

    # Classify error (existing from Story 6.1)
    error_analysis = classify_error(exception, context)

    # NEW: Set error_category for metrics breakdown
    if error_analysis.category not in ["TRANSIENT", "PERMANENT", "UNKNOWN"]:
        raise ValueError(f"Invalid error category: {error_analysis.category}")
    task.error_category = error_analysis.category

    # Existing retry logic...
    if should_retry_task(error_analysis, task.retry_count):
        task.retry_count += 1
        task.next_retry_at = calculate_next_retry(task.retry_count)
        task.last_error_timestamp = datetime.now(timezone.utc)
        # ... rest of existing logic

    await db.commit()


async def mark_task_recovered(
    task_id: UUID,
    db: AsyncSession
) -> None:
    """
    Mark task as successfully auto-recovered from error state.

    NEW for Story 6.10: Track successful auto-recovery for metrics.

    Call this when:
        - Task had error status (ASSET_ERROR, VIDEO_ERROR, etc.)
        - Retry succeeded (retry_count > 0)
        - Task reached successful state (PUBLISHED)

    Sets:
        - auto_recovered = True
        - recovery_attempt_number = retry_count at time of recovery
    """
    task = await db.get(Task, task_id)

    if task.retry_count > 0 and not task.is_manual_retry:
        # Automatic recovery (not user-triggered)
        task.auto_recovered = True
        task.recovery_attempt_number = task.retry_count

        log.info(
            "task_auto_recovered",
            task_id=str(task.id),
            channel_id=str(task.channel_id),
            retry_count=task.retry_count,
            recovery_attempt=task.recovery_attempt_number,
            error_category=task.error_category,
            correlation_id=context.correlation_id
        )

        await db.commit()
```

**Auto-Recovery Metrics Service (CREATE NEW):**
```python
# app/services/auto_recovery_metrics_service.py (CREATE)

"""
Auto-recovery success rate tracking service (Story 6.10).

Responsibilities:
1. Calculate weekly auto-recovery success rate
2. Store metrics in AutoRecoveryMetrics table (atomic upsert)
3. Check 80% target threshold and trigger alerts
4. Query historical metrics for trends

Integration:
- Story 6.2: Uses retry_count from exponential backoff
- Story 6.4: Uses error_category for breakdown metrics
- Story 6.8: Follows same atomic upsert + threshold alerting pattern
- Story 6.9: Uses retry tracking fields for metrics calculation
"""

import structlog
from datetime import datetime, date, timedelta, timezone
from sqlalchemy import select, func, insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from uuid import UUID

from app.models import Task, AutoRecoveryMetrics, Channel
from app.services.alert_service import send_discord_alert

log = structlog.get_logger()


def get_week_starting_date(target_date: date) -> date:
    """
    Get Monday of the ISO week containing target_date.

    Args:
        target_date: Any date in the target week

    Returns:
        date: Monday of that week (ISO week starts Monday)

    Example:
        >>> get_week_starting_date(date(2026, 1, 23))  # Thursday
        date(2026, 1, 20)  # Previous Monday
    """
    weekday = target_date.weekday()  # Monday=0, Sunday=6
    monday = target_date - timedelta(days=weekday)
    return monday


async def calculate_weekly_metrics(
    channel_id: UUID,
    week_starting_date: date,
    db: AsyncSession
) -> AutoRecoveryMetrics:
    """
    Calculate auto-recovery success rate for specific week.

    Args:
        channel_id: Channel to calculate metrics for
        week_starting_date: Monday of target week
        db: Database session

    Returns:
        AutoRecoveryMetrics: Calculated metrics (saved to database)

    Metrics Calculated:
        - total_retry_attempts: Tasks with retry_count > 0 in week
        - total_auto_recovered: Tasks with auto_recovered=True
        - success_rate: (total_auto_recovered / total_retry_attempts) * 100
        - average_retries_before_success: AVG(recovery_attempt_number)
        - transient_error_count: error_category=TRANSIENT count
        - transient_recovered: TRANSIENT errors that recovered
        - permanent_error_count: error_category=PERMANENT count

    Week Boundary:
        Monday 00:00:00 UTC to Sunday 23:59:59 UTC (inclusive)

    Integration:
        - Story 6.8: Atomic upsert pattern (INSERT ON CONFLICT UPDATE)
        - Story 6.2: retry_count field from exponential backoff
        - Story 6.4: error_category field from granular error status
    """
    # Calculate week boundaries (UTC)
    week_start = datetime.combine(week_starting_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    week_end = week_start + timedelta(days=7) - timedelta(microseconds=1)

    log.info(
        "calculating_weekly_metrics",
        channel_id=str(channel_id),
        week_starting_date=week_starting_date.isoformat(),
        week_start=week_start.isoformat(),
        week_end=week_end.isoformat()
    )

    # Query tasks in target week
    query = select(Task).where(
        Task.channel_id == channel_id,
        Task.updated_at >= week_start,
        Task.updated_at <= week_end
    )
    result = await db.execute(query)
    tasks = result.scalars().all()

    # Calculate metrics
    total_retry_attempts = sum(1 for t in tasks if t.retry_count > 0)
    total_auto_recovered = sum(1 for t in tasks if t.auto_recovered)

    # Success rate calculation (handle zero division)
    success_rate = (
        (total_auto_recovered / total_retry_attempts * 100)
        if total_retry_attempts > 0
        else 0.0
    )

    # Average retries before success
    recovered_tasks = [t for t in tasks if t.auto_recovered and t.recovery_attempt_number]
    average_retries = (
        sum(t.recovery_attempt_number for t in recovered_tasks) / len(recovered_tasks)
        if recovered_tasks
        else None
    )

    # Error category breakdown
    transient_error_count = sum(1 for t in tasks if t.error_category == "TRANSIENT")
    transient_recovered = sum(
        1 for t in tasks
        if t.error_category == "TRANSIENT" and t.auto_recovered
    )
    permanent_error_count = sum(1 for t in tasks if t.error_category == "PERMANENT")

    # Atomic upsert (Story 6.8 pattern)
    stmt = pg_insert(AutoRecoveryMetrics).values(
        channel_id=channel_id,
        week_starting_date=week_starting_date,
        total_retry_attempts=total_retry_attempts,
        total_auto_recovered=total_auto_recovered,
        success_rate=success_rate,
        average_retries_before_success=average_retries,
        transient_error_count=transient_error_count,
        transient_recovered=transient_recovered,
        permanent_error_count=permanent_error_count,
        calculated_at=datetime.now(timezone.utc)
    )

    # Update existing record if conflict
    stmt = stmt.on_conflict_do_update(
        index_elements=['channel_id', 'week_starting_date'],
        set_={
            'total_retry_attempts': stmt.excluded.total_retry_attempts,
            'total_auto_recovered': stmt.excluded.total_auto_recovered,
            'success_rate': stmt.excluded.success_rate,
            'average_retries_before_success': stmt.excluded.average_retries_before_success,
            'transient_error_count': stmt.excluded.transient_error_count,
            'transient_recovered': stmt.excluded.transient_recovered,
            'permanent_error_count': stmt.excluded.permanent_error_count,
            'calculated_at': stmt.excluded.calculated_at,
            'updated_at': datetime.now(timezone.utc)
        }
    )

    await db.execute(stmt)
    await db.commit()

    # Retrieve saved metrics
    metrics = await get_auto_recovery_metrics(channel_id, week_starting_date, db)

    log.info(
        "weekly_metrics_calculated",
        channel_id=str(channel_id),
        week_starting_date=week_starting_date.isoformat(),
        total_retry_attempts=total_retry_attempts,
        total_auto_recovered=total_auto_recovered,
        success_rate=round(success_rate, 2),
        average_retries=round(average_retries, 2) if average_retries else None,
        transient_error_count=transient_error_count,
        transient_recovered=transient_recovered,
        permanent_error_count=permanent_error_count
    )

    # Check thresholds and alert if needed
    await check_success_rate_thresholds(metrics, db)

    return metrics


async def get_auto_recovery_metrics(
    channel_id: UUID,
    week_starting_date: date,
    db: AsyncSession
) -> Optional[AutoRecoveryMetrics]:
    """
    Retrieve auto-recovery metrics for specific week.

    Args:
        channel_id: Channel to query
        week_starting_date: Monday of target week
        db: Database session

    Returns:
        AutoRecoveryMetrics | None: Metrics if exists, None otherwise
    """
    query = select(AutoRecoveryMetrics).where(
        AutoRecoveryMetrics.channel_id == channel_id,
        AutoRecoveryMetrics.week_starting_date == week_starting_date
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def check_success_rate_thresholds(
    metrics: AutoRecoveryMetrics,
    db: AsyncSession
) -> None:
    """
    Check FR35 (80% target) and trigger alert if below threshold.

    Args:
        metrics: Calculated metrics for week
        db: Database session

    Alert Conditions:
        - success_rate < 80% (FR35 target)
        - At least 5 retry attempts in week (meaningful sample size)

    Alert Details:
        - Channel name
        - Week ending date
        - Success rate (percentage)
        - Total recovered / total attempts
        - Failure pattern summary (error categories)

    Rate Limiting:
        - Max 1 alert per channel per week
        - Tracked via calculated_at timestamp

    Integration:
        - Story 6.6: Discord webhook alerting
        - Story 6.8: Similar threshold alerting pattern
    """
    # Skip alert if insufficient data
    if metrics.total_retry_attempts < 5:
        log.info(
            "skipping_threshold_check_insufficient_data",
            channel_id=str(metrics.channel_id),
            week_starting_date=metrics.week_starting_date.isoformat(),
            total_retry_attempts=metrics.total_retry_attempts
        )
        return

    # Check 80% threshold (FR35)
    if metrics.success_rate < 80.0:
        # Get channel name for alert
        channel_query = select(Channel).where(Channel.id == metrics.channel_id)
        channel_result = await db.execute(channel_query)
        channel = channel_result.scalar_one()

        # Week ending date (Sunday)
        week_ending = metrics.week_starting_date + timedelta(days=6)

        # Failure pattern summary
        transient_recovery_rate = (
            (metrics.transient_recovered / metrics.transient_error_count * 100)
            if metrics.transient_error_count > 0
            else 0.0
        )

        alert_message = f"""
**Auto-Recovery Rate Below Target**

**Channel:** {channel.channel_name}
**Week:** {metrics.week_starting_date.isoformat()} to {week_ending.isoformat()}

**Metrics:**
- Success Rate: {metrics.success_rate:.1f}% (Target: 80%+)
- Recovered: {metrics.total_auto_recovered} / {metrics.total_retry_attempts} attempts
- Average Retries: {metrics.average_retries_before_success:.1f} attempts

**Failure Pattern:**
- Transient Errors: {metrics.transient_error_count} ({transient_recovery_rate:.1f}% recovered)
- Permanent Errors: {metrics.permanent_error_count}

**Action:** Investigate failure patterns in error logs for this channel.
"""

        await send_discord_alert(
            alert_type="low_recovery_rate",
            title=f"Auto-Recovery Rate {metrics.success_rate:.1f}% < 80% Target",
            description=alert_message,
            channel_id=str(metrics.channel_id)
        )

        log.warning(
            "auto_recovery_rate_below_target",
            channel_id=str(metrics.channel_id),
            channel_name=channel.channel_name,
            week_starting_date=metrics.week_starting_date.isoformat(),
            success_rate=metrics.success_rate,
            target_rate=80.0,
            total_recovered=metrics.total_auto_recovered,
            total_attempts=metrics.total_retry_attempts
        )


async def calculate_all_channels_weekly_metrics(
    week_starting_date: date,
    db: AsyncSession
) -> list[AutoRecoveryMetrics]:
    """
    Calculate auto-recovery metrics for all active channels for specific week.

    Args:
        week_starting_date: Monday of target week
        db: Database session

    Returns:
        list[AutoRecoveryMetrics]: Metrics for all channels with retry activity

    Usage:
        Called by weekly scheduled job (Monday 00:00 UTC) to calculate
        previous week's metrics for all channels.

    Example:
        >>> # Calculate metrics for week of 2026-01-20
        >>> metrics = await calculate_all_channels_weekly_metrics(
        ...     date(2026, 1, 20),
        ...     db
        ... )
    """
    # Get all active channels
    channels_query = select(Channel).where(Channel.is_active == True)
    channels_result = await db.execute(channels_query)
    channels = channels_result.scalars().all()

    metrics_list = []
    for channel in channels:
        metrics = await calculate_weekly_metrics(
            channel_id=channel.id,
            week_starting_date=week_starting_date,
            db=db
        )
        metrics_list.append(metrics)

    log.info(
        "all_channels_weekly_metrics_calculated",
        week_starting_date=week_starting_date.isoformat(),
        channels_count=len(channels),
        total_retry_attempts=sum(m.total_retry_attempts for m in metrics_list),
        total_auto_recovered=sum(m.total_auto_recovered for m in metrics_list)
    )

    return metrics_list
```

### Previous Story Intelligence

**Story 6.8: API Quota Monitoring (PATTERN REFERENCE - CRITICAL)**

Completed in commit b11db74. Story 6.10 follows identical atomic upsert + threshold alerting pattern:

**Key Integration Points:**
1. **Atomic Upsert Pattern:** Composite PK (channel_id, date/week) with INSERT ON CONFLICT UPDATE
2. **Threshold Alerting:** Check percentage against target, send Discord alert if below
3. **Database Model:** Similar structure (channel FK, date/week, counts, percentages, timestamps)
4. **Service Organization:** Separate service file (quota_service.py → auto_recovery_metrics_service.py)

**Pattern Comparison:**
```python
# Quota monitoring (Story 6.8)
YouTubeQuotaUsage:
    PK: (channel_id, date)
    Metrics: units_used, daily_limit
    Percentage: units_used / daily_limit * 100
    Threshold: 80% WARNING, 100% CRITICAL

# Auto-recovery metrics (Story 6.10)
AutoRecoveryMetrics:
    PK: (channel_id, week_starting_date)
    Metrics: total_auto_recovered, total_retry_attempts
    Percentage: total_auto_recovered / total_retry_attempts * 100
    Threshold: <80% WARNING (FR35 target)
```

**Story 6.9: Retry State Visibility (INTEGRATION)**

Completed in commit 25caba7. Story 6.10 uses retry tracking fields from 6.9:

**Retry Fields Used:**
- `retry_count` - Number of retry attempts (0-5)
- `next_retry_at` - Scheduled retry time (nullable)
- `last_error_timestamp` - Most recent error time
- `max_retry_attempts` - Default 5

**New Fields for 6.10:**
- `auto_recovered` - Did task recover via retry? (boolean)
- `recovery_attempt_number` - Which retry succeeded? (1-5)
- `error_category` - Error classification (TRANSIENT/PERMANENT/UNKNOWN)

**Story 6.2: Exponential Backoff Retry Logic (FOUNDATION)**

Completed in commit 18cab12. Story 6.10 tracks success of retry logic from 6.2:

**Retry Schedule (reused):**
- Attempt 1 → 1 minute delay
- Attempt 2 → 5 minute delay
- Attempt 3 → 15 minute delay
- Attempt 4 → 1 hour delay
- Attempt 5 → Terminal failure (no more retries)

**Metrics Tracking:**
- Success after attempt 1 → fast recovery (ideal)
- Success after attempt 5 → slow recovery (still counts as success)
- Average retry attempts before success → measures retry efficiency

**Story 6.4: Granular Error Status Updates (ERROR CLASSIFICATION)**

Completed with fixes. Story 6.10 uses error category breakdown:

**Error Categories (from error_classifier.py):**
- **TRANSIENT:** Network timeouts, rate limits (429), server errors (500/502/503) - should recover
- **PERMANENT:** Bad requests (400), unauthorized (401), not found (404) - won't recover
- **UNKNOWN:** Unexpected errors - may or may not recover

**Metrics Breakdown:**
- transient_error_count / transient_recovered → measures transient recovery rate
- permanent_error_count → should be zero (these never recover)
- UNKNOWN errors → investigate pattern if high

### Technical Requirements

**New Database Fields: Task Model**

Alembic migration required:
```python
# alembic/versions/YYYYMMDD_HHMM_add_auto_recovery_tracking.py

def upgrade():
    op.add_column('tasks', sa.Column('auto_recovered', sa.Boolean(),
                   nullable=False, server_default='false'))
    op.add_column('tasks', sa.Column('recovery_attempt_number', sa.Integer(),
                   nullable=True))
    op.add_column('tasks', sa.Column('error_category', sa.String(20),
                   nullable=True))

    # Indexes for metrics queries (performance)
    op.create_index('ix_tasks_auto_recovered', 'tasks', ['auto_recovered'],
                    postgresql_where=sa.text("auto_recovered = true"))
    op.create_index('ix_tasks_error_category', 'tasks', ['error_category'])
    op.create_index('ix_tasks_updated_at_retry', 'tasks', ['updated_at', 'retry_count'])

def downgrade():
    op.drop_index('ix_tasks_updated_at_retry')
    op.drop_index('ix_tasks_error_category')
    op.drop_index('ix_tasks_auto_recovered')
    op.drop_column('tasks', 'error_category')
    op.drop_column('tasks', 'recovery_attempt_number')
    op.drop_column('tasks', 'auto_recovered')
```

**New Database Table: AutoRecoveryMetrics**

Alembic migration required:
```python
# alembic/versions/YYYYMMDD_HHMM_create_auto_recovery_metrics.py

def upgrade():
    op.create_table(
        'auto_recovery_metrics',
        sa.Column('channel_id', sa.UUID(), nullable=False),
        sa.Column('week_starting_date', sa.Date(), nullable=False),
        sa.Column('total_retry_attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_auto_recovered', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('success_rate', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('average_retries_before_success', sa.Float(), nullable=True),
        sa.Column('transient_error_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('transient_recovered', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('permanent_error_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('calculated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('channel_id', 'week_starting_date', name='pk_auto_recovery_metrics'),
        sa.ForeignKeyConstraint(['channel_id'], ['channels.id'], ondelete='CASCADE')
    )

    # Indexes for queries
    op.create_index('ix_auto_recovery_metrics_week', 'auto_recovery_metrics', ['week_starting_date'])
    op.create_index('ix_auto_recovery_metrics_success_rate', 'auto_recovery_metrics', ['success_rate'])
    op.create_index('ix_auto_recovery_metrics_channel', 'auto_recovery_metrics', ['channel_id'])

def downgrade():
    op.drop_index('ix_auto_recovery_metrics_channel')
    op.drop_index('ix_auto_recovery_metrics_success_rate')
    op.drop_index('ix_auto_recovery_metrics_week')
    op.drop_table('auto_recovery_metrics')
```

**New Service: Auto-Recovery Metrics Service**

Create `app/services/auto_recovery_metrics_service.py`:
- `get_week_starting_date(target_date)` - Get Monday of ISO week
- `calculate_weekly_metrics(channel_id, week, db)` - Calculate success rate for week
- `get_auto_recovery_metrics(channel_id, week, db)` - Retrieve metrics for week
- `check_success_rate_thresholds(metrics, db)` - Alert if <80%
- `calculate_all_channels_weekly_metrics(week, db)` - Calculate for all channels

### Library & Framework Requirements

**No new dependencies required** - uses existing stack:
- `sqlalchemy>=2.0.0` - New models and indexes
- `structlog>=23.2.0` - Metrics calculation logging
- `python-dateutil>=2.8.2` - ISO week calculation

### File Structure Requirements

**New Files:**
1. `app/services/auto_recovery_metrics_service.py` - Metrics calculation service
2. `alembic/versions/YYYYMMDD_HHMM_add_auto_recovery_tracking.py` - Task model migration
3. `alembic/versions/YYYYMMDD_HHMM_create_auto_recovery_metrics.py` - Metrics table migration
4. `tests/test_services/test_auto_recovery_metrics.py` - Unit tests (15+ tests)
5. `tests/test_models/test_auto_recovery_fields.py` - Model field tests (5+ tests)

**Modified Files:**
1. `app/models.py` - Add auto-recovery fields to Task, add AutoRecoveryMetrics model
2. `app/services/retry_orchestrator.py` - Set error_category, call mark_task_recovered()
3. `app/entrypoints.py` or worker - Call mark_task_recovered() on successful retry completion
4. `app/services/alert_service.py` - Add low_recovery_rate alert type (if needed)
5. `tests/test_services/test_retry_orchestrator.py` - Add auto_recovered field tests

### Testing Requirements

**Unit Tests (`tests/test_services/test_auto_recovery_metrics.py`):**

1. **Week Boundary Calculation:**
   - Test get_week_starting_date() for various days of week
   - Test Monday → Monday (same), Sunday → Monday (6 days earlier)
   - Test edge cases: year boundary, leap year

2. **Metrics Calculation:**
   - Test calculate_weekly_metrics() with 0 retry attempts → success_rate=0.0
   - Test with 10 attempts, 8 recovered → success_rate=80.0%
   - Test with 10 attempts, 10 recovered → success_rate=100.0%
   - Test zero division handling (no retry attempts)
   - Test average_retries calculation

3. **Error Category Breakdown:**
   - Test transient_error_count / transient_recovered calculation
   - Test permanent_error_count tracking
   - Test mixed error categories in same week

4. **Atomic Upsert:**
   - Test INSERT creates new record
   - Test UPDATE modifies existing record (same channel + week)
   - Test concurrent updates don't lose data

5. **Threshold Alerting:**
   - Test success_rate >= 80% → no alert
   - Test success_rate < 80% → alert triggered
   - Test insufficient data (< 5 attempts) → no alert
   - Test alert rate limiting (max 1 per week)

**Integration Tests:**

1. **End-to-End Metrics Flow:**
   - Fail task → retry → recover → mark_task_recovered → calculate_weekly_metrics → verify metrics

2. **Multi-Channel Metrics:**
   - Test calculate_all_channels_weekly_metrics() with 3 channels
   - Verify metrics calculated independently per channel

**Test Pattern Example:**
```python
import pytest
from datetime import datetime, date, timedelta, timezone
from app.services.auto_recovery_metrics_service import (
    calculate_weekly_metrics,
    get_week_starting_date,
    check_success_rate_thresholds
)
from tests.support.factories import create_channel, create_task

@pytest.mark.asyncio
async def test_calculate_weekly_metrics_80_percent_success(db_session):
    """Verify 80% success rate calculation (8/10 recovered)."""
    channel = create_channel(channel_id="poke1")
    db_session.add(channel)
    await db_session.commit()

    # Create 10 failed tasks with retries
    week_start = date(2026, 1, 20)  # Monday
    for i in range(10):
        auto_recovered = i < 8  # First 8 recovered, last 2 failed
        task = create_task(
            channel_id=channel.id,
            status=TaskStatus.PUBLISHED if auto_recovered else TaskStatus.FAILED,
            retry_count=2,
            auto_recovered=auto_recovered,
            recovery_attempt_number=2 if auto_recovered else None,
            error_category="TRANSIENT",
            updated_at=datetime.combine(week_start + timedelta(days=i % 7), datetime.min.time()).replace(tzinfo=timezone.utc)
        )
        db_session.add(task)
    await db_session.commit()

    # Calculate metrics
    metrics = await calculate_weekly_metrics(
        channel_id=channel.id,
        week_starting_date=week_start,
        db=db_session
    )

    # Verify
    assert metrics.total_retry_attempts == 10
    assert metrics.total_auto_recovered == 8
    assert metrics.success_rate == 80.0
    assert metrics.transient_error_count == 10
    assert metrics.transient_recovered == 8

@pytest.mark.asyncio
async def test_check_threshold_alerts_when_below_80(db_session, mocker):
    """Verify alert triggered when success rate < 80%."""
    mock_alert = mocker.patch("app.services.auto_recovery_metrics_service.send_discord_alert")

    channel = create_channel(channel_id="poke1", channel_name="Pokemon Channel")
    db_session.add(channel)
    await db_session.commit()

    metrics = AutoRecoveryMetrics(
        channel_id=channel.id,
        week_starting_date=date(2026, 1, 20),
        total_retry_attempts=10,
        total_auto_recovered=7,  # 70% < 80% target
        success_rate=70.0,
        average_retries_before_success=2.5,
        transient_error_count=10,
        transient_recovered=7,
        permanent_error_count=0,
        calculated_at=datetime.now(timezone.utc)
    )
    db_session.add(metrics)
    await db_session.commit()

    # Check thresholds
    await check_success_rate_thresholds(metrics, db_session)

    # Verify alert was sent
    mock_alert.assert_called_once()
    call_args = mock_alert.call_args
    assert call_args.kwargs["alert_type"] == "low_recovery_rate"
    assert "70.0%" in call_args.kwargs["title"]
    assert "Pokemon Channel" in call_args.kwargs["description"]
```

### Project Structure Notes

**Alignment with Epic 6 Error Handling:**

Story 6.10 completes the auto-recovery visibility by tracking success rate:

1. **Story 6.1:** Classifies errors → Story 6.10 tracks recovery by error category
2. **Story 6.2:** Implements retry → Story 6.10 tracks which retry succeeded
3. **Story 6.8:** Monitors quota → Story 6.10 follows same metrics pattern
4. **Story 6.9:** Shows retry progress → Story 6.10 aggregates recovery outcomes

**Auto-Recovery Metrics Pattern:**

- **Internal state (database):** AutoRecoveryMetrics table, Task.auto_recovered field
- **Calculation trigger:** Weekly scheduled job (Monday 00:00 UTC)
- **Alert condition:** success_rate < 80% (FR35 target)
- **User visibility:** Notion summary view (optional), Discord alerts

**User Experience Flow:**

1. Task fails → Retry scheduled (Story 6.2)
2. Retry succeeds → mark_task_recovered() sets auto_recovered=True
3. Weekly calculation → calculate_weekly_metrics() aggregates successes
4. If <80% → Discord alert: "Auto-recovery rate 67% below 80% target for week of 2026-01-20"
5. Operator investigates → reviews error logs for that channel/week

### References

**Epic & Requirements:**
- PRD: FR35 (Auto-recovery success rate tracking with 80% target)
- Epic 6 Story 6.10: `_bmad-output/planning-artifacts/epics.md#story-610-auto-recovery-success-rate-tracking` (lines 1595-1621)
- Previous stories:
  - Story 6.2: `_bmad-output/implementation-artifacts/6-2-exponential-backoff-retry-logic.md` (retry orchestrator)
  - Story 6.8: `_bmad-output/implementation-artifacts/6-8-api-quota-monitoring.md` (atomic upsert + threshold alerting pattern)
  - Story 6.9: `_bmad-output/implementation-artifacts/6-9-retry-state-visibility.md` (retry tracking fields)

**Architecture:**
- Task lifecycle state machine: `architecture.md:403-427` (retry state transitions)
- Error handling patterns: `architecture.md:486-500` (retry strategy)
- Metrics tracking: `architecture.md` (observability section)

**Code References:**
- Quota service pattern: `app/services/quota_service.py` (atomic upsert, threshold alerting)
- Retry orchestrator: `app/services/retry_orchestrator.py` (schedule_retry, should_retry_task)
- Error classifier: `app/services/error_classifier.py` (error category classification)
- Alert service: `app/services/alert_service.py` (Discord webhook alerts)
- Models: `app/models.py` (Task, YouTubeQuotaUsage, GeminiQuotaUsage)

**Testing References:**
- Quota service tests: `tests/test_services/test_quota_service.py` (upsert, threshold alert tests)
- Retry orchestrator tests: `tests/test_services/test_retry_orchestrator_story_6_9.py` (retry field tests)
- Task factory: `tests/support/factories/task_factory.py` (create_task helper)

**Latest Best Practices (2026):**
- Python datetime with timezone awareness: https://docs.python.org/3/library/datetime.html#aware-and-naive-objects (always use UTC internally)
- SQLAlchemy atomic upsert: https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#insert-on-conflict-upsert (INSERT ON CONFLICT UPDATE)
- ISO week calculation: https://docs.python.org/3/library/datetime.html#datetime.date.isocalendar (Monday start weeks)

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

**IMPLEMENTATION COMPLETE - Manual Setup Required:**

All code implementation for Story 6.10 is complete. The following integration was added during code review:

1. ✅ **Integration Fix:** Added `mark_task_recovered()` call in `app/entrypoints.py:295-297` when tasks complete successfully after retry
2. ✅ **Status Fix:** Changed task completion status from string "completed" to `TaskStatus.PUBLISHED` enum
3. ✅ **Alert Type Fix:** Added "low_recovery_rate" to AlertType literal in alert_service.py for FR35 threshold alerts
4. ✅ **Verified:** error_category is set in schedule_retry() (line 188)
5. ✅ **Verified:** is_manual_retry field exists in Task model (line 608)

**⚠️ MANUAL SETUP REQUIRED - Weekly Metrics Calculation:**

The `calculate_all_channels_weekly_metrics()` function exists but requires a **scheduled job** to run automatically:

**Option 1: Railway Cron Job (Recommended)**
```yaml
# Add to railway.toml or Railway dashboard
[build]
builder = "nixpacks"

[deploy]
startCommand = "python -m app.worker"

[[crons]]
name = "weekly-metrics-calculation"
schedule = "0 0 * * MON"  # Every Monday at 00:00 UTC
command = "python -m scripts.calculate_weekly_metrics"
```

Create `scripts/calculate_weekly_metrics.py`:
```python
"""Weekly auto-recovery metrics calculation job.

Runs every Monday at 00:00 UTC to calculate previous week's metrics.
"""
import asyncio
from datetime import date, timedelta
from app.database import async_session_factory
from app.services.auto_recovery_metrics_service import (
    calculate_all_channels_weekly_metrics,
    get_week_starting_date
)

async def main():
    # Calculate metrics for previous week (ended Sunday)
    last_sunday = date.today() - timedelta(days=date.today().weekday() + 1)
    week_start = get_week_starting_date(last_sunday)

    async with async_session_factory() as db:
        metrics_list = await calculate_all_channels_weekly_metrics(
            week_starting_date=week_start,
            db=db
        )

    print(f"Calculated metrics for {len(metrics_list)} channels (week of {week_start})")

if __name__ == "__main__":
    asyncio.run(main())
```

**Option 2: Manual Invocation (For Testing)**
```python
# In Python REPL or admin script
from datetime import date, timedelta
from app.database import async_session_factory
from app.services.auto_recovery_metrics_service import calculate_all_channels_weekly_metrics, get_week_starting_date

# Calculate last week's metrics
last_monday = date.today() - timedelta(days=date.today().weekday() + 7)
async with async_session_factory() as db:
    metrics = await calculate_all_channels_weekly_metrics(last_monday, db)
```

**Option 3: Celery Beat (Future Enhancement)**
If Celery is added later:
```python
# In celerybeat_schedule
'calculate-weekly-metrics': {
    'task': 'app.tasks.calculate_weekly_metrics',
    'schedule': crontab(hour=0, minute=0, day_of_week=1),  # Monday 00:00 UTC
}
```

**Story Status:**
- Code: ✅ Complete (all tasks implemented)
- Integration: ✅ Complete (mark_task_recovered called from entrypoints)
- Tests: ✅ Complete (15+ comprehensive tests)
- Deployment: ⚠️ Pending (scheduled job setup required)

**Next Steps:**
1. Deploy code changes to Railway
2. Set up weekly cron job using Option 1 (Railway Cron)
3. Verify first metrics calculation runs on next Monday
4. Monitor Discord for <80% alerts

### File List

**New Files:**
1. `alembic/versions/20260123_2011_479d7df4f527_add_auto_recovery_tracking_fields_to_.py` - Migration to add auto_recovered, recovery_attempt_number, error_category fields to tasks table with performance indexes
2. `alembic/versions/20260123_2012_098f893ec56c_create_auto_recovery_metrics_table.py` - Migration to create auto_recovery_metrics table with composite PK and check constraints
3. `app/services/auto_recovery_metrics_service.py` - Core service for calculating weekly auto-recovery success rate, threshold alerting, and metrics aggregation (469 lines)
4. `tests/test_services/test_auto_recovery_metrics.py` - Comprehensive test suite with 15+ tests covering metrics calculation, alerting, and multi-channel scenarios (572 lines)

**Modified Files:**
1. `app/models.py` - Added auto_recovered, recovery_attempt_number, error_category fields to Task model (lines 619-642); Added complete AutoRecoveryMetrics model with composite PK (lines 1122-1292)
2. `app/services/retry_orchestrator.py` - Added mark_task_recovered() function to track successful auto-recovery (lines 518-580); Set error_category in schedule_retry() (line 188)
3. `app/entrypoints.py` - Added mark_task_recovered() call when tasks complete successfully after retry (lines 295-297); Changed status to TaskStatus.PUBLISHED (line 293)
4. `app/services/alert_service.py` - Added "low_recovery_rate" to AlertType literal for FR35 threshold alerts (line 24)
