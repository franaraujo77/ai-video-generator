"""Tests for auto-recovery metrics service (Story 6.10).

This module tests the auto-recovery success rate tracking functionality including:
- Week boundary calculation (get_week_starting_date)
- Weekly metrics calculation (calculate_weekly_metrics)
- Success rate computation with various scenarios
- Error category breakdown (transient vs permanent)
- Atomic upsert pattern
- Threshold alerting (<80% triggers Discord alert)

Test Strategy:
- Unit tests for week calculation and metrics logic
- Integration tests for database operations and alerting
- Edge cases: zero division, no data, boundary conditions
"""

import pytest
from datetime import datetime, date, timedelta, timezone
from uuid import uuid4

from app.models import Task, TaskStatus, AutoRecoveryMetrics
from app.services.auto_recovery_metrics_service import (
    get_week_starting_date,
    calculate_weekly_metrics,
    get_auto_recovery_metrics,
    check_success_rate_thresholds,
    calculate_all_channels_weekly_metrics,
)
from tests.support.factories import create_channel, create_task


class TestWeekBoundaryCalculation:
    """Tests for get_week_starting_date() ISO week calculation."""

    def test_get_week_starting_date_monday(self):
        """Monday returns same date (already start of week)."""
        monday = date(2026, 1, 19)  # Monday
        result = get_week_starting_date(monday)
        assert result == monday

    def test_get_week_starting_date_thursday(self):
        """Thursday returns previous Monday."""
        thursday = date(2026, 1, 22)  # Thursday
        expected = date(2026, 1, 19)  # Previous Monday
        result = get_week_starting_date(thursday)
        assert result == expected

    def test_get_week_starting_date_sunday(self):
        """Sunday returns previous Monday (week includes Sunday)."""
        sunday = date(2026, 1, 25)  # Sunday
        expected = date(2026, 1, 19)  # Previous Monday
        result = get_week_starting_date(sunday)
        assert result == expected

    def test_get_week_starting_date_year_boundary(self):
        """Week calculation works across year boundaries."""
        # Sunday Jan 4, 2026 is in week starting Monday Dec 30, 2025
        sunday = date(2026, 1, 4)  # Sunday
        expected = date(2025, 12, 29)  # Previous Monday
        result = get_week_starting_date(sunday)
        assert result == expected


@pytest.mark.asyncio
class TestCalculateWeeklyMetrics:
    """Tests for calculate_weekly_metrics() core functionality."""

    async def test_calculate_weekly_metrics_80_percent_success(self, async_session):
        """Verify 80% success rate calculation (8/10 recovered)."""
        # Create channel
        channel = create_channel(channel_id="poke1")
        async_session.add(channel)
        await async_session.commit()

        # Create 10 tasks with retries in target week
        week_start = date(2026, 1, 19)  # Monday
        for i in range(10):
            auto_recovered = i < 8  # First 8 recovered, last 2 failed
            task = create_task(
                channel_id=channel.id,
                status=TaskStatus.PUBLISHED if auto_recovered else TaskStatus.ASSET_ERROR,
                retry_count=2,
                auto_recovered=auto_recovered,
                recovery_attempt_number=2 if auto_recovered else None,
                error_category="TRANSIENT",
                updated_at=datetime.combine(
                    week_start + timedelta(days=i % 7), datetime.min.time()
                ).replace(tzinfo=timezone.utc),
            )
            async_session.add(task)
        await async_session.commit()

        # Calculate metrics
        metrics = await calculate_weekly_metrics(
            channel_id=channel.id, week_starting_date=week_start, db=async_session
        )

        # Verify
        assert metrics.total_retry_attempts == 10
        assert metrics.total_auto_recovered == 8
        assert metrics.success_rate == 80.0
        assert metrics.average_retries_before_success == 2.0
        assert metrics.transient_error_count == 10
        assert metrics.transient_recovered == 8

    async def test_calculate_weekly_metrics_100_percent_success(self, async_session):
        """Verify 100% success rate (all recovered)."""
        channel = create_channel(channel_id="poke1")
        async_session.add(channel)
        await async_session.commit()

        week_start = date(2026, 1, 19)
        for i in range(5):
            task = create_task(
                channel_id=channel.id,
                status=TaskStatus.PUBLISHED,
                retry_count=1,
                auto_recovered=True,
                recovery_attempt_number=1,
                error_category="TRANSIENT",
                updated_at=datetime.combine(
                    week_start + timedelta(days=i), datetime.min.time()
                ).replace(tzinfo=timezone.utc),
            )
            async_session.add(task)
        await async_session.commit()

        metrics = await calculate_weekly_metrics(
            channel_id=channel.id, week_starting_date=week_start, db=async_session
        )

        assert metrics.total_retry_attempts == 5
        assert metrics.total_auto_recovered == 5
        assert metrics.success_rate == 100.0

    async def test_calculate_weekly_metrics_zero_percent_success(self, async_session):
        """Verify 0% success rate (none recovered)."""
        channel = create_channel(channel_id="poke1")
        async_session.add(channel)
        await async_session.commit()

        week_start = date(2026, 1, 19)
        for i in range(5):
            task = create_task(
                channel_id=channel.id,
                status=TaskStatus.ASSET_ERROR,
                retry_count=5,
                auto_recovered=False,
                recovery_attempt_number=None,
                error_category="PERMANENT",
                updated_at=datetime.combine(
                    week_start + timedelta(days=i), datetime.min.time()
                ).replace(tzinfo=timezone.utc),
            )
            async_session.add(task)
        await async_session.commit()

        metrics = await calculate_weekly_metrics(
            channel_id=channel.id, week_starting_date=week_start, db=async_session
        )

        assert metrics.total_retry_attempts == 5
        assert metrics.total_auto_recovered == 0
        assert metrics.success_rate == 0.0

    async def test_calculate_weekly_metrics_no_retry_attempts(self, async_session):
        """Verify zero division handling when no retry attempts."""
        channel = create_channel(channel_id="poke1")
        async_session.add(channel)
        await async_session.commit()

        week_start = date(2026, 1, 19)
        # Create tasks that succeeded on first attempt (retry_count=0)
        for i in range(5):
            task = create_task(
                channel_id=channel.id,
                status=TaskStatus.PUBLISHED,
                retry_count=0,
                auto_recovered=False,
                recovery_attempt_number=None,
                error_category=None,
                updated_at=datetime.combine(
                    week_start + timedelta(days=i), datetime.min.time()
                ).replace(tzinfo=timezone.utc),
            )
            async_session.add(task)
        await async_session.commit()

        metrics = await calculate_weekly_metrics(
            channel_id=channel.id, week_starting_date=week_start, db=async_session
        )

        # No retry attempts = 0% success rate (no data)
        assert metrics.total_retry_attempts == 0
        assert metrics.total_auto_recovered == 0
        assert metrics.success_rate == 0.0
        assert metrics.average_retries_before_success is None

    async def test_calculate_weekly_metrics_error_category_breakdown(self, async_session):
        """Verify error category breakdown (transient vs permanent)."""
        channel = create_channel(channel_id="poke1")
        async_session.add(channel)
        await async_session.commit()

        week_start = date(2026, 1, 19)

        # 6 TRANSIENT errors, 4 recovered
        for i in range(6):
            auto_recovered = i < 4
            task = create_task(
                channel_id=channel.id,
                status=TaskStatus.PUBLISHED if auto_recovered else TaskStatus.VIDEO_ERROR,
                retry_count=2,
                auto_recovered=auto_recovered,
                recovery_attempt_number=2 if auto_recovered else None,
                error_category="TRANSIENT",
                updated_at=datetime.combine(
                    week_start + timedelta(days=i % 7), datetime.min.time()
                ).replace(tzinfo=timezone.utc),
            )
            async_session.add(task)

        # 3 PERMANENT errors, none recovered
        for i in range(3):
            task = create_task(
                channel_id=channel.id,
                status=TaskStatus.AUDIO_ERROR,
                retry_count=1,
                auto_recovered=False,
                recovery_attempt_number=None,
                error_category="PERMANENT",
                updated_at=datetime.combine(
                    week_start + timedelta(days=i % 7), datetime.min.time()
                ).replace(tzinfo=timezone.utc),
            )
            async_session.add(task)

        await async_session.commit()

        metrics = await calculate_weekly_metrics(
            channel_id=channel.id, week_starting_date=week_start, db=async_session
        )

        assert metrics.transient_error_count == 6
        assert metrics.transient_recovered == 4
        assert metrics.permanent_error_count == 3
        assert metrics.total_retry_attempts == 9
        assert metrics.total_auto_recovered == 4
        # Success rate: 4/9 = 44.4%
        assert pytest.approx(metrics.success_rate, 0.1) == 44.4

    async def test_calculate_weekly_metrics_atomic_upsert(self, async_session):
        """Verify atomic upsert updates existing record."""
        channel = create_channel(channel_id="poke1")
        async_session.add(channel)
        await async_session.commit()

        week_start = date(2026, 1, 19)

        # First calculation with 5 tasks
        for i in range(5):
            task = create_task(
                channel_id=channel.id,
                status=TaskStatus.PUBLISHED,
                retry_count=1,
                auto_recovered=True,
                recovery_attempt_number=1,
                error_category="TRANSIENT",
                updated_at=datetime.combine(
                    week_start + timedelta(days=i), datetime.min.time()
                ).replace(tzinfo=timezone.utc),
            )
            async_session.add(task)
        await async_session.commit()

        metrics1 = await calculate_weekly_metrics(
            channel_id=channel.id, week_starting_date=week_start, db=async_session
        )
        assert metrics1.total_retry_attempts == 5

        # Add 3 more tasks in same week
        for i in range(3):
            task = create_task(
                channel_id=channel.id,
                status=TaskStatus.PUBLISHED,
                retry_count=2,
                auto_recovered=True,
                recovery_attempt_number=2,
                error_category="TRANSIENT",
                updated_at=datetime.combine(
                    week_start + timedelta(days=i), datetime.min.time()
                ).replace(tzinfo=timezone.utc),
            )
            async_session.add(task)
        await async_session.commit()

        # Recalculate metrics (should update existing record)
        metrics2 = await calculate_weekly_metrics(
            channel_id=channel.id, week_starting_date=week_start, db=async_session
        )

        # Verify metrics updated (not duplicated)
        assert metrics2.total_retry_attempts == 8
        assert metrics2.total_auto_recovered == 8
        assert metrics2.success_rate == 100.0

        # Verify only one record exists for channel + week
        from sqlalchemy import func, select

        count_query = (
            select(func.count())
            .select_from(AutoRecoveryMetrics)
            .where(AutoRecoveryMetrics.channel_id == channel.id)
        )
        result = await async_session.execute(count_query)
        count = result.scalar()
        assert count == 1

    async def test_calculate_weekly_metrics_week_boundary_filtering(self, async_session):
        """Verify tasks outside week boundaries are excluded."""
        channel = create_channel(channel_id="poke1")
        async_session.add(channel)
        await async_session.commit()

        week_start = date(2026, 1, 19)  # Monday

        # Task in target week (should be included)
        task1 = create_task(
            channel_id=channel.id,
            status=TaskStatus.PUBLISHED,
            retry_count=1,
            auto_recovered=True,
            recovery_attempt_number=1,
            error_category="TRANSIENT",
            updated_at=datetime.combine(
                week_start + timedelta(days=3), datetime.min.time()
            ).replace(tzinfo=timezone.utc),
        )
        async_session.add(task1)

        # Task before week start (should be excluded)
        task2 = create_task(
            channel_id=channel.id,
            status=TaskStatus.PUBLISHED,
            retry_count=1,
            auto_recovered=True,
            recovery_attempt_number=1,
            error_category="TRANSIENT",
            updated_at=datetime.combine(
                week_start - timedelta(days=1), datetime.min.time()
            ).replace(tzinfo=timezone.utc),
        )
        async_session.add(task2)

        # Task after week end (should be excluded)
        task3 = create_task(
            channel_id=channel.id,
            status=TaskStatus.PUBLISHED,
            retry_count=1,
            auto_recovered=True,
            recovery_attempt_number=1,
            error_category="TRANSIENT",
            updated_at=datetime.combine(
                week_start + timedelta(days=7), datetime.min.time()
            ).replace(tzinfo=timezone.utc),
        )
        async_session.add(task3)

        await async_session.commit()

        metrics = await calculate_weekly_metrics(
            channel_id=channel.id, week_starting_date=week_start, db=async_session
        )

        # Only task1 should be counted
        assert metrics.total_retry_attempts == 1
        assert metrics.total_auto_recovered == 1


@pytest.mark.asyncio
class TestThresholdAlerting:
    """Tests for check_success_rate_thresholds() alerting logic."""

    async def test_check_threshold_no_alert_when_above_80(self, async_session, mocker):
        """Verify no alert when success rate >= 80%."""
        mock_alert = mocker.patch("app.services.auto_recovery_metrics_service.send_discord_alert")

        channel = create_channel(channel_id="poke1", channel_name="Pokemon Channel")
        async_session.add(channel)
        await async_session.commit()

        metrics = AutoRecoveryMetrics(
            channel_id=channel.id,
            week_starting_date=date(2026, 1, 19),
            total_retry_attempts=10,
            total_auto_recovered=9,  # 90% >= 80% target
            success_rate=90.0,
            average_retries_before_success=2.0,
            transient_error_count=10,
            transient_recovered=9,
            permanent_error_count=0,
            calculated_at=datetime.now(timezone.utc),
        )
        async_session.add(metrics)
        await async_session.commit()

        await check_success_rate_thresholds(metrics, async_session)

        # No alert should be sent
        mock_alert.assert_not_called()

    async def test_check_threshold_alerts_when_below_80(self, async_session, mocker):
        """Verify alert triggered when success rate < 80%."""
        # Mock both send_discord_alert and os.getenv for webhook URL
        mock_alert = mocker.patch("app.services.auto_recovery_metrics_service.send_discord_alert")
        mocker.patch(
            "app.services.auto_recovery_metrics_service.os.getenv",
            return_value="https://discord.webhook.url",
        )

        channel = create_channel(channel_id="poke1", channel_name="Pokemon Channel")
        async_session.add(channel)
        await async_session.commit()

        metrics = AutoRecoveryMetrics(
            channel_id=channel.id,
            week_starting_date=date(2026, 1, 19),
            total_retry_attempts=10,
            total_auto_recovered=7,  # 70% < 80% target
            success_rate=70.0,
            average_retries_before_success=2.5,
            transient_error_count=10,
            transient_recovered=7,
            permanent_error_count=0,
            calculated_at=datetime.now(timezone.utc),
        )
        async_session.add(metrics)
        await async_session.commit()

        await check_success_rate_thresholds(metrics, async_session)

        # Verify alert was sent
        mock_alert.assert_called_once()
        call_args = mock_alert.call_args
        assert call_args.kwargs["alert_type"] == "low_recovery_rate"
        assert "70.0%" in call_args.kwargs["title"]
        assert "Pokemon Channel" in call_args.kwargs["description"]

    async def test_check_threshold_no_alert_insufficient_data(self, async_session, mocker):
        """Verify no alert when sample size < 5 attempts."""
        mock_alert = mocker.patch("app.services.auto_recovery_metrics_service.send_discord_alert")

        channel = create_channel(channel_id="poke1")
        async_session.add(channel)
        await async_session.commit()

        metrics = AutoRecoveryMetrics(
            channel_id=channel.id,
            week_starting_date=date(2026, 1, 19),
            total_retry_attempts=3,  # < 5 minimum
            total_auto_recovered=1,  # 33% but insufficient data
            success_rate=33.3,
            average_retries_before_success=2.0,
            transient_error_count=3,
            transient_recovered=1,
            permanent_error_count=0,
            calculated_at=datetime.now(timezone.utc),
        )
        async_session.add(metrics)
        await async_session.commit()

        await check_success_rate_thresholds(metrics, async_session)

        # No alert due to insufficient sample size
        mock_alert.assert_not_called()


@pytest.mark.asyncio
class TestMultiChannelMetrics:
    """Tests for calculate_all_channels_weekly_metrics()."""

    async def test_calculate_all_channels_weekly_metrics(self, async_session):
        """Verify metrics calculated for all active channels."""
        # Create 3 channels (2 active, 1 inactive)
        channel1 = create_channel(channel_id="poke1", is_active=True)
        channel2 = create_channel(channel_id="poke2", is_active=True)
        channel3 = create_channel(channel_id="poke3", is_active=False)
        async_session.add_all([channel1, channel2, channel3])
        await async_session.commit()

        week_start = date(2026, 1, 19)

        # Add tasks for channel1 (80% success)
        for i in range(5):
            auto_recovered = i < 4
            task = create_task(
                channel_id=channel1.id,
                status=TaskStatus.PUBLISHED if auto_recovered else TaskStatus.ASSET_ERROR,
                retry_count=1,
                auto_recovered=auto_recovered,
                recovery_attempt_number=1 if auto_recovered else None,
                error_category="TRANSIENT",
                updated_at=datetime.combine(
                    week_start + timedelta(days=i), datetime.min.time()
                ).replace(tzinfo=timezone.utc),
            )
            async_session.add(task)

        # Add tasks for channel2 (100% success)
        for i in range(3):
            task = create_task(
                channel_id=channel2.id,
                status=TaskStatus.PUBLISHED,
                retry_count=2,
                auto_recovered=True,
                recovery_attempt_number=2,
                error_category="TRANSIENT",
                updated_at=datetime.combine(
                    week_start + timedelta(days=i), datetime.min.time()
                ).replace(tzinfo=timezone.utc),
            )
            async_session.add(task)

        # Add tasks for channel3 (inactive - should be excluded)
        task = create_task(
            channel_id=channel3.id,
            status=TaskStatus.PUBLISHED,
            retry_count=1,
            auto_recovered=True,
            recovery_attempt_number=1,
            error_category="TRANSIENT",
            updated_at=datetime.combine(
                week_start + timedelta(days=1), datetime.min.time()
            ).replace(tzinfo=timezone.utc),
        )
        async_session.add(task)

        await async_session.commit()

        # Calculate metrics for all channels
        metrics_list = await calculate_all_channels_weekly_metrics(
            week_starting_date=week_start, db=async_session
        )

        # Verify only active channels included
        assert len(metrics_list) == 2

        # Find metrics by channel
        channel1_metrics = next(m for m in metrics_list if m.channel_id == channel1.id)
        channel2_metrics = next(m for m in metrics_list if m.channel_id == channel2.id)

        # Verify channel1 metrics (80% success)
        assert channel1_metrics.total_retry_attempts == 5
        assert channel1_metrics.total_auto_recovered == 4
        assert channel1_metrics.success_rate == 80.0

        # Verify channel2 metrics (100% success)
        assert channel2_metrics.total_retry_attempts == 3
        assert channel2_metrics.total_auto_recovered == 3
        assert channel2_metrics.success_rate == 100.0
