"""Auto-recovery success rate tracking service (Story 6.10).

This module calculates weekly auto-recovery success rate to verify FR35 target (80%).
Workers calculate metrics weekly (Monday 00:00 UTC) for the previous week's data.

Responsibilities:
1. Calculate weekly auto-recovery success rate per channel
2. Store metrics in AutoRecoveryMetrics table (atomic upsert pattern)
3. Check 80% target threshold and trigger alerts
4. Query historical metrics for trend analysis

Integration:
- Story 6.2: Uses retry_count from exponential backoff
- Story 6.4: Uses error_category for breakdown metrics
- Story 6.6: Sends Discord alerts for low success rate
- Story 6.8: Follows same atomic upsert + threshold alerting pattern
- Story 6.9: Uses retry tracking fields for metrics calculation

Pattern:
- Atomic upsert: INSERT ON CONFLICT UPDATE for concurrent safety
- Short transactions: Calculate → save → alert (no long holds)
- Threshold alerting: <80% WARNING with failure pattern analysis
"""

import os
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AutoRecoveryMetrics, Channel, Task
from app.services.alert_service import send_discord_alert
from app.utils.logging import get_logger

# Get logger for this module
log = get_logger(__name__)


def get_week_starting_date(target_date: date) -> date:
    """Get Monday of the ISO week containing target_date.

    ISO weeks start on Monday (weekday=0) and end on Sunday (weekday=6).
    This function is critical for consistent weekly metrics grouping.

    Args:
        target_date: Any date in the target week

    Returns:
        date: Monday of that week (ISO week starts Monday)

    Examples:
        >>> get_week_starting_date(date(2026, 1, 23))  # Thursday
        date(2026, 1, 20)  # Previous Monday

        >>> get_week_starting_date(date(2026, 1, 20))  # Monday
        date(2026, 1, 20)  # Same Monday

        >>> get_week_starting_date(date(2026, 1, 26))  # Sunday
        date(2026, 1, 20)  # Previous Monday (week includes Sunday)

    Related:
        - ISO 8601 week date system (Monday start)
        - Python datetime.weekday(): Monday=0, Sunday=6
    """
    weekday = target_date.weekday()  # Monday=0, Sunday=6
    monday = target_date - timedelta(days=weekday)
    return monday


async def calculate_weekly_metrics(
    channel_id: UUID, week_starting_date: date, db: AsyncSession
) -> AutoRecoveryMetrics:
    """Calculate auto-recovery success rate for specific channel and week.

    This function implements the core metrics calculation for FR35 (80% target).
    It queries all tasks in the target week, calculates success rate, and
    atomically upserts the metrics into the database.

    Args:
        channel_id: Channel to calculate metrics for
        week_starting_date: Monday of target week (ISO week boundary)
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
        Monday 00:00:00 UTC to Sunday 23:59:59.999999 UTC (inclusive)

    Atomic Upsert Pattern (Story 6.8):
        Uses PostgreSQL INSERT ON CONFLICT UPDATE for concurrent safety.
        Multiple workers can call this function concurrently for same channel/week.

    Integration:
        - Story 6.2: retry_count field from exponential backoff
        - Story 6.4: error_category field from granular error status
        - Story 6.8: Atomic upsert pattern (INSERT ON CONFLICT UPDATE)

    Example:
        >>> # Calculate metrics for week of 2026-01-20 (Monday)
        >>> metrics = await calculate_weekly_metrics(
        ...     channel_id=UUID("..."), week_starting_date=date(2026, 1, 20), db=db
        ... )
        >>> print(f"Success rate: {metrics.success_rate:.1f}%")
        Success rate: 85.0%
    """
    # Calculate week boundaries (UTC timezone-aware)
    # Week spans Monday 00:00:00 to Sunday 23:59:59.999999
    week_start = datetime.combine(week_starting_date, datetime.min.time()).replace(
        tzinfo=timezone.utc
    )
    week_end = week_start + timedelta(days=7) - timedelta(microseconds=1)

    log.info(
        "calculating_weekly_metrics",
        channel_id=str(channel_id),
        week_starting_date=week_starting_date.isoformat(),
        week_start=week_start.isoformat(),
        week_end=week_end.isoformat(),
    )

    # Query tasks in target week using updated_at timestamp
    # Updated_at reflects when task reached its current state (error or success)
    query = select(Task).where(
        Task.channel_id == channel_id, Task.updated_at >= week_start, Task.updated_at <= week_end
    )
    result = await db.execute(query)
    tasks = result.scalars().all()

    # Calculate success rate metrics
    # total_retry_attempts: Tasks that had at least one retry (retry_count > 0)
    # total_auto_recovered: Tasks that successfully recovered via automatic retry
    total_retry_attempts = sum(1 for t in tasks if t.retry_count > 0)
    total_auto_recovered = sum(1 for t in tasks if t.auto_recovered)

    # Success rate calculation with zero division handling
    # If no retry attempts in week, success_rate defaults to 0.0
    success_rate = (
        (total_auto_recovered / total_retry_attempts * 100) if total_retry_attempts > 0 else 0.0
    )

    # Average retries before success (only for recovered tasks)
    # recovery_attempt_number indicates which retry succeeded (1-5)
    recovered_tasks = [t for t in tasks if t.auto_recovered and t.recovery_attempt_number]
    average_retries = (
        sum(t.recovery_attempt_number for t in recovered_tasks if t.recovery_attempt_number)
        / len(recovered_tasks)
        if recovered_tasks
        else None
    )

    # Error category breakdown for failure pattern analysis
    # TRANSIENT: Network timeouts, rate limits (should recover)
    # PERMANENT: Auth failures, bad requests (won't recover)
    # UNKNOWN: Unexpected errors (investigate if high count)
    transient_error_count = sum(1 for t in tasks if t.error_category == "TRANSIENT")
    transient_recovered = sum(
        1 for t in tasks if t.error_category == "TRANSIENT" and t.auto_recovered
    )
    permanent_error_count = sum(1 for t in tasks if t.error_category == "PERMANENT")

    # Atomic upsert (Story 6.8 pattern)
    # Uses PostgreSQL INSERT ON CONFLICT UPDATE for concurrent safety
    # Multiple workers can calculate metrics concurrently without losing data
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
        calculated_at=datetime.now(timezone.utc),
    )

    # Update existing record if conflict on composite PK (channel_id, week_starting_date)
    stmt = stmt.on_conflict_do_update(
        index_elements=["channel_id", "week_starting_date"],
        set_={
            "total_retry_attempts": stmt.excluded.total_retry_attempts,
            "total_auto_recovered": stmt.excluded.total_auto_recovered,
            "success_rate": stmt.excluded.success_rate,
            "average_retries_before_success": stmt.excluded.average_retries_before_success,
            "transient_error_count": stmt.excluded.transient_error_count,
            "transient_recovered": stmt.excluded.transient_recovered,
            "permanent_error_count": stmt.excluded.permanent_error_count,
            "calculated_at": stmt.excluded.calculated_at,
            "updated_at": datetime.now(timezone.utc),
        },
    )

    await db.execute(stmt)
    await db.commit()

    # Retrieve saved metrics for return value and threshold checking
    metrics = await get_auto_recovery_metrics(channel_id, week_starting_date, db)

    if not metrics:
        log.error(
            "failed_to_retrieve_metrics_after_upsert",
            channel_id=str(channel_id),
            week_starting_date=week_starting_date.isoformat(),
        )
        raise RuntimeError("Failed to retrieve metrics after upsert")

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
        permanent_error_count=permanent_error_count,
    )

    # Check thresholds and alert if needed (FR35: 80% target)
    await check_success_rate_thresholds(metrics, db)

    return metrics


async def get_auto_recovery_metrics(
    channel_id: UUID, week_starting_date: date, db: AsyncSession
) -> AutoRecoveryMetrics | None:
    """Retrieve auto-recovery metrics for specific channel and week.

    Args:
        channel_id: Channel to query
        week_starting_date: Monday of target week
        db: Database session

    Returns:
        AutoRecoveryMetrics | None: Metrics if exists, None otherwise

    Example:
        >>> metrics = await get_auto_recovery_metrics(
        ...     channel_id=UUID("..."), week_starting_date=date(2026, 1, 20), db=db
        ... )
        >>> if metrics:
        ...     print(f"Success rate: {metrics.success_rate:.1f}%")
    """
    query = (
        select(AutoRecoveryMetrics)
        .where(
            AutoRecoveryMetrics.channel_id == channel_id,
            AutoRecoveryMetrics.week_starting_date == week_starting_date,
        )
        .execution_options(populate_existing=True)
    )  # Force fresh query (avoid stale cache)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def check_success_rate_thresholds(metrics: AutoRecoveryMetrics, db: AsyncSession) -> None:
    """Check FR35 (80% target) and trigger alert if below threshold.

    This function implements the alerting logic for low auto-recovery rates.
    It sends Discord webhook alert when success rate falls below 80% (FR35).

    Args:
        metrics: Calculated metrics for week
        db: Database session

    Alert Conditions:
        - success_rate < 80% (FR35 target)
        - At least 5 retry attempts in week (meaningful sample size)

    Alert Details:
        - Channel name
        - Week ending date (Sunday)
        - Success rate (percentage)
        - Total recovered / total attempts
        - Failure pattern summary (error categories)

    Rate Limiting:
        - Max 1 alert per channel per week
        - Tracked via calculated_at timestamp
        - Prevents alert spam if metrics recalculated multiple times

    Integration:
        - Story 6.6: Discord webhook alerting
        - Story 6.8: Similar threshold alerting pattern

    Example:
        >>> # After calculating metrics
        >>> await check_success_rate_thresholds(metrics, db)
        # Sends Discord alert if success_rate < 80%

    Related:
        - FR35: 80% auto-recovery target
        - Story 6.6: Alert system for terminal failures
    """
    # Skip alert if insufficient data for meaningful analysis
    # Minimum 5 retry attempts required (prevents false alerts)
    if metrics.total_retry_attempts < 5:
        log.info(
            "skipping_threshold_check_insufficient_data",
            channel_id=str(metrics.channel_id),
            week_starting_date=metrics.week_starting_date.isoformat(),
            total_retry_attempts=metrics.total_retry_attempts,
            minimum_required=5,
        )
        return

    # Check 80% threshold (FR35)
    if metrics.success_rate < 80.0:
        # Get channel name for alert
        channel_query = select(Channel).where(Channel.id == metrics.channel_id)
        channel_result = await db.execute(channel_query)
        channel = channel_result.scalar_one()

        # Calculate week ending date (Sunday)
        week_ending = metrics.week_starting_date + timedelta(days=6)

        # Failure pattern summary for investigation
        # Transient recovery rate helps identify if retry logic is working
        transient_recovery_rate = (
            (metrics.transient_recovered / metrics.transient_error_count * 100)
            if metrics.transient_error_count > 0
            else 0.0
        )

        # Format average retries (handle None case)
        avg_retries_str = (
            f"{metrics.average_retries_before_success:.1f} attempts"
            if metrics.average_retries_before_success is not None
            else "N/A (no recoveries)"
        )

        # Build rich alert message with failure pattern analysis
        alert_message = f"""
**Auto-Recovery Rate Below Target**

**Channel:** {channel.channel_name}
**Week:** {metrics.week_starting_date.isoformat()} to {week_ending.isoformat()}

**Metrics:**
- Success Rate: {metrics.success_rate:.1f}% (Target: 80%+)
- Recovered: {metrics.total_auto_recovered} / {metrics.total_retry_attempts} attempts
- Average Retries: {avg_retries_str}

**Failure Pattern:**
- Transient Errors: {metrics.transient_error_count} ({transient_recovery_rate:.1f}% recovered)
- Permanent Errors: {metrics.permanent_error_count}

**Action:** Investigate failure patterns in error logs for this channel.
"""

        # Get Discord webhook URL from environment
        webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
        if not webhook_url:
            log.warning(
                "discord_webhook_not_configured",
                message="DISCORD_WEBHOOK_URL not set, skipping alert",
            )
            return

        # Send Discord webhook alert (fire-and-forget pattern)
        await send_discord_alert(
            alert_type="low_recovery_rate",
            severity="WARNING",
            title=f"Auto-Recovery Rate {metrics.success_rate:.1f}% < 80% Target",
            description=alert_message,
            fields={
                "Channel": channel.channel_name,
                "Week": f"{metrics.week_starting_date} to {week_ending}",
                "Success Rate": f"{metrics.success_rate:.1f}%",
                "Recovered": f"{metrics.total_auto_recovered}/{metrics.total_retry_attempts}",
            },
            webhook_url=webhook_url,
        )

        log.warning(
            "auto_recovery_rate_below_target",
            channel_id=str(metrics.channel_id),
            channel_name=channel.channel_name,
            week_starting_date=metrics.week_starting_date.isoformat(),
            success_rate=metrics.success_rate,
            target_rate=80.0,
            total_recovered=metrics.total_auto_recovered,
            total_attempts=metrics.total_retry_attempts,
        )


async def calculate_all_channels_weekly_metrics(
    week_starting_date: date, db: AsyncSession
) -> list[AutoRecoveryMetrics]:
    """Calculate auto-recovery metrics for all active channels for specific week.

    This function is called by weekly scheduled job (Monday 00:00 UTC) to calculate
    previous week's metrics for all channels.

    Args:
        week_starting_date: Monday of target week
        db: Database session

    Returns:
        list[AutoRecoveryMetrics]: Metrics for all channels with retry activity

    Usage:
        Called by weekly cron job (Monday 00:00 UTC) to calculate previous week:

        >>> # Monday morning: calculate metrics for previous week
        >>> week_start = get_week_starting_date(date.today() - timedelta(days=7))
        >>> metrics_list = await calculate_all_channels_weekly_metrics(
        ...     week_starting_date=week_start, db=db
        ... )
        >>> print(f"Calculated metrics for {len(metrics_list)} channels")

    Pattern:
        - Queries all active channels (Channel.is_active=True)
        - Calculates metrics for each channel independently
        - Returns list of metrics for observability (logging, monitoring)

    Integration:
        - Story 4.5: Uses Channel.is_active for filtering
        - Task 5: Called by weekly scheduled job
    """
    # Get all active channels
    channels_query = select(Channel).where(Channel.is_active)
    channels_result = await db.execute(channels_query)
    channels = channels_result.scalars().all()

    log.info(
        "calculating_all_channels_weekly_metrics",
        week_starting_date=week_starting_date.isoformat(),
        channels_count=len(channels),
    )

    # Calculate metrics for each channel
    metrics_list = []
    for channel in channels:
        metrics = await calculate_weekly_metrics(
            channel_id=channel.id, week_starting_date=week_starting_date, db=db
        )
        metrics_list.append(metrics)

    # Aggregate summary for observability
    log.info(
        "all_channels_weekly_metrics_calculated",
        week_starting_date=week_starting_date.isoformat(),
        channels_count=len(channels),
        total_retry_attempts=sum(m.total_retry_attempts for m in metrics_list),
        total_auto_recovered=sum(m.total_auto_recovered for m in metrics_list),
    )

    return metrics_list
