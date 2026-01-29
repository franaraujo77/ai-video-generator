"""Tests for cost reporting API endpoints (Story 8.2, 8.8).

Tests cover:
- Task-level cost breakdown endpoint (Story 8.2)
- Channel cost summary endpoint (Story 8.2)
- Cost trends endpoint (Story 8.2)
- Weekly cost summary endpoint (Story 8.8)
- Monthly cost summary endpoint (Story 8.8)
- Channel comparison endpoint (Story 8.8)
- Cost dashboard endpoint (Story 8.8)
"""

from decimal import Decimal
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Channel, Task, TaskStatus, VideoCost
from tests.support.factories import create_channel, create_task


# ============================================================================
# Story 8.8: Cost Dashboard & Reporting - Task 2 Tests (API Endpoints)
# ============================================================================


@pytest.mark.asyncio
async def test_get_weekly_cost_summary_endpoint(
    async_client: AsyncClient, async_session: AsyncSession
):
    """Test GET /api/v1/reports/weekly-cost-summary endpoint."""
    # Arrange: Create channel with costs
    channel = create_channel(channel_id="test1")
    async_session.add(channel)
    await async_session.flush()

    # Create task with costs in current week
    current_time = datetime.now(timezone.utc)
    task = create_task(correlation_id=uuid4(), channel_id=channel.id, status=TaskStatus.PUBLISHED)
    async_session.add(task)
    await async_session.flush()

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

    # Act: Call API endpoint
    response = await async_client.get(
        f"/api/v1/reports/weekly-cost-summary?channel_id={channel.id}"
    )

    # Assert: Response structure and values
    assert response.status_code == 200
    data = response.json()
    assert data["channel_id"] == str(channel.id)
    assert Decimal(data["total_cost"]) == Decimal("9.56")
    assert data["video_count"] == 1
    assert Decimal(data["avg_cost_per_video"]) == Decimal("9.56")
    assert "breakdown_by_component" in data
    assert "start_date" in data
    assert "end_date" in data


@pytest.mark.asyncio
async def test_get_monthly_cost_summary_endpoint(
    async_client: AsyncClient, async_session: AsyncSession
):
    """Test GET /api/v1/reports/monthly-cost-summary endpoint."""
    # Arrange: Create channel with costs
    channel = create_channel(channel_id="test1")
    async_session.add(channel)
    await async_session.flush()

    # Create 5 tasks with costs in current month
    current_time = datetime.now(timezone.utc)
    for i in range(5):
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
            timestamp=current_time,
        )
        async_session.add(cost)

    await async_session.commit()

    # Act: Call API endpoint
    response = await async_client.get(
        f"/api/v1/reports/monthly-cost-summary?channel_id={channel.id}"
    )

    # Assert: Response structure and values
    assert response.status_code == 200
    data = response.json()
    assert data["channel_id"] == str(channel.id)
    assert Decimal(data["total_cost"]) == Decimal("40.00")  # 5 videos x $8
    assert data["video_count"] == 5
    assert Decimal(data["avg_cost_per_video"]) == Decimal("8.00")


@pytest.mark.asyncio
async def test_get_channel_comparison_endpoint(
    async_client: AsyncClient, async_session: AsyncSession
):
    """Test GET /api/v1/reports/channel-comparison endpoint."""
    # Arrange: Create 2 channels with different costs
    channel1 = create_channel(channel_id="channel1")
    channel2 = create_channel(channel_id="channel2")
    async_session.add_all([channel1, channel2])
    await async_session.flush()

    current_time = datetime.now(timezone.utc)

    # Channel 1: 2 videos at $10 each
    for i in range(2):
        task = create_task(
            correlation_id=uuid4(), channel_id=channel1.id, status=TaskStatus.PUBLISHED
        )
        async_session.add(task)
        await async_session.flush()

        cost = VideoCost(
            task_id=task.id,
            component="kling_video",
            cost_usd=Decimal("10.00"),
            units_used=18,
            timestamp=current_time,
        )
        async_session.add(cost)

    # Channel 2: 3 videos at $8 each (more efficient)
    for i in range(3):
        task = create_task(
            correlation_id=uuid4(), channel_id=channel2.id, status=TaskStatus.PUBLISHED
        )
        async_session.add(task)
        await async_session.flush()

        cost = VideoCost(
            task_id=task.id,
            component="kling_video",
            cost_usd=Decimal("8.00"),
            units_used=18,
            timestamp=current_time,
        )
        async_session.add(cost)

    await async_session.commit()

    # Act: Call API endpoint
    response = await async_client.get("/api/v1/reports/channel-comparison?days=30")

    # Assert: Response structure
    assert response.status_code == 200
    data = response.json()
    assert "channels" in data
    assert data["days"] == 30
    assert len(data["channels"]) == 2
    # Should be sorted by efficiency (channel2 first with $8/video)
    assert Decimal(data["channels"][0]["avg_cost_per_video"]) == Decimal("8.00")
    assert Decimal(data["channels"][1]["avg_cost_per_video"]) == Decimal("10.00")


@pytest.mark.asyncio
async def test_get_cost_dashboard_endpoint(async_client: AsyncClient, async_session: AsyncSession):
    """Test GET /api/v1/reports/cost-dashboard endpoint."""
    # Arrange: Create channel with costs
    channel = create_channel(channel_id="test1")
    async_session.add(channel)
    await async_session.flush()

    # Create task with costs
    current_time = datetime.now(timezone.utc)
    task = create_task(correlation_id=uuid4(), channel_id=channel.id, status=TaskStatus.PUBLISHED)
    async_session.add(task)
    await async_session.flush()

    cost = VideoCost(
        task_id=task.id,
        component="kling_video",
        cost_usd=Decimal("8.00"),
        units_used=18,
        timestamp=current_time,
    )
    async_session.add(cost)
    await async_session.commit()

    # Act: Call API endpoint
    response = await async_client.get(
        f"/api/v1/reports/cost-dashboard?channel_id={channel.id}&trend_days=30"
    )

    # Assert: Response structure (complete dashboard)
    assert response.status_code == 200
    data = response.json()
    assert "weekly_summary" in data
    assert "monthly_summary" in data
    assert "channel_comparison" in data
    assert "trend_data" in data

    # Verify weekly summary structure
    assert data["weekly_summary"]["channel_id"] == str(channel.id)
    assert Decimal(data["weekly_summary"]["total_cost"]) == Decimal("8.00")

    # Verify monthly summary structure
    assert data["monthly_summary"]["channel_id"] == str(channel.id)
    assert Decimal(data["monthly_summary"]["total_cost"]) == Decimal("8.00")

    # Verify trend data structure
    assert "daily_costs" in data["trend_data"]
    assert "total_cost" in data["trend_data"]


@pytest.mark.asyncio
async def test_weekly_cost_summary_missing_channel_id(async_client: AsyncClient):
    """Test weekly cost summary endpoint requires channel_id parameter."""
    # Act: Call endpoint without channel_id
    response = await async_client.get("/api/v1/reports/weekly-cost-summary")

    # Assert: 422 validation error
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_channel_comparison_validates_days_range(async_client: AsyncClient):
    """Test channel comparison endpoint validates days parameter range."""
    # Act: Call endpoint with invalid days (> 365)
    response = await async_client.get("/api/v1/reports/channel-comparison?days=400")

    # Assert: 422 validation error
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_cost_dashboard_returns_empty_data_for_no_costs(
    async_client: AsyncClient, async_session: AsyncSession
):
    """Test cost dashboard endpoint handles channel with no costs gracefully."""
    # Arrange: Create channel with no costs
    channel = create_channel(channel_id="test1")
    async_session.add(channel)
    await async_session.commit()

    # Act: Call API endpoint
    response = await async_client.get(
        f"/api/v1/reports/cost-dashboard?channel_id={channel.id}&trend_days=30"
    )

    # Assert: Returns 200 with zero values
    assert response.status_code == 200
    data = response.json()
    assert Decimal(data["weekly_summary"]["total_cost"]) == Decimal("0.00")
    assert data["weekly_summary"]["video_count"] == 0
    assert Decimal(data["monthly_summary"]["total_cost"]) == Decimal("0.00")
    assert data["monthly_summary"]["video_count"] == 0
