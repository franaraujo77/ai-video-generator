"""Tests for weekly metrics trend analysis query functions (Story 8.6, Task 5).

Tests trend analysis, week-over-week comparisons, and failure pattern analysis functions.
"""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Channel, WeeklyMetrics
from app.services.weekly_metrics_service import (
    get_failure_pattern_analysis,
    get_success_rate_trend,
    get_week_over_week_comparison,
    get_weekly_metrics_range,
)


@pytest.fixture
async def channel_with_weekly_metrics(async_session: AsyncSession):
    """Create channel with 12 weeks of metrics data for trend analysis."""
    # Create channel
    channel = Channel(
        channel_id="trend_channel",
        channel_name="Trend Analysis Channel",
        voice_id="test_voice",
        max_concurrent=2,
    )
    async_session.add(channel)
    await async_session.commit()
    await async_session.refresh(channel)

    # Create 12 weeks of metrics (simulating 3 months)
    # Week 1-4: Good performance (90-95% success rate)
    # Week 5-8: Degrading performance (80-85% success rate)
    # Week 9-12: Recovering performance (85-90% success rate)
    metrics_data = [
        # Week 1-4: Good period
        {
            "week": date(2026, 1, 5),  # Week 1
            "total": 100,
            "successful": 95,
            "rate": Decimal("95.00"),
            "transient": 3,
            "permanent": 2,
            "assets": 2,
            "video": 2,
            "audio": 1,
        },
        {
            "week": date(2026, 1, 12),  # Week 2
            "total": 110,
            "successful": 104,
            "rate": Decimal("94.55"),
            "transient": 4,
            "permanent": 2,
            "assets": 3,
            "video": 2,
            "audio": 1,
        },
        {
            "week": date(2026, 1, 19),  # Week 3
            "total": 105,
            "successful": 100,
            "rate": Decimal("95.24"),
            "transient": 3,
            "permanent": 2,
            "assets": 2,
            "video": 2,
            "audio": 1,
        },
        {
            "week": date(2026, 1, 26),  # Week 4
            "total": 108,
            "successful": 97,
            "rate": Decimal("89.81"),
            "transient": 5,
            "permanent": 6,
            "assets": 4,
            "video": 4,
            "audio": 3,
        },
        # Week 5-8: Degradation period
        {
            "week": date(2026, 2, 2),  # Week 5
            "total": 100,
            "successful": 82,
            "rate": Decimal("82.00"),
            "transient": 10,
            "permanent": 8,
            "assets": 8,
            "video": 6,
            "audio": 4,
        },
        {
            "week": date(2026, 2, 9),  # Week 6
            "total": 95,
            "successful": 79,
            "rate": Decimal("83.16"),
            "transient": 9,
            "permanent": 7,
            "assets": 7,
            "video": 5,
            "audio": 4,
        },
        {
            "week": date(2026, 2, 16),  # Week 7
            "total": 102,
            "successful": 84,
            "rate": Decimal("82.35"),
            "transient": 11,
            "permanent": 7,
            "assets": 9,
            "video": 5,
            "audio": 4,
        },
        {
            "week": date(2026, 2, 23),  # Week 8
            "total": 98,
            "successful": 81,
            "rate": Decimal("82.65"),
            "transient": 10,
            "permanent": 7,
            "assets": 8,
            "video": 5,
            "audio": 4,
        },
        # Week 9-12: Recovery period
        {
            "week": date(2026, 3, 2),  # Week 9
            "total": 105,
            "successful": 89,
            "rate": Decimal("84.76"),
            "transient": 8,
            "permanent": 8,
            "assets": 7,
            "video": 5,
            "audio": 4,
        },
        {
            "week": date(2026, 3, 9),  # Week 10
            "total": 110,
            "successful": 96,
            "rate": Decimal("87.27"),
            "transient": 7,
            "permanent": 7,
            "assets": 6,
            "video": 4,
            "audio": 4,
        },
        {
            "week": date(2026, 3, 16),  # Week 11
            "total": 108,
            "successful": 97,
            "rate": Decimal("89.81"),
            "transient": 6,
            "permanent": 5,
            "assets": 5,
            "video": 3,
            "audio": 3,
        },
        {
            "week": date(2026, 3, 23),  # Week 12 (most recent)
            "total": 112,
            "successful": 101,
            "rate": Decimal("90.18"),
            "transient": 5,
            "permanent": 6,
            "assets": 4,
            "video": 4,
            "audio": 3,
        },
    ]

    for data in metrics_data:
        metric = WeeklyMetrics(
            channel_id=channel.id,
            week_starting_date=data["week"],
            total_videos_processed=data["total"],
            successful_videos=data["successful"],
            success_rate=data["rate"],
            avg_processing_time_seconds=3600,
            auto_recovery_rate=Decimal("50.00"),
            transient_failures=data["transient"],
            permanent_failures=data["permanent"],
            unknown_failures=0,
            failed_at_assets=data["assets"],
            failed_at_video=data["video"],
            failed_at_audio=data["audio"],
            failed_at_upload=0,
            calculated_at=datetime(2026, 3, 30, 0, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 3, 30, 0, 0, 0, tzinfo=timezone.utc),
        )
        async_session.add(metric)

    await async_session.commit()
    return channel


class TestGetWeeklyMetricsRange:
    """Test get_weekly_metrics_range() function."""

    async def test_get_range_single_week(
        self, async_session: AsyncSession, channel_with_weekly_metrics: Channel
    ):
        """Test getting a single week range."""
        start_date = date(2026, 1, 19)
        end_date = date(2026, 1, 19)

        metrics = await get_weekly_metrics_range(
            channel_with_weekly_metrics.id, start_date, end_date, async_session
        )

        assert len(metrics) == 1
        assert metrics[0].week_starting_date == date(2026, 1, 19)
        assert metrics[0].success_rate == Decimal("95.24")

    async def test_get_range_multiple_weeks(
        self, async_session: AsyncSession, channel_with_weekly_metrics: Channel
    ):
        """Test getting multiple weeks in range."""
        start_date = date(2026, 2, 2)  # Week 5
        end_date = date(2026, 2, 23)  # Week 8

        metrics = await get_weekly_metrics_range(
            channel_with_weekly_metrics.id, start_date, end_date, async_session
        )

        assert len(metrics) == 4
        # Should be ordered by week_starting_date DESC (most recent first)
        assert metrics[0].week_starting_date == date(2026, 2, 23)
        assert metrics[1].week_starting_date == date(2026, 2, 16)
        assert metrics[2].week_starting_date == date(2026, 2, 9)
        assert metrics[3].week_starting_date == date(2026, 2, 2)

    async def test_get_range_no_data(self, async_session: AsyncSession):
        """Test getting range with no data returns empty list."""
        # Create channel without metrics
        channel = Channel(
            channel_id="empty_channel",
            channel_name="Empty Channel",
            voice_id="test_voice",
            max_concurrent=2,
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        metrics = await get_weekly_metrics_range(
            channel.id, date(2026, 1, 1), date(2026, 1, 31), async_session
        )

        assert metrics == []


class TestGetSuccessRateTrend:
    """Test get_success_rate_trend() function for charting."""

    async def test_get_trend_default_12_weeks(
        self, async_session: AsyncSession, channel_with_weekly_metrics: Channel
    ):
        """Test getting 12-week trend (default)."""
        trend = await get_success_rate_trend(
            channel_with_weekly_metrics.id, async_session
        )

        assert len(trend) == 12
        # Should be ordered oldest to newest (for time-series charting)
        assert trend[0]["week_starting_date"] == "2026-01-05"
        assert trend[-1]["week_starting_date"] == "2026-03-23"
        # Verify data structure
        assert "week_starting_date" in trend[0]
        assert "success_rate" in trend[0]
        assert "total_videos" in trend[0]
        assert "successful_videos" in trend[0]

    async def test_get_trend_custom_weeks(
        self, async_session: AsyncSession, channel_with_weekly_metrics: Channel
    ):
        """Test getting custom number of weeks."""
        trend = await get_success_rate_trend(
            channel_with_weekly_metrics.id, async_session, weeks=4
        )

        assert len(trend) == 4
        # Should be most recent 4 weeks (weeks 9-12)
        assert trend[0]["week_starting_date"] == "2026-03-02"  # Week 9 (oldest of recent 4)
        assert trend[-1]["week_starting_date"] == "2026-03-23"  # Week 12 (most recent)

    async def test_get_trend_no_data(self, async_session: AsyncSession):
        """Test getting trend with no data returns empty list."""
        # Create channel without metrics
        channel = Channel(
            channel_id="empty_channel",
            channel_name="Empty Channel",
            voice_id="test_voice",
            max_concurrent=2,
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        trend = await get_success_rate_trend(channel.id, async_session)

        assert trend == []


class TestGetWeekOverWeekComparison:
    """Test get_week_over_week_comparison() for delta calculations."""

    async def test_comparison_with_previous_week(
        self, async_session: AsyncSession, channel_with_weekly_metrics: Channel
    ):
        """Test week-over-week comparison when previous week exists."""
        current_week = date(2026, 3, 23)  # Week 12

        comparison = await get_week_over_week_comparison(
            channel_with_weekly_metrics.id, current_week, async_session
        )

        assert comparison["current_week"]["week_starting_date"] == "2026-03-23"
        assert comparison["current_week"]["success_rate"] == float(Decimal("90.18"))
        assert comparison["previous_week"]["week_starting_date"] == "2026-03-16"
        assert comparison["previous_week"]["success_rate"] == float(Decimal("89.81"))
        # Delta should be positive (improvement)
        assert comparison["delta"]["success_rate_change"] > 0
        assert "total_videos_change" in comparison["delta"]
        assert "successful_videos_change" in comparison["delta"]

    async def test_comparison_first_week_no_previous(
        self, async_session: AsyncSession, channel_with_weekly_metrics: Channel
    ):
        """Test comparison for first week (no previous week data)."""
        first_week = date(2026, 1, 5)  # Week 1

        comparison = await get_week_over_week_comparison(
            channel_with_weekly_metrics.id, first_week, async_session
        )

        assert comparison["current_week"]["week_starting_date"] == "2026-01-05"
        assert comparison["previous_week"] is None
        assert comparison["delta"] is None

    async def test_comparison_nonexistent_week(self, async_session: AsyncSession):
        """Test comparison for week with no data."""
        # Create channel without metrics
        channel = Channel(
            channel_id="empty_channel",
            channel_name="Empty Channel",
            voice_id="test_voice",
            max_concurrent=2,
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        comparison = await get_week_over_week_comparison(
            channel.id, date(2026, 1, 1), async_session
        )

        assert comparison["current_week"] is None
        assert comparison["previous_week"] is None
        assert comparison["delta"] is None


class TestGetFailurePatternAnalysis:
    """Test get_failure_pattern_analysis() for category trends."""

    async def test_failure_patterns_4_weeks(
        self, async_session: AsyncSession, channel_with_weekly_metrics: Channel
    ):
        """Test failure pattern analysis over 4 weeks."""
        analysis = await get_failure_pattern_analysis(
            channel_with_weekly_metrics.id, async_session, weeks=4
        )

        # Should analyze most recent 4 weeks (weeks 9-12)
        assert "time_range" in analysis
        assert analysis["time_range"]["start_week"] == "2026-03-02"  # Week 9 (oldest of recent 4)
        assert analysis["time_range"]["end_week"] == "2026-03-23"  # Week 12 (most recent)
        # Failure category breakdown
        assert "category_breakdown" in analysis
        assert "transient_failures" in analysis["category_breakdown"]
        assert "permanent_failures" in analysis["category_breakdown"]
        # Stage breakdown
        assert "stage_breakdown" in analysis
        assert "assets" in analysis["stage_breakdown"]
        assert "video" in analysis["stage_breakdown"]
        assert "audio" in analysis["stage_breakdown"]
        # Most common patterns
        assert "most_common_category" in analysis
        assert "most_common_stage" in analysis

    async def test_failure_patterns_custom_weeks(
        self, async_session: AsyncSession, channel_with_weekly_metrics: Channel
    ):
        """Test failure pattern analysis with custom week count."""
        analysis = await get_failure_pattern_analysis(
            channel_with_weekly_metrics.id, async_session, weeks=8
        )

        # Should analyze 8 weeks (Week 5-12)
        assert analysis["time_range"]["start_week"] == "2026-02-02"
        assert analysis["time_range"]["end_week"] == "2026-03-23"

    async def test_failure_patterns_no_data(self, async_session: AsyncSession):
        """Test failure pattern analysis with no data."""
        # Create channel without metrics
        channel = Channel(
            channel_id="empty_channel",
            channel_name="Empty Channel",
            voice_id="test_voice",
            max_concurrent=2,
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        analysis = await get_failure_pattern_analysis(channel.id, async_session)

        # Should return structure with zeros
        assert analysis["category_breakdown"]["transient_failures"] == 0
        assert analysis["category_breakdown"]["permanent_failures"] == 0
        assert analysis["most_common_category"] == "none"
        assert analysis["most_common_stage"] == "none"
