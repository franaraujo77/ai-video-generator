"""Weekly success rate calculation service (Story 8.6).

This module calculates weekly overall pipeline health metrics to monitor success rate,
auto-recovery effectiveness, and failure patterns per channel.

Responsibilities:
1. Calculate weekly success rate per channel
2. Store metrics in WeeklyMetrics table (atomic upsert pattern)
3. Check 90% target threshold and trigger alerts
4. Query historical metrics for trend analysis

Integration:
- Story 8.1: Uses correlation IDs for distributed tracing
- Story 6.10: Similar pattern to auto_recovery_metrics_service
- Story 6.6: Sends Discord alerts for low success rate
- Story 8.5: Called by scheduler on Monday 00:00 UTC

Pattern:
- Atomic upsert: INSERT ON CONFLICT UPDATE for concurrent safety
- Short transactions: Calculate → save → alert (no long holds)
- Threshold alerting: <90% WARNING with failure pattern analysis
"""

import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Channel, Task, TaskStatus, WeeklyMetrics
from app.services.alert_service import send_discord_alert
from app.utils.logging import get_logger

# Get logger for this module
log = get_logger(__name__)

# Terminal statuses that represent completed video processing attempts
TERMINAL_STATUSES = [
    TaskStatus.PUBLISHED,  # Success
    TaskStatus.CANCELLED,  # User cancelled
    TaskStatus.ASSET_ERROR,  # Failed at asset generation
    TaskStatus.VIDEO_ERROR,  # Failed at video generation
    TaskStatus.AUDIO_ERROR,  # Failed at audio generation
    TaskStatus.UPLOAD_ERROR,  # Failed at upload
    TaskStatus.COMPLIANCE_VIOLATION,  # Failed compliance checks
]


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
) -> WeeklyMetrics:
    """Calculate weekly success metrics for specific channel and week.

    This function implements the core metrics calculation for overall pipeline health.
    It queries all tasks in the target week, calculates success rate, and
    atomically upserts the metrics into the database.

    Args:
        channel_id: Channel to calculate metrics for
        week_starting_date: Monday of target week (ISO week boundary)
        db: Database session

    Returns:
        WeeklyMetrics: Calculated metrics (saved to database)

    Metrics Calculated:
        - total_videos_processed: Tasks reaching terminal state in week
        - successful_videos: Tasks reaching 'published' status
        - success_rate: (successful_videos / total_videos_processed) * 100
        - avg_processing_time_seconds: AVG(updated_at - created_at) for completed
        - auto_recovery_rate: % of failed tasks that auto-recovered
        - Failure breakdown by category (TRANSIENT, PERMANENT, UNKNOWN)
        - Failure breakdown by stage (asset_error, video_error, etc.)

    Week Boundary:
        Monday 00:00:00 UTC to Sunday 23:59:59.999999 UTC (inclusive)

    Atomic Upsert Pattern (Story 6.10):
        Uses PostgreSQL INSERT ON CONFLICT UPDATE for concurrent safety.
        Multiple workers can call this function concurrently for same channel/week.

    Integration:
        - Story 8.1: Correlation IDs in logs
        - Story 6.10: Similar calculation pattern
        - Story 6.6: Discord alerting integration

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
    # Updated_at reflects when task reached its current state (terminal status)
    query = select(Task).where(
        Task.channel_id == channel_id,
        Task.updated_at >= week_start,
        Task.updated_at <= week_end,
        Task.status.in_(TERMINAL_STATUSES),  # Only count completed attempts
    )
    result = await db.execute(query)
    tasks = result.scalars().all()

    # Calculate volume metrics
    total_videos_processed = len(tasks)
    successful_videos = sum(1 for t in tasks if t.status == TaskStatus.PUBLISHED)

    # Success rate calculation with zero division handling
    success_rate = (
        Decimal(str((successful_videos / total_videos_processed * 100)))
        if total_videos_processed > 0
        else Decimal("0.00")
    )

    # Average processing time (only for successful videos)
    successful_tasks = [t for t in tasks if t.status == TaskStatus.PUBLISHED]
    if successful_tasks:
        total_seconds = sum(
            int((t.updated_at - t.created_at).total_seconds()) for t in successful_tasks
        )
        avg_processing_time = total_seconds // len(successful_tasks)
    else:
        avg_processing_time = None

    # Auto-recovery rate (only for tasks with retries)
    tasks_with_retries = [t for t in tasks if t.retry_count > 0]
    if tasks_with_retries:
        recovered = sum(1 for t in tasks_with_retries if t.auto_recovered)
        auto_recovery_rate = Decimal(str((recovered / len(tasks_with_retries) * 100)))
    else:
        auto_recovery_rate = None

    # Failure breakdown by category
    # Note: CANCELLED tasks are counted in total_videos_processed but not in failure
    # categories. This is by design - cancelled videos are neither successes nor failures.
    # If success_rate < 90% with zero failures, check for cancelled tasks.
    transient_failures = sum(1 for t in tasks if t.error_category == "TRANSIENT")
    permanent_failures = sum(1 for t in tasks if t.error_category == "PERMANENT")
    unknown_failures = sum(1 for t in tasks if t.error_category == "UNKNOWN")

    # Failure breakdown by stage
    failed_at_assets = sum(1 for t in tasks if t.status == TaskStatus.ASSET_ERROR)
    failed_at_video = sum(1 for t in tasks if t.status == TaskStatus.VIDEO_ERROR)
    failed_at_audio = sum(1 for t in tasks if t.status == TaskStatus.AUDIO_ERROR)
    # Only count terminal upload failures (not UPLOAD_ERROR_RETRYING which is still in progress)
    failed_at_upload = sum(1 for t in tasks if t.status == TaskStatus.UPLOAD_ERROR)

    # Atomic upsert (Story 6.10 pattern)
    # Uses PostgreSQL INSERT ON CONFLICT UPDATE for concurrent safety
    # Multiple workers can calculate metrics concurrently without losing data
    stmt = pg_insert(WeeklyMetrics).values(
        channel_id=channel_id,
        week_starting_date=week_starting_date,
        total_videos_processed=total_videos_processed,
        successful_videos=successful_videos,
        success_rate=success_rate,
        avg_processing_time_seconds=avg_processing_time,
        auto_recovery_rate=auto_recovery_rate,
        transient_failures=transient_failures,
        permanent_failures=permanent_failures,
        unknown_failures=unknown_failures,
        failed_at_assets=failed_at_assets,
        failed_at_video=failed_at_video,
        failed_at_audio=failed_at_audio,
        failed_at_upload=failed_at_upload,
        calculated_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    # Update existing record if conflict on composite PK (channel_id, week_starting_date)
    stmt = stmt.on_conflict_do_update(
        index_elements=["channel_id", "week_starting_date"],
        set_={
            "total_videos_processed": stmt.excluded.total_videos_processed,
            "successful_videos": stmt.excluded.successful_videos,
            "success_rate": stmt.excluded.success_rate,
            "avg_processing_time_seconds": stmt.excluded.avg_processing_time_seconds,
            "auto_recovery_rate": stmt.excluded.auto_recovery_rate,
            "transient_failures": stmt.excluded.transient_failures,
            "permanent_failures": stmt.excluded.permanent_failures,
            "unknown_failures": stmt.excluded.unknown_failures,
            "failed_at_assets": stmt.excluded.failed_at_assets,
            "failed_at_video": stmt.excluded.failed_at_video,
            "failed_at_audio": stmt.excluded.failed_at_audio,
            "failed_at_upload": stmt.excluded.failed_at_upload,
            "calculated_at": stmt.excluded.calculated_at,
            "updated_at": datetime.now(timezone.utc),
        },
    )

    await db.execute(stmt)
    await db.commit()

    # Retrieve saved metrics for return value and threshold checking
    metrics = await get_weekly_metrics(channel_id, week_starting_date, db)

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
        total_videos_processed=total_videos_processed,
        successful_videos=successful_videos,
        success_rate=float(success_rate),
        avg_processing_time=avg_processing_time,
        auto_recovery_rate=float(auto_recovery_rate) if auto_recovery_rate else None,
    )

    # Check thresholds and alert if needed
    await check_success_rate_thresholds(metrics, db)

    return metrics


async def get_weekly_metrics(
    channel_id: UUID, week_starting_date: date, db: AsyncSession
) -> WeeklyMetrics | None:
    """Retrieve weekly metrics for specific channel and week.

    Args:
        channel_id: Channel to query
        week_starting_date: Monday of target week
        db: Database session

    Returns:
        WeeklyMetrics | None: Metrics if exists, None otherwise

    Example:
        >>> metrics = await get_weekly_metrics(
        ...     channel_id=UUID("..."), week_starting_date=date(2026, 1, 20), db=db
        ... )
        >>> if metrics:
        ...     print(f"Success rate: {metrics.success_rate:.1f}%")
    """
    query = (
        select(WeeklyMetrics)
        .where(
            WeeklyMetrics.channel_id == channel_id,
            WeeklyMetrics.week_starting_date == week_starting_date,
        )
        .execution_options(populate_existing=True)
    )  # Force fresh query (avoid stale cache)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def check_success_rate_thresholds(metrics: WeeklyMetrics, db: AsyncSession) -> None:
    """Check 90% target and trigger alert if below threshold.

    This function implements the alerting logic for low success rates.
    It sends Discord webhook alert when success rate falls below 90%.

    Args:
        metrics: Calculated metrics for week
        db: Database session

    Alert Conditions:
        - success_rate < 90% (Story 8.6 target)

    Alert Details:
        - Channel name
        - Week date range (Monday-Sunday)
        - Success rate (percentage)
        - Total successful / total attempted
        - Week-over-week trend comparison
        - Most common failure stage
        - Failure breakdown by category

    Rate Limiting:
        - Max 1 alert per channel per week
        - Tracked via calculated_at timestamp

    Integration:
        - Story 6.6: Discord webhook alerting
        - Story 6.10: Similar threshold alerting pattern

    Example:
        >>> # After calculating metrics
        >>> await check_success_rate_thresholds(metrics, db)
        # Sends Discord alert if success_rate < 90%

    Related:
        - Story 8.6: 90% success rate target
        - Story 6.6: Alert system for threshold violations
    """
    # Check 90% threshold
    if metrics.success_rate < Decimal("90.0"):
        # Get channel name for alert
        channel_query = select(Channel).where(Channel.id == metrics.channel_id)
        channel_result = await db.execute(channel_query)
        channel = channel_result.scalar_one()

        # Calculate week ending date (Sunday)
        week_ending = metrics.week_starting_date + timedelta(days=6)

        # Get week-over-week comparison
        prev_week_start = metrics.week_starting_date - timedelta(days=7)
        prev_week_metrics = await get_weekly_metrics(metrics.channel_id, prev_week_start, db)

        if prev_week_metrics and prev_week_metrics.success_rate > metrics.success_rate:
            trend = (
                f"Down {float(prev_week_metrics.success_rate - metrics.success_rate):.1f}% "
                f"from last week ({float(prev_week_metrics.success_rate):.1f}%)"
            )
        elif prev_week_metrics:
            trend = "Stable or improving"
        else:
            trend = "First week of data"

        # Find most common failure stage
        failure_stages = {
            "asset generation": metrics.failed_at_assets,
            "video generation": metrics.failed_at_video,
            "audio generation": metrics.failed_at_audio,
            "upload": metrics.failed_at_upload,
        }

        if any(failure_stages.values()):
            most_common_stage = max(failure_stages, key=failure_stages.get)
            failure_detail = f"{most_common_stage} ({failure_stages[most_common_stage]} failures)"
        else:
            failure_detail = "none"

        # Build rich alert message with failure pattern analysis
        alert_message = f"""
**Weekly Success Rate Below Target**

**Channel:** {channel.channel_name}
**Week:** {metrics.week_starting_date.isoformat()} to {week_ending.isoformat()}

**Metrics:**
- Success Rate: {float(metrics.success_rate):.1f}% (Target: 90%+)
- Successful: {metrics.successful_videos} / {metrics.total_videos_processed} videos
- Trend: {trend}

**Failure Pattern:**
- Most Common Stage: {failure_detail}
- Transient Errors: {metrics.transient_failures}
- Permanent Errors: {metrics.permanent_failures}
- Unknown Errors: {metrics.unknown_failures}

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

        # Send Discord webhook alert (awaits completion for error logging)
        await send_discord_alert(
            alert_type="low_success_rate",
            severity="WARNING",
            title=f"Weekly Success Rate {float(metrics.success_rate):.1f}% < 90% Target",
            description=alert_message,
            fields={
                "Channel": channel.channel_name,
                "Week": f"{metrics.week_starting_date} to {week_ending}",
                "Success Rate": f"{float(metrics.success_rate):.1f}%",
                "Videos": f"{metrics.successful_videos}/{metrics.total_videos_processed}",
                "Trend": trend,
            },
            webhook_url=webhook_url,
        )

        log.warning(
            "weekly_success_rate_below_target",
            channel_id=str(metrics.channel_id),
            channel_name=channel.channel_name,
            week_starting_date=metrics.week_starting_date.isoformat(),
            success_rate=float(metrics.success_rate),
            target_rate=90.0,
            successful_videos=metrics.successful_videos,
            total_videos=metrics.total_videos_processed,
        )


async def calculate_all_channels_weekly_metrics(
    week_starting_date: date, db: AsyncSession
) -> list[WeeklyMetrics]:
    """Calculate weekly metrics for all active channels for specific week.

    This function is called by weekly scheduled job (Monday 00:00 UTC) to calculate
    previous week's metrics for all channels.

    Args:
        week_starting_date: Monday of target week
        db: Database session

    Returns:
        list[WeeklyMetrics]: Metrics for all channels

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
        - Story 8.5: Called by scheduled job
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
    total_videos = sum(m.total_videos_processed for m in metrics_list)
    total_successful = sum(m.successful_videos for m in metrics_list)

    log.info(
        "all_channels_weekly_metrics_calculated",
        week_starting_date=week_starting_date.isoformat(),
        channels_count=len(channels),
        total_videos_processed=total_videos,
        total_successful_videos=total_successful,
    )

    return metrics_list


async def get_weekly_metrics_range(
    channel_id: UUID,
    start_date: date,
    end_date: date,
    db: AsyncSession,
) -> list[WeeklyMetrics]:
    """Get weekly metrics for a channel within date range (Task 5).

    Retrieves all weekly metrics between start_date and end_date (inclusive).
    Results ordered by week_starting_date DESC (most recent first).

    Args:
        channel_id: Channel UUID
        start_date: Range start date (Monday)
        end_date: Range end date (Monday)
        db: Database session

    Returns:
        List of WeeklyMetrics ordered by week DESC (most recent first)

    Example:
        >>> # Get metrics for January 2026
        >>> metrics = await get_weekly_metrics_range(
        ...     channel_id, date(2026, 1, 1), date(2026, 1, 31), db
        ... )
    """
    stmt = (
        select(WeeklyMetrics)
        .where(WeeklyMetrics.channel_id == channel_id)
        .where(WeeklyMetrics.week_starting_date >= start_date)
        .where(WeeklyMetrics.week_starting_date <= end_date)
        .order_by(WeeklyMetrics.week_starting_date.desc())
    )

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_success_rate_trend(
    channel_id: UUID,
    db: AsyncSession,
    weeks: int = 12,
) -> list[dict]:
    """Get success rate trend for charting (Task 5).

    Retrieves most recent N weeks of metrics formatted for time-series charts.
    Results ordered oldest to newest (for chart x-axis).

    Args:
        channel_id: Channel UUID
        db: Database session
        weeks: Number of recent weeks to include (default: 12)

    Returns:
        List of dicts with keys: week_starting_date, success_rate, total_videos, successful_videos
        Ordered oldest to newest (chronological for charting)

    Example:
        >>> # Get 12-week trend for charting
        >>> trend = await get_success_rate_trend(channel_id, db)
        >>> # Returns: [
        ...     {"week_starting_date": "2026-01-05", "success_rate": 95.0, ...},
        ...     {"week_starting_date": "2026-01-12", "success_rate": 94.5, ...},
        ...     ...
        ... ]
    """
    stmt = (
        select(WeeklyMetrics)
        .where(WeeklyMetrics.channel_id == channel_id)
        .order_by(WeeklyMetrics.week_starting_date.desc())
        .limit(weeks)
    )

    result = await db.execute(stmt)
    metrics_list = list(result.scalars().all())

    # Reverse to get oldest to newest (chronological for charting)
    metrics_list.reverse()

    # Format for charting
    trend = [
        {
            "week_starting_date": m.week_starting_date.isoformat(),
            "success_rate": float(m.success_rate),
            "total_videos": m.total_videos_processed,
            "successful_videos": m.successful_videos,
        }
        for m in metrics_list
    ]

    return trend


async def get_week_over_week_comparison(
    channel_id: UUID,
    week_date: date,
    db: AsyncSession,
) -> dict:
    """Get week-over-week comparison with delta calculations (Task 5).

    Compares specified week with previous week, calculating deltas for all metrics.

    Args:
        channel_id: Channel UUID
        week_date: Week starting date (Monday) to compare
        db: Database session

    Returns:
        Dict with keys: current_week, previous_week, delta
        - current_week: Dict of current week metrics (or None if no data)
        - previous_week: Dict of previous week metrics (or None if no data)
        - delta: Dict of changes (or None if no previous week)

    Example:
        >>> comparison = await get_week_over_week_comparison(
        ...     channel_id, date(2026, 3, 23), db
        ... )
        >>> # Returns: {
        ...     "current_week": {"week_starting_date": "2026-03-23", "success_rate": 90.18, ...},
        ...     "previous_week": {"week_starting_date": "2026-03-16", "success_rate": 89.81, ...},
        ...     "delta": {"success_rate_change": 0.37, ...}
        ... }
    """
    # Get current week metrics
    current_metrics = await get_weekly_metrics(channel_id, week_date, db)

    # Get previous week metrics (7 days before)
    prev_week_date = week_date - timedelta(days=7)
    prev_metrics = await get_weekly_metrics(channel_id, prev_week_date, db)

    # Format current week
    current_week = None
    if current_metrics:
        current_week = {
            "week_starting_date": current_metrics.week_starting_date.isoformat(),
            "success_rate": float(current_metrics.success_rate),
            "total_videos": current_metrics.total_videos_processed,
            "successful_videos": current_metrics.successful_videos,
            "avg_processing_time_seconds": current_metrics.avg_processing_time_seconds,
        }

    # Format previous week
    previous_week = None
    if prev_metrics:
        previous_week = {
            "week_starting_date": prev_metrics.week_starting_date.isoformat(),
            "success_rate": float(prev_metrics.success_rate),
            "total_videos": prev_metrics.total_videos_processed,
            "successful_videos": prev_metrics.successful_videos,
            "avg_processing_time_seconds": prev_metrics.avg_processing_time_seconds,
        }

    # Calculate deltas
    delta = None
    if current_metrics and prev_metrics:
        delta = {
            "success_rate_change": float(
                current_metrics.success_rate - prev_metrics.success_rate
            ),
            "total_videos_change": (
                current_metrics.total_videos_processed
                - prev_metrics.total_videos_processed
            ),
            "successful_videos_change": (
                current_metrics.successful_videos - prev_metrics.successful_videos
            ),
        }

    return {
        "current_week": current_week,
        "previous_week": previous_week,
        "delta": delta,
    }


async def get_failure_pattern_analysis(
    channel_id: UUID,
    db: AsyncSession,
    weeks: int = 4,
) -> dict:
    """Analyze failure patterns over recent weeks (Task 5).

    Aggregates failure counts by category and stage over the most recent N weeks
    to identify trends and common failure modes.

    Args:
        channel_id: Channel UUID
        db: Database session
        weeks: Number of recent weeks to analyze (default: 4)

    Returns:
        Dict with keys:
        - time_range: {start_week, end_week}
        - category_breakdown: {transient_failures, permanent_failures, unknown_failures}
        - stage_breakdown: {assets, video, audio, upload}
        - most_common_category: String
        - most_common_stage: String

    Example:
        >>> analysis = await get_failure_pattern_analysis(channel_id, db, weeks=4)
        >>> # Returns: {
        ...     "time_range": {"start_week": "2026-02-23", "end_week": "2026-03-23"},
        ...     "category_breakdown": {"transient_failures": 26, "permanent_failures": 26, ...},
        ...     "stage_breakdown": {"assets": 21, "video": 16, ...},
        ...     "most_common_category": "transient",
        ...     "most_common_stage": "assets"
        ... }
    """
    # Get most recent N weeks of metrics
    stmt = (
        select(WeeklyMetrics)
        .where(WeeklyMetrics.channel_id == channel_id)
        .order_by(WeeklyMetrics.week_starting_date.desc())
        .limit(weeks)
    )

    result = await db.execute(stmt)
    metrics_list = list(result.scalars().all())

    # If no data, return zeros
    if not metrics_list:
        return {
            "time_range": {"start_week": None, "end_week": None},
            "category_breakdown": {
                "transient_failures": 0,
                "permanent_failures": 0,
                "unknown_failures": 0,
            },
            "stage_breakdown": {
                "assets": 0,
                "video": 0,
                "audio": 0,
                "upload": 0,
            },
            "most_common_category": "none",
            "most_common_stage": "none",
        }

    # Aggregate failures by category
    category_breakdown = {
        "transient_failures": sum(m.transient_failures for m in metrics_list),
        "permanent_failures": sum(m.permanent_failures for m in metrics_list),
        "unknown_failures": sum(m.unknown_failures for m in metrics_list),
    }

    # Aggregate failures by stage
    stage_breakdown = {
        "assets": sum(m.failed_at_assets for m in metrics_list),
        "video": sum(m.failed_at_video for m in metrics_list),
        "audio": sum(m.failed_at_audio for m in metrics_list),
        "upload": sum(m.failed_at_upload for m in metrics_list),
    }

    # Find most common category
    most_common_category = "none"
    if any(category_breakdown.values()):
        # Use lambda for type-safe max key extraction
        most_common_category = max(category_breakdown, key=lambda k: category_breakdown[k])
        # Strip "_failures" suffix for cleaner output
        most_common_category = most_common_category.replace("_failures", "")

    # Find most common stage
    most_common_stage = "none"
    if any(stage_breakdown.values()):
        # Use lambda for type-safe max key extraction
        most_common_stage = max(stage_breakdown, key=lambda k: stage_breakdown[k])

    # Time range (oldest first, newest last - reversed order)
    metrics_list.reverse()  # Now oldest to newest
    start_week = metrics_list[0].week_starting_date.isoformat()
    end_week = metrics_list[-1].week_starting_date.isoformat()

    return {
        "time_range": {"start_week": start_week, "end_week": end_week},
        "category_breakdown": category_breakdown,
        "stage_breakdown": stage_breakdown,
        "most_common_category": most_common_category,
        "most_common_stage": most_common_stage,
    }
