"""Tests for health check endpoint (Story 8.7 - AC1, AC2, AC3, AC4).

These tests validate the health check endpoint including:
- AC1: Basic health check with response time
- AC2: Database connectivity check
- AC3: Worker heartbeat monitoring
- AC4: Performance budget (< 500ms)
"""

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.models import TaskStatus, WorkerHeartbeat
from tests.support.factories import create_channel, create_task


@pytest.mark.asyncio
class TestHealthCheckEndpoint:
    """Test suite for /health endpoint."""

    async def test_health_check_healthy_status_all_systems_operational(
        self, async_client: AsyncClient, async_session
    ):
        """AC1, AC3: Test health check returns healthy when all systems operational."""
        # Arrange - Create 3 active worker heartbeats
        for i in range(1, 4):
            heartbeat = WorkerHeartbeat(
                worker_id=f"worker-{i}",
                last_seen_at=datetime.now(timezone.utc),
                status="online",
                active_task_count=0,
            )
            async_session.add(heartbeat)
        await async_session.commit()

        # Act
        response = await async_client.get("/health")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["database"] == "connected"
        assert data["workers"]["count"] == 3
        assert data["workers"]["active_timestamp"] is not None
        assert "queue_depth" in data
        assert "schedulers" in data

    async def test_health_check_degraded_no_workers_active(
        self, async_client: AsyncClient, async_session
    ):
        """AC3: Test health check returns degraded when no workers active."""
        # Arrange - No worker heartbeats (or old ones)

        # Act
        response = await async_client.get("/health")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["database"] == "connected"
        assert data["workers"]["count"] == 0
        assert data["workers"]["active_timestamp"] is None

    async def test_health_check_degraded_only_one_worker_active(
        self, async_client: AsyncClient, async_session
    ):
        """AC3: Test health check returns degraded when < 3 workers active."""
        # Arrange - Only 1 worker heartbeat
        heartbeat = WorkerHeartbeat(
            worker_id="worker-1",
            last_seen_at=datetime.now(timezone.utc),
            status="online",
            active_task_count=2,
        )
        async_session.add(heartbeat)
        await async_session.commit()

        # Act
        response = await async_client.get("/health")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["database"] == "connected"
        assert data["workers"]["count"] == 1

    async def test_health_check_degraded_workers_stale_heartbeats(
        self, async_client: AsyncClient, async_session
    ):
        """AC3: Test health check returns degraded when workers haven't checked in for 5+ minutes."""
        # Arrange - Create 3 workers with stale heartbeats (> 5 minutes old)
        six_minutes_ago = datetime.now(timezone.utc) - timedelta(minutes=6)
        for i in range(1, 4):
            heartbeat = WorkerHeartbeat(
                worker_id=f"worker-{i}",
                last_seen_at=six_minutes_ago,
                status="online",
                active_task_count=0,
            )
            async_session.add(heartbeat)
        await async_session.commit()

        # Act
        response = await async_client.get("/health")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["database"] == "connected"
        assert data["workers"]["count"] == 0  # Stale workers not counted

    @patch("app.main.check_database_connection")
    async def test_health_check_unhealthy_database_connection_fails(
        self, mock_check_db, async_client: AsyncClient, async_session
    ):
        """AC2: Test health check returns unhealthy when database connection fails."""
        # Arrange - Mock database connection failure
        mock_check_db.return_value = False

        # Act
        response = await async_client.get("/health")

        # Assert
        assert response.status_code == 200  # Always 200 for Railway
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["database"] == "error"

    @patch("app.main.check_database_connection")
    async def test_health_check_unhealthy_database_timeout(
        self, mock_check_db, async_client: AsyncClient, async_session
    ):
        """AC2: Test health check returns unhealthy when database times out."""
        # Arrange - Mock database timeout (should return False, not raise exception)
        mock_check_db.return_value = False

        # Act
        response = await async_client.get("/health")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["database"] == "error"

    async def test_health_check_includes_queue_depth(
        self, async_client: AsyncClient, async_session
    ):
        """AC1: Test health check includes queue depth in response."""
        # Arrange - Create channel and queued tasks
        channel = create_channel(channel_id="poke1")
        async_session.add(channel)
        await async_session.commit()

        for i in range(5):
            task = create_task(
                channel_id=channel.id,
                notion_page_id=f"queued{i}",
                title=f"Task {i}",
                status=TaskStatus.QUEUED,
            )
            async_session.add(task)
        await async_session.commit()

        # Act
        response = await async_client.get("/health")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["queue_depth"] == 5

    async def test_health_check_response_time_within_budget(
        self, async_client: AsyncClient, async_session
    ):
        """AC4: Test health check completes within 500ms performance budget."""
        # Arrange - Create 3 active workers
        for i in range(1, 4):
            heartbeat = WorkerHeartbeat(
                worker_id=f"worker-{i}",
                last_seen_at=datetime.now(timezone.utc),
                status="online",
                active_task_count=0,
            )
            async_session.add(heartbeat)
        await async_session.commit()

        # Act
        start_time = time.time()
        response = await async_client.get("/health")
        elapsed_ms = (time.time() - start_time) * 1000

        # Assert
        assert response.status_code == 200
        assert elapsed_ms < 500, f"Health check took {elapsed_ms:.2f}ms, exceeds 500ms budget"

    async def test_health_check_always_returns_200_ok_even_if_unhealthy(
        self, async_client: AsyncClient, async_session
    ):
        """Test that health check always returns 200 OK (Railway expects 200 for liveness)."""
        # Arrange - No workers (degraded state)

        # Act
        response = await async_client.get("/health")

        # Assert
        assert response.status_code == 200  # Always 200, even if degraded
        data = response.json()
        assert data["status"] == "degraded"

    async def test_health_check_includes_scheduler_status(
        self, async_client: AsyncClient, async_session
    ):
        """Test that health check includes scheduler status fields."""
        # Arrange - Create 3 active workers for healthy state
        for i in range(1, 4):
            heartbeat = WorkerHeartbeat(
                worker_id=f"worker-{i}",
                last_seen_at=datetime.now(timezone.utc),
                status="online",
                active_task_count=0,
            )
            async_session.add(heartbeat)
        await async_session.commit()

        # Act
        response = await async_client.get("/health")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "schedulers" in data
        assert "quota_reset" in data["schedulers"]
        assert "cleanup" in data["schedulers"]
        assert "weekly_metrics" in data["schedulers"]

    async def test_health_check_workers_at_5_minute_boundary(
        self, async_client: AsyncClient, async_session
    ):
        """Test worker count at exact 5-minute boundary (edge case)."""
        # Arrange - Create worker at 4 minutes 59 seconds ago (just inside threshold)
        almost_five_minutes = datetime.now(timezone.utc) - timedelta(minutes=4, seconds=59)
        heartbeat = WorkerHeartbeat(
            worker_id="worker-1",
            last_seen_at=almost_five_minutes,
            status="online",
            active_task_count=0,
        )
        async_session.add(heartbeat)
        await async_session.commit()

        # Act
        response = await async_client.get("/health")

        # Assert
        assert response.status_code == 200
        data = response.json()
        # Worker at 4:59 should be counted (within 5-minute threshold)
        assert data["workers"]["count"] == 1

    async def test_health_check_mixed_active_and_stale_workers(
        self, async_client: AsyncClient, async_session
    ):
        """Test worker count with mixed active and stale workers."""
        # Arrange - Create 2 active + 1 stale worker
        now = datetime.now(timezone.utc)
        heartbeat1 = WorkerHeartbeat(
            worker_id="worker-1",
            last_seen_at=now,
            status="online",
            active_task_count=0,
        )
        heartbeat2 = WorkerHeartbeat(
            worker_id="worker-2",
            last_seen_at=now - timedelta(minutes=2),
            status="online",
            active_task_count=1,
        )
        heartbeat3 = WorkerHeartbeat(
            worker_id="worker-3",
            last_seen_at=now - timedelta(minutes=10),  # Stale
            status="online",
            active_task_count=0,
        )
        async_session.add_all([heartbeat1, heartbeat2, heartbeat3])
        await async_session.commit()

        # Act
        response = await async_client.get("/health")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["workers"]["count"] == 2  # Only active workers counted
        assert data["status"] == "degraded"  # < 3 workers

    async def test_health_check_empty_queue_depth(self, async_client: AsyncClient, async_session):
        """Test health check with empty queue (no pending/queued tasks)."""
        # Arrange - Create 3 active workers, no tasks
        for i in range(1, 4):
            heartbeat = WorkerHeartbeat(
                worker_id=f"worker-{i}",
                last_seen_at=datetime.now(timezone.utc),
                status="online",
                active_task_count=0,
            )
            async_session.add(heartbeat)
        await async_session.commit()

        # Act
        response = await async_client.get("/health")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["queue_depth"] == 0
        assert data["status"] == "healthy"

    async def test_health_check_large_queue_depth(self, async_client: AsyncClient, async_session):
        """Test health check with large queue depth (stress test)."""
        # Arrange - Create channel and 100 queued tasks
        channel = create_channel(channel_id="poke1")
        async_session.add(channel)
        await async_session.commit()

        for i in range(100):
            task = create_task(
                channel_id=channel.id,
                notion_page_id=f"task{i:03d}",
                title=f"Task {i}",
                status=TaskStatus.QUEUED,
            )
            async_session.add(task)
        await async_session.commit()

        # Act
        response = await async_client.get("/health")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["queue_depth"] == 100
