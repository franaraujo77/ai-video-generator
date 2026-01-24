"""YouTube and Gemini API quota tracking and monitoring service.

Responsibilities:
1. Record YouTube/Gemini API operations with quota costs
2. Check quota availability before operations
3. Trigger alerts at 80% and 100% thresholds
4. Prevent quota exhaustion across multiple channels

Integration:
- Story 6.6: Uses Discord webhook for quota alerts
- Epic 7: YouTube upload service records quota usage
- Epic 4: Workers check quota before claiming upload tasks
- Story 3.3: Asset generation records Gemini quota usage

Timezone Considerations (Code Review Issue #8):
- YouTube API: Quota resets at midnight PST (UTC-8/-7)
- Gemini API: Quota resets at midnight PST (UTC-8/-7)
- Current Implementation: Uses UTC for date boundaries (hardcoded)
- Impact: Quota checks may be off by 7-8 hours from actual API reset
- Future Enhancement: Add configurable QUOTA_TIMEZONE="America/Los_Angeles"
- Recommendation: Document timezone assumption in deployment guide
"""

import os
from datetime import date, datetime, timezone
from uuid import UUID

import structlog
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import GeminiQuotaUsage, YouTubeQuotaUsage
from app.services.alert_service import send_discord_alert

log = structlog.get_logger()

# YouTube Data API v3 quota costs
# Source: https://developers.google.com/youtube/v3/determine_quota_cost
YOUTUBE_OPERATION_COSTS = {
    "upload": 1600,  # videos.insert
    "update": 50,  # videos.update
    "list": 1,  # videos.list
    "search": 100,  # search.list
    "rate": 50,  # videos.rate
    "delete": 50,  # videos.delete
}


async def record_youtube_operation(
    channel_id: UUID,
    operation: str,
    task_id: UUID | None = None,
    video_id: str | None = None,
    db: AsyncSession | None = None,
) -> None:
    """Record YouTube API operation quota usage atomically.

    Uses INSERT ON CONFLICT UPDATE to handle concurrent worker updates safely.

    Args:
        channel_id: Channel UUID that made the API call
        operation: Operation type (e.g., "upload", "list", "search")
        task_id: Task UUID that triggered operation (for correlation)
        video_id: YouTube video ID (if applicable)
        db: Database session

    Raises:
        ValueError: If operation not in YOUTUBE_OPERATION_COSTS

    Integration:
        - Story 6.6: Triggers alerts at 80%/100% thresholds
        - Story 6.8: Core quota tracking implementation
    """
    if operation not in YOUTUBE_OPERATION_COSTS:
        raise ValueError(f"Unknown YouTube operation: {operation}")

    if db is None:
        raise ValueError("Database session required for quota tracking")

    cost = YOUTUBE_OPERATION_COSTS[operation]
    today = datetime.now(timezone.utc).date()

    # Atomic upsert: INSERT ON CONFLICT UPDATE
    # This handles concurrent worker updates safely using database's native atomicity
    stmt = insert(YouTubeQuotaUsage).values(
        channel_id=channel_id,
        date=today,
        units_used=cost,
        daily_limit=10000,  # Default, can be configured per channel
    )

    # SQLite/PostgreSQL compatible upsert: Use text() for excluded pseudo-table reference
    # 'excluded' is a special pseudo-table in SQL containing the values that would be inserted
    # text() prevents the column name from being quoted as a string literal
    stmt = stmt.on_conflict_do_update(
        index_elements=["channel_id", "date"],
        set_={
            "units_used": text("units_used + excluded.units_used"),
        },
    )

    await db.execute(stmt)
    await db.commit()

    # Manually expire any cached YouTube quota objects to ensure fresh read
    # This is needed because expire_on_commit=False in sessions
    # We only expire YouTubeQuotaUsage objects, not other objects like Channel
    for obj in list(db.identity_map.values()):
        if isinstance(obj, YouTubeQuotaUsage):
            await db.refresh(obj)

    # Query updated quota for threshold checks
    quota = await get_youtube_quota_usage(channel_id, today, db)

    if quota:
        # Log quota operation
        log.info(
            "youtube_quota_recorded",
            channel_id=str(channel_id),
            operation=operation,
            cost=cost,
            units_used=quota.units_used,
            daily_limit=quota.daily_limit,
            percentage=round((quota.units_used / quota.daily_limit) * 100, 1),
            task_id=str(task_id) if task_id else None,
            video_id=video_id,
        )

        # Check thresholds and alert if needed
        await check_youtube_quota_thresholds(quota, db)


async def get_youtube_quota_usage(
    channel_id: UUID, date_value: date, db: AsyncSession
) -> YouTubeQuotaUsage | None:
    """Get YouTube quota usage for channel on specific date."""
    stmt = select(YouTubeQuotaUsage).where(
        YouTubeQuotaUsage.channel_id == channel_id, YouTubeQuotaUsage.date == date_value
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def check_youtube_quota(channel_id: UUID, operation: str, db: AsyncSession) -> bool:
    """Check if YouTube quota available for operation.

    Args:
        channel_id: Channel UUID to check quota for
        operation: Operation type (e.g., "upload")
        db: Database session

    Returns:
        bool: True if quota available, False if would exceed limit

    Integration:
        - Epic 4: Workers call this before claiming upload tasks
        - NFR-I4: Quota exhaustion recovery (pause uploads)
        - Story 6.8: Check quota_exhausted flag set at 100% threshold
    """
    if operation not in YOUTUBE_OPERATION_COSTS:
        raise ValueError(f"Unknown YouTube operation: {operation}")

    # CRITICAL (Story 6.8): Check if channel has quota_exhausted flag set
    # This flag is set at 100% threshold and prevents tasks from being claimed
    from app.models import Channel

    stmt = select(Channel).where(Channel.id == channel_id)
    result = await db.execute(stmt)
    channel = result.scalar_one_or_none()

    if channel and channel.youtube_quota_exhausted:
        log.warning(
            "youtube_quota_flag_exhausted",
            channel_id=str(channel_id),
            operation=operation,
            message="Channel quota_exhausted flag set, operation blocked",
        )
        return False

    cost = YOUTUBE_OPERATION_COSTS[operation]
    today = datetime.now(timezone.utc).date()

    quota = await get_youtube_quota_usage(channel_id, today, db)

    if quota is None:
        # No usage today, operation allowed
        return True

    remaining = quota.daily_limit - quota.units_used
    can_proceed = remaining >= cost

    if not can_proceed:
        log.warning(
            "youtube_quota_insufficient",
            channel_id=str(channel_id),
            operation=operation,
            cost=cost,
            units_used=quota.units_used,
            daily_limit=quota.daily_limit,
            remaining=remaining,
        )

    return can_proceed


async def check_youtube_quota_thresholds(
    quota: YouTubeQuotaUsage, db: AsyncSession | None = None
) -> None:
    """Check quota thresholds and trigger alerts if needed.

    Thresholds:
    - 80%: WARNING alert, uploads continue
    - 100%: CRITICAL alert, uploads pause until reset

    Rate Limiting: Max 1 alert per channel per threshold per day (via alert_service)

    Integration:
        - Story 6.6: Uses Discord webhook for alerts
        - NFR-I4: Quota exhaustion triggers pause
    """
    percentage = (quota.units_used / quota.daily_limit) * 100
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")

    if not webhook_url:
        log.warning("discord_webhook_not_configured", message="Quota alerts disabled")
        return

    # 100% CRITICAL threshold
    if percentage >= 100:
        await send_discord_alert(
            alert_type="quota_exhausted",
            severity="CRITICAL",
            title="YouTube Quota Exhausted",
            description=(
                f"YouTube API quota exhausted for channel {quota.channel_id}\n"
                f"Used: {quota.units_used}/{quota.daily_limit} units (100%)\n"
                f"Uploads paused until midnight UTC reset"
            ),
            fields={
                "Channel ID": str(quota.channel_id),
                "Date": str(quota.date),
                "Units Used": f"{quota.units_used}/{quota.daily_limit}",
                "Remaining": "0",
                "Next Reset": "Midnight UTC",
            },
            webhook_url=webhook_url,
        )

        # Set quota_exhausted flag to pause upload tasks (Story 6.8 AC)
        # This prevents workers from claiming upload tasks for this channel
        # Flag will be reset by scheduled job at midnight UTC
        if db:
            from app.models import Channel

            stmt = select(Channel).where(Channel.id == quota.channel_id)
            result = await db.execute(stmt)
            channel = result.scalar_one_or_none()

            if channel and not channel.youtube_quota_exhausted:
                channel.youtube_quota_exhausted = True
                await db.commit()
                log.info(
                    "youtube_quota_exhausted_flag_set",
                    channel_id=str(quota.channel_id),
                    message="Upload tasks paused until quota reset",
                )

        log.critical(
            "youtube_quota_exhausted",
            channel_id=str(quota.channel_id),
            units_used=quota.units_used,
            daily_limit=quota.daily_limit,
            percentage=percentage,
        )

    # 80% WARNING threshold
    elif percentage >= 80:
        remaining_uploads = (quota.daily_limit - quota.units_used) // 1600
        await send_discord_alert(
            alert_type="quota_warning",
            severity="WARNING",
            title="YouTube Quota Warning",
            description=(
                f"YouTube API quota at {percentage:.1f}% for channel {quota.channel_id}\n"
                f"Used: {quota.units_used}/{quota.daily_limit} units\n"
                f"Remaining: {quota.daily_limit - quota.units_used} units "
                f"(~{remaining_uploads} uploads)\n"
                f"Uploads continuing but monitored"
            ),
            fields={
                "Channel ID": str(quota.channel_id),
                "Date": str(quota.date),
                "Usage": f"{percentage:.1f}%",
                "Remaining Uploads": str(remaining_uploads),
                "Next Reset": "Midnight UTC",
            },
            webhook_url=webhook_url,
        )

        log.warning(
            "youtube_quota_warning",
            channel_id=str(quota.channel_id),
            units_used=quota.units_used,
            daily_limit=quota.daily_limit,
            percentage=percentage,
        )


async def record_gemini_operation(
    channel_id: UUID,
    task_id: UUID | None = None,
    asset_name: str | None = None,
    db: AsyncSession | None = None,
) -> None:
    """Record Gemini API operation (image generation request).

    Uses INSERT ON CONFLICT UPDATE to handle concurrent worker updates safely.

    Args:
        channel_id: Channel UUID that made the API call
        task_id: Task UUID that triggered operation (for correlation)
        asset_name: Asset filename being generated (for debugging)
        db: Database session

    Integration:
        - Story 6.8: Gemini quota monitoring (FR34, NFR-I4)
        - Story 3.3: Asset generation records quota usage
    """
    if db is None:
        raise ValueError("Database session required for quota tracking")

    today = datetime.now(timezone.utc).date()

    # Atomic upsert: INSERT ON CONFLICT UPDATE
    # This handles concurrent worker updates safely using database's native atomicity
    stmt = insert(GeminiQuotaUsage).values(
        channel_id=channel_id,
        date=today,
        requests_used=1,
        daily_limit=1500,  # Default Gemini Free Tier
    )

    # SQLite/PostgreSQL compatible upsert: Use text() for excluded pseudo-table reference
    # 'excluded' is a special pseudo-table in SQL containing the values that would be inserted
    # text() prevents the column name from being quoted as a string literal
    stmt = stmt.on_conflict_do_update(
        index_elements=["channel_id", "date"],
        set_={
            "requests_used": text("requests_used + excluded.requests_used"),
        },
    )

    await db.execute(stmt)
    await db.commit()

    # Manually expire any cached Gemini quota objects to ensure fresh read
    # This is needed because expire_on_commit=False in sessions
    # We only expire GeminiQuotaUsage objects, not other objects like Channel
    for obj in list(db.identity_map.values()):
        if isinstance(obj, GeminiQuotaUsage):
            await db.refresh(obj)

    # Query updated quota for threshold checks
    quota = await get_gemini_quota_usage(channel_id, today, db)

    if quota:
        # Log quota operation
        log.info(
            "gemini_quota_recorded",
            channel_id=str(channel_id),
            requests_used=quota.requests_used,
            daily_limit=quota.daily_limit,
            percentage=round((quota.requests_used / quota.daily_limit) * 100, 1),
            task_id=str(task_id) if task_id else None,
            asset_name=asset_name,
        )

        # Check thresholds and alert if needed
        await check_gemini_quota_thresholds(quota, db)


async def get_gemini_quota_usage(
    channel_id: UUID, date_value: date, db: AsyncSession
) -> GeminiQuotaUsage | None:
    """Get Gemini quota usage for channel on specific date."""
    stmt = select(GeminiQuotaUsage).where(
        GeminiQuotaUsage.channel_id == channel_id, GeminiQuotaUsage.date == date_value
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def check_gemini_quota(channel_id: UUID, db: AsyncSession) -> bool:
    """Check if Gemini quota available for asset generation.

    Args:
        channel_id: Channel UUID to check quota for
        db: Database session

    Returns:
        bool: True if quota available, False if would exceed limit

    Integration:
        - Story 3.3: Asset generation checks quota before claiming tasks
        - NFR-I4: Quota exhaustion recovery (pause until midnight PST)
        - Story 6.8: Check quota_exhausted flag set at 100% threshold
    """
    # CRITICAL (Story 6.8): Check if channel has quota_exhausted flag set
    # This flag is set at 100% threshold and prevents tasks from being claimed
    from app.models import Channel

    stmt = select(Channel).where(Channel.id == channel_id)
    result = await db.execute(stmt)
    channel = result.scalar_one_or_none()

    if channel and channel.gemini_quota_exhausted:
        log.warning(
            "gemini_quota_flag_exhausted",
            channel_id=str(channel_id),
            message="Channel quota_exhausted flag set, operation blocked",
        )
        return False

    today = datetime.now(timezone.utc).date()

    quota = await get_gemini_quota_usage(channel_id, today, db)

    if quota is None:
        # No usage today, operation allowed
        return True

    remaining = quota.daily_limit - quota.requests_used
    can_proceed = remaining >= 1  # Each request costs 1

    if not can_proceed:
        log.warning(
            "gemini_quota_insufficient",
            channel_id=str(channel_id),
            requests_used=quota.requests_used,
            daily_limit=quota.daily_limit,
            remaining=remaining,
        )

    return can_proceed


async def check_gemini_quota_thresholds(
    quota: GeminiQuotaUsage, db: AsyncSession | None = None
) -> None:
    """Check Gemini quota thresholds and trigger alerts if needed.

    Thresholds:
    - 80%: WARNING alert, asset generation continues
    - 100%: CRITICAL alert, asset generation paused until reset

    Rate Limiting: Max 1 alert per channel per threshold per day (via alert_service)

    Integration:
        - Story 6.6: Uses Discord webhook for alerts
        - NFR-I4: Quota exhaustion triggers pause
    """
    percentage = (quota.requests_used / quota.daily_limit) * 100
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")

    if not webhook_url:
        log.warning("discord_webhook_not_configured", message="Quota alerts disabled")
        return

    # 100% CRITICAL threshold
    if percentage >= 100:
        await send_discord_alert(
            alert_type="quota_exhausted",
            severity="CRITICAL",
            title="Gemini Quota Exhausted",
            description=(
                f"Gemini API quota exhausted for channel {quota.channel_id}\n"
                f"Used: {quota.requests_used}/{quota.daily_limit} requests (100%)\n"
                f"Asset generation paused until midnight PST reset"
            ),
            fields={
                "Channel ID": str(quota.channel_id),
                "Date": str(quota.date),
                "Requests Used": f"{quota.requests_used}/{quota.daily_limit}",
                "Remaining": "0",
                "Next Reset": "Midnight PST",
            },
            webhook_url=webhook_url,
        )

        # Set quota_exhausted flag to pause asset generation tasks (Story 6.8 AC)
        # This prevents workers from claiming asset generation tasks for this channel
        # Flag will be reset by scheduled job at midnight PST
        if db:
            from app.models import Channel

            stmt = select(Channel).where(Channel.id == quota.channel_id)
            result = await db.execute(stmt)
            channel = result.scalar_one_or_none()

            if channel and not channel.gemini_quota_exhausted:
                channel.gemini_quota_exhausted = True
                await db.commit()
                log.info(
                    "gemini_quota_exhausted_flag_set",
                    channel_id=str(quota.channel_id),
                    message="Asset generation tasks paused until quota reset",
                )

        log.critical(
            "gemini_quota_exhausted",
            channel_id=str(quota.channel_id),
            requests_used=quota.requests_used,
            daily_limit=quota.daily_limit,
            percentage=percentage,
        )

    # 80% WARNING threshold
    elif percentage >= 80:
        remaining_requests = quota.daily_limit - quota.requests_used
        await send_discord_alert(
            alert_type="quota_warning",
            severity="WARNING",
            title="Gemini Quota Warning",
            description=(
                f"Gemini API quota at {percentage:.1f}% for channel {quota.channel_id}\n"
                f"Used: {quota.requests_used}/{quota.daily_limit} requests\n"
                f"Remaining: {remaining_requests} requests\n"
                f"Asset generation continuing but monitored"
            ),
            fields={
                "Channel ID": str(quota.channel_id),
                "Date": str(quota.date),
                "Usage": f"{percentage:.1f}%",
                "Remaining Requests": str(remaining_requests),
                "Next Reset": "Midnight PST",
            },
            webhook_url=webhook_url,
        )

        log.warning(
            "gemini_quota_warning",
            channel_id=str(quota.channel_id),
            requests_used=quota.requests_used,
            daily_limit=quota.daily_limit,
            percentage=percentage,
        )
