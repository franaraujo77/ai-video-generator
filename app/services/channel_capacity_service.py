"""Channel capacity tracking service for queue management.

This module provides the ChannelCapacityService class for tracking queue depth
and processing capacity per channel (FR13, FR16). This enables:
- Monitoring channel load
- Fair scheduling across channels
- Capacity-based task selection for workers

Capacity Calculation:
    - pending_count: Tasks with status = "pending"
    - in_progress_count: Tasks with status IN ("claimed", "processing", "awaiting_review")
    - has_capacity: True when in_progress_count < max_concurrent

Usage:
    >>> service = ChannelCapacityService()
    >>> stats = await service.get_queue_stats(db)
    >>> channels_with_capacity = await service.get_channels_with_capacity(db)
"""

from dataclasses import dataclass

import structlog
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import IN_PROGRESS_STATUSES, PENDING_STATUSES, Channel, Task

log = structlog.get_logger()


@dataclass(frozen=True)
class ChannelQueueStats:
    """Queue statistics for a single channel.

    Immutable dataclass representing the current queue state for a channel.
    Used by workers to determine task scheduling and by operators for monitoring.

    Attributes:
        channel_id: Business identifier for the channel.
        channel_name: Human-readable display name.
        pending_count: Number of tasks with status='pending'.
        in_progress_count: Number of tasks with status in (claimed, processing, awaiting_review).
        max_concurrent: Maximum allowed concurrent tasks for this channel.
        has_capacity: True if in_progress_count < max_concurrent.
    """

    channel_id: str
    channel_name: str
    pending_count: int
    in_progress_count: int
    max_concurrent: int
    has_capacity: bool


class ChannelCapacityService:
    """Service for tracking channel queue depth and processing capacity.

    Provides methods for:
    - Getting queue statistics per channel (get_queue_stats)
    - Checking specific channel capacity (get_channel_capacity)
    - Checking if a channel has capacity (has_capacity)
    - Getting list of channels with available capacity (get_channels_with_capacity)

    All methods take an AsyncSession for dependency injection.
    """

    async def get_queue_stats(self, db: AsyncSession) -> list[ChannelQueueStats]:
        """Get queue depth per channel.

        Returns count of pending and in-progress tasks per active channel.
        Uses a single aggregation query with JOIN to avoid N+1 queries.

        Args:
            db: Async database session.

        Returns:
            List of ChannelQueueStats for all active channels.
            Channels with no tasks return zero counts.
        """
        # Use SQLAlchemy 2.0 select() style with aggregation
        stmt = (
            select(
                Channel.channel_id,
                Channel.channel_name,
                Channel.max_concurrent,
                func.count(case((Task.status.in_(PENDING_STATUSES), 1))).label("pending_count"),
                func.count(case((Task.status.in_(IN_PROGRESS_STATUSES), 1))).label(
                    "in_progress_count"
                ),
            )
            .outerjoin(Task, Channel.id == Task.channel_id)
            .where(Channel.is_active == True)  # noqa: E712 - SQLAlchemy needs ==
            .group_by(Channel.channel_id, Channel.channel_name, Channel.max_concurrent)
        )

        result = await db.execute(stmt)
        rows = result.all()

        stats = [
            ChannelQueueStats(
                channel_id=row.channel_id,
                channel_name=row.channel_name,
                pending_count=row.pending_count,
                in_progress_count=row.in_progress_count,
                max_concurrent=row.max_concurrent,
                has_capacity=row.in_progress_count < row.max_concurrent,
            )
            for row in rows
        ]

        log.debug(
            "queue_stats_retrieved",
            channel_count=len(stats),
            total_pending=sum(s.pending_count for s in stats),
            total_in_progress=sum(s.in_progress_count for s in stats),
        )

        return stats

    async def get_channel_capacity(
        self, channel_id: str, db: AsyncSession
    ) -> ChannelQueueStats | None:
        """Get capacity stats for a specific channel.

        Args:
            channel_id: Business identifier for the channel.
            db: Async database session.

        Returns:
            ChannelQueueStats for the specified channel, or None if not found
            or channel is inactive.
        """
        stmt = (
            select(
                Channel.channel_id,
                Channel.channel_name,
                Channel.max_concurrent,
                func.count(case((Task.status.in_(PENDING_STATUSES), 1))).label("pending_count"),
                func.count(case((Task.status.in_(IN_PROGRESS_STATUSES), 1))).label(
                    "in_progress_count"
                ),
            )
            .outerjoin(Task, Channel.id == Task.channel_id)
            .where(Channel.channel_id == channel_id)
            .where(Channel.is_active == True)  # noqa: E712
            .group_by(Channel.channel_id, Channel.channel_name, Channel.max_concurrent)
        )

        result = await db.execute(stmt)
        row = result.one_or_none()

        if row is None:
            log.warning(
                "channel_capacity_not_found",
                channel_id=channel_id,
                message="Channel not found or inactive",
            )
            return None

        stats = ChannelQueueStats(
            channel_id=row.channel_id,
            channel_name=row.channel_name,
            pending_count=row.pending_count,
            in_progress_count=row.in_progress_count,
            max_concurrent=row.max_concurrent,
            has_capacity=row.in_progress_count < row.max_concurrent,
        )

        log.debug(
            "channel_capacity_retrieved",
            channel_id=channel_id,
            pending_count=stats.pending_count,
            in_progress_count=stats.in_progress_count,
            max_concurrent=stats.max_concurrent,
            has_capacity=stats.has_capacity,
        )

        return stats

    async def has_capacity(self, channel_id: str, db: AsyncSession) -> bool:
        """Check if channel has capacity for new work.

        Capacity is available when:
            in_progress_count < max_concurrent

        In-progress includes: claimed, processing, awaiting_review statuses.

        Args:
            channel_id: Business identifier for the channel.
            db: Async database session.

        Returns:
            True if channel has capacity for new work, False otherwise.
            Returns False if channel not found or inactive.
        """
        stats = await self.get_channel_capacity(channel_id, db)
        if stats is None:
            return False
        return stats.has_capacity

    async def get_channels_with_capacity(self, db: AsyncSession) -> list[str]:
        """Get channel_ids that have capacity for new work.

        Used by workers to determine which channels to pull tasks from.
        Returns empty list if all channels are at capacity.

        Args:
            db: Async database session.

        Returns:
            List of channel_id strings for channels with available capacity.
        """
        stats = await self.get_queue_stats(db)
        channels_with_capacity = [s.channel_id for s in stats if s.has_capacity]

        log.debug(
            "channels_with_capacity",
            count=len(channels_with_capacity),
            channel_ids=channels_with_capacity,
        )

        return channels_with_capacity
