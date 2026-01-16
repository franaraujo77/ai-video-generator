"""YouTube API quota management with per-channel tracking.

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

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import YouTubeQuotaUsage
from app.utils.alerts import send_alert
from app.utils.logging import get_logger

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

# Alert throttling (prevent spam)
MIN_ALERT_INTERVAL_SECONDS = 300  # 5 minutes between alerts per channel

# Track last alert time per channel (in-memory)
_last_alert_times: dict[tuple[UUID, str], datetime] = {}


def _should_send_alert(channel_id: UUID, level: str) -> bool:
    """Check if alert should be sent based on throttling rules.

    Prevents alert spam by enforcing minimum interval between alerts
    per channel per level (WARNING/CRITICAL).

    Args:
        channel_id: Channel UUID
        level: Alert level ("WARNING" or "CRITICAL")

    Returns:
        True if alert should be sent, False if throttled
    """
    from datetime import timedelta

    key = (channel_id, level)
    now = datetime.now()

    last_alert_time = _last_alert_times.get(key)
    if last_alert_time is None:
        # First alert for this channel/level
        _last_alert_times[key] = now
        return True

    # Check if enough time has passed since last alert
    time_since_last = (now - last_alert_time).total_seconds()
    if time_since_last >= MIN_ALERT_INTERVAL_SECONDS:
        _last_alert_times[key] = now
        return True

    # Throttled - too soon since last alert
    log.debug(
        "alert_throttled",
        channel_id=str(channel_id),
        level=level,
        time_since_last=time_since_last,
        min_interval=MIN_ALERT_INTERVAL_SECONDS
    )
    return False


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

    # Trigger alerts (with throttling to prevent spam)
    if percentage >= YOUTUBE_QUOTA_CRITICAL_THRESHOLD:
        if _should_send_alert(channel_id, "CRITICAL"):
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
        if _should_send_alert(channel_id, "WARNING"):
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
