# Story 8.5: Temporary File Cleanup - Implementation Summary

**Status**: Review (Ready for Code Review)
**Completed**: 2026-01-27
**Test Coverage**: 16/16 tests passing

## Overview

Implemented daily workspace cleanup to prevent unbounded disk growth on Railway persistent volumes. The system automatically deletes workspace directories for completed tasks (PUBLISHED/CANCELLED) older than the retention period while preserving in-progress and error state tasks for debugging.

## Completed Tasks

### ✅ Task 1: Daily Cleanup Scheduler
- **File**: `app/scheduler.py` (lines 242-397)
- **Integration**: `app/worker.py` (lines 460, 500, 547, 552)
- **Implementation**:
  - Added cleanup scheduler following Story 7.0 APScheduler pattern
  - Implemented `_cleanup_old_workspaces_job()` scheduled function
  - Implemented `start_cleanup_scheduler()` with configurable cron schedule
  - Implemented `shutdown_cleanup_scheduler()` for graceful shutdown
  - Implemented `is_cleanup_scheduler_running()` health check
  - Integrated into worker startup/shutdown lifecycle
  - Default schedule: 3am Pacific Time daily (configurable)

### ✅ Task 2: Workspace Cleanup Service
- **File**: `app/services/workspace_cleanup.py` (310 lines)
- **Tests**: `tests/test_services/test_workspace_cleanup.py` (11 tests passing)
- **Implementation**:
  - Created `WorkspaceCleanupService` with session_factory injection
  - Implemented short transaction pattern: Query → Close DB → Delete → New DB → Update
  - Eligible task query: PUBLISHED/CANCELLED older than retention period
  - Skips: IN_PROGRESS, REVIEW_GATE, ERROR state tasks
  - Workspace deletion with disk space calculation
  - R2 asset cleanup integration for storage_strategy="r2" channels
  - Comprehensive error handling (FileNotFoundError, PermissionError)
  - Structured logging with correlation IDs
  - Metrics reporting (directories_cleaned, disk_freed_mb, r2_assets_deleted, duration_seconds)

**Key Technical Decisions**:
- **Eager Loading**: `selectinload(Task.channel)` to avoid detached instance errors
- **SQL Updates**: Direct `update()` instead of ORM merge() to bypass status validation
- **Session Factory Injection**: Testability pattern for creating new sessions during cleanup
- **Idempotent Design**: Handles nonexistent directories, already-cleaned tasks gracefully

### ✅ Task 4: Cleanup Tracking Schema
- **File**: `app/models.py` (line ~870)
- **Migration**: `alembic/versions/20260127_2300_add_cleanup_performed_at.py`
- **Tests**: `tests/test_models/test_task_cleanup_tracking.py` (5 tests passing)
- **Implementation**:
  - Added `cleanup_performed_at: Mapped[datetime | None]` to Task model
  - Created indexed column for efficient "uncleaned tasks" queries
  - Alembic migration with upgrade/downgrade functions
  - Tests verify field existence, timestamp setting, query filtering, timezone awareness

### ✅ Task 5: Cleanup Configuration
- **File**: `app/config.py` (lines 445-505)
- **Implementation**:
  - `get_workspace_cleanup_enabled()` - Enable/disable cleanup (default: true)
  - `get_workspace_cleanup_retention_days()` - Retention period (default: 7 days, clamped 1-365)
  - `get_workspace_cleanup_schedule()` - Cron schedule (default: "0 3 * * *")
  - Updated module docstring with new environment variables

**Environment Variables**:
```bash
WORKSPACE_CLEANUP_ENABLED=true              # Enable daily cleanup
WORKSPACE_CLEANUP_RETENTION_DAYS=7          # Keep files for 7 days
WORKSPACE_CLEANUP_SCHEDULE="0 3 * * *"      # Daily at 3am Pacific
```

## Pending Tasks

### Task 3: R2 Bulk Delete Optimization (OPTIONAL)
- Not required for story completion
- Current implementation deletes R2 assets one-by-one
- Future optimization: Implement `R2StorageClient.bulk_delete_assets()` batch API

### Task 6: Integration Tests & Documentation (REVIEW PHASE)
- Integration test: Full cleanup cycle
- Integration test: Error state preservation
- Integration test: R2 cleanup
- Integration test: Metrics reporting
- Architecture documentation
- Deployment guide updates

## Test Coverage

**Total**: 16 tests passing

**Model Tests** (`test_task_cleanup_tracking.py`): 5 tests
- Field existence and accessibility
- Timestamp setting and persistence
- Query filtering (cleanup_performed_at IS NULL)
- Timezone awareness (SQLite vs PostgreSQL)
- Index existence verification

**Service Tests** (`test_workspace_cleanup.py`): 11 tests
- Cleanup published tasks older than retention
- Skip in-progress tasks (CLAIMED, GENERATING_ASSETS, etc.)
- Skip error state tasks (ASSET_ERROR, VIDEO_ERROR, etc.)
- Skip recently completed tasks (within retention period)
- Skip already-cleaned tasks (idempotent)
- Handle nonexistent workspace directories
- Handle permission errors gracefully
- Cleanup cancelled tasks
- Disk space calculation accuracy
- Multiple tasks cleanup (atomic operations)
- Custom retention period configuration

## Architecture Highlights

### Short Transaction Pattern
```python
# Query eligible tasks (short transaction)
tasks = await db.execute(select(Task).options(selectinload(Task.channel)).where(...))

# Close DB before file operations
await db.close()

# Delete files (long-running, no DB lock)
for task in tasks:
    await self._cleanup_task_workspace(task)

# Update DB with cleanup timestamp (new transaction)
async with self._session_factory() as db_update:
    await db_update.execute(update(Task).where(...).values(cleanup_performed_at=...))
    await db_update.commit()
```

### Eligibility Logic
```python
# Eligible: PUBLISHED/CANCELLED older than retention period, not already cleaned
eligible_tasks = await db.execute(
    select(Task)
    .options(selectinload(Task.channel))
    .where(
        Task.status.in_([TaskStatus.PUBLISHED, TaskStatus.CANCELLED]),
        Task.updated_at < cutoff_date,
        Task.cleanup_performed_at.is_(None)
    )
    .order_by(Task.updated_at.asc())
)
```

### R2 Storage Integration
```python
# Delete R2 assets if storage_strategy="r2"
if task.channel.storage_strategy == "r2":
    r2_assets = await db.execute(
        select(AssetMetadata).where(
            AssetMetadata.task_id == task.id,
            AssetMetadata.storage_strategy == "r2"
        )
    )
    for asset in r2_assets:
        r2_key = extract_r2_key_from_url(asset.asset_url)
        await r2_client.delete_asset(r2_key)
```

## Files Changed

### New Files (3)
1. `app/services/workspace_cleanup.py` - Core cleanup service (310 lines)
2. `alembic/versions/20260127_2300_add_cleanup_performed_at.py` - Migration
3. `tests/test_services/test_workspace_cleanup.py` - Service tests (11 tests)
4. `tests/test_models/test_task_cleanup_tracking.py` - Model tests (5 tests)

### Modified Files (4)
1. `app/models.py` - Added cleanup_performed_at field
2. `app/scheduler.py` - Added cleanup scheduler functions (~160 lines)
3. `app/worker.py` - Integrated cleanup scheduler startup/shutdown
4. `app/config.py` - Added cleanup configuration functions

## Next Steps

1. **Code Review**: Run `/bmad:bmm:workflows:code-review 8.5` for adversarial review
2. **Integration Tests**: Implement Task 6 integration tests
3. **Documentation**: Update architecture and deployment guides
4. **Deployment**: Apply Alembic migration to production database
5. **Monitoring**: Verify daily cleanup job logs and metrics

## Dependencies

- **Story 8.1**: Structured logging with correlation IDs ✅
- **Story 8.3**: AssetMetadata model for R2 asset tracking ✅
- **Story 8.4**: R2StorageClient for R2 asset deletion ✅
- **Story 7.0**: APScheduler pattern for daily jobs ✅
- **project-context.md**: Filesystem helpers for workspace paths ✅

## Acceptance Criteria Status

- ✅ **AC1**: Published Task Cleanup - Tasks older than 7 days are deleted
- ✅ **AC2**: In-Progress Task Preservation - Active tasks are preserved
- ✅ **AC3**: Error State File Preservation - Error tasks preserved for debugging
- ✅ **AC4**: Cleanup Logging and Metrics - Structured logs with metrics

---

**Ready for Code Review**: All core tasks complete, 16 tests passing, story meets all acceptance criteria.
