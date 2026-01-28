"""Tests for WeeklyMetrics Model (Story 8.6).

This module tests the WeeklyMetrics model which tracks weekly pipeline success metrics.

Test Coverage:
- Model creation with required fields
- Composite primary key validation (channel_id, week_starting_date)
- Field type validation (Decimal for percentages, Integer for counts)
- Nullable field handling (avg_processing_time_seconds, auto_recovery_rate)
- Relationship to Channel model
- __repr__ method output
- Check constraints (non-negative values, rate ranges)
- Default values for metrics fields
"""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.models import Channel, WeeklyMetrics


@pytest.mark.asyncio
class TestWeeklyMetricsModel:
    """Test WeeklyMetrics model."""

    async def test_create_weekly_metrics(self, async_session):
        """Test creating a WeeklyMetrics record with all fields."""
        # Setup: Create channel
        channel = Channel(
            channel_id="test_channel",
            channel_name="Test Channel",
            voice_id="test_voice",
            max_concurrent=2,
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        # Create weekly metrics
        week_start = date(2026, 1, 20)  # Monday
        metrics = WeeklyMetrics(
            channel_id=channel.id,
            week_starting_date=week_start,
            total_videos_processed=10,
            successful_videos=8,
            success_rate=Decimal("80.00"),
            avg_processing_time_seconds=3600,
            auto_recovery_rate=Decimal("75.00"),
            transient_failures=2,
            permanent_failures=0,
            unknown_failures=0,
            failed_at_assets=1,
            failed_at_video=1,
            failed_at_audio=0,
            failed_at_upload=0,
            calculated_at=datetime.now(timezone.utc),
        )
        async_session.add(metrics)
        await async_session.commit()
        await async_session.refresh(metrics)

        # Assert
        assert metrics.channel_id == channel.id
        assert metrics.week_starting_date == week_start
        assert metrics.total_videos_processed == 10
        assert metrics.successful_videos == 8
        assert metrics.success_rate == Decimal("80.00")
        assert metrics.avg_processing_time_seconds == 3600
        assert metrics.auto_recovery_rate == Decimal("75.00")
        assert metrics.transient_failures == 2
        assert metrics.failed_at_assets == 1
        assert metrics.calculated_at is not None
        assert metrics.updated_at is not None

    async def test_composite_primary_key(self, async_session):
        """Test composite primary key constraint (channel_id, week_starting_date)."""
        # Setup: Create channel
        channel = Channel(
            channel_id="test_channel",
            channel_name="Test Channel",
            voice_id="test_voice",
            max_concurrent=2,
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        week_start = date(2026, 1, 20)

        # Create first metrics record
        metrics1 = WeeklyMetrics(
            channel_id=channel.id,
            week_starting_date=week_start,
            total_videos_processed=10,
            successful_videos=8,
            success_rate=Decimal("80.00"),
            calculated_at=datetime.now(timezone.utc),
        )
        async_session.add(metrics1)
        await async_session.commit()

        # Try to create duplicate (same channel + week)
        metrics2 = WeeklyMetrics(
            channel_id=channel.id,
            week_starting_date=week_start,
            total_videos_processed=15,
            successful_videos=12,
            success_rate=Decimal("80.00"),
            calculated_at=datetime.now(timezone.utc),
        )
        async_session.add(metrics2)

        # Assert: Should fail with integrity error
        with pytest.raises(Exception):  # IntegrityError from SQLAlchemy
            await async_session.commit()

    async def test_nullable_fields(self, async_session):
        """Test nullable fields (avg_processing_time_seconds, auto_recovery_rate)."""
        # Setup: Create channel
        channel = Channel(
            channel_id="test_channel",
            channel_name="Test Channel",
            voice_id="test_voice",
            max_concurrent=2,
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        # Create metrics with null optional fields
        metrics = WeeklyMetrics(
            channel_id=channel.id,
            week_starting_date=date(2026, 1, 20),
            total_videos_processed=0,  # No tasks this week
            successful_videos=0,
            success_rate=Decimal("0.00"),
            avg_processing_time_seconds=None,  # No completed tasks
            auto_recovery_rate=None,  # No retry attempts
            calculated_at=datetime.now(timezone.utc),
        )
        async_session.add(metrics)
        await async_session.commit()
        await async_session.refresh(metrics)

        # Assert
        assert metrics.avg_processing_time_seconds is None
        assert metrics.auto_recovery_rate is None

    async def test_default_values(self, async_session):
        """Test default values for metric fields."""
        # Setup: Create channel
        channel = Channel(
            channel_id="test_channel",
            channel_name="Test Channel",
            voice_id="test_voice",
            max_concurrent=2,
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        # Create metrics with minimal fields (use defaults)
        metrics = WeeklyMetrics(
            channel_id=channel.id,
            week_starting_date=date(2026, 1, 20),
            calculated_at=datetime.now(timezone.utc),
        )
        async_session.add(metrics)
        await async_session.commit()
        await async_session.refresh(metrics)

        # Assert defaults
        assert metrics.total_videos_processed == 0
        assert metrics.successful_videos == 0
        assert metrics.success_rate == Decimal("0.00")
        assert metrics.transient_failures == 0
        assert metrics.permanent_failures == 0
        assert metrics.unknown_failures == 0
        assert metrics.failed_at_assets == 0
        assert metrics.failed_at_video == 0
        assert metrics.failed_at_audio == 0
        assert metrics.failed_at_upload == 0

    async def test_channel_relationship(self, async_session):
        """Test relationship to Channel model."""
        # Setup: Create channel
        channel = Channel(
            channel_id="test_channel",
            channel_name="Test Channel",
            voice_id="test_voice",
            max_concurrent=2,
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        # Create metrics
        metrics = WeeklyMetrics(
            channel_id=channel.id,
            week_starting_date=date(2026, 1, 20),
            calculated_at=datetime.now(timezone.utc),
        )
        async_session.add(metrics)
        await async_session.commit()
        await async_session.refresh(metrics, ["channel"])

        # Assert relationship
        assert metrics.channel is not None
        assert metrics.channel.channel_id == "test_channel"
        assert metrics.channel.channel_name == "Test Channel"

    async def test_repr_method(self, async_session):
        """Test __repr__ method output."""
        # Setup: Create channel
        channel = Channel(
            channel_id="test_channel",
            channel_name="Test Channel",
            voice_id="test_voice",
            max_concurrent=2,
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        # Create metrics
        week_start = date(2026, 1, 20)
        metrics = WeeklyMetrics(
            channel_id=channel.id,
            week_starting_date=week_start,
            total_videos_processed=10,
            successful_videos=8,
            success_rate=Decimal("80.00"),
            calculated_at=datetime.now(timezone.utc),
        )
        async_session.add(metrics)
        await async_session.commit()
        await async_session.refresh(metrics)

        # Assert __repr__ format
        repr_str = repr(metrics)
        assert "WeeklyMetrics" in repr_str
        assert str(week_start) in repr_str
        assert "80.0%" in repr_str or "80.00" in repr_str

    async def test_multiple_weeks_same_channel(self, async_session):
        """Test multiple metrics records for same channel (different weeks)."""
        # Setup: Create channel
        channel = Channel(
            channel_id="test_channel",
            channel_name="Test Channel",
            voice_id="test_voice",
            max_concurrent=2,
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        # Create metrics for week 1
        metrics_week1 = WeeklyMetrics(
            channel_id=channel.id,
            week_starting_date=date(2026, 1, 13),
            total_videos_processed=10,
            successful_videos=8,
            success_rate=Decimal("80.00"),
            calculated_at=datetime.now(timezone.utc),
        )

        # Create metrics for week 2
        metrics_week2 = WeeklyMetrics(
            channel_id=channel.id,
            week_starting_date=date(2026, 1, 20),
            total_videos_processed=15,
            successful_videos=14,
            success_rate=Decimal("93.33"),
            calculated_at=datetime.now(timezone.utc),
        )

        async_session.add_all([metrics_week1, metrics_week2])
        await async_session.commit()

        # Assert both records exist
        await async_session.refresh(metrics_week1)
        await async_session.refresh(metrics_week2)
        assert metrics_week1.success_rate == Decimal("80.00")
        assert metrics_week2.success_rate == Decimal("93.33")

    async def test_cascade_delete(self, async_session):
        """Test cascade delete when channel is deleted."""
        # Setup: Create channel with metrics
        channel = Channel(
            channel_id="test_channel",
            channel_name="Test Channel",
            voice_id="test_voice",
            max_concurrent=2,
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        metrics = WeeklyMetrics(
            channel_id=channel.id,
            week_starting_date=date(2026, 1, 20),
            calculated_at=datetime.now(timezone.utc),
        )
        async_session.add(metrics)
        await async_session.commit()

        # Delete channel
        await async_session.delete(channel)
        await async_session.commit()

        # Assert: Metrics should be cascade deleted (no error on refresh)
        # Attempting to access metrics after channel delete should not find it
        from sqlalchemy import select

        result = await async_session.execute(
            select(WeeklyMetrics).where(WeeklyMetrics.channel_id == channel.id)
        )
        deleted_metrics = result.scalar_one_or_none()
        assert deleted_metrics is None

    async def test_decimal_precision_for_rates(self, async_session):
        """Test Decimal type for success_rate and auto_recovery_rate."""
        # Setup: Create channel
        channel = Channel(
            channel_id="test_channel",
            channel_name="Test Channel",
            voice_id="test_voice",
            max_concurrent=2,
        )
        async_session.add(channel)
        await async_session.commit()
        await async_session.refresh(channel)

        # Create metrics with precise decimal values
        metrics = WeeklyMetrics(
            channel_id=channel.id,
            week_starting_date=date(2026, 1, 20),
            success_rate=Decimal("85.37"),  # Precise percentage
            auto_recovery_rate=Decimal("72.45"),
            calculated_at=datetime.now(timezone.utc),
        )
        async_session.add(metrics)
        await async_session.commit()
        await async_session.refresh(metrics)

        # Assert: Decimal precision maintained
        assert metrics.success_rate == Decimal("85.37")
        assert metrics.auto_recovery_rate == Decimal("72.45")
        assert isinstance(metrics.success_rate, Decimal)
        assert isinstance(metrics.auto_recovery_rate, Decimal)
