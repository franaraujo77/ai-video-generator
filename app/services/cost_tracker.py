"""Cost Tracking Service (Story 8.2).

Provides cost tracking functionality for video generation with database persistence.
Tracks costs at component level (Gemini, Kling, ElevenLabs) for financial analysis.

Architecture:
- Component-level tracking: Separate row per API component
- Correlation IDs: Distributed tracing from Story 8.1
- Error resilience: Log failures but don't crash pipeline
- Type safety: Decimal for precision, convert to float only at DB layer

Dependencies:
- Story 8.1: Correlation ID context variables
- Story 1.1: Task model with total_cost_usd field
- Epic 3: Worker cost calculation methods
"""

# ruff: noqa: D417

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Channel, CostThreshold, Task, VideoCost
from app.utils.context import get_correlation_id
from app.utils.logging import get_logger

log = get_logger(__name__)

# Valid component names for cost tracking
VALID_COMPONENTS = {
    "gemini_assets",
    "kling_video",
    "elevenlabs_narration",
    "elevenlabs_sfx",
}


async def track_api_cost(
    db: AsyncSession,
    task_id: UUID,
    component: str,
    cost_usd: Decimal,
    api_calls: int,
    units_consumed: int,
) -> None:
    """Track API cost for a video component.

    Persists cost to video_costs table for granular financial tracking.
    Correlation ID automatically populated from async context for traceability.

    Args:
        db: Database session (AsyncSession from SQLAlchemy)
        task_id: Task UUID (costs are tracked per task, not per video)
        component: Component name (gemini_assets, kling_video, elevenlabs_narration, elevenlabs_sfx)
        cost_usd: Cost in USD (Decimal for precision)
        api_calls: Number of API calls made (for metrics)
        units_consumed: Number of units consumed (e.g., clips, images, characters)

    Raises:
        No exceptions raised - failures are logged but don't crash pipeline

    Example:
        >>> await track_api_cost(
        ...     db=db,
        ...     task_id=task.id,
        ...     component="kling_video",
        ...     cost_usd=Decimal("7.56"),
        ...     api_calls=18,
        ...     units_consumed=18,
        ... )
    """
    correlation_id = get_correlation_id()  # From Story 8.1 context

    # Validate component name
    if component not in VALID_COMPONENTS:
        log.error(
            "invalid_component_name",
            component=component,
            valid_components=list(VALID_COMPONENTS),
            task_id=str(task_id),
            correlation_id=correlation_id,
        )
        return  # Don't persist invalid data

    try:
        # Create cost record
        cost_record = VideoCost(
            task_id=task_id,
            component=component,
            cost_usd=cost_usd,
            units_used=units_consumed,
            correlation_id=UUID(correlation_id) if correlation_id else None,
        )

        db.add(cost_record)
        await db.commit()

        log.info(
            "cost_tracked_to_database",
            task_id=str(task_id),
            component=component,
            cost_usd=str(cost_usd),
            api_calls=api_calls,
            units_consumed=units_consumed,
            correlation_id=correlation_id,
        )

    except Exception as e:
        # Log error but don't fail pipeline
        log.error(
            "cost_tracking_failed",
            task_id=str(task_id),
            component=component,
            error=str(e),
            correlation_id=correlation_id,
            exc_info=True,
        )
        # Rollback to avoid session corruption
        await db.rollback()


async def get_task_cost_breakdown(db: AsyncSession, task_id: UUID) -> dict[str, Decimal]:
    """Get cost breakdown by component for a task.

    Returns:
        Dict mapping component name to cost in USD
        Example: {
            "gemini_assets": Decimal("1.50"),
            "kling_video": Decimal("7.56"),
            "elevenlabs_narration": Decimal("0.72"),
            "elevenlabs_sfx": Decimal("0.72")
        }
    """
    stmt = select(VideoCost.component, VideoCost.cost_usd).where(VideoCost.task_id == task_id)
    result = await db.execute(stmt)
    rows = result.all()

    return {row.component: row.cost_usd for row in rows}


async def get_task_total_cost(db: AsyncSession, task_id: UUID) -> Decimal:
    """Get total cost for a task by summing all components.

    Returns:
        Total cost in USD as Decimal
    """
    stmt = select(func.sum(VideoCost.cost_usd)).where(VideoCost.task_id == task_id)
    result = await db.execute(stmt)
    total = result.scalar_one_or_none()

    return total if total is not None else Decimal("0.00")


async def get_channel_cost_summary(
    db: AsyncSession,
    channel_id: UUID,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict[str, Any]:
    """Get aggregated cost summary for a channel.

    Args:
        channel_id: Channel identifier (UUID)
        start_date: Optional start date for filtering (UTC)
        end_date: Optional end date for filtering (UTC)

    Returns:
        Dict with total_cost, video_count, avg_cost_per_video, breakdown_by_component
    """
    # Build query with optional date filters
    stmt = (
        select(VideoCost)
        .join(Task, VideoCost.task_id == Task.id)
        .where(Task.channel_id == channel_id)
    )

    if start_date:
        stmt = stmt.where(VideoCost.timestamp >= start_date)
    if end_date:
        stmt = stmt.where(VideoCost.timestamp <= end_date)

    result = await db.execute(stmt)
    costs = result.scalars().all()

    if not costs:
        return {
            "total_cost": Decimal("0.00"),
            "video_count": 0,
            "avg_cost_per_video": Decimal("0.00"),
            "breakdown_by_component": {},
        }

    # Calculate aggregations
    total_cost = sum(cost.cost_usd for cost in costs)
    task_ids = {cost.task_id for cost in costs}
    video_count = len(task_ids)
    avg_cost = total_cost / video_count if video_count > 0 else Decimal("0.00")

    # Breakdown by component
    breakdown: dict[str, Decimal] = {}
    for cost in costs:
        breakdown[cost.component] = breakdown.get(cost.component, Decimal("0.00")) + cost.cost_usd

    return {
        "total_cost": total_cost,
        "video_count": video_count,
        "avg_cost_per_video": avg_cost,
        "breakdown_by_component": breakdown,
    }


async def get_average_cost_per_video(db: AsyncSession, channel_id: UUID, days: int = 30) -> Decimal:
    """Get average cost per video for last N days.

    Args:
        channel_id: Channel identifier (UUID)
        days: Number of days to look back (default: 30)

    Returns:
        Average cost per video as Decimal
    """
    start_date = datetime.now(timezone.utc) - timedelta(days=days)
    summary = await get_channel_cost_summary(db, channel_id, start_date=start_date)

    avg_cost: Decimal = summary["avg_cost_per_video"]
    return avg_cost


# ============================================================================
# Story 8.8: Cost Dashboard & Reporting Functions
# ============================================================================


async def get_weekly_cost_summary(
    db: AsyncSession,
    channel_id: UUID,
) -> dict[str, Any]:
    """Get cost summary for current week (Monday 00:00 to Sunday 23:59 UTC) (Story 8.8, Task 1).

    Args:
        channel_id: Channel identifier (UUID)

    Returns:
        Dict with:
        - total_cost: Total cost this week (Decimal)
        - video_count: Number of videos this week (int)
        - avg_cost_per_video: Average cost per video (Decimal)
        - breakdown_by_component: Cost by component (dict[str, Decimal])
        - start_date: Week start date (Monday 00:00 UTC)
        - end_date: Week end date (Sunday 23:59 UTC)

    Example:
        >>> summary = await get_weekly_cost_summary(db, channel_id)
        >>> print(f"This week: ${summary['total_cost']}, {summary['video_count']} videos")
    """
    # Get current week boundaries (Monday 00:00 to Sunday 23:59)
    today = datetime.now(timezone.utc)
    days_since_monday = today.weekday()  # Monday=0, Sunday=6
    week_start = (today - timedelta(days=days_since_monday)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    week_end = (week_start + timedelta(days=6)).replace(
        hour=23, minute=59, second=59, microsecond=999999
    )

    # Use existing channel cost summary function with date filtering
    summary = await get_channel_cost_summary(
        db=db, channel_id=channel_id, start_date=week_start, end_date=week_end
    )

    # Add date boundaries to response
    summary["start_date"] = week_start
    summary["end_date"] = week_end

    return summary


async def get_monthly_cost_summary(
    db: AsyncSession,
    channel_id: UUID,
) -> dict[str, Any]:
    """Get cost summary for current month (1st 00:00 to last day 23:59 UTC) (Story 8.8, Task 1).

    Args:
        channel_id: Channel identifier (UUID)

    Returns:
        Dict with:
        - total_cost: Total cost this month (Decimal)
        - video_count: Number of videos this month (int)
        - avg_cost_per_video: Average cost per video (Decimal)
        - breakdown_by_component: Cost by component (dict[str, Decimal])
        - start_date: Month start date (1st 00:00 UTC)
        - end_date: Month end date (last day 23:59 UTC)
    """
    # Get current month boundaries (1st 00:00 to last day 23:59)
    today = datetime.now(timezone.utc)
    month_start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Calculate last day of month
    if today.month == 12:
        next_month_start = today.replace(
            year=today.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0
        )
    else:
        next_month_start = today.replace(
            month=today.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0
        )

    month_end = next_month_start - timedelta(microseconds=1)

    # Use existing channel cost summary function with date filtering
    summary = await get_channel_cost_summary(
        db=db, channel_id=channel_id, start_date=month_start, end_date=month_end
    )

    # Add date boundaries to response
    summary["start_date"] = month_start
    summary["end_date"] = month_end

    return summary


async def get_cost_comparison_across_channels(
    db: AsyncSession, days: int = 30
) -> list[dict[str, Any]]:
    """Get cost comparison across all channels for efficiency analysis (Story 8.8, Task 1).

    Sorts channels by cost efficiency (lowest avg cost per video first).

    Args:
        days: Number of days to analyze (default: 30)

    Returns:
        List of dicts, sorted by avg_cost_per_video (ascending):
        [
            {
                "channel_id": UUID,
                "channel_name": str,
                "total_cost": Decimal,
                "video_count": int,
                "avg_cost_per_video": Decimal
            },
            ...
        ]

    Example:
        >>> comparison = await get_cost_comparison_across_channels(db)
        >>> for channel in comparison:
        ...     print(f"{channel['channel_name']}: ${channel['avg_cost_per_video']}/video")
    """
    # Get all active channels
    stmt = select(Channel).where(Channel.is_active == True)  # noqa: E712
    result = await db.execute(stmt)
    channels = result.scalars().all()

    # Calculate costs for each channel
    start_date = datetime.now(timezone.utc) - timedelta(days=days)
    comparison_data = []

    for channel in channels:
        summary = await get_channel_cost_summary(
            db=db, channel_id=channel.id, start_date=start_date
        )

        # Only include channels with videos
        if summary["video_count"] > 0:
            comparison_data.append(
                {
                    "channel_id": channel.id,
                    "channel_name": channel.channel_name,
                    "total_cost": summary["total_cost"],
                    "video_count": summary["video_count"],
                    "avg_cost_per_video": summary["avg_cost_per_video"],
                }
            )

    # Sort by cost efficiency (lowest avg cost first)
    comparison_data.sort(key=lambda x: x["avg_cost_per_video"])

    return comparison_data


async def get_cost_trend_data(db: AsyncSession, channel_id: UUID, days: int = 30) -> dict[str, Any]:
    """Get historical cost trend data for last N days (Story 8.8, Task 1).

    Args:
        channel_id: Channel identifier (UUID)
        days: Number of days to analyze (default: 30)

    Returns:
        Dict with:
        - daily_costs: List of {date: str, cost: Decimal, video_count: int}
        - total_cost: Total cost over period (Decimal)
        - avg_daily_cost: Average cost per day (Decimal)

    Example:
        >>> trend = await get_cost_trend_data(db, channel_id, days=7)
        >>> for day in trend["daily_costs"]:
        ...     print(f"{day['date']}: ${day['cost']}")
    """
    start_date = datetime.now(timezone.utc) - timedelta(days=days)
    start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)

    # Query costs for date range
    stmt = (
        select(VideoCost)
        .join(Task, VideoCost.task_id == Task.id)
        .where(Task.channel_id == channel_id, VideoCost.timestamp >= start_date)
        .order_by(VideoCost.timestamp)
    )
    result = await db.execute(stmt)
    costs = result.scalars().all()

    # Group costs by date
    daily_costs_map: dict[str, dict[str, Any]] = {}
    for cost in costs:
        date_key = cost.timestamp.date().isoformat()
        if date_key not in daily_costs_map:
            daily_costs_map[date_key] = {
                "date": date_key,
                "cost": Decimal("0.00"),
                "video_count": set(),
            }
        daily_costs_map[date_key]["cost"] += cost.cost_usd
        daily_costs_map[date_key]["video_count"].add(cost.task_id)

    # Convert to list and calculate video counts
    daily_costs_list = []
    total_cost = Decimal("0.00")
    for date_key in sorted(daily_costs_map.keys()):
        day_data = daily_costs_map[date_key]
        daily_costs_list.append(
            {
                "date": day_data["date"],
                "cost": day_data["cost"],
                "video_count": len(day_data["video_count"]),
            }
        )
        total_cost += day_data["cost"]

    avg_daily_cost = total_cost / days if days > 0 else Decimal("0.00")

    return {
        "daily_costs": daily_costs_list,
        "total_cost": total_cost,
        "avg_daily_cost": avg_daily_cost,
    }


# ============================================================================
# Story 8.8: Cost Threshold Alerting Functions
# ============================================================================


async def get_active_thresholds(
    db: AsyncSession,
    channel_id: UUID,
) -> list[CostThreshold]:
    """Get all active cost thresholds for a channel (Story 8.8, Task 3).

    Args:
        channel_id: Channel identifier (UUID)

    Returns:
        List of active CostThreshold objects
    """
    stmt = (
        select(CostThreshold)
        .where(
            CostThreshold.channel_id == channel_id,
            CostThreshold.enabled == True,  # noqa: E712
        )
        .order_by(CostThreshold.period)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def check_cost_thresholds(
    db: AsyncSession,
    channel_id: UUID,
) -> list[dict[str, Any]]:
    """Check if current costs exceed configured thresholds (Story 8.8, Task 3).

    Returns list of threshold violations with alert details.
    Does NOT send alerts - use this for checking, send alerts separately.

    Args:
        channel_id: Channel identifier (UUID)

    Returns:
        List of threshold violations:
        [
            {
                "threshold_id": UUID,
                "period": "weekly" | "monthly",
                "threshold_usd": Decimal,
                "current_cost": Decimal,
                "percentage": Decimal (e.g., 85.5 for 85.5%),
                "exceeded": bool,
                "approaching": bool (>= 80%),
                "exceeded_by": Decimal (if exceeded)
            },
            ...
        ]

    Example:
        >>> violations = await check_cost_thresholds(db, channel_id)
        >>> for v in violations:
        ...     if v["exceeded"]:
        ...         print(f"ALERT: {v['period']} threshold exceeded by ${v['exceeded_by']}")
    """
    thresholds = await get_active_thresholds(db, channel_id)
    violations = []

    for threshold in thresholds:
        # Get current cost for threshold period
        if threshold.period == "weekly":
            summary = await get_weekly_cost_summary(db, channel_id)
        elif threshold.period == "monthly":
            summary = await get_monthly_cost_summary(db, channel_id)
        else:
            log.warning(
                "invalid_threshold_period",
                threshold_id=str(threshold.id),
                period=threshold.period,
                channel_id=str(channel_id),
            )
            continue

        current_cost = summary["total_cost"]
        percentage = (
            (current_cost / threshold.threshold_usd * 100)
            if threshold.threshold_usd > 0
            else Decimal("0.00")
        )
        exceeded = current_cost >= threshold.threshold_usd
        approaching = percentage >= Decimal("80.0")

        # Only include if threshold is exceeded or approaching (and alert_on_approach is enabled)
        if exceeded or (approaching and threshold.alert_on_approach):
            violation = {
                "threshold_id": threshold.id,
                "period": threshold.period,
                "threshold_usd": threshold.threshold_usd,
                "current_cost": current_cost,
                "percentage": percentage,
                "exceeded": exceeded,
                "approaching": approaching,
                "discord_webhook_url": threshold.discord_webhook_url,
            }

            if exceeded:
                violation["exceeded_by"] = current_cost - threshold.threshold_usd

            violations.append(violation)

            log.info(
                "cost_threshold_violation_detected",
                threshold_id=str(threshold.id),
                channel_id=str(channel_id),
                period=threshold.period,
                threshold_usd=str(threshold.threshold_usd),
                current_cost=str(current_cost),
                percentage=str(percentage),
                exceeded=exceeded,
                approaching=approaching,
            )

    return violations


async def create_cost_threshold(
    db: AsyncSession,
    channel_id: UUID,
    threshold_usd: Decimal,
    period: str,
    enabled: bool = True,
    alert_on_approach: bool = True,
    discord_webhook_url: str | None = None,
) -> CostThreshold:
    """Create a new cost threshold for a channel (Story 8.8, Task 3).

    Args:
        db: Database session
        channel_id: Channel identifier (UUID)
        threshold_usd: Cost limit in USD (must be > 0)
        period: "weekly" or "monthly"
        enabled: Whether threshold checking is active (default: True)
        alert_on_approach: Alert at 80% threshold (default: True)
        discord_webhook_url: Optional per-threshold webhook override

    Returns:
        Created CostThreshold object

    Raises:
        ValueError: If threshold_usd <= 0 or invalid period
    """
    # Validate inputs
    if threshold_usd <= 0:
        raise ValueError("threshold_usd must be greater than 0")
    if period not in ("weekly", "monthly"):
        raise ValueError("period must be 'weekly' or 'monthly'")

    threshold = CostThreshold(
        channel_id=channel_id,
        threshold_usd=threshold_usd,
        period=period,
        enabled=enabled,
        alert_on_approach=alert_on_approach,
        discord_webhook_url=discord_webhook_url,
    )

    db.add(threshold)
    await db.commit()
    await db.refresh(threshold)

    log.info(
        "cost_threshold_created",
        threshold_id=str(threshold.id),
        channel_id=str(channel_id),
        threshold_usd=str(threshold_usd),
        period=period,
        enabled=enabled,
    )

    return threshold


async def update_cost_threshold(
    db: AsyncSession,
    threshold_id: UUID,
    threshold_usd: Decimal | None = None,
    enabled: bool | None = None,
    alert_on_approach: bool | None = None,
    discord_webhook_url: str | None = None,
) -> CostThreshold:
    """Update an existing cost threshold (Story 8.8, Task 3).

    Args:
        db: Database session
        threshold_id: Threshold identifier (UUID)
        threshold_usd: New cost limit (optional)
        enabled: New enabled status (optional)
        alert_on_approach: New alert_on_approach setting (optional)
        discord_webhook_url: New webhook URL (optional, use "" to clear)

    Returns:
        Updated CostThreshold object

    Raises:
        ValueError: If threshold not found or invalid threshold_usd
    """
    stmt = select(CostThreshold).where(CostThreshold.id == threshold_id)
    result = await db.execute(stmt)
    threshold = result.scalar_one_or_none()

    if not threshold:
        raise ValueError(f"Cost threshold {threshold_id} not found")

    # Update fields if provided
    if threshold_usd is not None:
        if threshold_usd <= 0:
            raise ValueError("threshold_usd must be greater than 0")
        threshold.threshold_usd = threshold_usd

    if enabled is not None:
        threshold.enabled = enabled

    if alert_on_approach is not None:
        threshold.alert_on_approach = alert_on_approach

    if discord_webhook_url is not None:
        threshold.discord_webhook_url = discord_webhook_url if discord_webhook_url else None

    await db.commit()
    await db.refresh(threshold)

    log.info(
        "cost_threshold_updated",
        threshold_id=str(threshold_id),
        channel_id=str(threshold.channel_id),
        threshold_usd=str(threshold.threshold_usd),
        enabled=threshold.enabled,
    )

    return threshold


async def delete_cost_threshold(
    db: AsyncSession,
    threshold_id: UUID,
) -> bool:
    """Delete a cost threshold (Story 8.8, Task 3).

    Args:
        db: Database session
        threshold_id: Threshold identifier (UUID)

    Returns:
        True if deleted, False if not found
    """
    stmt = select(CostThreshold).where(CostThreshold.id == threshold_id)
    result = await db.execute(stmt)
    threshold = result.scalar_one_or_none()

    if not threshold:
        return False

    channel_id = threshold.channel_id
    await db.delete(threshold)
    await db.commit()

    log.info("cost_threshold_deleted", threshold_id=str(threshold_id), channel_id=str(channel_id))

    return True


async def generate_weekly_cost_report(db: AsyncSession) -> None:
    """Generate weekly cost report for all channels (Story 8.8, Task 4).

    Called by weekly scheduler (Monday 00:00 UTC) to:
    1. Calculate weekly cost summaries for all active channels
    2. Check cost thresholds and send alerts for violations
    3. Log weekly cost report summary

    Args:
        db: Database session

    Note:
        Does not raise exceptions - logs errors but continues processing other channels.
        Integrates with Story 8.6 weekly metrics scheduler.
    """
    log.info("weekly_cost_report_started")

    # Get all active channels
    stmt = select(Channel).where(Channel.is_active == True)  # noqa: E712
    result = await db.execute(stmt)
    channels = result.scalars().all()

    total_violations = 0
    channels_processed = 0

    for channel in channels:
        try:
            # Get weekly cost summary
            summary = await get_weekly_cost_summary(db, channel.id)

            # Check cost thresholds
            violations = await check_cost_thresholds(db, channel.id)

            if violations:
                total_violations += len(violations)
                log.warning(
                    "weekly_cost_threshold_violations_detected",
                    channel_id=str(channel.id),
                    channel_name=channel.channel_name,
                    violation_count=len(violations),
                    weekly_cost=str(summary["total_cost"]),
                )

                # Send alerts for violations (Discord webhooks)
                for violation in violations:
                    await _send_cost_threshold_alert(channel=channel, violation=violation)

            channels_processed += 1

            log.info(
                "channel_weekly_cost_summary",
                channel_id=str(channel.id),
                channel_name=channel.channel_name,
                weekly_cost=str(summary["total_cost"]),
                video_count=summary["video_count"],
                violations=len(violations),
            )

        except Exception as e:
            log.error(
                "channel_cost_report_failed",
                channel_id=str(channel.id),
                channel_name=channel.channel_name,
                error=str(e),
                exc_info=True,
            )
            # Continue processing other channels

    log.info(
        "weekly_cost_report_completed",
        channels_processed=channels_processed,
        total_violations=total_violations,
    )


async def _send_cost_threshold_alert(channel: "Channel", violation: dict[str, Any]) -> None:
    """Send Discord alert for cost threshold violation (Story 8.8, Task 4).

    Integrates with Story 6.6 Discord alerting pattern.

    Args:
        channel: Channel object with name for alert
        violation: Violation dict from check_cost_thresholds()

    Note:
        Uses violation["discord_webhook_url"] if set, otherwise uses global DISCORD_WEBHOOK_URL.
        Logs error but does not raise on alert failure.
    """
    import os

    import httpx

    # Determine webhook URL (per-threshold override or global)
    webhook_url = violation.get("discord_webhook_url") or os.getenv("DISCORD_WEBHOOK_URL")

    if not webhook_url:
        log.warning(
            "discord_webhook_not_configured",
            channel_id=str(channel.id),
            threshold_id=str(violation["threshold_id"]),
        )
        return

    # Build alert message
    severity = "🔴 EXCEEDED" if violation["exceeded"] else "🟡 APPROACHING"
    message = f"""
**Cost Threshold Alert - {channel.channel_name}**

{severity} {violation["period"].capitalize()} Budget Limit

- **Threshold**: ${violation["threshold_usd"]}
- **Current Cost**: ${violation["current_cost"]} ({violation["percentage"]:.1f}%)
- **Period**: {violation["period"].capitalize()}
"""

    if violation["exceeded"]:
        message += f"- **Exceeded By**: ${violation.get('exceeded_by', 0)}\n"

    message += f"\n_Channel: {channel.channel_name} ({channel.id})_"

    # Send Discord webhook
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(webhook_url, json={"content": message}, timeout=10.0)
            response.raise_for_status()

        log.info(
            "cost_threshold_alert_sent",
            channel_id=str(channel.id),
            threshold_id=str(violation["threshold_id"]),
            severity="exceeded" if violation["exceeded"] else "approaching",
        )

    except Exception as e:
        log.error(
            "cost_threshold_alert_failed",
            channel_id=str(channel.id),
            threshold_id=str(violation["threshold_id"]),
            error=str(e),
            exc_info=True,
        )
        # Don't raise - log error and continue


# ============================================================================
# Story 8.8: Task 5 - Cost Trend Analysis Functions
# ============================================================================


async def calculate_cost_trend(
    db: AsyncSession, channel_id: UUID, weeks: int = 4
) -> dict[str, Any]:
    """Calculate week-over-week cost trends (Story 8.8, Task 5).

    Args:
        channel_id: Channel identifier (UUID)
        weeks: Number of weeks to analyze (default: 4)

    Returns:
        Dict with week-over-week changes:
        {
            "weeks": int,
            "trend": "increasing" | "decreasing" | "stable",
            "percentage_change": Decimal,
            "weekly_costs": [Decimal, ...],  # Ordered oldest to newest
            "average_cost": Decimal
        }
    """
    today = datetime.now(timezone.utc)
    weekly_costs = []

    # Get costs for each week (going back N weeks)
    for week_offset in range(weeks, 0, -1):
        week_start = today - timedelta(days=(week_offset * 7) + today.weekday())
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        week_end = (week_start + timedelta(days=6)).replace(
            hour=23, minute=59, second=59, microsecond=999999
        )

        summary = await get_channel_cost_summary(
            db=db, channel_id=channel_id, start_date=week_start, end_date=week_end
        )
        weekly_costs.append(summary["total_cost"])

    # Calculate trend
    if len(weekly_costs) < 2:
        return {
            "weeks": weeks,
            "trend": "stable",
            "percentage_change": Decimal("0.00"),
            "weekly_costs": weekly_costs,
            "average_cost": sum(weekly_costs) / len(weekly_costs)
            if weekly_costs
            else Decimal("0.00"),
        }

    # Compare most recent week to average of previous weeks
    recent_week = weekly_costs[-1]
    previous_avg = (
        sum(weekly_costs[:-1]) / len(weekly_costs[:-1])
        if len(weekly_costs) > 1
        else Decimal("0.00")
    )

    if previous_avg > 0:
        percentage_change = ((recent_week - previous_avg) / previous_avg) * 100
    else:
        percentage_change = Decimal("0.00")

    # Determine trend (>10% change is significant)
    if percentage_change > 10:
        trend = "increasing"
    elif percentage_change < -10:
        trend = "decreasing"
    else:
        trend = "stable"

    return {
        "weeks": weeks,
        "trend": trend,
        "percentage_change": percentage_change,
        "weekly_costs": weekly_costs,
        "average_cost": sum(weekly_costs) / len(weekly_costs),
    }


# ============================================================================
# Story 8.8: Task 6 - Dashboard Data Aggregation
# ============================================================================

# Simple in-memory cache for dashboard data (5-minute TTL)
_dashboard_cache: dict[str, tuple[datetime, dict[str, Any]]] = {}
_CACHE_TTL_SECONDS = 300  # 5 minutes


async def get_dashboard_data(
    db: AsyncSession, channel_id: UUID, use_cache: bool = True
) -> dict[str, Any]:
    """Get comprehensive cost dashboard data (Story 8.8, Task 6).

    Aggregates all cost data into single dashboard response with 5-minute caching.

    Args:
        db: Database session
        channel_id: Channel identifier (UUID)
        use_cache: Whether to use cached data (default: True)

    Returns:
        Complete dashboard data:
        {
            "weekly_summary": {...},
            "monthly_summary": {...},
            "trend": {...},
            "channel_comparison": [...],
            "thresholds": [...],
            "generated_at": datetime
        }
    """
    cache_key = f"dashboard:{channel_id}"

    # Check cache
    if use_cache and cache_key in _dashboard_cache:
        cached_time, cached_data = _dashboard_cache[cache_key]
        age_seconds = (datetime.now(timezone.utc) - cached_time).total_seconds()

        if age_seconds < _CACHE_TTL_SECONDS:
            log.debug(
                "dashboard_data_cache_hit", channel_id=str(channel_id), age_seconds=age_seconds
            )
            return cached_data

    # Fetch fresh data
    log.debug("dashboard_data_cache_miss", channel_id=str(channel_id))

    weekly_summary = await get_weekly_cost_summary(db, channel_id)
    monthly_summary = await get_monthly_cost_summary(db, channel_id)
    trend = await calculate_cost_trend(db, channel_id, weeks=4)
    comparison = await get_cost_comparison_across_channels(db, days=30)
    violations = await check_cost_thresholds(db, channel_id)

    dashboard_data = {
        "weekly_summary": weekly_summary,
        "monthly_summary": monthly_summary,
        "trend": trend,
        "channel_comparison": comparison,
        "threshold_violations": violations,
        "generated_at": datetime.now(timezone.utc),
    }

    # Update cache
    _dashboard_cache[cache_key] = (datetime.now(timezone.utc), dashboard_data)

    log.info(
        "dashboard_data_generated",
        channel_id=str(channel_id),
        weekly_cost=str(weekly_summary["total_cost"]),
        monthly_cost=str(monthly_summary["total_cost"]),
        violations=len(violations),
    )

    return dashboard_data
