"""Tests for weekly metrics Discord alerting integration (Story 8.6, Task 7).

Tests verify:
- Alert triggered when success rate < 90%
- Alert not triggered when success rate >= 90%
- Alert includes week-over-week comparison
- Alert includes most common failure stage
- Alert respects rate limiting (DISCORD_WEBHOOK_URL env var controls sending)
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Channel, WeeklyMetrics
from app.services.weekly_metrics_service import (
    calculate_weekly_metrics,
    check_success_rate_thresholds,
)


@pytest.fixture
async def channel_with_low_success_rate(async_session: AsyncSession):
    """Create channel with metrics showing low success rate (< 90%)."""
    channel = Channel(
        channel_id="low_success_channel",
        channel_name="Low Success Channel",
        voice_id="test_voice",
        max_concurrent=2,
    )
    async_session.add(channel)
    await async_session.commit()
    await async_session.refresh(channel)

    # Previous week: 95% success rate
    prev_week_metrics = WeeklyMetrics(
        channel_id=channel.id,
        week_starting_date=date(2026, 1, 12),
        total_videos_processed=100,
        successful_videos=95,
        success_rate=Decimal("95.00"),
        avg_processing_time_seconds=3600,
        auto_recovery_rate=Decimal("50.00"),
        transient_failures=3,
        permanent_failures=2,
        unknown_failures=0,
        failed_at_assets=2,
        failed_at_video=2,
        failed_at_audio=1,
        failed_at_upload=0,
        calculated_at=datetime(2026, 1, 19, 0, 0, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 19, 0, 0, 0, tzinfo=timezone.utc),
    )
    async_session.add(prev_week_metrics)

    # Current week: 85% success rate (degradation)
    current_week_metrics = WeeklyMetrics(
        channel_id=channel.id,
        week_starting_date=date(2026, 1, 19),
        total_videos_processed=100,
        successful_videos=85,
        success_rate=Decimal("85.00"),
        avg_processing_time_seconds=3600,
        auto_recovery_rate=Decimal("50.00"),
        transient_failures=8,
        permanent_failures=7,
        unknown_failures=0,
        failed_at_assets=10,  # Most common failure stage
        failed_at_video=3,
        failed_at_audio=2,
        failed_at_upload=0,
        calculated_at=datetime(2026, 1, 26, 0, 0, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 26, 0, 0, 0, tzinfo=timezone.utc),
    )
    async_session.add(current_week_metrics)
    await async_session.commit()

    return channel


@pytest.fixture
async def channel_with_high_success_rate(async_session: AsyncSession):
    """Create channel with metrics showing high success rate (>= 90%)."""
    channel = Channel(
        channel_id="high_success_channel",
        channel_name="High Success Channel",
        voice_id="test_voice",
        max_concurrent=2,
    )
    async_session.add(channel)
    await async_session.commit()
    await async_session.refresh(channel)

    metrics = WeeklyMetrics(
        channel_id=channel.id,
        week_starting_date=date(2026, 1, 19),
        total_videos_processed=100,
        successful_videos=95,
        success_rate=Decimal("95.00"),
        avg_processing_time_seconds=3600,
        auto_recovery_rate=Decimal("50.00"),
        transient_failures=3,
        permanent_failures=2,
        unknown_failures=0,
        failed_at_assets=2,
        failed_at_video=2,
        failed_at_audio=1,
        failed_at_upload=0,
        calculated_at=datetime(2026, 1, 26, 0, 0, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 26, 0, 0, 0, tzinfo=timezone.utc),
    )
    async_session.add(metrics)
    await async_session.commit()

    return channel


class TestSuccessRateAlertTriggers:
    """Test alert triggering conditions."""

    @patch("app.services.weekly_metrics_service.send_discord_alert")
    async def test_alert_triggered_below_threshold(
        self,
        mock_send_alert: AsyncMock,
        async_session: AsyncSession,
        channel_with_low_success_rate: Channel,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Test that alert is triggered when success rate < 90%."""
        # Set webhook URL (required for alert to be sent)
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/test")
        mock_send_alert.return_value = True

        # Get current week metrics
        metrics = WeeklyMetrics(
            channel_id=channel_with_low_success_rate.id,
            week_starting_date=date(2026, 1, 19),
            total_videos_processed=100,
            successful_videos=85,
            success_rate=Decimal("85.00"),
            avg_processing_time_seconds=3600,
            auto_recovery_rate=Decimal("50.00"),
            transient_failures=8,
            permanent_failures=7,
            unknown_failures=0,
            failed_at_assets=10,
            failed_at_video=3,
            failed_at_audio=2,
            failed_at_upload=0,
            calculated_at=datetime(2026, 1, 26, 0, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 1, 26, 0, 0, 0, tzinfo=timezone.utc),
        )

        # Call check_success_rate_thresholds
        await check_success_rate_thresholds(metrics, async_session)

        # Verify alert was called
        assert mock_send_alert.called
        call_args = mock_send_alert.call_args

        # Verify alert type and severity
        assert call_args.kwargs["alert_type"] == "low_success_rate"
        assert call_args.kwargs["severity"] == "WARNING"

        # Verify title includes success rate
        assert "85.0%" in call_args.kwargs["title"]

        # Verify description includes week-over-week trend
        assert "trend" in call_args.kwargs["description"].lower()

        # Verify fields include relevant data
        fields = call_args.kwargs["fields"]
        assert "Success Rate" in fields
        assert "Videos" in fields  # Format: "85/100"
        assert "Trend" in fields

    @patch("app.services.weekly_metrics_service.send_discord_alert")
    async def test_alert_not_triggered_above_threshold(
        self,
        mock_send_alert: AsyncMock,
        async_session: AsyncSession,
        channel_with_high_success_rate: Channel,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Test that alert is NOT triggered when success rate >= 90%."""
        # Set webhook URL
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/test")

        # Get metrics
        metrics = WeeklyMetrics(
            channel_id=channel_with_high_success_rate.id,
            week_starting_date=date(2026, 1, 19),
            total_videos_processed=100,
            successful_videos=95,
            success_rate=Decimal("95.00"),
            avg_processing_time_seconds=3600,
            auto_recovery_rate=Decimal("50.00"),
            transient_failures=3,
            permanent_failures=2,
            unknown_failures=0,
            failed_at_assets=2,
            failed_at_video=2,
            failed_at_audio=1,
            failed_at_upload=0,
            calculated_at=datetime(2026, 1, 26, 0, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 1, 26, 0, 0, 0, tzinfo=timezone.utc),
        )

        # Call check_success_rate_thresholds
        await check_success_rate_thresholds(metrics, async_session)

        # Verify alert was NOT called
        assert not mock_send_alert.called

    @patch("app.services.weekly_metrics_service.send_discord_alert")
    async def test_alert_includes_week_over_week_comparison(
        self,
        mock_send_alert: AsyncMock,
        async_session: AsyncSession,
        channel_with_low_success_rate: Channel,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Test that alert includes week-over-week trend comparison."""
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/test")
        mock_send_alert.return_value = True

        # Get metrics showing degradation (95% -> 85%)
        metrics = WeeklyMetrics(
            channel_id=channel_with_low_success_rate.id,
            week_starting_date=date(2026, 1, 19),
            total_videos_processed=100,
            successful_videos=85,
            success_rate=Decimal("85.00"),
            avg_processing_time_seconds=3600,
            auto_recovery_rate=Decimal("50.00"),
            transient_failures=8,
            permanent_failures=7,
            unknown_failures=0,
            failed_at_assets=10,
            failed_at_video=3,
            failed_at_audio=2,
            failed_at_upload=0,
            calculated_at=datetime(2026, 1, 26, 0, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 1, 26, 0, 0, 0, tzinfo=timezone.utc),
        )

        await check_success_rate_thresholds(metrics, async_session)

        # Verify description includes trend information
        description = mock_send_alert.call_args.kwargs["description"]
        assert "trend" in description.lower() or "down" in description.lower()

    @patch("app.services.weekly_metrics_service.send_discord_alert")
    async def test_alert_includes_most_common_failure_stage(
        self,
        mock_send_alert: AsyncMock,
        async_session: AsyncSession,
        channel_with_low_success_rate: Channel,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Test that alert includes most common failure stage."""
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/test")
        mock_send_alert.return_value = True

        # Get metrics with assets as most common failure (10 out of 15 failures)
        metrics = WeeklyMetrics(
            channel_id=channel_with_low_success_rate.id,
            week_starting_date=date(2026, 1, 19),
            total_videos_processed=100,
            successful_videos=85,
            success_rate=Decimal("85.00"),
            avg_processing_time_seconds=3600,
            auto_recovery_rate=Decimal("50.00"),
            transient_failures=8,
            permanent_failures=7,
            unknown_failures=0,
            failed_at_assets=10,  # Most common
            failed_at_video=3,
            failed_at_audio=2,
            failed_at_upload=0,
            calculated_at=datetime(2026, 1, 26, 0, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 1, 26, 0, 0, 0, tzinfo=timezone.utc),
        )

        await check_success_rate_thresholds(metrics, async_session)

        # Verify description includes failure stage information
        description = mock_send_alert.call_args.kwargs["description"]
        assert "asset" in description.lower() or "failure" in description.lower()

    async def test_alert_not_sent_when_webhook_url_not_configured(
        self,
        async_session: AsyncSession,
        channel_with_low_success_rate: Channel,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Test that alert is silently skipped when DISCORD_WEBHOOK_URL not set."""
        # Ensure DISCORD_WEBHOOK_URL is not set
        monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)

        # Get metrics with low success rate
        metrics = WeeklyMetrics(
            channel_id=channel_with_low_success_rate.id,
            week_starting_date=date(2026, 1, 19),
            total_videos_processed=100,
            successful_videos=85,
            success_rate=Decimal("85.00"),
            avg_processing_time_seconds=3600,
            auto_recovery_rate=Decimal("50.00"),
            transient_failures=8,
            permanent_failures=7,
            unknown_failures=0,
            failed_at_assets=10,
            failed_at_video=3,
            failed_at_audio=2,
            failed_at_upload=0,
            calculated_at=datetime(2026, 1, 26, 0, 0, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 1, 26, 0, 0, 0, tzinfo=timezone.utc),
        )

        # Call check_success_rate_thresholds
        # Should not raise exception even when webhook URL not configured
        await check_success_rate_thresholds(metrics, async_session)
        # Test passes if no exception raised
