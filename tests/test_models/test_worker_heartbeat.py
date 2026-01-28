"""Tests for WorkerHeartbeat model (Story 8.7 - Task 1).

These tests validate the worker heartbeat infrastructure model including:
- Field validation and types
- Composite unique constraint on worker_id
- Index on last_seen_at for active worker queries
- Model representation and relationships
"""

import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import WorkerHeartbeat


@pytest.mark.asyncio
class TestWorkerHeartbeatModel:
    """Test suite for WorkerHeartbeat model."""

    async def test_create_worker_heartbeat_success(self, async_session):
        """Test creating a valid worker heartbeat record."""
        # Arrange
        worker_id = "worker-1"
        last_seen = datetime.now(timezone.utc)

        # Act
        heartbeat = WorkerHeartbeat(
            worker_id=worker_id,
            last_seen_at=last_seen,
            status="online",
            active_task_count=2
        )
        async_session.add(heartbeat)
        await async_session.commit()

        # Assert
        assert heartbeat.id is not None
        assert heartbeat.worker_id == worker_id
        assert heartbeat.last_seen_at == last_seen
        assert heartbeat.status == "online"
        assert heartbeat.active_task_count == 2
        assert heartbeat.created_at is not None
        assert heartbeat.updated_at is not None

    async def test_worker_id_unique_constraint(self, async_session):
        """Test that worker_id has unique constraint for atomic upserts."""
        # Arrange
        worker_id = "worker-1"
        heartbeat1 = WorkerHeartbeat(
            worker_id=worker_id,
            last_seen_at=datetime.now(timezone.utc),
            status="online"
        )
        async_session.add(heartbeat1)
        await async_session.commit()

        # Act & Assert - Attempting to create duplicate should fail
        heartbeat2 = WorkerHeartbeat(
            worker_id=worker_id,  # Same worker_id
            last_seen_at=datetime.now(timezone.utc),
            status="online"
        )
        async_session.add(heartbeat2)

        with pytest.raises(IntegrityError):
            await async_session.commit()

    async def test_default_values(self, async_session):
        """Test that default values are set correctly."""
        # Arrange & Act - Create with minimal fields
        heartbeat = WorkerHeartbeat(
            worker_id="worker-test",
            last_seen_at=datetime.now(timezone.utc)
        )
        async_session.add(heartbeat)
        await async_session.commit()

        # Assert - Check defaults
        assert heartbeat.status == "online"  # Default status
        assert heartbeat.active_task_count == 0  # Default task count
        assert heartbeat.created_at is not None
        assert heartbeat.updated_at is not None

    async def test_last_seen_at_required(self, async_session):
        """Test that last_seen_at is required field."""
        # Arrange & Act & Assert
        heartbeat = WorkerHeartbeat(
            worker_id="worker-1"
            # Missing last_seen_at - should fail
        )
        async_session.add(heartbeat)

        with pytest.raises(IntegrityError):
            await async_session.commit()

    async def test_worker_id_required(self, async_session):
        """Test that worker_id is required field."""
        # Arrange & Act & Assert
        heartbeat = WorkerHeartbeat(
            last_seen_at=datetime.now(timezone.utc)
            # Missing worker_id - should fail
        )
        async_session.add(heartbeat)

        with pytest.raises(IntegrityError):
            await async_session.commit()

    async def test_query_by_worker_id_index(self, async_session):
        """Test that worker_id index allows efficient lookups."""
        # Arrange - Create multiple heartbeats
        for i in range(1, 4):
            heartbeat = WorkerHeartbeat(
                worker_id=f"worker-{i}",
                last_seen_at=datetime.now(timezone.utc),
                status="online"
            )
            async_session.add(heartbeat)
        await async_session.commit()

        # Act - Query by worker_id (uses ix_worker_heartbeats_worker_id index)
        result = await async_session.execute(
            select(WorkerHeartbeat).where(WorkerHeartbeat.worker_id == "worker-2")
        )
        heartbeat = result.scalar_one()

        # Assert
        assert heartbeat.worker_id == "worker-2"

    async def test_query_by_last_seen_at_index(self, async_session):
        """Test that last_seen_at index allows efficient active worker queries."""
        # Arrange - Create heartbeats with different timestamps
        now = datetime.now(timezone.utc)
        old_timestamp = now - timedelta(minutes=10)
        recent_timestamp = now - timedelta(minutes=2)

        # Old heartbeat (inactive)
        old_heartbeat = WorkerHeartbeat(
            worker_id="worker-old",
            last_seen_at=old_timestamp,
            status="idle"
        )
        async_session.add(old_heartbeat)

        # Recent heartbeats (active)
        for i in range(1, 3):
            heartbeat = WorkerHeartbeat(
                worker_id=f"worker-{i}",
                last_seen_at=recent_timestamp,
                status="online"
            )
            async_session.add(heartbeat)
        await async_session.commit()

        # Act - Query active workers (last 5 minutes) - uses ix_worker_heartbeats_last_seen_at
        five_minutes_ago = now - timedelta(minutes=5)
        result = await async_session.execute(
            select(WorkerHeartbeat).where(WorkerHeartbeat.last_seen_at >= five_minutes_ago)
        )
        active_workers = result.scalars().all()

        # Assert - Only recent workers returned
        assert len(active_workers) == 2
        assert all(w.worker_id.startswith("worker-") for w in active_workers)
        assert "worker-old" not in [w.worker_id for w in active_workers]

    async def test_model_repr(self, async_session):
        """Test __repr__ returns useful debugging information."""
        # Arrange
        last_seen = datetime.now(timezone.utc)
        heartbeat = WorkerHeartbeat(
            worker_id="worker-1",
            last_seen_at=last_seen,
            status="processing"
        )
        async_session.add(heartbeat)
        await async_session.commit()

        # Act
        repr_str = repr(heartbeat)

        # Assert
        assert "WorkerHeartbeat" in repr_str
        assert "worker-1" in repr_str
        assert "processing" in repr_str

    async def test_status_values(self, async_session):
        """Test that different status values are stored correctly."""
        # Arrange & Act - Create heartbeats with different statuses
        statuses = ["online", "idle", "processing"]
        for i, status_val in enumerate(statuses):
            heartbeat = WorkerHeartbeat(
                worker_id=f"worker-{i+1}",
                last_seen_at=datetime.now(timezone.utc),
                status=status_val
            )
            async_session.add(heartbeat)
        await async_session.commit()

        # Assert - Query and verify
        result = await async_session.execute(select(WorkerHeartbeat))
        all_heartbeats = result.scalars().all()

        assert len(all_heartbeats) == 3
        stored_statuses = {h.status for h in all_heartbeats}
        assert stored_statuses == set(statuses)

    async def test_active_task_count_tracking(self, async_session):
        """Test that active_task_count field tracks concurrent tasks correctly."""
        # Arrange & Act
        heartbeat = WorkerHeartbeat(
            worker_id="worker-busy",
            last_seen_at=datetime.now(timezone.utc),
            status="processing",
            active_task_count=5
        )
        async_session.add(heartbeat)
        await async_session.commit()

        # Assert
        assert heartbeat.active_task_count == 5

        # Update task count
        heartbeat.active_task_count = 3
        await async_session.commit()
        await async_session.refresh(heartbeat)

        assert heartbeat.active_task_count == 3
