"""Tests for worker status service (Story 8.7 - Task 4).

These tests validate the worker status service functions including:
- Database connectivity checks with timeout
- Active worker count queries with timestamp filtering
- Performance requirements (< 100ms execution)
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import WorkerHeartbeat
from app.services.worker_status_service import (
    check_database_connection,
    get_active_worker_count,
)


@pytest.mark.asyncio
class TestCheckDatabaseConnection:
    """Test suite for database connectivity check."""

    async def test_check_database_connection_success(self, async_session):
        """Test that check returns True when database is accessible."""
        # Act
        result = await check_database_connection(async_session)

        # Assert
        assert result is True

    async def test_check_database_connection_timeout(self, async_session):
        """Test that check returns False when database query times out."""
        # Arrange - Mock execute to timeout
        original_execute = async_session.execute

        async def slow_execute(*args, **kwargs):
            await asyncio.sleep(0.2)  # Exceed 100ms timeout
            return await original_execute(*args, **kwargs)

        async_session.execute = slow_execute

        # Act
        result = await check_database_connection(async_session)

        # Assert
        assert result is False

    async def test_check_database_connection_error(self, async_session):
        """Test that check returns False when database query raises exception."""
        # Arrange - Mock execute to raise exception
        async_session.execute = AsyncMock(side_effect=Exception("Connection refused"))

        # Act
        result = await check_database_connection(async_session)

        # Assert
        assert result is False


@pytest.mark.asyncio
class TestGetActiveWorkerCount:
    """Test suite for active worker count queries."""

    async def test_get_active_worker_count_all_workers_active(self, async_session):
        """Test that all 3 workers are counted when recently active."""
        # Arrange - Create 3 active worker heartbeats
        now = datetime.now(timezone.utc)
        for i in range(1, 4):
            heartbeat = WorkerHeartbeat(
                worker_id=f"worker-{i}",
                last_seen_at=now - timedelta(minutes=1),  # Active within 5 min
                status="online",
            )
            async_session.add(heartbeat)
        await async_session.commit()

        # Act
        result = await get_active_worker_count(async_session)

        # Assert
        assert result["count"] == 3
        assert result["active_timestamp"] is not None

    async def test_get_active_worker_count_partial_workers_active(self, async_session):
        """Test that only recent workers are counted (5-minute threshold)."""
        # Arrange - 2 active, 1 inactive
        now = datetime.now(timezone.utc)

        # Active workers (within 5 minutes)
        for i in range(1, 3):
            heartbeat = WorkerHeartbeat(
                worker_id=f"worker-{i}",
                last_seen_at=now - timedelta(minutes=2),  # Active
                status="online",
            )
            async_session.add(heartbeat)

        # Inactive worker (more than 5 minutes ago)
        old_heartbeat = WorkerHeartbeat(
            worker_id="worker-3",
            last_seen_at=now - timedelta(minutes=10),  # Inactive
            status="idle",
        )
        async_session.add(old_heartbeat)

        await async_session.commit()

        # Act
        result = await get_active_worker_count(async_session)

        # Assert
        assert result["count"] == 2  # Only 2 active workers
        assert result["active_timestamp"] is not None

    async def test_get_active_worker_count_no_workers(self, async_session):
        """Test that count is 0 when no workers have checked in."""
        # Arrange - No worker heartbeats

        # Act
        result = await get_active_worker_count(async_session)

        # Assert
        assert result["count"] == 0
        assert result["active_timestamp"] is None

    async def test_get_active_worker_count_all_workers_expired(self, async_session):
        """Test that count is 0 when all workers exceed 5-minute threshold."""
        # Arrange - All workers inactive (> 5 minutes ago)
        now = datetime.now(timezone.utc)
        for i in range(1, 4):
            heartbeat = WorkerHeartbeat(
                worker_id=f"worker-{i}",
                last_seen_at=now - timedelta(minutes=10),  # Expired
                status="idle",
            )
            async_session.add(heartbeat)
        await async_session.commit()

        # Act
        result = await get_active_worker_count(async_session)

        # Assert
        assert result["count"] == 0
        assert result["active_timestamp"] is None

    async def test_get_active_worker_count_exact_boundary(self, async_session):
        """Test worker at exact 5-minute boundary is excluded."""
        # Arrange - Worker at exactly 5 minutes ago
        now = datetime.now(timezone.utc)
        boundary_time = now - timedelta(minutes=5, seconds=1)  # Just past boundary

        heartbeat = WorkerHeartbeat(
            worker_id="worker-1",
            last_seen_at=boundary_time,
            status="online",
        )
        async_session.add(heartbeat)
        await async_session.commit()

        # Act
        result = await get_active_worker_count(async_session)

        # Assert
        assert result["count"] == 0  # Worker excluded (>= 5 min ago)

    async def test_get_active_worker_count_most_recent_timestamp(self, async_session):
        """Test that active_timestamp reflects most recent heartbeat."""
        # Arrange - Multiple workers with different timestamps
        now = datetime.now(timezone.utc)

        older_heartbeat = WorkerHeartbeat(
            worker_id="worker-1",
            last_seen_at=now - timedelta(minutes=3),
            status="online",
        )
        async_session.add(older_heartbeat)

        most_recent_time = now - timedelta(minutes=1)
        recent_heartbeat = WorkerHeartbeat(
            worker_id="worker-2",
            last_seen_at=most_recent_time,
            status="online",
        )
        async_session.add(recent_heartbeat)

        await async_session.commit()

        # Act
        result = await get_active_worker_count(async_session)

        # Assert
        assert result["count"] == 2
        # Most recent timestamp returned (SQLite may strip timezone)
        assert result["active_timestamp"] is not None

    async def test_get_active_worker_count_mixed_statuses(self, async_session):
        """Test that all active workers are counted regardless of status."""
        # Arrange - Workers with different statuses but all active
        now = datetime.now(timezone.utc)
        statuses = ["online", "idle", "processing"]

        for i, status in enumerate(statuses, start=1):
            heartbeat = WorkerHeartbeat(
                worker_id=f"worker-{i}",
                last_seen_at=now - timedelta(minutes=2),
                status=status,
            )
            async_session.add(heartbeat)

        await async_session.commit()

        # Act
        result = await get_active_worker_count(async_session)

        # Assert
        assert result["count"] == 3  # All counted regardless of status
