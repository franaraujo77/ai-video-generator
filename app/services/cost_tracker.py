"""Cost Tracking Service (Stub).

This module provides cost tracking functionality for video generation.
NOTE: This is a stub implementation until Story 3.3 is fully completed.
The full implementation should track costs in a video_costs table.

Dependencies:
    - Story 3.3: Full cost tracking implementation
    - Epic 1: Database models (VideoCost table)
"""

from decimal import Decimal
from typing import Any
from uuid import UUID

from app.utils.logging import get_logger

log = get_logger(__name__)


async def track_api_cost(
    db: Any, task_id: UUID, component: str, cost_usd: Decimal, api_calls: int, units_consumed: int
) -> None:
    """Track API cost for a video component.

    STUB IMPLEMENTATION: Logs costs but doesn't persist to database.
    Full implementation will save to video_costs table.

    Args:
        db: Database session (AsyncSession from SQLAlchemy)
        task_id: Task UUID (costs are tracked per task, not per video)
        component: Component name (e.g., "kling_video_clips")
        cost_usd: Cost in USD (Decimal for precision)
        api_calls: Number of API calls made
        units_consumed: Number of units consumed (e.g., clips generated)

    Example:
        >>> await track_api_cost(
        ...     db=db,
        ...     task_id=task.id,
        ...     component="kling_video_clips",
        ...     cost_usd=Decimal("7.56"),
        ...     api_calls=18,
        ...     units_consumed=18,
        ... )
    """
    log.info(
        "cost_tracked",
        task_id=str(task_id),
        component=component,
        cost_usd=str(cost_usd),
        api_calls=api_calls,
        units_consumed=units_consumed,
        note="STUB: Cost not persisted to database (waiting for Story 3.3)",
    )
    # TODO: Implement full cost tracking when VideoCost model exists
    # async with db.begin():
    #     cost_record = VideoCost(
    #         video_id=video_id,
    #         component=component,
    #         cost_usd=cost_usd,
    #         api_calls=api_calls,
    #         units_consumed=units_consumed
    #     )
    #     db.add(cost_record)
    #     await db.commit()
