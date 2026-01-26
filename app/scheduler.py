"""APScheduler configuration for daily quota resets.

Configures timezone-aware cron jobs that run at midnight Pacific Time.
Jobs reset YouTube and Gemini quotas for all active channels.

Key Features:
- Runs at midnight America/Los_Angeles timezone
- Misfire grace time: 60 seconds (skip if worker down at midnight)
- Jobs re-register on worker restart (in-memory scheduler)
- Graceful shutdown on worker termination

Usage:
    >>> from app.scheduler import start_quota_reset_scheduler, shutdown_quota_reset_scheduler
    >>> await start_quota_reset_scheduler()
    >>> # ... worker runs ...
    >>> shutdown_quota_reset_scheduler()
"""

import os
from datetime import datetime
from zoneinfo import ZoneInfo

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

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
    reset_func,
    quota_table: str,
    usage_field: str,
    daily_limit: int,
    exhausted_flag: str,
):
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
        - Sends CRITICAL Discord alert on failure
        - Includes manual fallback SQL commands in alert
    """
    from app.services.alert_service import send_alert

    # Get today's date in Pacific timezone
    pacific_tz = ZoneInfo(QUOTA_TIMEZONE)
    today = datetime.now(pacific_tz).date()

    # Create database session
    async with AsyncSessionLocal() as db:
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

            # Send CRITICAL Discord alert with fallback instructions
            alert_message = (
                f"🚨 **CRITICAL: {service_name.title()} Quota Reset Job Failed**\n\n"
                f"**Service:** {service_name}\n"
                f"**Date:** {today}\n"
                f"**Timezone:** {QUOTA_TIMEZONE}\n"
                f"**Error:** {e!s}\n\n"
                f"**Manual Fallback Instructions:**\n"
                f"Run this SQL to manually reset {service_name.title()} quotas:\n"
                f"```sql\n"
                f"-- Reset {service_name.title()} quotas for all active channels\n"
                f"INSERT INTO {quota_table} (channel_id, date, {usage_field}, daily_limit)\n"
                f"SELECT id, '{today}', 0, {daily_limit}\n"
                f"FROM channels WHERE is_active = true\n"
                f"ON CONFLICT (channel_id, date) DO NOTHING;\n\n"
                f"UPDATE channels SET {exhausted_flag} = false WHERE is_active = true;\n"
                f"```\n"
            )

            try:
                await send_alert(alert_message, severity="CRITICAL")
            except Exception as alert_error:
                log.error(
                    "failed_to_send_quota_reset_alert",
                    alert_error=str(alert_error),
                    original_error=str(e),
                )

            # Don't re-raise to prevent scheduler crash
            # Alert sent, manual intervention required


async def _reset_youtube_quotas_job():
    """Scheduled job to reset YouTube quotas at midnight Pacific Time."""
    await _reset_quota_job(
        service_name="youtube",
        reset_func=reset_youtube_quotas,
        quota_table="youtube_quota_usage",
        usage_field="units_used",
        daily_limit=10000,
        exhausted_flag="youtube_quota_exhausted",
    )


async def _reset_gemini_quotas_job():
    """Scheduled job to reset Gemini quotas at midnight Pacific Time."""
    await _reset_quota_job(
        service_name="gemini",
        reset_func=reset_gemini_quotas,
        quota_table="gemini_quota_usage",
        usage_field="requests_used",
        daily_limit=1500,
        exhausted_flag="gemini_quota_exhausted",
    )


async def start_quota_reset_scheduler():
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


def shutdown_quota_reset_scheduler():
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

    _scheduler.shutdown(wait=True)
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
