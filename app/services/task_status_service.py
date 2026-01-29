"""Task status service for queue depth monitoring (Story 8.7).

This service provides functions to query task queue status for the
health check endpoint.

Functions:
    - get_queue_depth: Count pending + queued tasks waiting for processing
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PENDING_STATUSES, Task


async def get_queue_depth(db: AsyncSession) -> int:
    """Get count of queued tasks awaiting processing.

    Queries Task table for tasks in PENDING_STATUSES (queued).
    Health check endpoint uses this for informational visibility into
    system workload (not a health gate - just reporting).

    Args:
        db: Async database session

    Returns:
        Integer count of tasks waiting to be processed

    Performance:
        - Uses indexed query on status column (< 100ms)
        - COUNT aggregation on filtered rows (efficient)
        - Expected execution time: < 50ms on healthy database

    Status Filtering:
        - Uses PENDING_STATUSES constant from models.py
        - Currently: [TaskStatus.QUEUED] - tasks enqueued awaiting worker availability

    Example:
        ```python
        depth = await get_queue_depth(db)
        # 42 tasks waiting for processing
        ```
    """
    result = await db.execute(select(func.count(Task.id)).where(Task.status.in_(PENDING_STATUSES)))
    count = result.scalar_one()
    return count
