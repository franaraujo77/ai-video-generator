"""Worker status service for health check monitoring (Story 8.7).

This service provides functions to check worker heartbeat status and database
connectivity for the health check endpoint.

Functions:
    - check_database_connection: Verify database connectivity with timeout
    - get_active_worker_count: Query active workers (last 5 minutes)
"""

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import WorkerHeartbeat


async def check_database_connection(db: AsyncSession) -> bool:
    """Check database connectivity with 100ms timeout.

    Used by health check endpoint to determine if database is reachable.
    Fast execution (< 100ms) is critical for staying within 500ms budget.

    Args:
        db: Async database session

    Returns:
        True if database is connected and responsive, False otherwise

    Performance:
        - Uses simple SELECT 1 query (no table scan)
        - 100ms timeout prevents health check from hanging
        - Expected execution time: < 50ms on healthy database
    """
    try:
        # Simple query with 100ms timeout
        await asyncio.wait_for(db.execute(select(1)), timeout=0.1)
        return True
    except (asyncio.TimeoutError, Exception):
        # Any error (timeout, connection refused, etc.) = database unavailable
        return False


async def get_active_worker_count(db: AsyncSession) -> dict[str, int | str | None]:
    """Get count of workers active in last 5 minutes.

    Queries WorkerHeartbeat table for workers with recent check-ins.
    Health check endpoint uses this to determine if system is degraded
    (fewer than expected 3 workers active).

    Args:
        db: Async database session

    Returns:
        Dictionary with:
            - count: Number of active workers (0-3 expected)
            - active_timestamp: ISO timestamp of most recent heartbeat (or None)

    Performance:
        - Uses indexed query on last_seen_at column (< 100ms)
        - COUNT + MAX aggregation (efficient, no full table scan)
        - Expected execution time: < 50ms on healthy database

    Example:
        ```python
        result = await get_active_worker_count(db)
        # {"count": 3, "active_timestamp": "2026-01-28T12:00:00+00:00"}
        ```
    """
    five_minutes_ago = datetime.now(timezone.utc) - timedelta(minutes=5)

    # Query: COUNT active workers + MAX last_seen_at timestamp
    # Uses ix_worker_heartbeats_last_seen_at index for fast execution
    result = await db.execute(
        select(func.count(WorkerHeartbeat.id), func.max(WorkerHeartbeat.last_seen_at)).where(
            WorkerHeartbeat.last_seen_at >= five_minutes_ago
        )
    )
    count, most_recent = result.one()

    return {
        "count": count or 0,
        "active_timestamp": most_recent.isoformat() if most_recent else None,
    }
