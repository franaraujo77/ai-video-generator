"""Tests for cost tracking service (Story 8.2).

Tests cover:
- track_api_cost() database persistence
- Correlation ID integration from Story 8.1
- Error handling (log but don't fail pipeline)
- Cost aggregation query functions
- Channel-level cost summaries
"""

from decimal import Decimal
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Channel, Task, TaskStatus, VideoCost
from app.services.cost_tracker import (
    track_api_cost,
    get_task_cost_breakdown,
    get_task_total_cost,
    get_channel_cost_summary,
    get_average_cost_per_video,
)
from tests.support.factories import create_channel, create_task


@pytest.mark.asyncio
async def test_track_api_cost_creates_database_record(async_session: AsyncSession):
    """Test that track_api_cost persists to database (not just logging)."""
    # Arrange: Create channel and task
    channel = create_channel(channel_id="test1")
    async_session.add(channel)
    await async_session.flush()

    task = create_task(correlation_id=uuid4(), channel_id=channel.id, status=TaskStatus.GENERATING_ASSETS)
    async_session.add(task)
    await async_session.commit()

    # Act: Track API cost
    await track_api_cost(
        db=async_session,
        task_id=task.id,
        component="kling_video",
        cost_usd=Decimal("7.56"),
        api_calls=18,
        units_consumed=18,
    )

    # Assert: Cost record created in database
    stmt = select(VideoCost).where(VideoCost.task_id == task.id)
    result = await async_session.execute(stmt)
    costs = result.scalars().all()

    assert len(costs) == 1
    assert costs[0].component == "kling_video"
    assert costs[0].cost_usd == Decimal("7.56")
    assert costs[0].units_used == 18


@pytest.mark.asyncio
async def test_track_api_cost_populates_correlation_id(async_session: AsyncSession, monkeypatch):
    """Test that correlation_id from context is automatically populated."""
    # Arrange: Mock correlation ID context
    test_correlation_id = str(uuid4())

    def mock_get_correlation_id():
        return test_correlation_id

    from app.services import cost_tracker as ct_module
    monkeypatch.setattr(ct_module, "get_correlation_id", mock_get_correlation_id)

    # Create channel and task
    channel = create_channel(channel_id="test1")
    async_session.add(channel)
    await async_session.flush()

    task = create_task(correlation_id=uuid4(), channel_id=channel.id, status=TaskStatus.GENERATING_ASSETS)
    async_session.add(task)
    await async_session.commit()

    # Act: Track API cost
    await track_api_cost(
        db=async_session,
        task_id=task.id,
        component="gemini_assets",
        cost_usd=Decimal("1.50"),
        api_calls=22,
        units_consumed=22,
    )

    # Assert: Correlation ID populated
    stmt = select(VideoCost).where(VideoCost.task_id == task.id)
    result = await async_session.execute(stmt)
    cost = result.scalar_one()

    assert cost.correlation_id is not None
    assert str(cost.correlation_id) == test_correlation_id


@pytest.mark.asyncio
async def test_track_api_cost_handles_errors_gracefully(async_session: AsyncSession, caplog, monkeypatch):
    """Test that database failures don't crash pipeline (log error, continue)."""
    # Arrange: Mock commit to raise an exception
    async def mock_commit_error():
        raise Exception("Database connection lost")

    monkeypatch.setattr(async_session, "commit", mock_commit_error)

    # Valid task_id but commit will fail
    task_id = uuid4()

    # Act: Track API cost (commit will fail)
    await track_api_cost(
        db=async_session,
        task_id=task_id,
        component="kling_video",
        cost_usd=Decimal("7.56"),
        api_calls=18,
        units_consumed=18,
    )

    # Assert: No exception raised (graceful error handling)
    # Error logged but pipeline continues
    assert "cost_tracking_failed" in caplog.text


@pytest.mark.asyncio
async def test_get_task_cost_breakdown(async_session: AsyncSession):
    """Test cost breakdown query by component."""
    # Arrange: Create channel and task
    channel = create_channel(channel_id="test1")
    async_session.add(channel)
    await async_session.flush()

    task = create_task(correlation_id=uuid4(), channel_id=channel.id, status=TaskStatus.GENERATING_ASSETS)
    async_session.add(task)
    await async_session.flush()

    # Create multiple cost records
    costs = [
        VideoCost(task_id=task.id, component="gemini_assets", cost_usd=Decimal("1.50"), units_used=22),
        VideoCost(task_id=task.id, component="kling_video", cost_usd=Decimal("7.56"), units_used=18),
        VideoCost(task_id=task.id, component="elevenlabs_narration", cost_usd=Decimal("0.72"), units_used=18),
    ]
    for cost in costs:
        async_session.add(cost)
    await async_session.commit()

    # Act: Get cost breakdown
    breakdown = await get_task_cost_breakdown(async_session, task.id)

    # Assert: All components present with correct costs
    assert breakdown["gemini_assets"] == Decimal("1.50")
    assert breakdown["kling_video"] == Decimal("7.56")
    assert breakdown["elevenlabs_narration"] == Decimal("0.72")


@pytest.mark.asyncio
async def test_get_task_total_cost(async_session: AsyncSession):
    """Test total cost aggregation for a task."""
    # Arrange: Create channel and task
    channel = create_channel(channel_id="test1")
    async_session.add(channel)
    await async_session.flush()

    task = create_task(correlation_id=uuid4(), channel_id=channel.id, status=TaskStatus.GENERATING_ASSETS)
    async_session.add(task)
    await async_session.flush()

    # Create multiple cost records
    costs = [
        VideoCost(task_id=task.id, component="gemini_assets", cost_usd=Decimal("1.50"), units_used=22),
        VideoCost(task_id=task.id, component="kling_video", cost_usd=Decimal("7.56"), units_used=18),
        VideoCost(task_id=task.id, component="elevenlabs_narration", cost_usd=Decimal("0.72"), units_used=18),
        VideoCost(task_id=task.id, component="elevenlabs_sfx", cost_usd=Decimal("0.72"), units_used=18),
    ]
    for cost in costs:
        async_session.add(cost)
    await async_session.commit()

    # Act: Get total cost
    total = await get_task_total_cost(async_session, task.id)

    # Assert: Sum of all components
    assert total == Decimal("10.50")


@pytest.mark.asyncio
async def test_get_task_total_cost_returns_zero_for_no_costs(async_session: AsyncSession):
    """Test that tasks with no cost records return zero (not None)."""
    # Arrange: Create channel and task with no costs
    channel = create_channel(channel_id="test1")
    async_session.add(channel)
    await async_session.flush()

    task = create_task(correlation_id=uuid4(), channel_id=channel.id, status=TaskStatus.QUEUED)
    async_session.add(task)
    await async_session.commit()

    # Act: Get total cost
    total = await get_task_total_cost(async_session, task.id)

    # Assert: Returns Decimal zero, not None
    assert total == Decimal("0.00")


@pytest.mark.asyncio
async def test_get_channel_cost_summary(async_session: AsyncSession):
    """Test channel-level cost aggregation across multiple tasks."""
    # Arrange: Create channel with multiple tasks
    channel = create_channel(channel_id="test1")
    async_session.add(channel)
    await async_session.flush()

    # Task 1
    task1 = create_task(correlation_id=uuid4(), channel_id=channel.id, status=TaskStatus.PUBLISHED)
    async_session.add(task1)
    await async_session.flush()

    cost1 = VideoCost(task_id=task1.id, component="kling_video", cost_usd=Decimal("7.56"), units_used=18)
    async_session.add(cost1)

    # Task 2
    task2 = create_task(correlation_id=uuid4(), channel_id=channel.id, status=TaskStatus.PUBLISHED)
    async_session.add(task2)
    await async_session.flush()

    cost2 = VideoCost(task_id=task2.id, component="kling_video", cost_usd=Decimal("7.56"), units_used=18)
    async_session.add(cost2)

    await async_session.commit()

    # Act: Get channel cost summary
    summary = await get_channel_cost_summary(async_session, channel.id)

    # Assert: Aggregated across both tasks
    assert summary["total_cost"] == Decimal("15.12")
    assert summary["video_count"] == 2
    assert summary["avg_cost_per_video"] == Decimal("7.56")
    assert summary["breakdown_by_component"]["kling_video"] == Decimal("15.12")


@pytest.mark.asyncio
async def test_get_channel_cost_summary_with_date_filter(async_session: AsyncSession):
    """Test channel cost summary filtered by date range."""
    # Arrange: Create channel and task
    channel = create_channel(channel_id="test1")
    async_session.add(channel)
    await async_session.flush()

    task = create_task(correlation_id=uuid4(), channel_id=channel.id, status=TaskStatus.PUBLISHED)
    async_session.add(task)
    await async_session.flush()

    # Create cost with specific timestamp
    old_timestamp = datetime.now(timezone.utc) - timedelta(days=60)
    cost = VideoCost(
        task_id=task.id,
        component="kling_video",
        cost_usd=Decimal("7.56"),
        units_used=18,
        timestamp=old_timestamp
    )
    async_session.add(cost)
    await async_session.commit()

    # Act: Get summary for last 30 days (should exclude old cost)
    start_date = datetime.now(timezone.utc) - timedelta(days=30)
    summary = await get_channel_cost_summary(async_session, channel.id, start_date=start_date)

    # Assert: Old cost not included
    assert summary["total_cost"] == Decimal("0.00")
    assert summary["video_count"] == 0


@pytest.mark.asyncio
async def test_get_average_cost_per_video(async_session: AsyncSession):
    """Test average cost calculation for last N days."""
    # Arrange: Create channel with task
    channel = create_channel(channel_id="test1")
    async_session.add(channel)
    await async_session.flush()

    task = create_task(correlation_id=uuid4(), channel_id=channel.id, status=TaskStatus.PUBLISHED)
    async_session.add(task)
    await async_session.flush()

    costs = [
        VideoCost(task_id=task.id, component="gemini_assets", cost_usd=Decimal("1.50"), units_used=22),
        VideoCost(task_id=task.id, component="kling_video", cost_usd=Decimal("7.56"), units_used=18),
    ]
    for cost in costs:
        async_session.add(cost)
    await async_session.commit()

    # Act: Get average cost for last 30 days
    avg_cost = await get_average_cost_per_video(async_session, channel.id, days=30)

    # Assert: Average of total cost
    assert avg_cost == Decimal("9.06")


@pytest.mark.asyncio
async def test_track_api_cost_rejects_invalid_component(async_session: AsyncSession, caplog):
    """Test that invalid component names are rejected and not persisted."""
    # Arrange: Create channel and task
    channel = create_channel(channel_id="test1")
    async_session.add(channel)
    await async_session.flush()

    task = create_task(correlation_id=uuid4(), channel_id=channel.id, status=TaskStatus.GENERATING_ASSETS)
    async_session.add(task)
    await async_session.commit()

    # Act: Track API cost with invalid component name
    await track_api_cost(
        db=async_session,
        task_id=task.id,
        component="invalid_component_name",  # Invalid!
        cost_usd=Decimal("999.99"),
        api_calls=1,
        units_consumed=1,
    )

    # Assert: No cost record created
    stmt = select(VideoCost).where(VideoCost.task_id == task.id)
    result = await async_session.execute(stmt)
    costs = result.scalars().all()

    assert len(costs) == 0
    assert "invalid_component_name" in caplog.text
