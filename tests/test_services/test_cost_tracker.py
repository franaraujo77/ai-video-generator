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

from app.models import Channel, Task, TaskStatus, VideoCost, CostThreshold
from app.services.cost_tracker import (
    track_api_cost,
    get_task_cost_breakdown,
    get_task_total_cost,
    get_channel_cost_summary,
    get_average_cost_per_video,
    get_weekly_cost_summary,
    get_monthly_cost_summary,
    get_cost_comparison_across_channels,
    get_cost_trend_data,
    get_active_thresholds,
    check_cost_thresholds,
    create_cost_threshold,
    update_cost_threshold,
    delete_cost_threshold,
)
from tests.support.factories import create_channel, create_task


@pytest.mark.asyncio
async def test_track_api_cost_creates_database_record(async_session: AsyncSession):
    """Test that track_api_cost persists to database (not just logging)."""
    # Arrange: Create channel and task
    channel = create_channel(channel_id="test1")
    async_session.add(channel)
    await async_session.flush()

    task = create_task(
        correlation_id=uuid4(), channel_id=channel.id, status=TaskStatus.GENERATING_ASSETS
    )
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

    task = create_task(
        correlation_id=uuid4(), channel_id=channel.id, status=TaskStatus.GENERATING_ASSETS
    )
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
async def test_track_api_cost_handles_errors_gracefully(
    async_session: AsyncSession, caplog, monkeypatch
):
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

    task = create_task(
        correlation_id=uuid4(), channel_id=channel.id, status=TaskStatus.GENERATING_ASSETS
    )
    async_session.add(task)
    await async_session.flush()

    # Create multiple cost records
    costs = [
        VideoCost(
            task_id=task.id, component="gemini_assets", cost_usd=Decimal("1.50"), units_used=22
        ),
        VideoCost(
            task_id=task.id, component="kling_video", cost_usd=Decimal("7.56"), units_used=18
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

    task = create_task(
        correlation_id=uuid4(), channel_id=channel.id, status=TaskStatus.GENERATING_ASSETS
    )
    async_session.add(task)
    await async_session.flush()

    # Create multiple cost records
    costs = [
        VideoCost(
            task_id=task.id, component="gemini_assets", cost_usd=Decimal("1.50"), units_used=22
        ),
        VideoCost(
            task_id=task.id, component="kling_video", cost_usd=Decimal("7.56"), units_used=18
        ),
        VideoCost(
            task_id=task.id,
            component="elevenlabs_narration",
            cost_usd=Decimal("0.72"),
            units_used=18,
        ),
        VideoCost(
            task_id=task.id, component="elevenlabs_sfx", cost_usd=Decimal("0.72"), units_used=18
        ),
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

    cost1 = VideoCost(
        task_id=task1.id, component="kling_video", cost_usd=Decimal("7.56"), units_used=18
    )
    async_session.add(cost1)

    # Task 2
    task2 = create_task(correlation_id=uuid4(), channel_id=channel.id, status=TaskStatus.PUBLISHED)
    async_session.add(task2)
    await async_session.flush()

    cost2 = VideoCost(
        task_id=task2.id, component="kling_video", cost_usd=Decimal("7.56"), units_used=18
    )
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
        timestamp=old_timestamp,
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
        VideoCost(
            task_id=task.id, component="gemini_assets", cost_usd=Decimal("1.50"), units_used=22
        ),
        VideoCost(
            task_id=task.id, component="kling_video", cost_usd=Decimal("7.56"), units_used=18
        ),
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

    task = create_task(
        correlation_id=uuid4(), channel_id=channel.id, status=TaskStatus.GENERATING_ASSETS
    )
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


# ============================================================================
# Story 8.8: Cost Dashboard & Reporting - Task 1 Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_weekly_cost_summary_current_week(async_session: AsyncSession):
    """Test weekly cost summary for current week with multiple tasks."""
    # Arrange: Create channel
    channel = create_channel(channel_id="test1")
    async_session.add(channel)
    await async_session.flush()

    # Create 3 tasks with costs in current week
    current_time = datetime.now(timezone.utc)
    for i in range(3):
        task = create_task(
            correlation_id=uuid4(), channel_id=channel.id, status=TaskStatus.PUBLISHED
        )
        async_session.add(task)
        await async_session.flush()

        # Add costs for each task
        cost1 = VideoCost(
            task_id=task.id,
            component="gemini_assets",
            cost_usd=Decimal("2.00"),
            units_used=20,
            timestamp=current_time,
        )
        cost2 = VideoCost(
            task_id=task.id,
            component="kling_video",
            cost_usd=Decimal("7.56"),
            units_used=18,
            timestamp=current_time,
        )
        async_session.add_all([cost1, cost2])

    await async_session.commit()

    # Act: Get weekly cost summary
    summary = await get_weekly_cost_summary(async_session, channel.id)

    # Assert: Correct totals
    assert summary["total_cost"] == Decimal("28.68")  # 3 x (2.00 + 7.56)
    assert summary["video_count"] == 3
    assert summary["avg_cost_per_video"] == Decimal("9.56")
    assert "breakdown_by_component" in summary
    assert summary["breakdown_by_component"]["gemini_assets"] == Decimal("6.00")
    assert summary["breakdown_by_component"]["kling_video"] == Decimal("22.68")
    assert "start_date" in summary
    assert "end_date" in summary


@pytest.mark.asyncio
async def test_get_weekly_cost_summary_no_costs(async_session: AsyncSession):
    """Test weekly cost summary when no costs exist."""
    # Arrange: Create channel with no tasks
    channel = create_channel(channel_id="test1")
    async_session.add(channel)
    await async_session.commit()

    # Act: Get weekly cost summary
    summary = await get_weekly_cost_summary(async_session, channel.id)

    # Assert: Zero values
    assert summary["total_cost"] == Decimal("0.00")
    assert summary["video_count"] == 0
    assert summary["avg_cost_per_video"] == Decimal("0.00")
    assert summary["breakdown_by_component"] == {}


@pytest.mark.asyncio
async def test_get_monthly_cost_summary_current_month(async_session: AsyncSession):
    """Test monthly cost summary for current month."""
    # Arrange: Create channel
    channel = create_channel(channel_id="test1")
    async_session.add(channel)
    await async_session.flush()

    # Create 10 tasks with costs in current month
    current_time = datetime.now(timezone.utc)
    for i in range(10):
        task = create_task(
            correlation_id=uuid4(), channel_id=channel.id, status=TaskStatus.PUBLISHED
        )
        async_session.add(task)
        await async_session.flush()

        # Add costs
        cost = VideoCost(
            task_id=task.id,
            component="kling_video",
            cost_usd=Decimal("7.56"),
            units_used=18,
            timestamp=current_time,
        )
        async_session.add(cost)

    await async_session.commit()

    # Act: Get monthly cost summary
    summary = await get_monthly_cost_summary(async_session, channel.id)

    # Assert: Correct totals
    assert summary["total_cost"] == Decimal("75.60")  # 10 x 7.56
    assert summary["video_count"] == 10
    assert summary["avg_cost_per_video"] == Decimal("7.56")
    assert "start_date" in summary
    assert "end_date" in summary

    # Bug fix validation: month_end should be 23:59:59.999999 of last day of month
    # Not midnight of next month (which would include costs from next month)
    assert summary["end_date"].hour == 23
    assert summary["end_date"].minute == 59
    assert summary["end_date"].second == 59
    assert summary["end_date"].month == current_time.month  # Same month as current


@pytest.mark.asyncio
async def test_get_cost_comparison_across_channels(async_session: AsyncSession):
    """Test cost comparison returns efficiency metrics for all channels."""
    # Arrange: Create 3 channels with different costs
    channels_data = [
        ("channel1", 5, Decimal("10.00")),  # 5 videos, $10 each = $50 total
        ("channel2", 10, Decimal("8.00")),  # 10 videos, $8 each = $80 total
        ("channel3", 3, Decimal("15.00")),  # 3 videos, $15 each = $45 total
    ]

    current_time = datetime.now(timezone.utc)
    for channel_id, video_count, cost_per_video in channels_data:
        channel = create_channel(channel_id=channel_id)
        async_session.add(channel)
        await async_session.flush()

        for i in range(video_count):
            task = create_task(
                correlation_id=uuid4(), channel_id=channel.id, status=TaskStatus.PUBLISHED
            )
            async_session.add(task)
            await async_session.flush()

            cost = VideoCost(
                task_id=task.id,
                component="kling_video",
                cost_usd=cost_per_video,
                units_used=18,
                timestamp=current_time,
            )
            async_session.add(cost)

    await async_session.commit()

    # Act: Get cost comparison
    comparison = await get_cost_comparison_across_channels(async_session)

    # Assert: Returns data for all channels
    assert len(comparison) == 3
    # Should be sorted by efficiency (lowest cost per video first)
    assert comparison[0]["avg_cost_per_video"] == Decimal("8.00")  # channel2 most efficient
    assert comparison[1]["avg_cost_per_video"] == Decimal("10.00")  # channel1
    assert comparison[2]["avg_cost_per_video"] == Decimal("15.00")  # channel3 least efficient


@pytest.mark.asyncio
async def test_get_cost_trend_data_30_days(async_session: AsyncSession):
    """Test cost trend data returns daily costs for last 30 days."""
    # Arrange: Create channel
    channel = create_channel(channel_id="test1")
    async_session.add(channel)
    await async_session.flush()

    # Create costs spread across last 7 days
    today = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    for days_ago in range(7):
        task_date = today - timedelta(days=days_ago)
        task = create_task(
            correlation_id=uuid4(), channel_id=channel.id, status=TaskStatus.PUBLISHED
        )
        async_session.add(task)
        await async_session.flush()

        cost = VideoCost(
            task_id=task.id,
            component="kling_video",
            cost_usd=Decimal("8.00"),
            units_used=18,
            timestamp=task_date,
        )
        async_session.add(cost)

    await async_session.commit()

    # Act: Get trend data
    trend_data = await get_cost_trend_data(async_session, channel.id, days=30)

    # Assert: Returns trend structure
    assert "daily_costs" in trend_data
    assert len(trend_data["daily_costs"]) <= 30  # At most 30 days
    assert "total_cost" in trend_data
    assert trend_data["total_cost"] == Decimal("56.00")  # 7 days x $8


# ============================================================================
# Story 8.8: Cost Dashboard & Reporting - Task 3 Tests (Cost Threshold Alerting)
# ============================================================================


@pytest.mark.asyncio
async def test_create_cost_threshold(async_session: AsyncSession):
    """Test creating a cost threshold for a channel."""
    # Arrange: Create channel
    channel = create_channel(channel_id="test1")
    async_session.add(channel)
    await async_session.commit()

    # Act: Create cost threshold
    threshold = await create_cost_threshold(
        db=async_session,
        channel_id=channel.id,
        threshold_usd=Decimal("500.00"),
        period="weekly",
        enabled=True,
        alert_on_approach=True,
    )

    # Assert: Threshold created with correct values
    assert threshold.id is not None
    assert threshold.channel_id == channel.id
    assert threshold.threshold_usd == Decimal("500.00")
    assert threshold.period == "weekly"
    assert threshold.enabled is True
    assert threshold.alert_on_approach is True


@pytest.mark.asyncio
async def test_create_cost_threshold_validates_positive_amount(async_session: AsyncSession):
    """Test that create_cost_threshold rejects zero or negative amounts."""
    # Arrange: Create channel
    channel = create_channel(channel_id="test1")
    async_session.add(channel)
    await async_session.commit()

    # Act & Assert: Reject zero threshold
    with pytest.raises(ValueError, match="threshold_usd must be greater than 0"):
        await create_cost_threshold(
            db=async_session, channel_id=channel.id, threshold_usd=Decimal("0.00"), period="weekly"
        )


@pytest.mark.asyncio
async def test_create_cost_threshold_validates_period(async_session: AsyncSession):
    """Test that create_cost_threshold rejects invalid periods."""
    # Arrange: Create channel
    channel = create_channel(channel_id="test1")
    async_session.add(channel)
    await async_session.commit()

    # Act & Assert: Reject invalid period
    with pytest.raises(ValueError, match="period must be"):
        await create_cost_threshold(
            db=async_session,
            channel_id=channel.id,
            threshold_usd=Decimal("500.00"),
            period="daily",  # Invalid!
        )


@pytest.mark.asyncio
async def test_get_active_thresholds(async_session: AsyncSession):
    """Test retrieving active thresholds for a channel."""
    # Arrange: Create channel with 2 thresholds (1 active, 1 disabled)
    channel = create_channel(channel_id="test1")
    async_session.add(channel)
    await async_session.commit()

    threshold1 = await create_cost_threshold(
        db=async_session,
        channel_id=channel.id,
        threshold_usd=Decimal("500.00"),
        period="weekly",
        enabled=True,
    )

    threshold2 = await create_cost_threshold(
        db=async_session,
        channel_id=channel.id,
        threshold_usd=Decimal("2000.00"),
        period="monthly",
        enabled=False,  # Disabled
    )

    # Act: Get active thresholds
    active = await get_active_thresholds(async_session, channel.id)

    # Assert: Only enabled threshold returned
    assert len(active) == 1
    assert active[0].id == threshold1.id
    assert active[0].enabled is True


@pytest.mark.asyncio
async def test_check_cost_thresholds_exceeded(async_session: AsyncSession):
    """Test cost threshold checking when threshold is exceeded."""
    # Arrange: Create channel with threshold
    channel = create_channel(channel_id="test1")
    async_session.add(channel)
    await async_session.flush()

    threshold = await create_cost_threshold(
        db=async_session,
        channel_id=channel.id,
        threshold_usd=Decimal("50.00"),
        period="weekly",
        enabled=True,
    )

    # Create costs exceeding threshold (55.00 total)
    current_time = datetime.now(timezone.utc)
    for i in range(6):
        task = create_task(
            correlation_id=uuid4(), channel_id=channel.id, status=TaskStatus.PUBLISHED
        )
        async_session.add(task)
        await async_session.flush()

        cost = VideoCost(
            task_id=task.id,
            component="kling_video",
            cost_usd=Decimal("9.17"),  # 6 x 9.17 = 55.02
            units_used=18,
            timestamp=current_time,
        )
        async_session.add(cost)

    await async_session.commit()

    # Act: Check thresholds
    violations = await check_cost_thresholds(async_session, channel.id)

    # Assert: Threshold exceeded
    assert len(violations) == 1
    assert violations[0]["threshold_id"] == threshold.id
    assert violations[0]["exceeded"] is True
    assert violations[0]["current_cost"] > threshold.threshold_usd
    assert "exceeded_by" in violations[0]


@pytest.mark.asyncio
async def test_check_cost_thresholds_approaching(async_session: AsyncSession):
    """Test cost threshold checking when approaching threshold (80%)."""
    # Arrange: Create channel with threshold
    channel = create_channel(channel_id="test1")
    async_session.add(channel)
    await async_session.flush()

    threshold = await create_cost_threshold(
        db=async_session,
        channel_id=channel.id,
        threshold_usd=Decimal("100.00"),
        period="weekly",
        enabled=True,
        alert_on_approach=True,
    )

    # Create costs at 85% of threshold (85.00)
    current_time = datetime.now(timezone.utc)
    task = create_task(correlation_id=uuid4(), channel_id=channel.id, status=TaskStatus.PUBLISHED)
    async_session.add(task)
    await async_session.flush()

    cost = VideoCost(
        task_id=task.id,
        component="kling_video",
        cost_usd=Decimal("85.00"),
        units_used=18,
        timestamp=current_time,
    )
    async_session.add(cost)
    await async_session.commit()

    # Act: Check thresholds
    violations = await check_cost_thresholds(async_session, channel.id)

    # Assert: Approaching alert triggered
    assert len(violations) == 1
    assert violations[0]["approaching"] is True
    assert violations[0]["exceeded"] is False
    assert violations[0]["percentage"] >= Decimal("80.0")


@pytest.mark.asyncio
async def test_update_cost_threshold(async_session: AsyncSession):
    """Test updating a cost threshold."""
    # Arrange: Create channel with threshold
    channel = create_channel(channel_id="test1")
    async_session.add(channel)
    await async_session.commit()

    threshold = await create_cost_threshold(
        db=async_session,
        channel_id=channel.id,
        threshold_usd=Decimal("500.00"),
        period="weekly",
        enabled=True,
    )

    # Act: Update threshold amount
    updated = await update_cost_threshold(
        db=async_session, threshold_id=threshold.id, threshold_usd=Decimal("750.00")
    )

    # Assert: Threshold updated
    assert updated.threshold_usd == Decimal("750.00")
    assert updated.id == threshold.id


@pytest.mark.asyncio
async def test_delete_cost_threshold(async_session: AsyncSession):
    """Test deleting a cost threshold."""
    # Arrange: Create channel with threshold
    channel = create_channel(channel_id="test1")
    async_session.add(channel)
    await async_session.commit()

    threshold = await create_cost_threshold(
        db=async_session, channel_id=channel.id, threshold_usd=Decimal("500.00"), period="weekly"
    )

    # Act: Delete threshold
    deleted = await delete_cost_threshold(async_session, threshold.id)

    # Assert: Threshold deleted
    assert deleted is True

    # Verify no longer exists
    active = await get_active_thresholds(async_session, channel.id)
    assert len(active) == 0
