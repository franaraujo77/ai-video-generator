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

from decimal import Decimal
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models import VideoCost, Task
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
    units_consumed: int
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
            correlation_id=UUID(correlation_id) if correlation_id else None
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
            exc_info=True
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
    stmt = select(VideoCost.component, VideoCost.cost_usd).where(
        VideoCost.task_id == task_id
    )
    result = await db.execute(stmt)
    rows = result.all()

    return {row.component: row.cost_usd for row in rows}


async def get_task_total_cost(db: AsyncSession, task_id: UUID) -> Decimal:
    """Get total cost for a task by summing all components.

    Returns:
        Total cost in USD as Decimal
    """
    stmt = select(func.sum(VideoCost.cost_usd)).where(
        VideoCost.task_id == task_id
    )
    result = await db.execute(stmt)
    total = result.scalar_one_or_none()

    return total if total is not None else Decimal("0.00")


async def get_channel_cost_summary(
    db: AsyncSession,
    channel_id: UUID,
    start_date: datetime | None = None,
    end_date: datetime | None = None
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
            "breakdown_by_component": {}
        }

    # Calculate aggregations
    total_cost = sum(cost.cost_usd for cost in costs)
    task_ids = set(cost.task_id for cost in costs)
    video_count = len(task_ids)
    avg_cost = total_cost / video_count if video_count > 0 else Decimal("0.00")

    # Breakdown by component
    breakdown = {}
    for cost in costs:
        breakdown[cost.component] = breakdown.get(cost.component, Decimal("0.00")) + cost.cost_usd

    return {
        "total_cost": total_cost,
        "video_count": video_count,
        "avg_cost_per_video": avg_cost,
        "breakdown_by_component": breakdown
    }


async def get_average_cost_per_video(
    db: AsyncSession,
    channel_id: UUID,
    days: int = 30
) -> Decimal:
    """Get average cost per video for last N days.

    Args:
        channel_id: Channel identifier (UUID)
        days: Number of days to look back (default: 30)

    Returns:
        Average cost per video as Decimal
    """
    start_date = datetime.now(timezone.utc) - timedelta(days=days)
    summary = await get_channel_cost_summary(db, channel_id, start_date=start_date)

    return summary["avg_cost_per_video"]
