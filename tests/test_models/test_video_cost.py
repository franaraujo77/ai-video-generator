"""Tests for VideoCost model (Story 8.2).

Tests cover:
- Model field validation
- Foreign key relationships to Task
- Composite indexes
- Decimal precision for financial amounts
- Correlation ID integration
"""

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Channel, Task, TaskStatus, VideoCost
from tests.support.factories import create_channel, create_task


@pytest.mark.asyncio
async def test_video_cost_creation(async_session: AsyncSession):
    """Test basic VideoCost record creation."""
    # Arrange: Create channel and task
    channel = create_channel(channel_id="test1")
    async_session.add(channel)
    await async_session.flush()

    task = create_task(
        correlation_id=uuid4(), channel_id="test1", status=TaskStatus.GENERATING_ASSETS
    )
    async_session.add(task)
    await async_session.flush()

    # Act: Create VideoCost record
    cost = VideoCost(
        task_id=task.id,
        component="kling_video",
        cost_usd=Decimal("7.56"),
        units_used=18,
        correlation_id=uuid4(),
    )
    async_session.add(cost)
    await async_session.commit()

    # Assert: Record created with correct values
    assert cost.id is not None
    assert cost.task_id == task.id
    assert cost.component == "kling_video"
    assert cost.cost_usd == Decimal("7.56")
    assert cost.units_used == 18
    assert cost.timestamp is not None
    assert cost.correlation_id is not None


@pytest.mark.asyncio
async def test_video_cost_task_relationship(async_session: AsyncSession):
    """Test VideoCost -> Task relationship navigation."""
    # Arrange: Create channel and task
    channel = create_channel(channel_id="test1")
    async_session.add(channel)
    await async_session.flush()

    task = create_task(
        correlation_id=uuid4(), channel_id=channel.id, status=TaskStatus.GENERATING_ASSETS
    )
    async_session.add(task)
    await async_session.flush()

    # Act: Create cost record
    cost = VideoCost(
        task_id=task.id,
        component="gemini_assets",
        cost_usd=Decimal("1.50"),
        units_used=22,
    )
    async_session.add(cost)
    await async_session.commit()

    # Assert: Can navigate to task
    await async_session.refresh(cost, ["task"])
    assert cost.task.id == task.id
    assert cost.task.channel_id == channel.id


@pytest.mark.asyncio
async def test_task_costs_relationship(async_session: AsyncSession):
    """Test Task -> costs relationship (one-to-many)."""
    # Arrange: Create channel and task
    channel = create_channel(channel_id="test1")
    async_session.add(channel)
    await async_session.flush()

    task = create_task(
        correlation_id=uuid4(), channel_id="test1", status=TaskStatus.GENERATING_ASSETS
    )
    async_session.add(task)
    await async_session.flush()

    # Act: Create multiple cost records for same task
    costs = [
        VideoCost(
            task_id=task.id,
            component="gemini_assets",
            cost_usd=Decimal("1.50"),
            units_used=22,
        ),
        VideoCost(
            task_id=task.id,
            component="kling_video",
            cost_usd=Decimal("7.56"),
            units_used=18,
        ),
        VideoCost(
            task_id=task.id,
            component="elevenlabs_narration",
            cost_usd=Decimal("0.72"),
            units_used=18,
        ),
    ]
    for cost in costs:
        async_session.add(cost)
    await async_session.commit()

    # Assert: Can navigate from task to all costs
    await async_session.refresh(task, ["costs"])
    assert len(task.costs) == 3
    assert task.costs[0].component == "gemini_assets"
    assert task.costs[1].component == "kling_video"
    assert task.costs[2].component == "elevenlabs_narration"


@pytest.mark.asyncio
async def test_video_cost_cascade_delete(async_session: AsyncSession):
    """Test that deleting task cascades to delete cost records."""
    # Arrange: Create channel, task, and cost
    channel = create_channel(channel_id="test1")
    async_session.add(channel)
    await async_session.flush()

    task = create_task(
        correlation_id=uuid4(), channel_id="test1", status=TaskStatus.GENERATING_ASSETS
    )
    async_session.add(task)
    await async_session.flush()

    cost = VideoCost(
        task_id=task.id,
        component="kling_video",
        cost_usd=Decimal("7.56"),
        units_used=18,
    )
    async_session.add(cost)
    await async_session.commit()

    cost_id = cost.id

    # Act: Delete task
    await async_session.delete(task)
    await async_session.commit()

    # Assert: Cost record also deleted (cascade)
    result = await async_session.get(VideoCost, cost_id)
    assert result is None


@pytest.mark.asyncio
async def test_video_cost_decimal_precision(async_session: AsyncSession):
    """Test Decimal precision for financial amounts (4 decimal places)."""
    # Arrange: Create channel and task
    channel = create_channel(channel_id="test1")
    async_session.add(channel)
    await async_session.flush()

    task = create_task(
        correlation_id=uuid4(), channel_id="test1", status=TaskStatus.GENERATING_ASSETS
    )
    async_session.add(task)
    await async_session.flush()

    # Act: Create cost with 4 decimal places
    cost = VideoCost(
        task_id=task.id,
        component="gemini_assets",
        cost_usd=Decimal("1.5678"),  # 4 decimal places
        units_used=22,
    )
    async_session.add(cost)
    await async_session.commit()

    # Assert: Precision preserved
    result = await async_session.get(VideoCost, cost.id)
    assert result is not None
    assert result.cost_usd == Decimal("1.5678")


@pytest.mark.asyncio
async def test_video_cost_query_by_task_id_timestamp_index(async_session: AsyncSession):
    """Test composite index (task_id, timestamp) for efficient queries."""
    # Arrange: Create channel and task
    channel = create_channel(channel_id="test1")
    async_session.add(channel)
    await async_session.flush()

    task = create_task(
        correlation_id=uuid4(), channel_id="test1", status=TaskStatus.GENERATING_ASSETS
    )
    async_session.add(task)
    await async_session.flush()

    # Create multiple costs for task
    for i, component in enumerate(
        ["gemini_assets", "kling_video", "elevenlabs_narration", "elevenlabs_sfx"]
    ):
        cost = VideoCost(
            task_id=task.id,
            component=component,
            cost_usd=Decimal(f"{i + 1}.00"),
            units_used=18,
        )
        async_session.add(cost)
    await async_session.commit()

    # Act: Query costs for task ordered by timestamp
    stmt = select(VideoCost).where(VideoCost.task_id == task.id).order_by(VideoCost.timestamp)
    result = await async_session.execute(stmt)
    costs = result.scalars().all()

    # Assert: All costs retrieved for task
    assert len(costs) == 4
    assert costs[0].component == "gemini_assets"


@pytest.mark.asyncio
async def test_video_cost_nullable_correlation_id(async_session: AsyncSession):
    """Test that correlation_id is optional (nullable)."""
    # Arrange: Create channel and task
    channel = create_channel(channel_id="test1")
    async_session.add(channel)
    await async_session.flush()

    task = create_task(
        correlation_id=uuid4(), channel_id="test1", status=TaskStatus.GENERATING_ASSETS
    )
    async_session.add(task)
    await async_session.flush()

    # Act: Create cost without correlation_id
    cost = VideoCost(
        task_id=task.id,
        component="kling_video",
        cost_usd=Decimal("7.56"),
        units_used=18,
        # correlation_id is None
    )
    async_session.add(cost)
    await async_session.commit()

    # Assert: Record created successfully
    assert cost.id is not None
    assert cost.correlation_id is None


@pytest.mark.asyncio
async def test_video_cost_repr(async_session: AsyncSession):
    """Test __repr__ method for debugging."""
    # Arrange: Create channel and task
    channel = create_channel(channel_id="test1")
    async_session.add(channel)
    await async_session.flush()

    task = create_task(
        correlation_id=uuid4(), channel_id="test1", status=TaskStatus.GENERATING_ASSETS
    )
    async_session.add(task)
    await async_session.flush()

    # Act: Create cost
    cost = VideoCost(
        task_id=task.id,
        component="kling_video",
        cost_usd=Decimal("7.56"),
        units_used=18,
    )
    async_session.add(cost)
    await async_session.commit()

    # Assert: __repr__ shows key fields
    repr_str = repr(cost)
    assert "VideoCost" in repr_str
    assert str(cost.id) in repr_str
    assert str(task.id) in repr_str
    assert "kling_video" in repr_str
    assert "7.56" in repr_str
