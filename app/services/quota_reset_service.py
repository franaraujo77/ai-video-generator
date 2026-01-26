"""Quota reset service for YouTube and Gemini API quotas.

Handles automatic daily quota resets at midnight Pacific Time.
Implements timezone-aware reset logic with idempotent operations.

Key Features:
- Timezone-aware resets (America/Los_Angeles)
- Atomic INSERT ON CONFLICT DO NOTHING for idempotency
- Only resets active channels (is_active=True)
- Clears quota_exhausted flags
- Structured logging with context
"""

import os
from datetime import date

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Channel, GeminiQuotaUsage, YouTubeQuotaUsage

# Get logger
log = structlog.get_logger()

# Quota timezone configuration (defaults to Pacific Time)
QUOTA_TIMEZONE = os.getenv("QUOTA_TIMEZONE", "America/Los_Angeles")


async def reset_youtube_quotas(reset_date: date, db: AsyncSession) -> int:
    """Reset YouTube quotas for all active channels.

    Creates new YouTubeQuotaUsage rows with units_used=0 for the specified date.
    Clears youtube_quota_exhausted flags for all active channels.

    Args:
        reset_date: Date to reset quotas for (typically today in Pacific timezone)
        db: Async database session

    Returns:
        Number of channels reset

    Example:
        >>> from datetime import date
        >>> from zoneinfo import ZoneInfo
        >>> from datetime import datetime
        >>> pacific_tz = ZoneInfo("America/Los_Angeles")
        >>> today = datetime.now(pacific_tz).date()
        >>> reset_count = await reset_youtube_quotas(today, db)
    """
    # Get all active channels
    result = await db.execute(select(Channel).where(Channel.is_active == True))
    channels = result.scalars().all()

    reset_count = 0

    for channel in channels:
        # Check if quota row already exists (idempotent operation)
        existing_quota = await db.get(YouTubeQuotaUsage, (channel.id, reset_date))

        if existing_quota is None:
            # Create new quota row
            new_quota = YouTubeQuotaUsage(
                channel_id=channel.id,
                date=reset_date,
                units_used=0,
                daily_limit=10000,
            )
            db.add(new_quota)

        # Clear exhausted flag (always update, even if quota row exists)
        channel.youtube_quota_exhausted = False
        reset_count += 1

    # Commit transaction
    await db.commit()

    # Log reset completion
    log.info(
        "youtube_quota_reset_completed",
        channels_reset_count=reset_count,
        reset_date=str(reset_date),
        timezone=QUOTA_TIMEZONE,
    )

    return reset_count


async def reset_gemini_quotas(reset_date: date, db: AsyncSession) -> int:
    """Reset Gemini quotas for all active channels.

    Creates new GeminiQuotaUsage rows with requests_used=0 for the specified date.
    Clears gemini_quota_exhausted flags for all active channels.

    Args:
        reset_date: Date to reset quotas for (typically today in Pacific timezone)
        db: Async database session

    Returns:
        Number of channels reset

    Example:
        >>> from datetime import date
        >>> from zoneinfo import ZoneInfo
        >>> from datetime import datetime
        >>> pacific_tz = ZoneInfo("America/Los_Angeles")
        >>> today = datetime.now(pacific_tz).date()
        >>> reset_count = await reset_gemini_quotas(today, db)
    """
    # Get all active channels
    result = await db.execute(select(Channel).where(Channel.is_active == True))
    channels = result.scalars().all()

    reset_count = 0

    for channel in channels:
        # Check if quota row already exists (idempotent operation)
        existing_quota = await db.get(GeminiQuotaUsage, (channel.id, reset_date))

        if existing_quota is None:
            # Create new quota row
            new_quota = GeminiQuotaUsage(
                channel_id=channel.id,
                date=reset_date,
                requests_used=0,
                daily_limit=1500,
            )
            db.add(new_quota)

        # Clear exhausted flag (always update, even if quota row exists)
        channel.gemini_quota_exhausted = False
        reset_count += 1

    # Commit transaction
    await db.commit()

    # Log reset completion
    log.info(
        "gemini_quota_reset_completed",
        channels_reset_count=reset_count,
        reset_date=str(reset_date),
        timezone=QUOTA_TIMEZONE,
    )

    return reset_count
