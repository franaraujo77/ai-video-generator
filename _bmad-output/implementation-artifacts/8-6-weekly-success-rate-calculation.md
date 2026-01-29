# Story 8.6: Weekly Success Rate Calculation

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **system operator**,
I want **weekly metrics on overall pipeline success, auto-recovery effectiveness, and failure patterns**,
so that **I can monitor system health, identify recurring issues, and make data-driven optimization decisions**.

## Acceptance Criteria

### AC1: Weekly Metrics Calculation

**Given** a week of video processing has completed (Monday-Sunday)
**When** the weekly metrics job runs (Monday 00:00 UTC)
**Then** the following metrics are calculated and stored:
- Total videos processed (count of tasks that reached any terminal state)
- Overall success rate (% completed videos vs total attempted)
- Average processing time per video (end-to-end duration)
- Auto-recovery effectiveness (% of failed tasks that auto-recovered)
- Failure breakdown by category (TRANSIENT, PERMANENT, UNKNOWN)
- Failed videos by pipeline stage (asset_error, video_error, audio_error, upload_error)

**And** metrics are stored in `weekly_metrics` table with:
- `channel_id` (FK to channels)
- `week_starting_date` (Monday date, composite PK with channel_id)
- All metrics fields as nullable integers/decimals
- `calculated_at` timestamp (UTC)
- Composite primary key: (channel_id, week_starting_date)

### AC2: Success Rate Alerting

**Given** weekly metrics are calculated
**When** overall success rate falls below 90%
**Then** a Discord webhook alert is sent with:
- Channel name
- Week date range
- Success rate (percentage)
- Failure breakdown by category
- Most common failure stage
- Actionable investigation prompt

**And** alert includes comparison to previous week (trend indicator)
**And** alerts are rate-limited to max 1 per channel per week

### AC3: Historical Trend Analysis

**Given** multiple weeks of metrics exist
**When** trend reports are requested
**Then** the following analytics are available:
- Success rate trends over time (line chart data)
- Average processing time trends
- Auto-recovery rate trends
- Failure pattern changes (category distribution)
- Week-over-week comparisons

**And** trend data is queryable via API endpoints
**And** data spans minimum 4 weeks for meaningful analysis

## Tasks / Subtasks

- [x] Task 1: Create WeeklyMetrics Database Model (AC: 1)
  - [x] Add WeeklyMetrics model to app/models.py with all required fields
  - [x] Add foreign key relationship to Channel model
  - [x] Define composite primary key (channel_id, week_starting_date)
  - [x] Add indexes: (channel_id, week_starting_date DESC) for trend queries
  - [x] Add index on calculated_at for audit trail
  - [x] Write model unit tests (8-10 tests: validation, relationships, constraints)

- [x] Task 2: Create Alembic Migration (AC: 1)
  - [x] Generate migration: `alembic revision --autogenerate -m "Add weekly_metrics table"`
  - [x] Review migration SQL for correctness (composite PK, indexes, nullable columns)
  - [x] Test migration: up and down
  - [x] Verify foreign key constraints and cascade behavior
  - [x] Document migration in version file with Epic 8.6 reference

- [x] Task 3: Implement Weekly Metrics Service (AC: 1, 2)
  - [x] Create app/services/weekly_metrics_service.py
  - [x] Implement calculate_weekly_metrics(channel_id, week_starting_date) -> WeeklyMetrics
  - [x] Query Task table for week boundaries (updated_at timestamps)
  - [x] Calculate all metrics: success rate, processing time, auto-recovery, failure breakdown
  - [x] Use atomic upsert pattern (PostgreSQL INSERT ON CONFLICT UPDATE)
  - [x] Add helper function get_week_starting_date(target_date) -> date (ISO week Monday)
  - [x] Implement check_success_rate_thresholds(metrics) for alerting (AC2)
  - [x] Add calculate_all_channels_weekly_metrics(week_starting_date) for scheduler
  - [x] Write comprehensive service tests (15-20 tests covering all calculation logic)

- [x] Task 4: Integrate with Scheduler (AC: 1)
  - [x] Add weekly metrics job to app/scheduler.py
  - [x] Schedule for Monday 00:00 UTC (calculate previous week: Sunday ending)
  - [x] Job calls calculate_all_channels_weekly_metrics() for all active channels
  - [x] Add error handling with retries (job failure should not crash scheduler)
  - [x] Log job execution metrics (channels processed, duration, errors)
  - [x] Write scheduler integration tests (6 tests: lifecycle, job registration, config)

- [x] Task 5: Add Trend Analysis Query Functions (AC: 3)
  - [x] Add get_weekly_metrics(channel_id, week_starting_date) -> WeeklyMetrics | None (already done in Task 3)
  - [x] Add get_weekly_metrics_range(channel_id, start_date, end_date) -> list[WeeklyMetrics]
  - [x] Add get_success_rate_trend(channel_id, weeks=12) -> list[dict] (for charting)
  - [x] Add get_week_over_week_comparison(channel_id, week_date) -> dict (delta calculations)
  - [x] Add get_failure_pattern_analysis(channel_id, weeks=4) -> dict (category trends)
  - [x] Write integration tests for all query functions (12 tests)

- [x] Task 6: Create Reporting API Endpoints (AC: 3)
  - [x] Create app/routes/weekly_reports.py
  - [x] GET /api/v1/channels/{channel_id}/weekly-metrics - List weekly metrics with pagination
  - [x] GET /api/v1/channels/{channel_id}/weekly-metrics/{week_date} - Single week detail
  - [x] GET /api/v1/channels/{channel_id}/success-rate-trend - Trend analysis (12 weeks default)
  - [x] GET /api/v1/reports/weekly-summary - Cross-channel weekly summary
  - [x] Add Pydantic schemas for request validation and response formatting
  - [x] Register router in app/main.py
  - [x] Write API endpoint tests (12 tests: valid requests, error cases, edge cases)

- [x] Task 7: Discord Alerting Integration (AC: 2)
  - [x] Verify alert_service.py send_discord_alert() supports weekly metrics format
  - [x] Implement alert message formatting in check_success_rate_thresholds() (done in Task 3)
  - [x] Add week-over-week trend comparison to alert (done in Task 3)
  - [x] Add most common failure stage to alert message (done in Task 3)
  - [x] Test alert rate limiting (inherent via weekly schedule + 60s batching)
  - [x] Write alert integration tests (5 tests: trigger conditions, message format, missing webhook)

- [x] Task 8: Documentation & Validation (AC: 1, 2, 3)
  - [x] Document weekly_metrics table schema in models.py docstrings
  - [x] Document metrics calculation logic in service docstrings
  - [x] Document ISO week boundaries (Monday start, Sunday end)
  - [x] Document alerting thresholds and rate limiting
  - [x] Document API endpoints in routes docstrings
  - [x] Run all tests (62 tests passing - exceeds 55-65 target)
  - [x] Ready for code review and merge

## Dev Notes

### Critical Architectural Context

**Epic 8 Overview:**
- This is Story 8.6: "Weekly Success Rate Calculation" in Epic 8: "Monitoring, Observability & Cost Tracking"
- Builds on Story 8.1 (Structured Logging) for correlation IDs
- Complements Story 6.10 (Auto-Recovery Metrics) but focuses on overall pipeline health
- Provides high-level health monitoring for multi-channel production system

**System Architecture - Weekly Metrics Integration:**
```
┌──────────────────────────────────────────────────────────────┐
│ Weekly Metrics Calculation (Scheduled Job)                   │
│                                                                │
│  Monday 00:00 UTC Trigger (Scheduler)                        │
│    ↓                                                          │
│  calculate_all_channels_weekly_metrics()                     │
│    ↓                                                          │
│  For each active channel:                                    │
│    1. Query tasks table for previous week (Mon-Sun)         │
│    2. Calculate metrics:                                     │
│       - Total videos processed                               │
│       - Success rate (completed / total attempted)           │
│       - Avg processing time (created_at to updated_at)       │
│       - Auto-recovery rate (from retry fields)               │
│       - Failure breakdown (error_category counts)            │
│       - Failed videos by stage (status counts)               │
│    3. Atomic upsert to weekly_metrics table                  │
│    4. Check 90% threshold → Discord alert if below           │
│                                                                │
│  ┌──────────────────────────────────────────┐                │
│  │ PostgreSQL Database                      │                │
│  │                                           │                │
│  │  channels table                          │                │
│  │       ↑ FK relationship                  │                │
│  │  weekly_metrics table                    │                │
│  │    - channel_id, week_starting_date (PK) │                │
│  │    - total_videos_processed              │                │
│  │    - successful_videos                   │                │
│  │    - success_rate (percentage)           │                │
│  │    - avg_processing_time_seconds         │                │
│  │    - auto_recovery_rate                  │                │
│  │    - transient_failures                  │                │
│  │    - permanent_failures                  │                │
│  │    - unknown_failures                    │                │
│  │    - failed_at_assets                    │                │
│  │    - failed_at_video                     │                │
│  │    - failed_at_audio                     │                │
│  │    - failed_at_upload                    │                │
│  │    - calculated_at (timestamp)           │                │
│  └──────────────────────────────────────────┘                │
└──────────────────────────────────────────────────────────────┘
```

**Metrics Calculation Logic:**
1. **Week Boundaries**: ISO weeks (Monday 00:00:00 to Sunday 23:59:59.999999 UTC)
2. **Total Videos Processed**: Tasks with updated_at in week range (any terminal state)
3. **Success Rate**: (successful_videos / total_videos_processed) × 100
4. **Avg Processing Time**: AVG(updated_at - created_at) for completed tasks
5. **Auto-Recovery Rate**: Tasks with auto_recovered=True / tasks with retry_count > 0
6. **Failure Breakdown**: Count tasks by error_category (TRANSIENT, PERMANENT, UNKNOWN)
7. **Failed by Stage**: Count tasks by error status (asset_error, video_error, etc.)

**Atomic Upsert Pattern (Story 8.2, 6.10):**
```python
stmt = pg_insert(WeeklyMetrics).values(...)
stmt = stmt.on_conflict_do_update(
    index_elements=["channel_id", "week_starting_date"],
    set_={
        # Update all calculated fields
        "total_videos_processed": stmt.excluded.total_videos_processed,
        # ... (all other fields)
        "calculated_at": stmt.excluded.calculated_at,
        "updated_at": datetime.now(timezone.utc),
    },
)
await db.execute(stmt)
```

**Success Rate Alerting Logic:**
```python
if metrics.success_rate < 90.0:
    # Get week-over-week comparison
    prev_week_metrics = await get_weekly_metrics(
        channel_id, week_starting_date - timedelta(days=7), db
    )
    trend = (
        f"Down {prev_week_metrics.success_rate - metrics.success_rate:.1f}%"
        if prev_week_metrics and prev_week_metrics.success_rate > metrics.success_rate
        else "Stable or improving"
    )

    # Find most common failure stage
    failure_stages = {
        "asset_error": metrics.failed_at_assets,
        "video_error": metrics.failed_at_video,
        # ... etc
    }
    most_common_stage = max(failure_stages, key=failure_stages.get)

    await send_discord_alert(
        alert_type="low_success_rate",
        severity="WARNING",
        title=f"Weekly Success Rate {metrics.success_rate:.1f}% < 90% Target",
        description=f"Week {week_start} to {week_end}\nTrend: {trend}\nMost failures at: {most_common_stage}",
        # ... fields
    )
```

### Project Structure Notes

**Files to Create:**
1. `app/models.py` - Add WeeklyMetrics model (existing file, ~750 lines)
2. `app/services/weekly_metrics_service.py` - New service (similar to auto_recovery_metrics_service.py)
3. `app/routes/weekly_reports.py` - New API routes (similar to cost_reports.py)
4. `alembic/versions/XXXX_add_weekly_metrics_table.py` - New migration

**Files to Modify:**
1. `app/utils/scheduler.py` - Add weekly metrics job registration
2. `app/main.py` - Register weekly_reports router

**Testing Files:**
1. `tests/test_models/test_weekly_metrics.py` - Model tests
2. `tests/test_services/test_weekly_metrics_service.py` - Service tests
3. `tests/test_routes/test_weekly_reports.py` - API endpoint tests
4. `tests/test_workers/test_scheduler_integration.py` - Scheduler integration tests (may need to create)

**Alignment with Epic 8 Patterns:**
- Follows Story 6.10 (AutoRecoveryMetrics) pattern: composite PK, atomic upsert, threshold alerting
- Follows Story 8.2 (Cost Tracking) pattern: aggregate metrics, trend analysis, API endpoints
- Follows Story 8.5 (Workspace Cleanup) pattern: scheduler integration, lifecycle management
- Consistent with Story 8.1: correlation IDs in logs, structured logging
- Consistent with Story 6.6: Discord alerting for threshold violations

### Database Schema Details

**WeeklyMetrics Model Fields:**
```python
class WeeklyMetrics(Base):
    __tablename__ = "weekly_metrics"

    # Composite Primary Key
    channel_id: Mapped[UUID] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), primary_key=True
    )
    week_starting_date: Mapped[date] = mapped_column(
        Date, primary_key=True, comment="Monday of ISO week"
    )

    # Volume Metrics
    total_videos_processed: Mapped[int] = mapped_column(
        Integer, default=0, comment="Tasks reaching any terminal state"
    )
    successful_videos: Mapped[int] = mapped_column(
        Integer, default=0, comment="Tasks reaching 'published' status"
    )
    success_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=0.0, comment="Percentage (0.00-100.00)"
    )

    # Performance Metrics
    avg_processing_time_seconds: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Average end-to-end duration"
    )

    # Recovery Metrics
    auto_recovery_rate: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True, comment="% of failed tasks that recovered"
    )

    # Failure Breakdown by Category
    transient_failures: Mapped[int] = mapped_column(
        Integer, default=0, comment="error_category=TRANSIENT count"
    )
    permanent_failures: Mapped[int] = mapped_column(
        Integer, default=0, comment="error_category=PERMANENT count"
    )
    unknown_failures: Mapped[int] = mapped_column(
        Integer, default=0, comment="error_category=UNKNOWN count"
    )

    # Failure Breakdown by Stage
    failed_at_assets: Mapped[int] = mapped_column(
        Integer, default=0, comment="Tasks with status=asset_error"
    )
    failed_at_video: Mapped[int] = mapped_column(
        Integer, default=0, comment="Tasks with status=video_error"
    )
    failed_at_audio: Mapped[int] = mapped_column(
        Integer, default=0, comment="Tasks with status=audio_error"
    )
    failed_at_upload: Mapped[int] = mapped_column(
        Integer, default=0, comment="Tasks with status=upload_error"
    )

    # Audit Timestamps
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="When metrics were calculated"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationship
    channel: Mapped["Channel"] = relationship(back_populates="weekly_metrics")

    # Indexes
    __table_args__ = (
        Index("ix_weekly_metrics_channel_week_desc", "channel_id", "week_starting_date",
              postgresql_ops={"week_starting_date": "DESC"}),  # For trend queries
        Index("ix_weekly_metrics_calculated_at", "calculated_at"),  # For audit trail
    )
```

**Channel Model Update:**
```python
# Add to Channel model
weekly_metrics: Mapped[list["WeeklyMetrics"]] = relationship(
    back_populates="channel", cascade="all, delete-orphan"
)
```

### Testing Standards

**Test Coverage Requirements (Epic 8 Standard):**
- Model tests: 8-10 tests (field validation, relationships, constraints, __repr__)
- Service tests: 15-20 tests (all calculation logic, edge cases, error handling)
- Integration tests: 8-10 tests (database persistence, atomic upsert, query functions)
- API endpoint tests: 8-10 tests (valid requests, validation errors, edge cases)
- Scheduler tests: 4-5 tests (job registration, execution, error handling)
- **Total Target**: 55-65 tests passing

**Test Patterns from Epic 8:**
1. **Async Fixtures**: Use `async_session` fixture for database tests
2. **Factory Pattern**: Use create_channel(), create_task() helpers
3. **Monkeypatch**: Use for context variables (correlation_id)
4. **Parametrize**: Use for testing multiple scenarios
5. **Integration Tests**: Test full flow (calculate → upsert → query → alert)
6. **Edge Cases**: Zero division (no tasks), null handling, week boundaries
7. **Concurrent Safety**: Test atomic upsert with concurrent calls

**Example Test Structure:**
```python
# tests/test_services/test_weekly_metrics_service.py

@pytest.mark.asyncio
class TestCalculateWeeklyMetrics:
    async def test_calculate_metrics_success_rate(self, async_session):
        """Test success rate calculation with mixed outcomes."""
        # Setup: Create channel and tasks
        channel = create_channel(channel_id="test1")
        async_session.add(channel)
        await async_session.commit()

        week_start = date(2026, 1, 20)  # Monday

        # Create 10 tasks: 8 successful, 2 failed
        for i in range(8):
            task = create_task(channel_id=channel.id, status=TaskStatus.PUBLISHED)
            task.updated_at = datetime(2026, 1, 21 + i, tzinfo=timezone.utc)
            async_session.add(task)

        for i in range(2):
            task = create_task(channel_id=channel.id, status=TaskStatus.ASSET_ERROR)
            task.updated_at = datetime(2026, 1, 25 + i, tzinfo=timezone.utc)
            async_session.add(task)

        await async_session.commit()

        # Execute
        metrics = await calculate_weekly_metrics(channel.id, week_start, async_session)

        # Assert
        assert metrics.total_videos_processed == 10
        assert metrics.successful_videos == 8
        assert metrics.success_rate == Decimal("80.00")
        assert metrics.failed_at_assets == 2

    async def test_week_boundary_calculation(self, async_session):
        """Test ISO week boundary handling (Monday-Sunday)."""
        # Test that Sunday task is included in week
        # Test that next Monday task is excluded
        pass

    async def test_atomic_upsert_concurrent(self, async_session):
        """Test multiple concurrent calculations don't lose data."""
        # Simulate concurrent calls with same channel/week
        pass
```

### Architectural Decisions from Epic 8

**AD1: Composite Primary Keys for Time-Series Data (Story 8.2, 6.10)**
- Rationale: Natural uniqueness (channel + week), efficient queries, prevents duplicates
- Implementation: (channel_id, week_starting_date) as composite PK
- Index strategy: Add DESC index for trend queries (most recent first)

**AD2: Decimal Precision for Percentages (Story 8.2, 6.10)**
- Rationale: Numeric(5,2) stores percentages with 2 decimal precision (0.00-100.00)
- Avoid Float for financial/percentage data (precision loss)
- Example: 85.37% stored as Decimal("85.37")

**AD3: Nullable Metrics for Incomplete Data (Story 8.2, 6.10)**
- Rationale: avg_processing_time_seconds may be null if no completed tasks
- auto_recovery_rate may be null if no retry attempts
- Explicit nullability better than zero for "no data" vs "zero value"

**AD4: Atomic Upsert Pattern (Story 6.8, 6.10, 8.2)**
- Rationale: PostgreSQL INSERT ON CONFLICT UPDATE prevents race conditions
- Multiple workers can calculate metrics concurrently safely
- Pattern: `on_conflict_do_update(index_elements=[PK], set_={...})`

**AD5: ISO Week Boundaries (Story 6.10)**
- Rationale: Monday-Sunday weeks align with business reporting
- Use Python datetime.weekday() (Monday=0, Sunday=6)
- Helper function: get_week_starting_date(target_date) -> date

**AD6: Threshold Alerting with Rate Limiting (Story 6.6, 6.10)**
- Rationale: Alert only when actionable (< 90% threshold)
- Rate limit: Max 1 alert per channel per week (via calculated_at)
- Include trend comparison and actionable investigation prompts

### References

**Architecture Patterns:**
- [Source: app/services/auto_recovery_metrics_service.py] - Composite PK, atomic upsert, threshold alerting
- [Source: app/services/cost_tracker.py] - Aggregate metrics, query functions, API endpoints
- [Source: app/utils/scheduler.py] - Job registration, lifecycle integration (Story 8.5)
- [Source: app/services/alert_service.py] - Discord webhook alerting (Story 6.6)

**Database Patterns:**
- [Source: app/models.py:AutoRecoveryMetrics] - Composite PK, Decimal precision, nullable fields
- [Source: app/models.py:VideoCost] - Composite PK with timestamp, foreign key relationships
- [Source: alembic/versions/*_add_auto_recovery_metrics.py] - Migration structure

**Testing Patterns:**
- [Source: tests/test_services/test_auto_recovery_metrics_service.py] - Service test structure
- [Source: tests/test_services/test_cost_tracker.py] - Integration test patterns
- [Source: tests/test_routes/test_cost_reports.py] - API endpoint test structure

**Scheduler Integration:**
- [Source: app/utils/scheduler.py] - Job registration with APScheduler (Story 8.5)
- [Source: app/workers/main.py] - Scheduler lifecycle management

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.5 (claude-sonnet-4-5-20250929)

### Debug Log References

(To be filled during implementation)

### Completion Notes List

**Task 1 & 2 Complete (2026-01-28)**:
- ✅ Created WeeklyMetrics model in app/models.py with comprehensive docstrings
- ✅ Implemented composite primary key (channel_id, week_starting_date)
- ✅ Added all required fields with proper types (Decimal for percentages, Integer for counts)
- ✅ Added nullable fields for incomplete data (avg_processing_time_seconds, auto_recovery_rate)
- ✅ Added relationship to Channel model with cascade delete
- ✅ Implemented 11 check constraints for data integrity
- ✅ Added DESC index on week_starting_date for efficient trend queries
- ✅ Wrote 9 comprehensive model tests (all passing)
- ✅ Created Alembic migration (53568460d196) with complete upgrade/downgrade logic
- ✅ Fixed migration chain issue (updated down_revision in 20260127_2300)
- ✅ Migration follows AutoRecoveryMetrics pattern for consistency

**Code Review Fixes Complete (2026-01-28)**:
- ✅ Fixed Issue #1-2: Removed UPLOAD_ERROR_RETRYING from failed_at_upload count (consistency fix)
- ✅ Verified Issue #3-4: cascade="all, delete-orphan" and __repr__ already present (false positives)
- ✅ Fixed Issue #5: Added start_weekly_metrics_scheduler() to app/worker.py startup (CRITICAL)
- ✅ Fixed Issue #6: Added weekly_metrics_scheduler status to /health endpoint
- ✅ Fixed Issue #7: Documented CANCELLED tasks edge case in metrics calculation
- ✅ Fixed Issue #8: Updated story status from "ready-for-dev" to "in-progress"
- ✅ Fixed Issue #9: Corrected "fire-and-forget" comment (now "awaits completion")
- ✅ Fixed Issue #10: Router registration works (resolved by fixing Issue #5)
- ✅ Fixed Issue #11: Added date normalization message to 404 error responses
- ✅ Fixed Issue #12: Replaced type: ignore with lambda for type-safe max() calls
- 🎯 All 70 tests passing, scheduler integration complete, ready for final validation

### File List

**Modified Files:**
- app/models.py - Added WeeklyMetrics model and Channel.weekly_metrics relationship
- app/services/weekly_metrics_service.py - Weekly metrics calculation service with threshold alerting
- app/routes/weekly_reports.py - API endpoints for weekly metrics and trend analysis
- app/scheduler.py - Weekly metrics scheduler (Monday 00:00 UTC)
- app/worker.py - Integrated weekly metrics scheduler startup/shutdown
- app/main.py - Registered weekly_reports router and updated health check
- alembic/versions/20260127_2300_add_cleanup_performed_at.py - Fixed down_revision reference

**Created Files:**
- tests/test_models/test_weekly_metrics.py - 9 model tests
- tests/test_services/test_weekly_metrics_service.py - 16 service tests
- tests/test_services/test_weekly_metrics_alerting.py - 5 alerting tests
- tests/test_services/test_weekly_metrics_trend_analysis.py - 12 trend analysis tests
- tests/test_routes/test_weekly_reports.py - 12 API endpoint tests
- tests/test_scheduler_weekly_metrics.py - 6 scheduler tests
- alembic/versions/20260128_0848_53568460d196_add_weekly_metrics_table_story_8_6.py - Migration for weekly_metrics table
