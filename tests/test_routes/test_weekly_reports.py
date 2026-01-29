"""Tests for weekly metrics reporting API endpoints (Story 8.6).

Tests verify:
- Weekly metrics list endpoint with pagination
- Single week metrics detail endpoint
- Success rate trend analysis endpoint
- Cross-channel weekly summary endpoint
- Error handling for missing/invalid inputs
"""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models import Channel, WeeklyMetrics


@pytest.fixture
async def test_channel_with_metrics(async_session: AsyncSession):
    """Create test channel with 3 weeks of metrics data."""
    # Create channel
    channel = Channel(
        channel_id="test_channel",
        channel_name="Test Channel",
        voice_id="test_voice",
        max_concurrent=2,
    )
    async_session.add(channel)
    await async_session.commit()
    await async_session.refresh(channel)

    # Create 3 weeks of metrics
    weeks_data = [
        {
            "week": date(2026, 1, 19),  # Week 1
            "total": 100,
            "successful": 95,
            "rate": Decimal("95.00"),
        },
        {
            "week": date(2026, 1, 26),  # Week 2
            "total": 110,
            "successful": 99,
            "rate": Decimal("90.00"),
        },
        {
            "week": date(2026, 2, 2),  # Week 3
            "total": 105,
            "successful": 84,
            "rate": Decimal("80.00"),
        },
    ]

    for data in weeks_data:
        metric = WeeklyMetrics(
            channel_id=channel.id,
            week_starting_date=data["week"],
            total_videos_processed=data["total"],
            successful_videos=data["successful"],
            success_rate=data["rate"],
            avg_processing_time_seconds=3600,
            auto_recovery_rate=Decimal("50.00"),
            transient_failures=3,
            permanent_failures=2,
            unknown_failures=0,
            failed_at_assets=2,
            failed_at_video=2,
            failed_at_audio=1,
            failed_at_upload=0,
            calculated_at=datetime(2026, 2, 10, 0, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 2, 10, 0, 0, 0, tzinfo=timezone.utc),
        )
        async_session.add(metric)

    await async_session.commit()
    return channel


@pytest.mark.asyncio
async def test_list_weekly_metrics_success(
    async_client: AsyncClient,
    async_session: AsyncSession,
    test_channel_with_metrics: Channel,
) -> None:
    """Test listing weekly metrics for a channel."""
    response = await async_client.get(
        f"/api/v1/channels/{test_channel_with_metrics.id}/weekly-metrics",
        params={
            "start_date": "2026-01-19",
            "end_date": "2026-02-02",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["channel_id"] == str(test_channel_with_metrics.id)
    assert data["total_count"] == 3
    assert len(data["metrics"]) == 3
    # Verify first metric (most recent)
    assert data["metrics"][0]["week_starting_date"] == "2026-02-02"
    assert data["metrics"][0]["success_rate"] == "80.00"


@pytest.mark.asyncio
async def test_list_weekly_metrics_channel_not_found(
    async_client: AsyncClient,
) -> None:
    """Test listing metrics for nonexistent channel returns 404."""
    response = await async_client.get(
        "/api/v1/channels/00000000-0000-0000-0000-000000000000/weekly-metrics",
        params={
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
        },
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_weekly_metrics_empty_result(
    async_client: AsyncClient,
    async_session: AsyncSession,
    test_channel_with_metrics: Channel,
) -> None:
    """Test listing metrics with no data in range returns empty list."""
    response = await async_client.get(
        f"/api/v1/channels/{test_channel_with_metrics.id}/weekly-metrics",
        params={
            "start_date": "2025-01-01",  # Before any metrics exist
            "end_date": "2025-01-31",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 0
    assert len(data["metrics"]) == 0


@pytest.mark.asyncio
async def test_get_single_week_metrics_success(
    async_client: AsyncClient,
    async_session: AsyncSession,
    test_channel_with_metrics: Channel,
) -> None:
    """Test getting metrics for a specific week."""
    response = await async_client.get(
        f"/api/v1/channels/{test_channel_with_metrics.id}/weekly-metrics/2026-01-19"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["channel_id"] == str(test_channel_with_metrics.id)
    assert data["week_starting_date"] == "2026-01-19"
    assert data["success_rate"] == "95.00"
    assert data["total_videos_processed"] == 100
    assert data["successful_videos"] == 95


@pytest.mark.asyncio
async def test_get_single_week_metrics_week_not_found(
    async_client: AsyncClient,
    async_session: AsyncSession,
    test_channel_with_metrics: Channel,
) -> None:
    """Test getting metrics for nonexistent week returns 404."""
    response = await async_client.get(
        f"/api/v1/channels/{test_channel_with_metrics.id}/weekly-metrics/2025-01-01"
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_single_week_metrics_normalizes_to_monday(
    async_client: AsyncClient,
    async_session: AsyncSession,
    test_channel_with_metrics: Channel,
) -> None:
    """Test getting metrics with non-Monday date normalizes to Monday."""
    # 2026-01-21 is Wednesday, should normalize to Monday 2026-01-19
    response = await async_client.get(
        f"/api/v1/channels/{test_channel_with_metrics.id}/weekly-metrics/2026-01-21"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["week_starting_date"] == "2026-01-19"  # Normalized to Monday


@pytest.mark.asyncio
async def test_get_success_rate_trend_default_weeks(
    async_client: AsyncClient,
    async_session: AsyncSession,
    test_channel_with_metrics: Channel,
) -> None:
    """Test getting success rate trend with default 12 weeks."""
    response = await async_client.get(
        f"/api/v1/channels/{test_channel_with_metrics.id}/success-rate-trend"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["channel_id"] == str(test_channel_with_metrics.id)
    assert data["weeks"] == 12
    assert len(data["trend"]) == 3  # Only 3 weeks of data exist
    # Verify chronological order (oldest first)
    assert data["trend"][0]["week_starting_date"] == "2026-01-19"
    assert data["trend"][-1]["week_starting_date"] == "2026-02-02"


@pytest.mark.asyncio
async def test_get_success_rate_trend_custom_weeks(
    async_client: AsyncClient,
    async_session: AsyncSession,
    test_channel_with_metrics: Channel,
) -> None:
    """Test getting success rate trend with custom week count."""
    response = await async_client.get(
        f"/api/v1/channels/{test_channel_with_metrics.id}/success-rate-trend",
        params={"weeks": 2},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["weeks"] == 2
    assert len(data["trend"]) == 2  # Most recent 2 weeks
    assert data["trend"][0]["week_starting_date"] == "2026-01-26"
    assert data["trend"][-1]["week_starting_date"] == "2026-02-02"


@pytest.mark.asyncio
async def test_get_success_rate_trend_channel_not_found(
    async_client: AsyncClient,
) -> None:
    """Test getting trend for nonexistent channel returns 404."""
    response = await async_client.get(
        "/api/v1/channels/00000000-0000-0000-0000-000000000000/success-rate-trend"
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_weekly_summary_success(
    async_client: AsyncClient,
    async_session: AsyncSession,
    test_channel_with_metrics: Channel,
) -> None:
    """Test getting cross-channel weekly summary."""
    # Create second channel with metrics for same week
    channel2 = Channel(
        channel_id="test_channel_2",
        channel_name="Test Channel 2",
        voice_id="test_voice_2",
        max_concurrent=2,
        is_active=True,
    )
    async_session.add(channel2)
    await async_session.commit()
    await async_session.refresh(channel2)

    metric2 = WeeklyMetrics(
        channel_id=channel2.id,
        week_starting_date=date(2026, 1, 19),
        total_videos_processed=50,
        successful_videos=48,  # 96% success rate
        success_rate=Decimal("96.00"),
        avg_processing_time_seconds=3000,
        auto_recovery_rate=Decimal("60.00"),
        transient_failures=1,
        permanent_failures=1,
        unknown_failures=0,
        failed_at_assets=1,
        failed_at_video=0,
        failed_at_audio=1,
        failed_at_upload=0,
        calculated_at=datetime(2026, 2, 10, 0, 0, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 2, 10, 0, 0, 0, tzinfo=timezone.utc),
    )
    async_session.add(metric2)
    await async_session.commit()

    response = await async_client.get(
        "/api/v1/reports/weekly-summary",
        params={"week_date": "2026-01-19"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["week_starting_date"] == "2026-01-19"
    assert data["total_channels"] == 2
    assert data["channels_meeting_target"] == 2  # Both >= 90%
    assert data["total_videos_processed"] == 150  # 100 + 50
    assert data["total_successful_videos"] == 143  # 95 + 48
    # Verify weighted average: (143 / 150) * 100 = 95.33...
    assert float(data["overall_success_rate"]) >= 95.0


@pytest.mark.asyncio
async def test_get_weekly_summary_no_active_channels(
    async_client: AsyncClient,
    async_session: AsyncSession,
) -> None:
    """Test getting weekly summary with no active channels returns 404."""
    response = await async_client.get(
        "/api/v1/reports/weekly-summary",
        params={"week_date": "2026-01-01"},
    )

    assert response.status_code == 404
    assert "No active channels found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_weekly_summary_no_metrics_for_week(
    async_client: AsyncClient,
    async_session: AsyncSession,
    test_channel_with_metrics: Channel,
) -> None:
    """Test getting weekly summary for week with no metrics returns 404."""
    response = await async_client.get(
        "/api/v1/reports/weekly-summary",
        params={"week_date": "2025-01-01"},  # Before any metrics exist
    )

    assert response.status_code == 404
    assert "No metrics found for week" in response.json()["detail"]
