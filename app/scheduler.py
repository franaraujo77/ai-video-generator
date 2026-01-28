"""APScheduler configuration for daily scheduled jobs.

Configures timezone-aware cron jobs that run at specific times in Pacific Time.
Jobs include quota resets and workspace cleanup.

Key Features:
- Runs at configured times in America/Los_Angeles timezone
- Misfire grace time: 60 seconds (skip if worker down at scheduled time)
- Jobs re-register on worker restart (in-memory scheduler)
- Graceful shutdown on worker termination

Usage:
    >>> from app.scheduler import start_quota_reset_scheduler, start_cleanup_scheduler
    >>> await start_quota_reset_scheduler()
    >>> await start_cleanup_scheduler()
    >>> # ... worker runs ...
    >>> shutdown_quota_reset_scheduler()
    >>> shutdown_cleanup_scheduler()
"""

import os
from collections.abc import Awaitable, Callable
from datetime import date, datetime
from zoneinfo import ZoneInfo

import structlog
from apscheduler.schedulers.asyncio import (  # type: ignore[import-untyped, import-not-found, unused-ignore]
    AsyncIOScheduler,
)
from apscheduler.triggers.cron import (  # type: ignore[import-untyped, import-not-found, unused-ignore]
    CronTrigger,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.services.quota_reset_service import reset_gemini_quotas, reset_youtube_quotas

# Get logger
log = structlog.get_logger()

# Quota timezone (Pacific Time for YouTube and Gemini APIs)
QUOTA_TIMEZONE = os.getenv("QUOTA_TIMEZONE", "America/Los_Angeles")

# Global scheduler instance
_scheduler: AsyncIOScheduler | None = None


async def _reset_quota_job(
    service_name: str,
    reset_func: Callable[[date, AsyncSession], Awaitable[int]],
    quota_table: str,
    usage_field: str,
    daily_limit: int,
    exhausted_flag: str,
) -> None:
    """Generic scheduled job to reset API quotas at midnight Pacific Time.

    This is a DRY refactor to eliminate code duplication between YouTube and Gemini jobs.

    Args:
        service_name: Service identifier ("youtube" or "gemini")
        reset_func: Async function to call (reset_youtube_quotas or reset_gemini_quotas)
        quota_table: SQL table name for quota usage
        usage_field: SQL field name for usage tracking
        daily_limit: Daily quota limit value
        exhausted_flag: Channel field name for exhausted flag

    Error Handling:
        - Catches all exceptions
        - Logs CRITICAL error with manual fallback SQL commands
        - TODO: Send Discord alert on failure (Story 8.x)
    """
    # Get today's date in Pacific timezone
    pacific_tz = ZoneInfo(QUOTA_TIMEZONE)
    today = datetime.now(pacific_tz).date()

    # Create database session
    async with AsyncSessionLocal() as db:  # type: ignore[misc]
        try:
            reset_count = await reset_func(today, db)
            log.info(
                f"{service_name}_quota_reset_job_success",
                reset_count=reset_count,
                date=str(today),
                timezone=QUOTA_TIMEZONE,
            )
        except Exception as e:
            log.error(
                f"{service_name}_quota_reset_job_failed",
                error=str(e),
                date=str(today),
                timezone=QUOTA_TIMEZONE,
                exc_info=True,
            )

            # Log CRITICAL error with manual fallback instructions
            # TODO: Send Discord alert (Story 8.x)
            log.critical(
                f"{service_name}_quota_reset_requires_manual_intervention",
                service=service_name,
                date=str(today),
                timezone=QUOTA_TIMEZONE,
                manual_sql=(
                    f"-- Reset {service_name.title()} quotas for all active channels\n"
                    f"INSERT INTO {quota_table} (channel_id, date, {usage_field}, daily_limit)\n"
                    f"SELECT id, '{today}', 0, {daily_limit}\n"
                    f"FROM channels WHERE is_active = true\n"
                    f"ON CONFLICT (channel_id, date) DO NOTHING;\n"
                    f"UPDATE channels SET {exhausted_flag} = false WHERE is_active = true;"
                ),
            )

            # Don't re-raise to prevent scheduler crash
            # Manual intervention required


async def _reset_youtube_quotas_job() -> None:
    """Scheduled job to reset YouTube quotas at midnight Pacific Time."""
    await _reset_quota_job(
        service_name="youtube",
        reset_func=reset_youtube_quotas,
        quota_table="youtube_quota_usage",
        usage_field="units_used",
        daily_limit=10000,
        exhausted_flag="youtube_quota_exhausted",
    )


async def _reset_gemini_quotas_job() -> None:
    """Scheduled job to reset Gemini quotas at midnight Pacific Time."""
    await _reset_quota_job(
        service_name="gemini",
        reset_func=reset_gemini_quotas,
        quota_table="gemini_quota_usage",
        usage_field="requests_used",
        daily_limit=1500,
        exhausted_flag="gemini_quota_exhausted",
    )


async def start_quota_reset_scheduler() -> None:
    """Start APScheduler with daily quota reset jobs.

    Registers two jobs:
    1. YouTube quota reset at midnight Pacific Time
    2. Gemini quota reset at midnight Pacific Time

    Configuration:
    - Timezone: America/Los_Angeles (configurable via QUOTA_TIMEZONE env var)
    - Trigger: Cron (hour=0, minute=0)
    - Misfire grace time: 60 seconds (skip if worker down >60s past midnight)
    - Replace existing: True (prevent duplicates on restart)

    Example:
        >>> await start_quota_reset_scheduler()
        >>> # Scheduler running, jobs will fire at midnight PST
    """
    global _scheduler

    if _scheduler is not None and _scheduler.running:
        log.warning("quota_reset_scheduler_already_running")
        return

    # Create scheduler with Pacific timezone
    _scheduler = AsyncIOScheduler(timezone=QUOTA_TIMEZONE)

    # Add YouTube quota reset job (daily at midnight Pacific)
    _scheduler.add_job(
        _reset_youtube_quotas_job,
        trigger=CronTrigger(hour=0, minute=0, timezone=QUOTA_TIMEZONE),
        id="reset_youtube_quotas",
        replace_existing=True,  # Prevent duplicates on restart
        misfire_grace_time=60,  # Skip if more than 60s late
    )

    # Add Gemini quota reset job (daily at midnight Pacific)
    _scheduler.add_job(
        _reset_gemini_quotas_job,
        trigger=CronTrigger(hour=0, minute=0, timezone=QUOTA_TIMEZONE),
        id="reset_gemini_quotas",
        replace_existing=True,  # Prevent duplicates on restart
        misfire_grace_time=60,  # Skip if more than 60s late
    )

    # Start scheduler
    _scheduler.start()

    log.info(
        "quota_reset_scheduler_started",
        timezone=QUOTA_TIMEZONE,
        jobs=["reset_youtube_quotas", "reset_gemini_quotas"],
        next_youtube_run=str(_scheduler.get_job("reset_youtube_quotas").next_run_time),
        next_gemini_run=str(_scheduler.get_job("reset_gemini_quotas").next_run_time),
    )


def shutdown_quota_reset_scheduler() -> None:
    """Gracefully shut down the quota reset scheduler.

    Stops the scheduler and waits for running jobs to complete.
    Called on worker termination.

    Example:
        >>> shutdown_quota_reset_scheduler()
        >>> # Scheduler stopped, no more jobs will run
    """
    global _scheduler

    if _scheduler is None or not _scheduler.running:
        log.warning("quota_reset_scheduler_not_running")
        return

    try:
        _scheduler.shutdown(wait=True)
    except RuntimeError as e:
        # Handle "Event loop is closed" error during test teardown
        if "Event loop is closed" in str(e):
            log.debug("scheduler_shutdown_event_loop_closed", error=str(e))
        else:
            raise
    finally:
        _scheduler = None

    log.info("quota_reset_scheduler_shutdown")


def is_scheduler_running() -> bool:
    """Check if quota reset scheduler is running.

    Used for health check endpoint.

    Returns:
        True if scheduler is running, False otherwise

    Example:
        >>> is_scheduler_running()
        True
    """
    return _scheduler is not None and _scheduler.running


# Global cleanup scheduler instance (Story 8.5)
_cleanup_scheduler: AsyncIOScheduler | None = None


async def _cleanup_old_workspaces_job() -> None:
    """Scheduled job to cleanup old workspace files at 3am Pacific Time (Story 8.5)."""
    # Get configuration from config module (validated and clamped)
    from app.config import get_workspace_cleanup_retention_days

    retention_days = get_workspace_cleanup_retention_days()

    log.info("workspace_cleanup_job_started", retention_days=retention_days)

    from app.services.workspace_cleanup import WorkspaceCleanupService

    # Create database session
    async with AsyncSessionLocal() as db:  # type: ignore[misc]
        try:
            cleanup_service = WorkspaceCleanupService()
            result = await cleanup_service.cleanup_old_workspaces(db, retention_days)

            log.info(
                "workspace_cleanup_job_success",
                directories_cleaned=result["directories_cleaned"],
                disk_freed_mb=result["disk_freed_mb"],
                r2_assets_deleted=result["r2_assets_deleted"],
                duration_seconds=result["duration_seconds"],
                retention_days=retention_days,
            )
        except Exception as e:
            log.error(
                "workspace_cleanup_job_failed",
                error=str(e),
                retention_days=retention_days,
                exc_info=True,
            )

            # Log CRITICAL error for manual intervention
            # TODO: Send Discord alert (Story 8.x)
            log.critical(
                "workspace_cleanup_requires_manual_intervention",
                retention_days=retention_days,
                error=str(e),
                manual_action="Check workspace disk usage and manually run cleanup if needed",
            )

            # Don't re-raise to prevent scheduler crash
            # Manual intervention required


async def start_cleanup_scheduler() -> None:
    """Start APScheduler with daily workspace cleanup job (Story 8.5).

    Registers cleanup job that runs at 3am Pacific Time daily to remove
    old workspace files for completed tasks.

    Configuration:
    - Timezone: America/Los_Angeles (configurable via QUOTA_TIMEZONE env var)
    - Default Schedule: 3am daily (0 3 * * * cron format)
    - Configurable via WORKSPACE_CLEANUP_SCHEDULE env var
    - Retention: 7 days default (configurable via WORKSPACE_CLEANUP_RETENTION_DAYS)
    - Misfire grace time: 60 seconds (skip if worker down >60s past 3am)
    - Replace existing: True (prevent duplicates on restart)

    Example:
        >>> await start_cleanup_scheduler()
        >>> # Scheduler running, cleanup job will fire at 3am PST
    """
    global _cleanup_scheduler

    if _cleanup_scheduler is not None and _cleanup_scheduler.running:
        log.warning("cleanup_scheduler_already_running")
        return

    # Get configuration from config module (validated)
    from app.config import (
        get_workspace_cleanup_enabled,
        get_workspace_cleanup_retention_days,
        get_workspace_cleanup_schedule,
    )

    # Check if cleanup is enabled
    if not get_workspace_cleanup_enabled():
        log.info("cleanup_scheduler_disabled", reason="WORKSPACE_CLEANUP_ENABLED=false")
        return

    # Parse cron schedule from environment (default: 3am daily)
    schedule = get_workspace_cleanup_schedule()
    retention_days = get_workspace_cleanup_retention_days()

    # Parse cron schedule (minute hour day month day_of_week)
    parts = schedule.split()
    if len(parts) < 2:
        log.error("invalid_cleanup_schedule", schedule=schedule, reason="too_few_parts")
        return

    try:
        minute, hour = int(parts[0]), int(parts[1])
    except ValueError as e:
        log.error(
            "invalid_cleanup_schedule",
            schedule=schedule,
            reason="invalid_integer_values",
            error=str(e),
        )
        return

    # Create scheduler with Pacific timezone
    _cleanup_scheduler = AsyncIOScheduler(timezone=QUOTA_TIMEZONE)

    # Add workspace cleanup job (daily at 3am Pacific by default)
    _cleanup_scheduler.add_job(
        _cleanup_old_workspaces_job,
        trigger=CronTrigger(hour=hour, minute=minute, timezone=QUOTA_TIMEZONE),
        id="cleanup_old_workspaces",
        replace_existing=True,  # Prevent duplicates on restart
        misfire_grace_time=60,  # Skip if more than 60s late
    )

    # Start scheduler
    _cleanup_scheduler.start()

    log.info(
        "cleanup_scheduler_started",
        timezone=QUOTA_TIMEZONE,
        schedule=schedule,
        retention_days=retention_days,
        next_run=str(_cleanup_scheduler.get_job("cleanup_old_workspaces").next_run_time),
    )


def shutdown_cleanup_scheduler() -> None:
    """Gracefully shut down the workspace cleanup scheduler (Story 8.5).

    Stops the scheduler and waits for running jobs to complete.
    Called on worker termination.

    Example:
        >>> shutdown_cleanup_scheduler()
        >>> # Scheduler stopped, no more cleanup jobs will run
    """
    global _cleanup_scheduler

    if _cleanup_scheduler is None or not _cleanup_scheduler.running:
        log.warning("cleanup_scheduler_not_running")
        return

    try:
        _cleanup_scheduler.shutdown(wait=True)
    except RuntimeError as e:
        # Handle "Event loop is closed" error during test teardown
        if "Event loop is closed" in str(e):
            log.debug("cleanup_scheduler_shutdown_event_loop_closed", error=str(e))
        else:
            raise
    finally:
        _cleanup_scheduler = None

    log.info("cleanup_scheduler_shutdown")


def is_cleanup_scheduler_running() -> bool:
    """Check if workspace cleanup scheduler is running (Story 8.5).

    Used for health check endpoint.

    Returns:
        True if scheduler is running, False otherwise

    Example:
        >>> is_cleanup_scheduler_running()
        True
    """
    return _cleanup_scheduler is not None and _cleanup_scheduler.running


# Global weekly metrics scheduler instance (Story 8.6)
_weekly_metrics_scheduler: AsyncIOScheduler | None = None


async def _calculate_weekly_metrics_job() -> None:
    """Scheduled job to calculate weekly metrics at Monday 00:00 UTC (Story 8.6).

    Calculates metrics for the week that just ended (previous Monday to Sunday).
    When this job runs on Monday at 00:00, it calculates metrics for the week
    starting 7 days ago.

    Example:
        - Job runs: Monday Jan 26, 2026 at 00:00 UTC
        - Calculates week: Monday Jan 19 to Sunday Jan 25
        - week_starting_date: Jan 19 (7 days ago)
    """
    from datetime import timedelta

    # Get today's date in UTC
    from datetime import timezone as tz

    from app.services.weekly_metrics_service import calculate_all_channels_weekly_metrics

    today = datetime.now(tz.utc).date()

    # Calculate week_starting_date (7 days ago = previous Monday)
    week_starting_date = today - timedelta(days=7)

    log.info(
        "weekly_metrics_calculation_job_started",
        today=str(today),
        week_starting_date=str(week_starting_date),
    )

    # Create database session
    async with AsyncSessionLocal() as db:  # type: ignore[misc]
        try:
            metrics_list = await calculate_all_channels_weekly_metrics(week_starting_date, db)

            log.info(
                "weekly_metrics_calculation_job_success",
                channels_processed=len(metrics_list),
                week_starting_date=str(week_starting_date),
                today=str(today),
            )
        except Exception as e:
            log.error(
                "weekly_metrics_calculation_job_failed",
                error=str(e),
                week_starting_date=str(week_starting_date),
                today=str(today),
                exc_info=True,
            )

            # Log CRITICAL error for manual intervention
            # TODO: Send Discord alert (Story 8.x)
            log.critical(
                "weekly_metrics_calculation_requires_manual_intervention",
                week_starting_date=str(week_starting_date),
                today=str(today),
                error=str(e),
                manual_action=(
                    f"Check weekly metrics calculation for week {week_starting_date}. "
                    "Manually run: calculate_all_channels_weekly_metrics() if needed."
                ),
            )

            # Don't re-raise to prevent scheduler crash
            # Manual intervention required

    # Story 8.8: Generate weekly cost reports and check thresholds
    # Use separate session for isolation from weekly metrics calculation
    async with AsyncSessionLocal() as cost_db:  # type: ignore[misc]
        try:
            from app.services.cost_tracker import generate_weekly_cost_report

            await generate_weekly_cost_report(cost_db)
            log.info("weekly_cost_report_success")
        except Exception as e:
            log.error(
                "weekly_cost_report_failed",
                error=str(e),
                exc_info=True,
            )
            # Don't re-raise to prevent scheduler crash


async def start_weekly_metrics_scheduler() -> None:
    """Start APScheduler with weekly metrics calculation job (Story 8.6).

    Registers job that runs every Monday at 00:00 UTC to calculate previous week's metrics.

    Configuration:
    - Timezone: UTC (weekly metrics use ISO weeks in UTC)
    - Schedule: Every Monday at 00:00 (day_of_week=0, hour=0, minute=0)
    - Calculates: Previous week (Monday to Sunday ending yesterday)
    - Misfire grace time: 60 seconds (skip if worker down >60s past midnight)
    - Replace existing: True (prevent duplicates on restart)

    Example:
        >>> await start_weekly_metrics_scheduler()
        >>> # Scheduler running, metrics job will fire every Monday at 00:00 UTC
    """
    global _weekly_metrics_scheduler

    if _weekly_metrics_scheduler is not None and _weekly_metrics_scheduler.running:
        log.warning("weekly_metrics_scheduler_already_running")
        return

    # Create scheduler with UTC timezone (weekly metrics use UTC ISO weeks)
    _weekly_metrics_scheduler = AsyncIOScheduler(timezone="UTC")

    # Add weekly metrics calculation job (Monday 00:00 UTC)
    _weekly_metrics_scheduler.add_job(
        _calculate_weekly_metrics_job,
        trigger=CronTrigger(day_of_week=0, hour=0, minute=0, timezone="UTC"),  # Monday = 0
        id="calculate_weekly_metrics",
        replace_existing=True,  # Prevent duplicates on restart
        misfire_grace_time=60,  # Skip if more than 60s late
    )

    # Start scheduler
    _weekly_metrics_scheduler.start()

    log.info(
        "weekly_metrics_scheduler_started",
        timezone="UTC",
        schedule="Every Monday at 00:00 UTC",
        next_run=str(_weekly_metrics_scheduler.get_job("calculate_weekly_metrics").next_run_time),
    )


def shutdown_weekly_metrics_scheduler() -> None:
    """Gracefully shut down the weekly metrics scheduler (Story 8.6).

    Stops the scheduler and waits for running jobs to complete.
    Called on worker termination.

    Example:
        >>> shutdown_weekly_metrics_scheduler()
        >>> # Scheduler stopped, no more metrics jobs will run
    """
    global _weekly_metrics_scheduler

    if _weekly_metrics_scheduler is None or not _weekly_metrics_scheduler.running:
        log.warning("weekly_metrics_scheduler_not_running")
        return

    try:
        _weekly_metrics_scheduler.shutdown(wait=True)
    except RuntimeError as e:
        # Handle "Event loop is closed" error during test teardown
        if "Event loop is closed" in str(e):
            log.debug("weekly_metrics_scheduler_shutdown_event_loop_closed", error=str(e))
        else:
            raise
    finally:
        _weekly_metrics_scheduler = None

    log.info("weekly_metrics_scheduler_shutdown")


def is_weekly_metrics_scheduler_running() -> bool:
    """Check if weekly metrics scheduler is running (Story 8.6).

    Used for health check endpoint.

    Returns:
        True if scheduler is running, False otherwise

    Example:
        >>> is_weekly_metrics_scheduler_running()
        True
    """
    return _weekly_metrics_scheduler is not None and _weekly_metrics_scheduler.running
